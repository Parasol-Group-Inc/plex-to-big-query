"""Plex REST API (connect.plex.com) → BigQuery landing tables.

Deployed as a Cloud Function (Gen 2), triggered by Cloud Scheduler via HTTP.
The ODBC ETL is for heavy processes; this is a lightweight, near-real-time
pull of live Plex data for reports that can't tolerate a 4-hour lag.

Tables (created on first run):
    <dataset>.plex_api_payloads   append-only raw JSON, one row per CHANGED record
    <dataset>.plex_api_audit      one row per resource per run

Views (created/refreshed each run):
    <dataset>.plex_api_<resource>_latest   newest payload per record_id

A record is only inserted when its payload hash differs from the last stored
one, so a quiet hour costs zero rows.

Resources (RESOURCES env, comma list; default orders,order_lines,releases):
    orders       GET /sales/v1/orders
    order_lines  GET /sales/v1/orders/{id}/lines          (one call per order)
    releases     GET /sales/v1/releases
    parts        GET /mdm/v2/parts                        (15k+ rows; opt-in)
    customers    GET /mdm/v1/customers                    (opt-in)
    employees    GET /mdm/v1/employees                    (opt-in)

Environment:
    GCP_PROJECT                      voxdatalake
    BQ_DATASET                       PlexTest | PlexProd
    PLEX_API_CONSUMER_KEY            direct ...
    PLEX_API_CONSUMER_SECRET
    SECRET_PLEX_API_CONSUMER_KEY     ... or Secret Manager names   [plex-api-consumer-key]
    SECRET_PLEX_API_CONSUMER_SECRET                                [plex-api-consumer-secret]
    PLEX_API_TENANT_ID               optional: X-Plex-Connect-Tenant-Id header
    PLEX_API_CUSTOMER_ID             optional: X-Plex-Connect-Customer-Id header
    PLEX_API_BASE                    [https://connect.plex.com]
                                     test.connect.plex.com = TEST tenant
    MIN_INTERVAL                     seconds between calls; Plex throttles at 200/min [0.35]
    RESOURCES                        comma list [orders,order_lines,releases]
    DRY_RUN                          1 = fetch + count, write nothing
    MAX_PAGES                        [50]
"""
import datetime as dt
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

import functions_framework
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("plex_api_extract")

GCP_PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
BQ_DATASET = os.environ.get("BQ_DATASET", "PlexTest")
BASE = os.environ.get("PLEX_API_BASE", "https://connect.plex.com").rstrip("/")
DRY_RUN = os.environ.get("DRY_RUN", "") not in ("", "0", "false", "False")
MAX_PAGES = int(os.environ.get("MAX_PAGES", "50"))
PAGE_SIZE = 500
MIN_INTERVAL = float(os.environ.get("MIN_INTERVAL", "0.35"))

