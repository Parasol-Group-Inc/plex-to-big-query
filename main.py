import os
import re
import logging
from datetime import datetime, timezone
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

# "scheduled" (default, always runs) or "retry" — set by the 6 AM Mountain
# retry Cloud Scheduler trigger. In retry mode the job first checks whether
# today's scheduled run already succeeded/partial; if so it no-ops instead
# of running the full ETL again. See docs/OPERATIONS.md for the design.
RUN_MODE          = os.environ.get("RUN_MODE", "scheduled")
JOB_RUN_LOG_TABLE = os.environ.get("JOB_RUN_LOG_TABLE", "job_run_log")

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
    config = yaml.safe_load(load_gcs_text(config_path))
    if not isinstance(config, dict):
        raise ValueError(
            f"Report config at {config_path} is not a valid YAML mapping "
            f"(got {type(config).__name__}). Check the file wasn't saved empty."
        )
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
    rows = cursor.fetchall()
    df = pd.DataFrame.from_records(rows, columns=columns)
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
            schema = [bigquery.SchemaField(col, "STRING") for col in df.columns]
            bq.create_table(bigquery.Table(table_ref, schema=schema))
            log.info(f"0 rows for {table_name} — created empty table with {len(schema)} columns.")
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
        except Exception as exc:
            log.exception("Failed to load report config.")
            raise RuntimeError(f"Report config load failed: {exc}") from exc

        try:
            conn = get_odbc_connection(user, password, company_code, access_token)
        except Exception as exc:
            log.exception("Failed to establish ODBC connection to Plex.")
            raise RuntimeError(f"ODBC connection failed: {exc}") from exc

        try:
            for extraction in extractions:
                problem = validate_extraction(extraction)
                if problem:
                    log.error(f"Skipping invalid extraction entry: {problem}")
                    events.append(f"ERROR: invalid config entry skipped: {problem}")
                    partial_errors.append(f"config: {problem}")
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

                try:
                    create_or_replace_bq_view(bq, BQ_DATASET, view_name, view_sql)
                    events.append(f"Applied BigQuery view {BQ_DATASET}.{view_name}")
                    views_applied += 1
                except Exception as exc:
                    log.exception(f"Failed to create/update BigQuery view {view_name}: {exc}")
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
            log.info(f"Run skipped (retry no-op) for {job_identity}.")
            if OUTPUT_MODE == "bigquery":
                try:
                    log_job_run(bigquery.Client(project=GCP_PROJECT), job_identity, status="skipped", run_mode=RUN_MODE)
                except Exception:
                    log.exception("Failed to log skipped run status.")
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

    if OUTPUT_MODE == "bigquery":
        try:
            log_job_run(bigquery.Client(project=GCP_PROJECT), job_identity, status=status, run_mode=RUN_MODE)
        except Exception:
            log.exception("Failed to log job run status.")

    end_time = datetime.now(timezone.utc)
    report = {
        "status":           status,
        "start_time":       start_time.isoformat(),
        "end_time":         end_time.isoformat(),
        "duration_seconds": int((end_time - start_time).total_seconds()),
        "rows_fetched":     result.get("rows_fetched", 0),
        "rows_written":     result.get("rows_written", 0),
        "events":           result.get("events", []),
        "errors":           errors,
        "gcp_project":      result.get("gcp_project",    GCP_PROJECT),
        "bq_dataset":       result.get("bq_dataset",     BQ_DATASET),
        "bq_table":         result.get("bq_table",       BQ_TABLE),
        "plex_view":        result.get("plex_view",      PLEX_VIEW),
        "plex_filter":      result.get("plex_filter",    PLEX_FILTER) or "none",
        "plex_host":        result.get("plex_host",      PLEX_HOST),
        "execution_name":   result.get("execution_name", os.environ.get("CLOUD_RUN_EXECUTION", "")),
        "report_name":      result.get("report_name",    _default_report_name()),
        "report_category":  result.get("report_category", ""),
        "reports_detail":   result.get("reports_detail",  []),
    }

    task_attempt = int(os.environ.get("CLOUD_RUN_TASK_ATTEMPT", "0"))
    if OUTPUT_MODE == "bigquery" and (status == "success" or task_attempt == 0):
        try:
            send_report(report)
        except Exception:
            log.exception("Failed to send report email.")

    if error is not None:
        raise error

    return report


if __name__ == "__main__":
    run_and_report()
