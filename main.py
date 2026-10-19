import os
import re
import decimal
import hashlib
import json
import logging
from datetime import date, datetime, time, timezone
from typing import Optional

import pyodbc
import pandas as pd
import yaml
from google.api_core import exceptions as gcp_exceptions
from google.cloud import bigquery, secretmanager, storage

from email_utils import send_report

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
OUTPUT_MODE      = os.environ.get("OUTPUT_MODE", "bigquery").lower()  # "local" | "bigquery"
OUTPUT_DIR       = os.environ.get("OUTPUT_DIR", "/output")

GCP_PROJECT      = os.environ.get("GCP_PROJECT", "")
BQ_DATASET       = os.environ.get("BQ_DATASET", "")
BQ_TABLE         = os.environ.get("BQ_TABLE", "plex_extract")
PLEX_DSN         = os.environ.get("PLEX_DSN", "PlexProduction")
PLEX_HOST        = os.environ.get("PLEX_HOST", "")
PLEX_PORT        = os.environ.get("PLEX_PORT", "19995")
PLEX_SERVER_DS   = os.environ.get("PLEX_SERVER_DATASOURCE", "ReportDataSource")
METADATA_TABLE   = os.environ.get("METADATA_TABLE", "sync_metadata")
BACKFILL_MINUTES = int(os.environ.get("BACKFILL_MINUTES", "5"))

SECRET_USER      = os.environ.get("SECRET_ODBC_USER",    "plex-odbc-user")
SECRET_PASSWORD  = os.environ.get("SECRET_ODBC_PASSWORD", "plex-odbc-password")
SECRET_COMPANY   = os.environ.get("SECRET_COMPANY_CODE",  "plex-company-code")
SECRET_SENDGRID  = os.environ.get("SECRET_SENDGRID_KEY",  "sendgrid-api-key")
SECRET_TOKEN     = os.environ.get("SECRET_ACCESS_TOKEN",  "plex-access-token")

# GCS path to a report config YAML (gs://bucket/path or a local file path).
# When set, the job runs all extractions defined in the YAML instead of the
# single-view PLEX_VIEW env var.  Leave empty for legacy single-view mode.
REPORT_CONFIG_GCS_PATH = os.environ.get("REPORT_CONFIG_GCS_PATH", "")

# How this run was started. Set as an env override by whatever triggers the job:
#   scheduled  (default) a plain Cloud Scheduler fire, or a run started by hand.
#              Full run. A report with an EXPLICIT `probe: {queries: ...}` block
#              (label_design, hourly) still probes and may skip.
#   probe      started by the ETL dispatcher (deploy/etl_dispatcher/) at a probe
#              time from `etl_schedule`. Probes first and skips the extraction
#              when nothing it can see has changed since the last clean run.
#   full       started by the dispatcher at a full-run time (the 4 AM safety
#              net). Never skips, but still records the probe fingerprint so
#              the next probe compares against this run.
#   retry      the legacy 9:45 PM retry scheduler (test jobs only since the
#              probe rollout). Re-runs only if today's scheduled run failed.
# See docs/PROBE_BUILD_PLAN.md and docs/OPERATIONS.md.
RUN_MODE          = os.environ.get("RUN_MODE", "scheduled").lower()
JOB_RUN_LOG_TABLE = os.environ.get("JOB_RUN_LOG_TABLE", "job_run_log")

# Set by the dispatcher alongside RUN_MODE. When present, the run writes its
# outcome back onto that dispatch row, which is how the dispatcher knows a run
# failed and owes it one follow-up probe 15 minutes later.
DISPATCH_ID        = os.environ.get("DISPATCH_ID", "")
DISPATCH_LOG_TABLE = os.environ.get("DISPATCH_LOG_TABLE", "etl_dispatch_log")

# Emails show times in this zone, and the subject's date is this zone's date —
# an 11 PM Mountain run would otherwise land in the next day's UTC thread.
REPORT_TIME_ZONE  = os.environ.get("REPORT_TIME_ZONE", "America/Denver")

# "always" (default) or "on_error" — a pipeline that runs hourly behind a
# change probe (see below) would otherwise mail on every run that found
# something. With "on_error" the run email is sent only for a partial or
# failed run; a clean run is recorded in `job_run_log` / `probe_log` instead.
EMAIL_MODE        = os.environ.get("EMAIL_MODE", "always").lower()

# ── Legacy single-view config (used when REPORT_CONFIG_GCS_PATH is empty) ────
PLEX_VIEW     = os.environ.get("PLEX_VIEW",     "Part_v_Part")
PLEX_DATE_COL = os.environ.get("PLEX_DATE_COL", "")
PLEX_FILTER   = os.environ.get("PLEX_FILTER",   "WHERE Part_Type = 'Raw Materials'")


def _default_report_name() -> str:
    """
    Best-guess report name for the email subject when main() crashes before
    the YAML config is loaded (so the real report_name from the config is
    never set). Derives a readable name from the config filename rather than
    showing the raw gs:// URL as the subject.
    """
    if REPORT_CONFIG_GCS_PATH:
        filename = REPORT_CONFIG_GCS_PATH.rsplit("/", 1)[-1]
        return filename[:-len(".yaml")] if filename.endswith(".yaml") else filename
    return PLEX_VIEW


