import os
import logging
from datetime import datetime, timezone, timedelta

import pyodbc
import pandas as pd
from google.cloud import bigquery, secretmanager

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
METADATA_TABLE   = os.environ.get("METADATA_TABLE", "sync_metadata")
BACKFILL_MINUTES = int(os.environ.get("BACKFILL_MINUTES", "5"))

SECRET_USER      = os.environ.get("SECRET_ODBC_USER",    "plex-odbc-user")
SECRET_PASSWORD  = os.environ.get("SECRET_ODBC_PASSWORD", "plex-odbc-password")
SECRET_COMPANY   = os.environ.get("SECRET_COMPANY_CODE",  "plex-company-code")


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


# ── BigQuery helpers ──────────────────────────────────────────────────────────
def get_last_sync(bq: bigquery.Client) -> datetime:
    """
    Read the last successful sync timestamp from the metadata table.
    Returns epoch start if the table is empty (first run).
    """
    query = f"""
        SELECT MAX(max_modified_at) AS last_sync
        FROM `{GCP_PROJECT}.{BQ_DATASET}.{METADATA_TABLE}`
        WHERE table_name = '{BQ_TABLE}'
    """
    result = bq.query(query).result()
    row = next(iter(result))
    if row.last_sync is None:
        log.info("No previous sync found — performing full load.")
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    last_sync = row.last_sync
    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)
    log.info(f"Last sync (max modified): {last_sync}")
    return last_sync


def update_last_sync(
    bq: bigquery.Client,
    sync_time: datetime,
    rows_written: int,
    max_modified: datetime,
):
    """Record a successful sync in the metadata table."""
    rows = [{
        "table_name":    BQ_TABLE,
        "last_sync_at":  sync_time.isoformat(),
        "max_modified_at": max_modified.isoformat(),
        "rows_written":  rows_written,
        "synced_at":     datetime.now(timezone.utc).isoformat(),
    }]
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{METADATA_TABLE}"
    errors = bq.insert_rows_json(table_ref, rows)
    if errors:
        raise RuntimeError(f"Failed to update sync metadata: {errors}")
    log.info(f"Metadata updated — {rows_written} rows written.")