PAYLOADS = "plex_api_payloads"
AUDIT = "plex_api_audit"
PAYLOAD_SCHEMA = [
    bigquery.SchemaField("resource", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("record_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("parent_id", "STRING"),
    bigquery.SchemaField("payload_hash", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("payload", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("fetched_at", "TIMESTAMP", mode="REQUIRED"),
]
AUDIT_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("started_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("finished_at", "TIMESTAMP"),
    bigquery.SchemaField("resource", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("fetched", "INT64"),
    bigquery.SchemaField("inserted", "INT64"),
    bigquery.SchemaField("calls", "INT64"),
    bigquery.SchemaField("errors", "INT64"),
    bigquery.SchemaField("outcome", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("detail", "STRING"),
]

# resource -> (path, parent resource or None)
RESOURCE_DEFS = {
    "orders": ("/sales/v1/orders", None),
    "order_lines": ("/sales/v1/orders/{parent}/lines", "orders"),
    "releases": ("/sales/v1/releases", None),
    "parts": ("/mdm/v2/parts", None),
    "customers": ("/mdm/v1/customers", None),
    "employees": ("/mdm/v1/employees", None),
}

ORDER_FIELDS = ["orderNumber", "poNumber", "status", "type", "customerId", "insideSalesId",
                "orderDate", "createdDate", "modifiedDate", "note", "accountingJobNo"]

VIEW_SQL = """
CREATE OR REPLACE VIEW `{p}.{d}.plex_api_{res}_latest` AS
SELECT * EXCEPT (rn){extra}
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY record_id ORDER BY fetched_at DESC) AS rn
  FROM `{p}.{d}.{payloads}` WHERE resource = '{res}'
)
WHERE rn = 1
"""


class Api:
    def __init__(self, key, secret_val):
        self.headers = {"X-Plex-Connect-Api-Key": key,
                        "X-Plex-Connect-Api-Secret": secret_val,
                        "Accept": "application/json"}
        for header, env in (("X-Plex-Connect-Tenant-Id", "PLEX_API_TENANT_ID"),
                            ("X-Plex-Connect-Customer-Id", "PLEX_API_CUSTOMER_ID")):
            if os.environ.get(env):
                self.headers[header] = os.environ[env]
        self.last_call = 0.0
        self.calls = 0
        self.errors = 0

    def get(self, path, params=None, tries=4):
        url = BASE + path + ("?" + urllib.parse.urlencode(params, doseq=True) if params else "")
        err = ""
        for attempt in range(tries):
            wait = MIN_INTERVAL - (time.monotonic() - self.last_call)
            if wait > 0:
                time.sleep(wait)
            self.last_call = time.monotonic()
            self.calls += 1
            try:
                req = urllib.request.Request(url, headers=self.headers)
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code != 429 and e.code < 500:
                    self.errors += 1
                    raise RuntimeError(f"HTTP {e.code} {path}: {e.read().decode('utf-8', 'replace')[:300]}")
                err = f"HTTP {e.code}"
            except (urllib.error.URLError, TimeoutError) as e:
                err = str(e)
            time.sleep(2 ** attempt)
        self.errors += 1
        raise RuntimeError(f"{path} failed after {tries} tries: {err}")

    def list_all(self, path):
        seen, out = set(), []
        for page in range(MAX_PAGES):
            body = self.get(path, {"limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
            rows = body if isinstance(body, list) else (body.get("data") or body.get("items") or [])
            new = [r for r in rows if r.get("id") not in seen]
            seen.update(r.get("id") for r in new)
            out.extend(new)
            if not new or len(rows) < PAGE_SIZE:
                break
        else:
            log.warning("%s hit MAX_PAGES=%d, result may be incomplete", path, MAX_PAGES)
        return out


def _secret(env_value, env_name, default):
    if os.environ.get(env_value):
        return os.environ[env_value]
    from google.cloud import secretmanager
    name = f"projects/{GCP_PROJECT}/secrets/{os.environ.get(env_name, default)}/versions/latest"
    return secretmanager.SecretManagerServiceClient().access_secret_version(
        name=name).payload.data.decode("utf-8").strip()


def _ensure_tables(bq):
    for name, schema in ((PAYLOADS, PAYLOAD_SCHEMA), (AUDIT, AUDIT_SCHEMA)):
        t = bigquery.Table(f"{GCP_PROJECT}.{BQ_DATASET}.{name}", schema=schema)
        if name == PAYLOADS:
            t.time_partitioning = bigquery.TimePartitioning(field="fetched_at")
            t.clustering_fields = ["resource", "record_id"]
        bq.create_table(t, exists_ok=True)


def _ensure_views(bq, resources):
    for res in resources:
        extra = ""
        if res == "orders":
            extra = ",\n  " + ",\n  ".join(f"JSON_VALUE(payload, '$.{f}') AS {f}" for f in ORDER_FIELDS)
        bq.query(VIEW_SQL.format(p=GCP_PROJECT, d=BQ_DATASET, res=res, payloads=PAYLOADS,
                                 extra=extra)).result()


def _latest_hashes(bq, resource):
    q = f"""SELECT record_id, ARRAY_AGG(payload_hash ORDER BY fetched_at DESC LIMIT 1)[OFFSET(0)] AS h
            FROM `{GCP_PROJECT}.{BQ_DATASET}.{PAYLOADS}` WHERE resource = @r GROUP BY 1"""
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("r", "STRING", resource)])
    return {r.record_id: r.h for r in bq.query(q, job_config=cfg).result()}


def _load(bq, table, rows, schema):
    if not rows:
        return
    job = bq.load_table_from_json(rows, f"{GCP_PROJECT}.{BQ_DATASET}.{table}",
                                  job_config=bigquery.LoadJobConfig(
                                      schema=schema, write_disposition="WRITE_APPEND"))
    job.result()


def _run():
    """Core logic, returns (ok: bool, summary: str)."""
    wanted = [r.strip() for r in os.environ.get("RESOURCES", "orders,order_lines,releases").split(",") if r.strip()]
    unknown = [r for r in wanted if r not in RESOURCE_DEFS]
    if unknown:
        return False, f"unknown RESOURCES: {unknown}"

    api = Api(_secret("PLEX_API_CONSUMER_KEY", "SECRET_PLEX_API_CONSUMER_KEY", "plex-api-consumer-key"),
              _secret("PLEX_API_CONSUMER_SECRET", "SECRET_PLEX_API_CONSUMER_SECRET", "plex-api-consumer-secret"))
    bq = bigquery.Client(project=GCP_PROJECT)
    run_id, started = str(uuid.uuid4()), dt.datetime.now(dt.timezone.utc)
    if not DRY_RUN:
        _ensure_tables(bq)
    log.info("run %s -> %s.%s resources=%s dry_run=%s", run_id, GCP_PROJECT, BQ_DATASET, wanted, DRY_RUN)

    fetched_by_res, audit_rows, failed, summary = {}, [], False, []
    for res in wanted:
        path, parent = RESOURCE_DEFS[res]
        calls0, errs0 = api.calls, api.errors
        records, detail = [], []
        try:
            if parent is None:
                records = [(None, r) for r in api.list_all(path)]
            else:
                if parent not in fetched_by_res:
                    raise RuntimeError(f"'{res}' needs '{parent}' in RESOURCES")
                for p in fetched_by_res[parent]:
                    try:
                        records += [(p["id"], r) for r in api.get(path.format(parent=p["id"]))]
                    except RuntimeError as e:
                        detail.append(str(e)[:200])
        except RuntimeError as e:
            detail.append(str(e)[:400])
        fetched_by_res[res] = [r for _, r in records]

        now = dt.datetime.now(dt.timezone.utc)
        rows = []
        if not DRY_RUN and (records or not detail):
            old = _latest_hashes(bq, res)
            for parent_id, r in records:
                body = json.dumps(r, sort_keys=True, separators=(",", ":"))
                h = hashlib.sha256(body.encode("utf-8")).hexdigest()
                rid = str(r.get("id") or f"{parent_id}:{h[:12]}")
                if old.get(rid) != h:
                    rows.append({"resource": res, "record_id": rid, "parent_id": parent_id,
                                 "payload_hash": h, "payload": body, "run_id": run_id,
                                 "fetched_at": now.isoformat()})
            _load(bq, PAYLOADS, rows, PAYLOAD_SCHEMA)

        errors = api.errors - errs0
        outcome = "dry_run" if DRY_RUN else ("failed" if detail and not records else "partial" if detail else "ok")
        failed |= outcome == "failed"
        line = f"{res}: fetched={len(records)} inserted={len(rows)} errors={errors} {outcome}"
        log.info(line)
        summary.append(line)
        audit_rows.append({"run_id": run_id, "started_at": started.isoformat(),
                           "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "resource": res,
                           "fetched": len(records), "inserted": len(rows), "calls": api.calls - calls0,
                           "errors": errors, "outcome": outcome,
                           "detail": "; ".join([f"host={urllib.parse.urlparse(BASE).netloc}"] + detail)[:1000]})

    if not DRY_RUN:
        _load(bq, AUDIT, audit_rows, AUDIT_SCHEMA)
        _ensure_views(bq, wanted)

    return not failed, "\n".join(summary)


@functions_framework.http
def plex_api_extract(request):
    """HTTP entry point for Cloud Functions / Cloud Scheduler."""
    ok, summary = _run()
    return (summary, 200 if ok else 500)


# Also runnable directly: python main.py
if __name__ == "__main__":
    import sys
    ok, summary = _run()
    print(summary)
    sys.exit(0 if ok else 1)