# ── Secret Manager ────────────────────────────────────────────────────────────
def get_secret(secret_name: str) -> str:
    """Fetch the latest version of a secret from Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{GCP_PROJECT}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def get_credential(direct_env: str, secret_name: str) -> str:
    """Return a direct env var value if set, otherwise fetch from Secret Manager."""
    direct = os.environ.get(direct_env)
    if direct:
        log.info(f"Using direct credential from {direct_env}.")
        return direct
    return get_secret(secret_name)


# ── GCS / report config ───────────────────────────────────────────────────────
def load_gcs_text(uri: str) -> str:
    """Download text from a GCS URI (gs://bucket/path) or a local file path."""
    if uri.startswith("gs://"):
        gcs = storage.Client()
        bucket_name, blob_path = uri[len("gs://"):].split("/", 1)
        return gcs.bucket(bucket_name).blob(blob_path).download_as_text()
    with open(uri) as f:
        return f.read()


def load_report_config(config_path: str) -> dict:
    """Load a report definition YAML from GCS or a local path."""
    log.info(f"Loading report config from {config_path}")
    text = load_gcs_text(config_path)
    config = yaml.safe_load(text)
    if not isinstance(config, dict):
        raise ValueError(
            f"Report config at {config_path} is not a valid YAML mapping "
            f"(got {type(config).__name__}). Check the file wasn't saved empty."
        )
    # Kept for the probe: a deployed change to this file must count as a change
    # even when Plex is quiet (OPEN_ITEMS L10). Not a YAML key anyone writes.
    config["_config_sha"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    n = len(config.get("extractions", []))
    log.info(f"Report '{config.get('report_name', 'unnamed')}' loaded: {n} extraction(s)")
    return config


# Plex view / column names: letters, digits, underscores only.
_PLEX_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_]+$")


def validate_extraction(extraction: dict) -> str:
    """
    Validate one extraction entry from the report YAML before its values are
    interpolated into SQL. Returns an error message, or "" if valid.

    The YAML lives in GCS and is editable outside code review, so treat it as
    an untrusted boundary: identifiers must be plain identifiers, and the
    free-text filter may not contain statement separators or comment markers.
    """
    view  = extraction.get("plex_view", "")
    table = extraction.get("bq_table", "")
    filt  = extraction.get("filter", "") or ""
    date_col = extraction.get("date_col", "") or ""

    if not view or not table:
        return f"extraction entry missing required key(s) plex_view/bq_table: {extraction}"
    if not _PLEX_IDENTIFIER_RE.match(view):
        return f"plex_view '{view}' is not a valid identifier (letters/digits/_ only)"
    if not _PLEX_IDENTIFIER_RE.match(table):
        return f"bq_table '{table}' is not a valid identifier (letters/digits/_ only)"
    if date_col and not _PLEX_IDENTIFIER_RE.match(date_col):
        return f"date_col '{date_col}' is not a valid identifier (letters/digits/_ only)"
    if any(tok in filt for tok in (";", "--", "/*")):
        return f"filter for '{view}' contains a forbidden token (; -- /*): {filt}"
    return ""


def bq_view_configs(config: dict) -> list:
    """
    Normalize a report's bq_view entry to a list.

    Most reports define a single mapping (`bq_view: {name: ..., sql_file: ...}`).
    A report may also define a list of mappings when it needs to create more
    than one view from the same extraction run — e.g. a detail view and a
    separate aggregated rollup over the same raw tables. Missing entirely
    returns an empty list rather than erroring, since extractions-only
    reports (no view) are valid.
    """
    raw = config.get("bq_view")
    if raw is None:
        return []
    return raw if isinstance(raw, list) else [raw]


def validate_bq_view(view_cfg) -> str:
    """
    Validate one bq_view entry before its name is interpolated into DDL and
    its SQL is loaded. Returns an error message, or "" if valid.

    Same untrusted-YAML-boundary rationale as validate_extraction: the config
    lives in GCS and is editable outside code review, and `name` is
    interpolated directly into `CREATE OR REPLACE VIEW` DDL.
    """
    if not isinstance(view_cfg, dict):
        return f"bq_view entry is not a mapping: {view_cfg!r}"
    name     = view_cfg.get("name", "")
    sql      = view_cfg.get("sql", "")
    sql_file = view_cfg.get("sql_file", "")
    if not name:
        return f"bq_view entry missing required key 'name': {view_cfg}"
    if not _PLEX_IDENTIFIER_RE.match(name):
        return f"bq_view name '{name}' is not a valid identifier (letters/digits/_ only)"
    if not sql and not sql_file:
        return f"bq_view '{name}' has neither 'sql' nor 'sql_file'"
    return ""


# ── Change probe ──────────────────────────────────────────────────────────────
# A report may declare a probe: a handful of tiny Plex queries whose combined
# result fingerprints everything this report could turn into output. When that
# fingerprint matches the one stored by the last run that finished clean, the
# extraction is skipped: nothing in Plex that this report reads has moved.
#
# Two kinds (see docs/PROBE_BUILD_PLAN.md):
#
#   EXPLICIT  `probe: {queries: [...]}` — hand-written queries, used by
#             label_design to watch only the releases in Label Design status.
#             Probes on every scheduled run (hourly).
#
#   AUTO      `probe_mode: auto` — one aggregate query per extraction:
#                 SELECT COUNT(*), MAX(<col>), ... FROM <view> <filter>
#             where the MAX columns come from the extraction's own
#             `probe: [Update_Date, PO_Line_Key]` list (a change date and/or
#             the view's key; generated by scripts/generate_probe_columns.py).
#             An extraction with no list still contributes COUNT(*). Plex runs
#             these on its side: 0.2-0.5 s per table, measured 2026-10-19 (a
#             235,550-row table counts in 0.27 s against 6.5 s to pull it).
#             Probes only when the dispatcher starts the run with RUN_MODE=probe.
#
# Both kinds also fingerprint the report's own YAML and SQL files, so a
# deployed config/SQL change always runs in full (OPEN_ITEMS L10: a SQL-only
# deploy used to sit unapplied for as long as Plex stayed quiet).
#
# KNOWN LIMIT of AUTO: an edit to an existing row on a view with no change date
# keeps the same count and keys, so the probe cannot see it. That is what the
# daily 4 AM `full` run is for — such an edit is at most a day late.
#
# FAIL OPEN. Any trouble evaluating the probe — bad config, a query that errors,
# a bind that resolves to nothing, an unreadable probe log — runs the full
# extraction. A probe may never be the reason a real change is missed.
#
# THE FINGERPRINT IS STORED ONLY AFTER A CLEAN RUN (in run_and_report). A failed
# or partial run leaves the last applied fingerprint untouched, so the next
# probe still sees a difference and runs again: the probe IS the retry, which is
# why probe-driven pipelines have no `-retry` scheduler.
PROBE_LOG_TABLE = os.environ.get("PROBE_LOG_TABLE", "probe_log")
_PROBE_BIND_RE  = re.compile(r"^\d+$")
_CONFIG_SNAPSHOT_KEY = "(config + SQL)"


class ProbeInconclusive(Exception):
    """The probe could not be evaluated — run the full extraction."""


def probe_kind(config: dict) -> str:
    """'explicit', 'auto', or '' when the report has no probe.

    AUTO is `probe_mode: auto`, deliberately NOT `probe: auto`: images built
    before 2026-10-19 treat any truthy `probe:` as an explicit block and crash
    on a string, so a YAML deployed ahead of (or after a rollback of) the image
    would fail every nightly job. Older images ignore `probe_mode` entirely."""
    if config.get("probe_mode") == "auto":
        return "auto"
    probe = config.get("probe")
    if isinstance(probe, dict) and probe.get("queries"):
        return "explicit"
    return ""


def probe_may_skip(kind: str, run_mode: str) -> bool:
    """Whether an unchanged fingerprint is allowed to skip this run.

    `full` never skips. An explicit probe (label_design) skips on its normal
    scheduled runs and on dispatcher probe runs. An auto probe skips only when
    the dispatcher asked for a probe; a plain scheduled or hand-started run of
    a nightly pipeline is a full run, exactly as before the probe existed."""
    if run_mode == "probe":
        return True
    return kind == "explicit" and run_mode == "scheduled"


def validate_probe_query(q) -> str:
    """Validate one `probe.queries` entry. Returns an error message, or ""."""
    if not isinstance(q, dict):
        return f"probe query is not a mapping: {q!r}"
    view = q.get("plex_view", "") or ""
    cols = q.get("columns", [])
    filt = q.get("filter", "") or ""
    bind = q.get("bind", "") or ""
    if not _PLEX_IDENTIFIER_RE.match(view):
        return f"probe plex_view '{view}' is not a valid identifier (letters/digits/_ only)"
    if not cols or not isinstance(cols, list):
        return f"probe query for '{view}' needs a non-empty 'columns' list"
    for c in cols:
        if not isinstance(c, str) or not _PLEX_IDENTIFIER_RE.match(c):
            return f"probe column '{c}' for '{view}' is not a valid identifier"
    if bind and (not _PLEX_IDENTIFIER_RE.match(bind) or len(cols) != 1):
        return f"probe query for '{view}' has 'bind: {bind}' but not exactly one column"
    if any(tok in filt for tok in (";", "--", "/*")):
        return f"probe filter for '{view}' contains a forbidden token (; -- /*): {filt}"
    return ""


def _probe_fetch(conn, sql: str, view: str) -> list:
    log.info(f"Probe: {sql}")
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        return cursor.fetchall()
    except Exception as exc:
        raise ProbeInconclusive(f"probe query on '{view}' failed: {exc}")
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def _explicit_probe_parts(conn, config: dict) -> dict:
    """label_design's hand-written queries -> {"view(cols)": "count:hash"}."""
    binds, parts = {}, {}
    for n, q in enumerate(config["probe"]["queries"], start=1):
        problem = validate_probe_query(q)
        if problem:
            raise ProbeInconclusive(problem)
        view = q["plex_view"]
        cols = q["columns"]
        filt = (q.get("filter", "") or "").strip()
        if filt:
            try:
                filt = filt.format(**binds)
            except (KeyError, IndexError, ValueError) as exc:
                raise ProbeInconclusive(f"probe filter for '{view}' has a bad placeholder: {exc!r}")
        select = ", ".join(f"t.{c}" for c in cols)
        sql = f"SELECT {select} FROM {view} AS t" + (f" {filt}" if filt else "")
        rows = _probe_fetch(conn, sql, view)
        # Sorted, so the fingerprint is about the SET of keys and not the order
        # Plex happened to return them in. A line entering that set changes the
        # fingerprint; so does one leaving it, which costs one needless run and
        # no correctness.
        values = sorted("|".join(_cell(v) for v in row) for row in rows)
        digest = hashlib.sha256(";".join(values).encode("utf-8")).hexdigest()[:12]
        # Numbered: two queries on the same view and columns (different
        # filters) must not overwrite each other and drop out of the fingerprint.
        parts[f"{n}. {view}({','.join(cols)})"] = f"{len(values)} rows:{digest}"
        if q.get("bind"):
            keys = [v for v in values if _PROBE_BIND_RE.match(v)]
            if not keys or len(keys) != len(values):
                raise ProbeInconclusive(
                    f"probe bind '{q['bind']}' on '{view}' resolved to {len(values)} value(s) of "
                    f"which {len(keys)} are integers — refusing to build a filter from that"
                )
            binds[q["bind"]] = ",".join(keys)
    return parts


def _auto_probe_parts(conn, config: dict) -> dict:
    """One aggregate per extraction -> {bq_table: "count|max1|max2"}.

    Keyed by bq_table, not view: one view can feed two tables under different
    filters. An invalid extraction entry is the extraction loop's problem to
    report; here it only means the probe cannot vouch for the run."""
    parts = {}
    for extraction in config.get("extractions", []):
        problem = validate_extraction(extraction)
        if problem:
            raise ProbeInconclusive(f"cannot probe an invalid extraction: {problem}")
        view = extraction["plex_view"]
        cols = extraction.get("probe") or []
        if not isinstance(cols, list) or not all(
                isinstance(c, str) and _PLEX_IDENTIFIER_RE.match(c) for c in cols):
            raise ProbeInconclusive(f"probe column list for '{view}' must be plain identifiers: {cols!r}")
        filt = (extraction.get("filter", "") or "").strip()
        select = "COUNT(*)" + "".join(f", MAX({c})" for c in cols)
        # Same view and filter as query_plex(), unaliased, so the probe counts
        # exactly the rows the extraction would pull.
        sql = f"SELECT {select} FROM {view}" + (f" {filt}" if filt else "")
        rows = _probe_fetch(conn, sql, view)
        if len(rows) != 1:
            raise ProbeInconclusive(f"probe aggregate on '{view}' returned {len(rows)} rows, expected 1")
        parts[extraction["bq_table"]] = "|".join(_cell(v) for v in rows[0])
    if not parts:
        raise ProbeInconclusive("probe_mode: auto, but the report has no extractions")
    return parts


def config_fingerprint(config: dict) -> str:
    """Hash of the report YAML plus every view's SQL, as deployed in GCS."""
    h = hashlib.sha256((config.get("_config_sha") or "").encode("utf-8"))
    for view_cfg in bq_view_configs(config):
        if not isinstance(view_cfg, dict):
            continue
        sql = view_cfg.get("sql", "") or ""
        if not sql and view_cfg.get("sql_file"):
            try:
                sql = load_gcs_text(view_cfg["sql_file"])
            except Exception as exc:
                raise ProbeInconclusive(f"cannot read view SQL {view_cfg['sql_file']}: {exc}")
        h.update(f"\n{view_cfg.get('name', '')}\n{sql}".encode("utf-8"))
    return h.hexdigest()[:16]


def run_probe(conn, config: dict) -> tuple:
    """Fingerprint everything this report's probe can see, or raise.

    Returns (fingerprint, snapshot). The snapshot maps each probed source to
    the short value it produced; diffing two snapshots names the tables that
    changed, which is what the run email reports."""
    kind = probe_kind(config)
    if kind == "explicit":
        snapshot = _explicit_probe_parts(conn, config)
    elif kind == "auto":
        snapshot = _auto_probe_parts(conn, config)
    else:
        raise ProbeInconclusive("no probe configured")
    snapshot[_CONFIG_SNAPSHOT_KEY] = config_fingerprint(config)
    canonical = "\n".join(f"{k}={snapshot[k]}" for k in sorted(snapshot))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32], snapshot