def ensure_metadata_table(bq: bigquery.Client):
    """Create the metadata table if it doesn't exist yet."""
    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{METADATA_TABLE}"
    schema = [
        bigquery.SchemaField("table_name",   "STRING",    mode="REQUIRED"),
        bigquery.SchemaField("last_sync_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("max_modified_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("rows_written", "INTEGER",   mode="REQUIRED"),
        bigquery.SchemaField("synced_at",    "TIMESTAMP", mode="REQUIRED"),
    ]
    try:
        table = bq.get_table(table_ref)
        existing_fields = {field.name for field in table.schema}
        if "max_modified_at" not in existing_fields:
            table.schema = table.schema + [schema[2]]
            bq.update_table(table, ["schema"])
            log.info("Added max_modified_at to sync metadata table.")
    except Exception:
        table = bigquery.Table(table_ref, schema=schema)
        bq.create_table(table)


# ── ODBC connection ───────────────────────────────────────────────────────────
def get_odbc_connection(user: str, password: str, company_code: str) -> pyodbc.Connection:
    """
    Connect to Plex via ODBC using the DSN defined in /etc/odbc.ini.
    CompanyCode is injected at runtime from Secret Manager rather than
    hardcoded in the config file.
    """
    conn_str = (
        f"DSN={PLEX_DSN};"
        f"UID={user};"
        f"PWD={password};"
        f"CustomProperties=CompanyCode={company_code};"
    )
    log.info(f"Connecting to Plex via DSN: {PLEX_DSN}")
    conn = pyodbc.connect(conn_str, timeout=30)
    log.info("ODBC connection established.")
    return conn


# ── Plex query ────────────────────────────────────────────────────────────────
def query_plex(conn: pyodbc.Connection, last_sync: datetime) -> pd.DataFrame:
    """
    Pull records from Plex modified since the last sync.

    Replace the SQL below with the actual Plex report/view name and
    columns provided by the implementors. The modified_date filter
    keeps each run incremental — only new or changed rows are pulled.
    """
    sql = f"""
        SELECT
            P.Plexus_Customer_No,
            P.Part_No,
            P.Part_Name,
            P.Quantity,
            P.Status,
            P.Modified_Date
        FROM
            Production_Order_v_Production_Order AS P
        WHERE
            P.Modified_Date > ?
        ORDER BY
            P.Modified_Date ASC
    """
    log.info(f"Querying Plex for records modified after {last_sync}...")
    df = pd.read_sql(sql, conn, params=[last_sync])
    log.info(f"Fetched {len(df)} rows from Plex.")
    return df


# ── BigQuery write ────────────────────────────────────────────────────────────
def write_to_bigquery(bq: bigquery.Client, df: pd.DataFrame):
    """
    Append the DataFrame to the target BigQuery table.
    Uses WRITE_APPEND so incremental runs accumulate over time.
    """
    if df.empty:
        log.info("No new rows to write — skipping BigQuery write.")
        return 0

    table_ref = f"{GCP_PROJECT}.{BQ_DATASET}.{BQ_TABLE}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=True,
    )

    log.info(f"Writing {len(df)} rows to {table_ref}...")
    job = bq.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()  # wait for job to complete

    if job.errors:
        raise RuntimeError(f"BigQuery load job failed: {job.errors}")

    log.info(f"Successfully wrote {len(df)} rows to BigQuery.")
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
    sync_time = datetime.now(timezone.utc)
    log.info("=== Plex → BigQuery ETL job starting ===")
    events = []
    rows_fetched = 0
    rows_written = 0

    # Fetch credentials from Secret Manager
    log.info("Fetching credentials from Secret Manager...")
    try:
        user         = get_credential("PLEX_ODBC_USER",     SECRET_USER)
        password     = get_credential("PLEX_ODBC_PASSWORD",  SECRET_PASSWORD)
        company_code = get_credential("PLEX_COMPANY_CODE",   SECRET_COMPANY)
        events.append("Fetched credentials from Secret Manager")
    except Exception as exc:
        log.exception("Failed to fetch credentials from Secret Manager.")
        raise RuntimeError("Secret Manager fetch failed.") from exc

    # Init BigQuery client and get incremental sync cursor (bigquery mode only)
    if OUTPUT_MODE == "bigquery":
        try:
            bq = bigquery.Client(project=GCP_PROJECT)
            ensure_metadata_table(bq)
            events.append("Initialized BigQuery and metadata table")
        except Exception as exc:
            log.exception("Failed to initialize BigQuery client or metadata table.")
            raise RuntimeError("BigQuery initialization failed.") from exc
        try:
            last_sync = get_last_sync(bq)
        except Exception as exc:
            log.exception("Failed to fetch last sync metadata.")
            raise RuntimeError("Metadata lookup failed.") from exc
    else:
        bq = None
        last_sync = datetime(1970, 1, 1, tzinfo=timezone.utc)
        log.info("LOCAL MODE — skipping BigQuery, full extract from epoch.")
        events.append("Local mode — full extract")

    backfill_window = timedelta(minutes=BACKFILL_MINUTES)
    query_cutoff = last_sync - backfill_window
    if query_cutoff.tzinfo is None:
        query_cutoff = query_cutoff.replace(tzinfo=timezone.utc)
    log.info(f"Using backfill window: {BACKFILL_MINUTES} minutes")
    events.append(f"Using backfill window: {BACKFILL_MINUTES} minutes")

    # Connect to Plex and pull data
    try:
        conn = get_odbc_connection(user, password, company_code)
    except Exception as exc:
        log.exception("Failed to establish ODBC connection to Plex.")
        raise RuntimeError("ODBC connection failed.") from exc

    try:
        df = query_plex(conn, query_cutoff)
    except Exception as exc:
        log.exception("Plex query failed.")
        raise RuntimeError("Plex query failed.") from exc
    finally:
        try:
            conn.close()
            log.info("ODBC connection closed.")
        except Exception:
            log.warning("Failed to close ODBC connection cleanly.")

    if not df.empty and "Modified_Date" in df.columns:
        df["Modified_Date"] = pd.to_datetime(
            df["Modified_Date"],
            utc=True,
            errors="coerce",
        )
    rows_fetched = len(df)
    events.append(f"Fetched {rows_fetched} rows from Plex")

    # Write output
    if OUTPUT_MODE == "bigquery":
        try:
            rows_written = write_to_bigquery(bq, df)
        except Exception as exc:
            log.exception("BigQuery write failed.")
            raise RuntimeError("BigQuery write failed.") from exc
        if rows_written > 0:
            events.append(f"Wrote {rows_written} rows to BigQuery")
        else:
            events.append("No new rows to write")
    else:
        try:
            rows_written = write_to_csv(df, OUTPUT_DIR, BQ_TABLE)
        except Exception as exc:
            log.exception("CSV write failed.")
            raise RuntimeError("CSV write failed.") from exc
        events.append(f"Wrote {rows_written} rows to {OUTPUT_DIR}")

    # Update sync metadata (bigquery mode only)
    if OUTPUT_MODE == "bigquery" and rows_written > 0:
        if "Modified_Date" in df.columns:
            max_modified = df["Modified_Date"].max()
            if pd.isna(max_modified):
                max_modified = sync_time
        else:
            max_modified = sync_time
        try:
            update_last_sync(bq, sync_time, rows_written, max_modified)
            events.append("Updated sync metadata")
        except Exception as exc:
            log.exception("Failed to update sync metadata.")
            raise RuntimeError("Metadata update failed.") from exc
    else:
        events.append("No metadata update needed")

    log.info(f"=== ETL job complete — {rows_written} rows written ===")
    return {
        "rows_fetched": rows_fetched,
        "rows_written": rows_written,
        "events": events,
    }


def run_and_report():
    start_time = datetime.now(timezone.utc)
    error = None
    result = {
        "rows_fetched": 0,
        "rows_written": 0,
        "events": [],
    }

    try:
        result = main()
        status = "success"
        errors = []
    except Exception as exc:
        error = exc
        status = "failed"
        errors = [str(exc)]

    end_time = datetime.now(timezone.utc)
    report = {
        "status": status,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_seconds": int((end_time - start_time).total_seconds()),
        "rows_fetched": result.get("rows_fetched", 0),
        "rows_written": result.get("rows_written", 0),
        "events": result.get("events", []),
        "errors": errors,
    }

    if OUTPUT_MODE == "bigquery":
        try:
            send_report(report)
        except Exception:
            log.exception("Failed to send report email.")

    if error is not None:
        raise error

    return report


if __name__ == "__main__":
    run_and_report()