def changed_sources(previous: Optional[dict], current: dict) -> list:
    """Names whose probe value differs from the last clean run, sorted.
    No previous snapshot (first run, or a row from before snapshots existed)
    means everything counts as changed."""
    if not previous:
        return sorted(current)
    return sorted(k for k in set(previous) | set(current) if previous.get(k) != current.get(k))


def ensure_probe_log_table(bq: bigquery.Client):
    """Create the probe log table if it doesn't exist yet, and add the
    `snapshot` column to a table created before it existed (label_design's,
    2026-10-01). One row per probe: what it saw, and whether the run behind it
    was allowed to advance it."""
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{PROBE_LOG_TABLE}"
    schema = [
        bigquery.SchemaField("report_name", "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("job_name",    "STRING"),
        bigquery.SchemaField("probed_at",   "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("fingerprint", "STRING",    mode="REQUIRED"),
        # skipped      — fingerprint unchanged, no extraction ran
        # applied      — a clean run followed; this is now the reference
        # failed       — a run followed and did not finish clean; NOT the reference
        # inconclusive — the probe could not be evaluated; a full run followed
        bigquery.SchemaField("outcome",     "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("detail",      "STRING"),
        # JSON {source: value} — what each table looked like (added 2026-10-19)
        bigquery.SchemaField("snapshot",    "STRING"),
        bigquery.SchemaField("run_mode",    "STRING"),
    ]
    try:
        table = bq.get_table(table_ref)
    except gcp_exceptions.NotFound:
        bq.create_table(bigquery.Table(table_ref, schema=schema))
        return
    have = {f.name for f in table.schema}
    missing = [f for f in schema if f.name not in have]
    if missing:
        table.schema = list(table.schema) + [
            bigquery.SchemaField(f.name, f.field_type, mode="NULLABLE") for f in missing]
        bq.update_table(table, ["schema"])


def last_applied_probe(bq: bigquery.Client, report_name: str) -> tuple:
    """(fingerprint, snapshot dict or None) of the last clean run, or (None, None)."""
    query = f"""
        SELECT fingerprint, snapshot
        FROM `{GCP_PROJECT}.{BQ_DATASET}.{PROBE_LOG_TABLE}`
        WHERE report_name = @report_name
          AND outcome = 'applied'
        ORDER BY probed_at DESC
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("report_name", "STRING", report_name)]
    )
    rows = list(bq.query(query, job_config=job_config).result())
    if not rows:
        return None, None
    snapshot = None
    if rows[0].snapshot:
        try:
            snapshot = json.loads(rows[0].snapshot)
        except ValueError:
            snapshot = None
    return rows[0].fingerprint, snapshot


def log_probe(bq: bigquery.Client, report_name: str, job_name: str,
              fingerprint: str, outcome: str, detail: str = "",
              snapshot: Optional[dict] = None):
    """Record what this probe saw. Never fatal — a lost row only means the next
    run can't match the fingerprint and extracts again, which is the safe way
    to be wrong."""
    row = [{
        "report_name": report_name,
        "job_name":    job_name,
        "probed_at":   datetime.now(timezone.utc).isoformat(),
        "fingerprint": fingerprint,
        "outcome":     outcome,
        "detail":      detail or None,
        "snapshot":    json.dumps(snapshot, sort_keys=True) if snapshot else None,
        "run_mode":    RUN_MODE,
    }]
    try:
        errors = bq.insert_rows_json(f"{GCP_PROJECT}.{BQ_DATASET}.{PROBE_LOG_TABLE}", row)
    except Exception as exc:
        log.warning(f"Failed to log probe result: {exc}")
        return
    if errors:
        log.warning(f"Failed to log probe result: {errors}")


def record_dispatch_outcome(status: str, detail: str = ""):
    """Write this run's outcome onto the dispatcher row that started it.

    Only for dispatcher-started runs (DISPATCH_ID set). The dispatcher reads it
    back to decide whether a failed run owes one follow-up probe 15 minutes
    later. DML, not streaming: the dispatcher inserted the row with DML too, and
    a streamed row could not be updated for up to 90 minutes. Never fatal — a
    missing outcome reads as 'still running' until the dispatcher's timeout,
    which then treats it as failed."""
    if not DISPATCH_ID or OUTPUT_MODE != "bigquery":
        return
    query = f"""
        UPDATE `{GCP_PROJECT}.{BQ_DATASET}.{DISPATCH_LOG_TABLE}`
        SET outcome = @status, finished_at = CURRENT_TIMESTAMP(),
            execution_name = @execution, detail = @detail
        WHERE dispatch_id = @dispatch_id
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("status", "STRING", status),
        bigquery.ScalarQueryParameter("execution", "STRING", os.environ.get("CLOUD_RUN_EXECUTION", "")),
        bigquery.ScalarQueryParameter("detail", "STRING", (detail or "")[:1000] or None),
        bigquery.ScalarQueryParameter("dispatch_id", "STRING", DISPATCH_ID),
    ])
    try:
        bigquery.Client(project=GCP_PROJECT).query(query, job_config=job_config).result()
    except Exception:
        log.exception(f"Failed to record dispatch outcome for {DISPATCH_ID}.")


# ── BigQuery helpers ──────────────────────────────────────────────────────────
def update_last_sync(
    bq: bigquery.Client,
    sync_time: datetime,
    rows_written: int,
    max_modified: datetime,
    bq_table: str = None,
):
    """Record a successful sync in the metadata table."""
    table_name = bq_table or BQ_TABLE
    rows = [{
        "table_name":      table_name,
        "last_sync_at":    sync_time.isoformat(),
        "max_modified_at": max_modified.isoformat(),
        "rows_written":    rows_written,
        "synced_at":       datetime.now(timezone.utc).isoformat(),
    }]
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{METADATA_TABLE}"
    errors = bq.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(f"Failed to update sync metadata: {errors}")
    log.info(f"Metadata updated for {table_name} — {rows_written} rows written.")


def ensure_metadata_table(bq: bigquery.Client):
    """Create the metadata table if it doesn't exist yet."""
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{METADATA_TABLE}"
    schema = [
        bigquery.SchemaField("table_name",      "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("last_sync_at",    "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("max_modified_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("rows_written",    "INTEGER",   mode="REQUIRED"),
        bigquery.SchemaField("synced_at",       "TIMESTAMP", mode="REQUIRED"),
    ]
    try:
        table = bq.get_table(table_ref)
        existing_fields = {field.name for field in table.schema}
        if "max_modified_at" not in existing_fields:
            table.schema = table.schema + [schema[2]]
            bq.update_table(table, ["schema"])
            log.info("Added max_modified_at to sync metadata table.")
    except gcp_exceptions.NotFound:
        # Only create on a genuine missing-table; other errors (e.g. 403
        # permission denied) must propagate with their original message.
        table = bigquery.Table(table_ref, schema=schema)
        bq.create_table(table)


def ensure_job_run_log_table(bq: bigquery.Client):
    """
    Create the job run log table if it doesn't exist yet. One row per
    completed run (scheduled or retry) — lets a retry trigger check whether
    today's scheduled run already succeeded/partial before doing real work.
    """
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{JOB_RUN_LOG_TABLE}"
    schema = [
        bigquery.SchemaField("job_name",  "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("run_date",  "DATE",      mode="REQUIRED"),
        bigquery.SchemaField("status",    "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("run_mode",  "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("logged_at", "TIMESTAMP", mode="REQUIRED"),
    ]
    try:
        bq.get_table(table_ref)
    except gcp_exceptions.NotFound:
        bq.create_table(bigquery.Table(table_ref, schema=schema))


def get_todays_run_status(bq: bigquery.Client, job_name: str) -> Optional[str]:
    """Return the most recent SCHEDULED run's status logged today, or None."""
    query = f"""
        SELECT status
        FROM `{GCP_PROJECT}.{BQ_DATASET}.{JOB_RUN_LOG_TABLE}`
        WHERE job_name = @job_name
          AND run_date = CURRENT_DATE()
          AND run_mode = 'scheduled'
        ORDER BY logged_at DESC
        LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("job_name", "STRING", job_name)]
    )
    rows = list(bq.query(query, job_config=job_config).result())
    return rows[0].status if rows else None


def log_job_run(bq: bigquery.Client, job_name: str, status: str, run_mode: str):
    """Record this run's outcome so a future retry trigger can check it."""
    now = datetime.now(timezone.utc)
    row = [{
        "job_name":  job_name,
        "run_date":  now.date().isoformat(),
        "status":    status,
        "run_mode":  run_mode,
        "logged_at": now.isoformat(),
    }]
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{JOB_RUN_LOG_TABLE}"
    errors = bq.insert_rows_json(table_ref, row)
    if errors:
        log.warning(f"Failed to log job run status: {errors}")


def create_or_replace_bq_view(bq: bigquery.Client, dataset: str, name: str, sql: str):
    """Create or replace a BigQuery VIEW using DDL.

    DDL is more reliable than update_table() because it handles both create and
    update in one call and avoids field-mask ambiguity in the Python client.
    """
    view_ref = f"{GCP_PROJECT}.{dataset}.{name}"
    ddl = f"CREATE OR REPLACE VIEW `{view_ref}` AS\n{sql}"
    bq.query(ddl).result()
    log.info(f"Created/replaced BigQuery view {view_ref}")


# ── ODBC connection ───────────────────────────────────────────────────────────
def get_odbc_connection(user: str, password: str, company_code: str, access_token: str = "") -> pyodbc.Connection:
    """
    Connect to Plex via ODBC.

    IAM token auth: uses a driver-direct connection string (bypasses DSN lookup)
    because unixODBC does not forward driver-specific attributes like
    CustomProperties from the DSN file to the driver.

    Username/password auth: uses the DSN defined in /etc/odbc.ini.
    """
    if access_token:
        # Driver-direct: all attributes passed explicitly so CustomProperties
        # (which contains semicolons) is at the END of the string — no escaping needed.
        host = PLEX_HOST or ("vox.odbc.plex.com" if "test" in PLEX_DSN.lower() else "odbc.plex.com")
        conn_str = (
            "DRIVER={/usr/oaodbc81/lib64/ivoa27.so};"
            f"HOST={host};"
            f"PORT={PLEX_PORT};"
            f"ServerDataSource={PLEX_SERVER_DS};"
            "Encrypted=1;"
            "UseLDAP=0;"
            f"UID={user};"
            "PWD=;"
            f"CustomProperties=authmethod=iam; accesstoken={access_token}"
        )
        log.info(f"Connecting driver-direct to {host}:{PLEX_PORT} (IAM token auth, UID={user})")
    else:
        conn_str = (
            f"DSN={PLEX_DSN};"
            f"UID={user};"
            f"PWD={password};"
            f"CustomProperties=CompanyCode={company_code};"
        )
        log.info(f"Connecting via DSN={PLEX_DSN} (username/password auth)")
    conn = pyodbc.connect(conn_str, timeout=30)
    log.info("ODBC connection established.")
    return conn


# Maps a pyodbc cursor.description type_code (a Python type object -- e.g.
# `int`, `str`, `datetime.datetime` -- see extract_schema_catalog.py's
# describe_type(), which already relies on this exact shape from the same
# driver) to a BigQuery SchemaField type. Falls back to STRING for anything
# unrecognized, so this can never be less permissive than the previous
# blanket-STRING behavior.
_ODBC_TYPE_TO_BQ = {
    int:             "INT64",
    float:           "FLOAT64",
    bool:            "BOOL",
    str:             "STRING",
    bytes:           "BYTES",
    bytearray:       "BYTES",
    decimal.Decimal: "FLOAT64",  # matches the SAFE_CAST(... AS FLOAT64) convention already used throughout reports/sql/* for money/price columns
    datetime:        "TIMESTAMP",
    date:            "DATE",
    time:            "TIME",
}


def _bq_type_for_odbc(type_code) -> str:
    return _ODBC_TYPE_TO_BQ.get(type_code, "STRING")


# ── Plex query ────────────────────────────────────────────────────────────────
def query_plex(
    conn: pyodbc.Connection,
    plex_view: str = None,
    plex_filter: str = None,
    plex_date_col: str = None,
) -> pd.DataFrame:
    view     = plex_view     if plex_view     is not None else PLEX_VIEW
    filt     = plex_filter   if plex_filter   is not None else PLEX_FILTER
    date_col = plex_date_col if plex_date_col is not None else PLEX_DATE_COL
    filter_clause = f" {filt}" if filt else ""
    order_clause  = f" ORDER BY {date_col} ASC" if date_col else ""
    sql = f"SELECT * FROM {view}{filter_clause}{order_clause}"
    log.info(f"Querying Plex [{view}]...")
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    # Plex's real per-column type, straight from the ODBC driver -- used only
    # to type an EMPTY raw table's placeholder schema correctly (see
    # write_to_bigquery) instead of forcing every column to STRING, which is
    # what caused the recurring "No matching signature for operator = for
    # argument types: STRING, INT64" view-creation failures once a sibling
    # table populated with real INT64 data. Populated tables are unaffected --
    # autodetect=True still infers types from actual row values as before.
    odbc_schema = {col[0]: _bq_type_for_odbc(col[1]) for col in cursor.description}
    rows = cursor.fetchall()
    df = pd.DataFrame.from_records(rows, columns=columns)
    df.attrs["odbc_schema"] = odbc_schema
    cursor.close()
    log.info(f"Fetched {len(df)} rows from Plex [{view}].")
    return df


# ── BigQuery write ────────────────────────────────────────────────────────────
def write_to_bigquery(bq: bigquery.Client, df: pd.DataFrame, bq_table: str = None):
    """
    Replace the target BigQuery table with the current DataFrame.
    WRITE_TRUNCATE replaces the table atomically — idempotent on re-run.
    Always writes even when empty so the table exists for VIEW references.
    """
    table_name = bq_table or BQ_TABLE
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{table_name}"

    if df.empty and df.columns.empty:
        log.info(f"No rows and no schema for {table_name} — skipping BigQuery write.")
        return 0

    if df.empty:
        # 0 rows from Plex. NEVER truncate an existing table here — a transient
        # ODBC timeout or maintenance window would otherwise wipe yesterday's
        # data AND flatten the schema to all-STRING. Keep existing data; only
        # create the (empty, all-STRING) table if it doesn't exist yet so
        # VIEWs can reference it.
        try:
            bq.get_table(table_ref)
            log.warning(
                f"0 rows for {table_name} — existing table left untouched "
                f"(previous data preserved). Verify Plex returned data."
            )
        except gcp_exceptions.NotFound:
            odbc_schema = df.attrs.get("odbc_schema", {})
            schema = [
                bigquery.SchemaField(col, odbc_schema.get(col, "STRING"))
                for col in df.columns
            ]
            bq.create_table(bigquery.Table(table_ref, schema=schema))
            log.info(f"0 rows for {table_name} — created empty table with {len(schema)} column(s), typed from Plex's real ODBC schema.")
        return 0

    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )

    log.info(f"Writing {len(df)} rows to {table_ref}...")
    job = bq.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()

    if job.errors:
        raise RuntimeError(f"BigQuery load job failed: {job.errors}")

    log.info(f"Successfully wrote {len(df)} rows to {table_ref}.")
    return len(df)


# ── CSV writer (local mode) ───────────────────────────────────────────────────
def write_to_csv(df: pd.DataFrame, output_dir: str, table_name: str) -> int:
    if df.empty:
        log.info("No rows to write — skipping CSV output.")
        return 0

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filepath  = os.path.join(output_dir, f"{table_name}_{timestamp}.csv")

    df.to_csv(filepath, index=False)
    log.info(f"Wrote {len(df)} rows to {filepath}")
    return len(df)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    sync_time   = datetime.now(timezone.utc)
    log.info("=== Plex → BigQuery ETL job starting ===")
    events         = []
    partial_errors = []   # extraction-level failures (not fatal, but flagged in email)
    rows_fetched   = 0
    rows_written   = 0
    probe_fingerprint = ""   # set by the change probe, stored by run_and_report
    probe_snapshot    = None # per-source probe values, stored with the fingerprint
    probe_info        = {}   # what the probe saw, for the run email
    extraction_rows   = []   # one dict per extraction, for the run email
    report_name      = _default_report_name()
    report_category   = ""
    email_plex_view   = PLEX_VIEW
    email_plex_filter = PLEX_FILTER or "none"
    email_bq_table    = BQ_TABLE
    email_reports_detail = []

    # Fetch credentials — IAM token takes priority over username/password
    log.info("Fetching credentials...")
    try:
        access_token = os.environ.get("PLEX_ACCESS_TOKEN", "")
        if not access_token and OUTPUT_MODE == "bigquery":
            try:
                access_token = get_secret(SECRET_TOKEN)
            except Exception as sm_err:
                log.warning(
                    "Could not fetch IAM token from Secret Manager (%s) — falling back to username/password auth.",
                    sm_err,
                )

        if access_token:
            user         = os.environ.get("PLEX_ODBC_USER", "")
            password     = ""
            company_code = ""
            if not user:
                log.warning(
                    "PLEX_ODBC_USER is not set — connection string will have an "
                    "empty UID. If the ODBC connection fails with a credential "
                    "error, set this env var on the Cloud Run job."
                )
            log.info("Using IAM access token for Plex authentication.")
        else:
            user         = get_credential("PLEX_ODBC_USER",    SECRET_USER)
            password     = get_credential("PLEX_ODBC_PASSWORD", SECRET_PASSWORD)
            company_code = get_credential("PLEX_COMPANY_CODE",  SECRET_COMPANY)
            log.info("Using username/password for Plex authentication.")
        events.append("Fetched credentials")
    except Exception as exc:
        log.exception("Failed to fetch credentials.")
        raise RuntimeError(f"Credential fetch failed: {exc}") from exc

    # Init BigQuery client (bigquery mode only)
    if OUTPUT_MODE == "bigquery":
        try:
            bq = bigquery.Client(project=GCP_PROJECT)
            ensure_metadata_table(bq)
            ensure_job_run_log_table(bq)
            events.append("Initialized BigQuery and metadata table")
        except Exception as exc:
            log.exception("Failed to initialize BigQuery client or metadata table.")
            raise RuntimeError(f"BigQuery initialization failed: {exc}") from exc

        # Retry trigger (6 AM Mountain): only do real work if today's
        # scheduled run actually failed. A success/partial already covers
        # today, so a bare retry fire is a clean no-op, not a failure.
        job_identity = os.environ.get("CLOUD_RUN_JOB") or report_name
        if RUN_MODE == "retry":
            todays_status = get_todays_run_status(bq, job_identity)
            if todays_status in ("success", "partial"):
                log.info(
                    f"Retry trigger fired for {job_identity}, but today's "
                    f"scheduled run already completed with status={todays_status} "
                    f"— skipping."
                )
                return {
                    "rows_fetched":           0,
                    "rows_written":           0,
                    "events":                 [f"Retry skipped — today's scheduled run already {todays_status}"],
                    "partial_errors":         [],
                    "gcp_project":            GCP_PROJECT,
                    "bq_dataset":             BQ_DATASET,
                    "bq_table":               email_bq_table,
                    "report_name":            report_name,
                    "report_category":        report_category,
                    "reports_detail":         email_reports_detail,
                    "plex_view":              email_plex_view,
                    "plex_filter":            email_plex_filter,
                    "plex_host":              PLEX_HOST,
                    "report_config_gcs_path": REPORT_CONFIG_GCS_PATH,
                    "execution_name":         os.environ.get("CLOUD_RUN_EXECUTION", ""),
                    "job_identity":           job_identity,
                    "skipped":                True,
                }
            log.info(
                f"Retry trigger fired for {job_identity} (today's status: "
                f"{todays_status or 'not logged'}) — proceeding with a full run."
            )
    else:
        bq = None
        log.info("LOCAL MODE — skipping BigQuery, full extract.")
        events.append("Local mode — full extract")

    # ── Multi-report config mode ──────────────────────────────────────────────
    if REPORT_CONFIG_GCS_PATH:
        try:
            config = load_report_config(REPORT_CONFIG_GCS_PATH)
            report_name = config.get("report_name", REPORT_CONFIG_GCS_PATH)
            report_category = config.get("category", "")
            extractions = config.get("extractions", [])
            email_plex_view   = report_name
            email_plex_filter = f"{len(extractions)} extractions — see Events"
            view_cfgs         = [v for v in bq_view_configs(config) if isinstance(v, dict)]
            view_names        = [v.get("name", "?") for v in view_cfgs]
            email_bq_table    = ", ".join(view_names) if view_names else report_name
            # Peer reports produced by this one shared pipeline, named per the
            # Reports List (not just the raw BQ view name) — see the
            # display_name comment in reports/work_orders.yaml.
            email_reports_detail = [
                {"display_name": v.get("display_name", v.get("name", "?")), "table_name": v.get("name", "?")}
                for v in view_cfgs
            ]
            events.append(f"Loaded report config: {report_name} ({len(extractions)} extractions)")
            _RUN_CONTEXT.update({
                "report_name":     report_name,
                "report_category": report_category,
                "reports_detail":  email_reports_detail,
                "bq_table":        email_bq_table,
                "plex_view":       email_plex_view,
                "plex_filter":     email_plex_filter,
            })
        except Exception as exc:
            log.exception("Failed to load report config.")
            raise RuntimeError(f"Report config load failed: {exc}") from exc

        try:
            conn = get_odbc_connection(user, password, company_code, access_token)
        except Exception as exc:
            log.exception("Failed to establish ODBC connection to Plex.")
            raise RuntimeError(f"ODBC connection failed: {exc}") from exc

        # ── Change probe ──────────────────────────────────────────────────
        # Fingerprints what this report reads from Plex (see run_probe). When
        # the run is allowed to skip (probe_may_skip) and nothing changed since
        # the last clean run, the extraction AND the views are skipped — the
        # config/SQL are part of the fingerprint, so a deployed change can never
        # be what gets skipped. Fails open: any trouble runs the full extraction.
        kind = probe_kind(config)
        if OUTPUT_MODE == "bigquery" and kind:
            may_skip = probe_may_skip(kind, RUN_MODE)
            probe_started = datetime.now(timezone.utc)
            try:
                try:
                    ensure_probe_log_table(bq)
                    previous, previous_snapshot = last_applied_probe(bq, report_name)
                except Exception as exc:
                    # A BigQuery problem here used to fail the whole run. It is
                    # an inconclusive probe like any other: run in full.
                    raise ProbeInconclusive(f"probe log unreadable: {exc}")
                probe_fingerprint, probe_snapshot = run_probe(conn, config)
                changed = changed_sources(previous_snapshot, probe_snapshot)
                probe_info = {
                    "kind":            kind,
                    "sources_checked": len(probe_snapshot) - 1,   # minus the config entry
                    "changed":         [c for c in changed if c != _CONFIG_SNAPSHOT_KEY],
                    "config_changed":  _CONFIG_SNAPSHOT_KEY in changed and previous_snapshot is not None,
                    "first_run":       previous is None,
                    "seconds":         round((datetime.now(timezone.utc) - probe_started).total_seconds(), 1),
                    "may_skip":        may_skip,
                }
                if may_skip and previous and previous == probe_fingerprint:
                    log.info(
                        f"Probe unchanged for {report_name} (fingerprint "
                        f"{probe_fingerprint}) — skipping the extraction."
                    )
                    log_probe(bq, report_name, job_identity, probe_fingerprint, "skipped",
                              snapshot=probe_snapshot)
                    try:
                        conn.close()
                    except Exception:
                        log.warning("Failed to close ODBC connection cleanly.")
                    return {
                        "rows_fetched":           0,
                        "rows_written":           0,
                        "events":                 [f"Probe unchanged ({probe_fingerprint}) — extraction skipped"],
                        "partial_errors":         [],
                        "gcp_project":            GCP_PROJECT,
                        "bq_dataset":             BQ_DATASET,
                        "bq_table":               email_bq_table,
                        "report_name":            report_name,
                        "report_category":        report_category,
                        "reports_detail":         email_reports_detail,
                        "plex_view":              email_plex_view,
                        "plex_filter":            email_plex_filter,
                        "plex_host":              PLEX_HOST,
                        "report_config_gcs_path": REPORT_CONFIG_GCS_PATH,
                        "execution_name":         os.environ.get("CLOUD_RUN_EXECUTION", ""),
                        "job_identity":           job_identity,
                        "probe_fingerprint":      "",   # nothing ran; nothing to advance
                        "probe":                  probe_info,
                        "skipped":                True,
                        "skip_reason":            "probe",
                    }
                if not may_skip:
                    log.info(f"RUN_MODE={RUN_MODE}: full run; probe recorded as the next reference "
                             f"({probe_fingerprint}).")
                    events.append(f"Full run ({RUN_MODE}); probe fingerprint {probe_fingerprint}")
                else:
                    log.info(
                        f"Probe changed for {report_name}: {previous or 'no previous run'} "
                        f"-> {probe_fingerprint} — running the full extraction."
                    )
                    events.append(f"Probe changed ({previous or 'first run'} -> {probe_fingerprint})")
            except Exception as exc:
                # ProbeInconclusive is the expected case, but ANY error in the
                # probe block is treated the same way: the probe may cost time,
                # it may never fail a run that the extraction could finish.
                if not isinstance(exc, ProbeInconclusive):
                    log.exception("Unexpected error in the change probe — treating it as inconclusive.")
                log.warning(f"Probe inconclusive ({exc}) — running the full extraction.")
                events.append(f"WARNING: probe inconclusive: {exc} — ran the full extraction")
                probe_fingerprint, probe_snapshot = "", None
                probe_info = {"kind": kind, "inconclusive": str(exc)[:300], "may_skip": may_skip}
                # Logged, because a probe that is quietly inconclusive on every
                # run costs a full extraction each time and looks like success:
                #   SELECT * FROM <dataset>.probe_log
                #   WHERE outcome = 'inconclusive' ORDER BY probed_at DESC
                try:
                    log_probe(bq, report_name, job_identity, "(inconclusive)",
                              "inconclusive", detail=str(exc)[:1000])
                except Exception:
                    log.exception("Failed to log inconclusive probe.")

        try:
            for extraction in extractions:
                problem = validate_extraction(extraction)
                if problem:
                    log.error(f"Skipping invalid extraction entry: {problem}")
                    events.append(f"ERROR: invalid config entry skipped: {problem}")
                    partial_errors.append(f"config: {problem}")
                    extraction_rows.append({"table": str(extraction.get("bq_table", "?")) if isinstance(extraction, dict) else "?",
                                            "rows": None, "ok": False})
                    continue

                view     = extraction["plex_view"]
                table    = extraction["bq_table"]
                filt     = extraction.get("filter", "")
                date_col = extraction.get("date_col", "")

                log.info(f"--- Extracting {view} → {table} ---")
                try:
                    df = query_plex(conn, plex_view=view, plex_filter=filt, plex_date_col=date_col)
                except Exception as exc:
                    log.exception(f"Query failed for {view}: {exc}")
                    events.append(f"ERROR: {view} query failed: {exc}")
                    partial_errors.append(f"{view} query: {exc}")
                    extraction_rows.append({"table": table, "rows": None, "ok": False})
                    continue

                # NOTE: do NOT convert date_col in-place — a tz-aware column
                # lands in BigQuery as TIMESTAMP while every other date column
                # lands as INT64 nanoseconds, and the view SQL's NULLIF(x, 0)
                # zero-date guard only works on the INT64 form. Dates are
                # converted in the BigQuery VIEW, not here.
                max_modified = sync_time
                if date_col and date_col in df.columns and not df.empty:
                    col_max = pd.to_datetime(df[date_col], utc=True, errors="coerce").max()
                    if pd.notna(col_max):
                        max_modified = col_max.to_pydatetime()

                rows_fetched += len(df)
                events.append(f"Fetched {len(df)} rows from {view}")
                extraction_rows.append({"table": table, "rows": len(df), "ok": True})

                if OUTPUT_MODE == "bigquery":
                    try:
                        written = write_to_bigquery(bq, df, bq_table=table)
                        rows_written += written
                        if written > 0:
                            update_last_sync(bq, sync_time, written, max_modified, bq_table=table)
                            events.append(f"Wrote {written} rows to {table}")
                        else:
                            events.append(f"No rows to write for {table}")
                    except Exception as exc:
                        log.exception(f"BigQuery write failed for {table}: {exc}")
                        events.append(f"ERROR: {table} BQ write failed: {exc}")
                        partial_errors.append(f"{table} write: {exc}")
                        extraction_rows[-1]["ok"] = False
                else:
                    try:
                        written = write_to_csv(df, OUTPUT_DIR, table)
                        rows_written += written
                        events.append(f"Wrote {written} rows to {table} (CSV)")
                    except Exception as exc:
                        log.exception(f"CSV write failed for {table}: {exc}")
                        events.append(f"ERROR: {table} CSV write failed: {exc}")
                        partial_errors.append(f"{table} csv: {exc}")
        finally:
            try:
                conn.close()
                log.info("ODBC connection closed.")
            except Exception:
                log.warning("Failed to close ODBC connection cleanly.")

        if rows_fetched == 0 and not partial_errors:
            log.warning("All extractions returned 0 rows — verify Plex data availability.")
            events.append(
                "WARNING: all extractions returned 0 rows — "
                "check that Plex is returning data for this environment"
            )

        # Create/replace the BigQuery JOIN view(s) if defined in config.
        # A report may define one view (the common case) or a list of views
        # built from the same extracted raw tables (see bq_view_configs).
        # Each view is created independently — one bad/failing view must not
        # block the others from applying.
        if OUTPUT_MODE == "bigquery":
            views_applied = 0
            pending_views = []  # (view_name, view_sql) — config validated, SQL loaded, ready to attempt
            for view_cfg in bq_view_configs(config):
                problem = validate_bq_view(view_cfg)
                if problem:
                    log.error(f"Skipping invalid bq_view entry: {problem}")
                    events.append(f"ERROR: invalid bq_view config skipped: {problem}")
                    partial_errors.append(f"bq_view config: {problem}")
                    continue

                view_name = view_cfg["name"]
                view_sql  = view_cfg.get("sql", "")
                if not view_sql and view_cfg.get("sql_file"):
                    try:
                        raw_sql  = load_gcs_text(view_cfg["sql_file"])
                        view_sql = raw_sql.replace("{gcp_project}", GCP_PROJECT).replace("{dataset}", BQ_DATASET)
                    except Exception as exc:
                        log.exception(f"Failed to load view SQL for {view_name} from {view_cfg['sql_file']}: {exc}")
                        events.append(f"ERROR: Could not load view SQL for {view_name}: {exc}")
                        partial_errors.append(f"view SQL load ({view_name}): {exc}")
                        continue
                elif view_sql:
                    view_sql = view_sql.replace("{gcp_project}", GCP_PROJECT).replace("{dataset}", BQ_DATASET)

                pending_views.append((view_name, view_sql))

            # First pass, in config order. A thin alias view that SELECTs
            # from a sibling view listed later in the same config (e.g.
            # sales_orders_pending_approval_by_rep_view.sql) would otherwise
            # fail purely on list ordering — collected here and retried once
            # below, after every other view in this run has had a chance to
            # be created, instead of depending on a YAML comment to keep the
            # list in the right order forever.
            failed_views = []
            for view_name, view_sql in pending_views:
                try:
                    create_or_replace_bq_view(bq, BQ_DATASET, view_name, view_sql)
                    events.append(f"Applied BigQuery view {BQ_DATASET}.{view_name}")
                    views_applied += 1
                except Exception as exc:
                    log.warning(f"View {view_name} failed on first attempt, will retry once after the rest of this run's views: {exc}")
                    failed_views.append((view_name, view_sql))

            for view_name, view_sql in failed_views:
                try:
                    create_or_replace_bq_view(bq, BQ_DATASET, view_name, view_sql)
                    events.append(f"Applied BigQuery view {BQ_DATASET}.{view_name} (succeeded on retry after other views were created)")
                    views_applied += 1
                except Exception as exc:
                    log.exception(f"Failed to create/update BigQuery view {view_name} (also failed on retry): {exc}")
                    events.append(f"ERROR: BigQuery view update failed for {view_name}: {exc}")
                    partial_errors.append(f"view {view_name}: {exc}")

            if views_applied and partial_errors:
                # At least one view was refreshed, but something else in this
                # run failed (an extraction, another view, or config
                # validation) — flag it so the email doesn't read as a clean run.
                events.append(
                    f"WARNING: {views_applied} view(s) applied despite "
                    f"{len(partial_errors)} error(s) this run — some tables/views may hold stale data"
                )

    # ── Legacy single-view mode ───────────────────────────────────────────────
    else:
        try:
            conn = get_odbc_connection(user, password, company_code, access_token)
        except Exception as exc:
            log.exception("Failed to establish ODBC connection to Plex.")
            raise RuntimeError(f"ODBC connection failed: {exc}") from exc

        try:
            df = query_plex(conn)
        except Exception as exc:
            log.exception("Plex query failed.")
            raise RuntimeError(f"Plex query failed: {exc}") from exc
        finally:
            try:
                conn.close()
                log.info("ODBC connection closed.")
            except Exception:
                log.warning("Failed to close ODBC connection cleanly.")

        # date columns are converted in the BigQuery VIEW, not here (see
        # multi-report loop for rationale)
        max_modified = sync_time
        if not df.empty and PLEX_DATE_COL and PLEX_DATE_COL in df.columns:
            col_max = pd.to_datetime(df[PLEX_DATE_COL], utc=True, errors="coerce").max()
            if pd.notna(col_max):
                max_modified = col_max.to_pydatetime()
        rows_fetched = len(df)
        events.append(f"Fetched {rows_fetched} rows from Plex")

        if OUTPUT_MODE == "bigquery":
            try:
                rows_written = write_to_bigquery(bq, df)
            except Exception as exc:
                log.exception("BigQuery write failed.")
                raise RuntimeError(f"BigQuery write failed: {exc}") from exc
            if rows_written > 0:
                events.append(f"Wrote {rows_written} rows to BigQuery")
            else:
                events.append("No new rows to write")
        else:
            try:
                rows_written = write_to_csv(df, OUTPUT_DIR, BQ_TABLE)
            except Exception as exc:
                log.exception("CSV write failed.")
                raise RuntimeError(f"CSV write failed: {exc}") from exc
            events.append(f"Wrote {rows_written} rows to {OUTPUT_DIR}")

        if OUTPUT_MODE == "bigquery" and rows_written > 0:
            try:
                update_last_sync(bq, sync_time, rows_written, max_modified)
                events.append("Updated sync metadata")
            except Exception as exc:
                log.exception("Failed to update sync metadata.")
                raise RuntimeError(f"Metadata update failed: {exc}") from exc
        else:
            events.append("No metadata update needed")

    log.info(f"=== ETL job complete — {rows_written} rows written across {rows_fetched} fetched ===")
    return {
        "rows_fetched":           rows_fetched,
        "rows_written":           rows_written,
        "events":                 events,
        "partial_errors":         partial_errors,
        "gcp_project":            GCP_PROJECT,
        "bq_dataset":             BQ_DATASET,
        "bq_table":               email_bq_table,
        "report_name":            report_name,
        "report_category":        report_category,
        "reports_detail":         email_reports_detail,
        "plex_view":              email_plex_view,
        "plex_filter":            email_plex_filter,
        "plex_host":              PLEX_HOST,
        "report_config_gcs_path": REPORT_CONFIG_GCS_PATH,
        "execution_name":         os.environ.get("CLOUD_RUN_EXECUTION", ""),
        "probe_fingerprint":      probe_fingerprint,
        "probe_snapshot":         probe_snapshot,
        "probe":                  probe_info,
        "extractions":            extraction_rows,
    }


# Filled by main() as soon as the report config loads, so a run that crashes
# afterwards (ODBC refused, BigQuery down) still emails under the pipeline's
# real category and name — i.e. the SAME subject, and the same Gmail thread,
# as that pipeline's other runs. Before 2026-10-19 such a FAILED email fell
# back to the config filename and started a thread of its own.
_RUN_CONTEXT: dict = {}


def _report_identity(result: dict) -> dict:
    """The fields every run email carries, whatever happened in the run."""
    return {
        "gcp_project":     result.get("gcp_project",    GCP_PROJECT),
        "bq_dataset":      result.get("bq_dataset",     BQ_DATASET),
        "bq_table":        result.get("bq_table",       BQ_TABLE),
        "plex_view":       result.get("plex_view",      PLEX_VIEW),
        "plex_filter":     result.get("plex_filter",    PLEX_FILTER) or "none",
        "plex_host":       result.get("plex_host",      PLEX_HOST),
        "execution_name":  result.get("execution_name", os.environ.get("CLOUD_RUN_EXECUTION", "")),
        "report_name":     result.get("report_name",    _default_report_name()),
        "report_category": result.get("report_category", ""),
        "reports_detail":  result.get("reports_detail",  []),
        "time_zone":       REPORT_TIME_ZONE,
    }


def run_and_report():
    start_time = datetime.now(timezone.utc)
    error = None
    result = {
        "rows_fetched":           0,
        "rows_written":           0,
        "events":                 [],
        "gcp_project":            GCP_PROJECT,
        "bq_dataset":             BQ_DATASET,
        "bq_table":               BQ_TABLE,
        "report_name":            _default_report_name(),
        "report_category":        "",
        "reports_detail":         [],
        "plex_view":              PLEX_VIEW,
        "plex_filter":            PLEX_FILTER,
        "plex_host":              PLEX_HOST,
        "report_config_gcs_path": REPORT_CONFIG_GCS_PATH,
        "execution_name":         os.environ.get("CLOUD_RUN_EXECUTION", ""),
    }

    job_identity = os.environ.get("CLOUD_RUN_JOB") or REPORT_CONFIG_GCS_PATH or PLEX_VIEW

    try:
        result = main()
        if result.get("skipped"):
            probe_skip = result.get("skip_reason") == "probe"
            log.info(f"Run skipped ({'probe unchanged' if probe_skip else 'retry no-op'}) for {job_identity}.")
            if OUTPUT_MODE == "bigquery":
                try:
                    log_job_run(bigquery.Client(project=GCP_PROJECT), job_identity, status="skipped", run_mode=RUN_MODE)
                except Exception:
                    log.exception("Failed to log skipped run status.")
            record_dispatch_outcome("skipped")
            # A probe that found nothing still says so — with its own short
            # template and the SAME subject as a full run, so each pipeline's
            # day stays one Gmail thread. A retry no-op stays silent, as before.
            # EMAIL_MODE=on_error (label_design, hourly) keeps clean runs silent.
            if probe_skip and OUTPUT_MODE == "bigquery" and EMAIL_MODE != "on_error":
                end_time = datetime.now(timezone.utc)
                try:
                    send_report({
                        **_report_identity(result),
                        "status":           "no_changes",
                        "start_time":       start_time.isoformat(),
                        "end_time":         end_time.isoformat(),
                        "duration_seconds": int((end_time - start_time).total_seconds()),
                        "rows_fetched":     0,
                        "rows_written":     0,
                        "events":           result.get("events", []),
                        "errors":           [],
                        "run_mode":         RUN_MODE,
                        "probe":            result.get("probe", {}),
                        "extractions":      [],
                    })
                except Exception:
                    log.exception("Failed to send probe no-change email.")
            return result
        partial_errors = result.get("partial_errors", [])
        if partial_errors:
            status = "partial"
            errors = partial_errors
            log.warning("Job completed with %d extraction error(s).", len(partial_errors))
        else:
            status = "success"
            errors = []
    except Exception as exc:
        error = exc
        status = "failed"
        errors = [str(exc)]
        # main() raised, so `result` is still the defaults above. Use whatever
        # identity main() recorded before it failed (see _RUN_CONTEXT).
        result = {**result, **_RUN_CONTEXT}

    if OUTPUT_MODE == "bigquery":
        try:
            log_job_run(bigquery.Client(project=GCP_PROJECT), job_identity, status=status, run_mode=RUN_MODE)
        except Exception:
            log.exception("Failed to log job run status.")

    # The probe fingerprint becomes the reference ONLY after a clean run. A
    # partial or failed run logs it as 'failed' and leaves the reference where
    # it was, so the next scheduled probe sees a difference and runs again —
    # the retry, without a retry trigger. An exception before main() returned
    # carries no fingerprint at all, which has the same effect.
    fingerprint = result.get("probe_fingerprint", "") if isinstance(result, dict) else ""
    if OUTPUT_MODE == "bigquery" and fingerprint:
        try:
            log_probe(
                bigquery.Client(project=GCP_PROJECT),
                result.get("report_name", _default_report_name()),
                job_identity,
                fingerprint,
                "applied" if status == "success" else "failed",
                detail="; ".join(errors)[:1000] if errors else "",
                snapshot=result.get("probe_snapshot"),
            )
        except Exception:
            log.exception("Failed to log probe result.")

    record_dispatch_outcome(status, detail="; ".join(errors) if errors else "")

    end_time = datetime.now(timezone.utc)
    report = {
        **_report_identity(result),
        "status":           status,
        "start_time":       start_time.isoformat(),
        "end_time":         end_time.isoformat(),
        "duration_seconds": int((end_time - start_time).total_seconds()),
        "rows_fetched":     result.get("rows_fetched", 0),
        "rows_written":     result.get("rows_written", 0),
        "events":           result.get("events", []),
        "errors":           errors,
        "run_mode":         RUN_MODE,
        "probe":            result.get("probe", {}),
        "extractions":      result.get("extractions", []),
    }

    task_attempt = int(os.environ.get("CLOUD_RUN_TASK_ATTEMPT", "0"))
    email_wanted = EMAIL_MODE != "on_error" or status != "success"
    if OUTPUT_MODE == "bigquery" and email_wanted and (status == "success" or task_attempt == 0):
        try:
            send_report(report)
        except Exception:
            log.exception("Failed to send report email.")

    if error is not None:
        raise error

    return report


if __name__ == "__main__":
    run_and_report()
