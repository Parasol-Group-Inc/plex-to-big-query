#!/usr/bin/env python3
"""Plex REST API (connect.plex.com) -> BigQuery landing tables.

Why this exists: the ODBC ETL reads a Plex database that is up to 4 hours
behind, which is too stale for the Label Design queue. The REST API reads live
data. This job lands that data in BigQuery WITHOUT touching the ODBC tables:

    <dataset>.plex_api_payloads   append-only; one row per CHANGED record
                                  (resource, record_id, parent_id, payload JSON)
    <dataset>.plex_api_audit      one row per resource per run (rows, calls,
                                  errors, outcome)
    <dataset>.plex_api_<x>_latest views: newest payload per record (created by
                                  this job, see VIEW_SQL)

Run:
    python -m plex_api_service.extract              # in the container
    DRY_RUN=1 python -m plex_api_service.extract    # fetch + count, write nothing

A record is only inserted when its payload hash differs from the newest stored
one, so a run with no changes writes zero rows. Writes are batch LOAD jobs, not
streaming, so a test row can be deleted straight away.

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
    PLEX_API_CONSUMER_KEY            direct (local runs) ...
    PLEX_API_CONSUMER_SECRET
    SECRET_PLEX_API_CONSUMER_KEY     ... or Secret Manager names   [plex-api-consumer-key]
    SECRET_PLEX_API_CONSUMER_SECRET                                [plex-api-consumer-secret]
    PLEX_API_TENANT_ID               optional: run against another tenant (header
                                     X-Plex-Connect-Tenant-Id) than the key's default
    PLEX_API_CUSTOMER_ID             optional: same, by PCN (X-Plex-Connect-Customer-Id)
    PLEX_API_BASE                    https://connect.plex.com = PRODUCTION tenant,
                                     https://test.connect.plex.com = TEST tenant (feeds PlexTest)
                                     [https://connect.plex.com]
    MIN_INTERVAL                     seconds between calls; Plex throttles at 200/min [0.35]
    RESOURCES, DRY_RUN, MAX_PAGES    [50]
"""
import datetime as dt
import hashlib
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

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
    bigquery.SchemaField("parent_id", "STRING"),  # order id for order_lines
    bigquery.SchemaField("payload_hash", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("payload", "STRING", mode="REQUIRED"),  # raw JSON, untouched
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("fetched_at", "TIMESTAMP", mode="REQUIRED"),
]
AUDIT_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("started_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("finished_at", "TIMESTAMP"),
    bigquery.SchemaField("resource", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("fetched", "INT64"),   # records the API returned
    bigquery.SchemaField("inserted", "INT64"),  # new or changed -> written
    bigquery.SchemaField("calls", "INT64"),     # HTTP calls made
    bigquery.SchemaField("errors", "INT64"),    # calls that failed after retries
    bigquery.SchemaField("outcome", "STRING", mode="REQUIRED"),  # ok | partial | failed | dry_run
    bigquery.SchemaField("detail", "STRING"),
]

# resource -> (path, parent resource or None)
RESOURCES = {
    "orders": ("/sales/v1/orders", None),
    "order_lines": ("/sales/v1/orders/{parent}/lines", "orders"),
    "releases": ("/sales/v1/releases", None),
    "parts": ("/mdm/v2/parts", None),
    "customers": ("/mdm/v1/customers", None),
    "employees": ("/mdm/v1/employees", None),
}

# One "newest payload per record" view per resource. Orders is typed with the
# fields seen live on 2026-10-12; the rest expose the raw JSON until real rows
# (order lines, releases) show their shape.
VIEW_SQL = """
CREATE OR REPLACE VIEW `{p}.{d}.plex_api_{res}_latest` AS
SELECT * EXCEPT (rn){extra}
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY record_id ORDER BY fetched_at DESC) AS rn
  FROM `{p}.{d}.{payloads}` WHERE resource = '{res}'
)
WHERE rn = 1
"""
ORDER_FIELDS = ["orderNumber", "poNumber", "status", "type", "customerId", "insideSalesId",
                "orderDate", "createdDate", "modifiedDate", "note", "accountingJobNo"]


class Api:
    def __init__(self, key, secret):
        self.headers = {"X-Plex-Connect-Api-Key": key, "X-Plex-Connect-Api-Secret": secret,
                        "Accept": "application/json"}
        # The key's default tenant decides what it sees; these switch tenant.
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
                # 4xx other than 429 won't improve by retrying
                if e.code != 429 and e.code < 500:
                    self.errors += 1
                    raise RuntimeError(f"HTTP {e.code} {path}: {e.read().decode('utf-8', 'replace')[:300]}")
                err = f"HTTP {e.code}"
            except (urllib.error.URLError, TimeoutError) as e:
                err = str(e)
            time.sleep(2 ** attempt)
        self.errors += 1
        raise RuntimeError(f"{path} failed after {tries} tries: {err}")

    def list(self, path):
        """All records of a list endpoint. Paging is not documented for these
        endpoints (the order list ignored limit/offset when probed), so page
        until a page adds no new ids, which also ends a server that ignores
        offset and returns the same page forever."""
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


def secret(env_value, env_name, default):
    if os.environ.get(env_value):
        return os.environ[env_value]
    from google.cloud import secretmanager
    name = f"projects/{GCP_PROJECT}/secrets/{os.environ.get(env_name, default)}/versions/latest"
    return secretmanager.SecretManagerServiceClient().access_secret_version(
        name=name).payload.data.decode("utf-8").strip()


def ensure_tables(bq):
    for name, schema in ((PAYLOADS, PAYLOAD_SCHEMA), (AUDIT, AUDIT_SCHEMA)):
        t = bigquery.Table(f"{GCP_PROJECT}.{BQ_DATASET}.{name}", schema=schema)
        if name == PAYLOADS:
            t.time_partitioning = bigquery.TimePartitioning(field="fetched_at")
            t.clustering_fields = ["resource", "record_id"]
        bq.create_table(t, exists_ok=True)


def ensure_views(bq, resources):
    for res in resources:
        extra = ""
        if res == "orders":
            extra = ",\n  " + ",\n  ".join(f"JSON_VALUE(payload, '$.{f}') AS {f}" for f in ORDER_FIELDS)
        bq.query(VIEW_SQL.format(p=GCP_PROJECT, d=BQ_DATASET, res=res, payloads=PAYLOADS,
                                 extra=extra)).result()


def latest_hashes(bq, resource):
    q = f"""SELECT record_id, ARRAY_AGG(payload_hash ORDER BY fetched_at DESC LIMIT 1)[OFFSET(0)] AS h
            FROM `{GCP_PROJECT}.{BQ_DATASET}.{PAYLOADS}` WHERE resource = @r GROUP BY 1"""
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("r", "STRING", resource)])
    return {r.record_id: r.h for r in bq.query(q, job_config=cfg).result()}


def load(bq, table, rows, schema):
    if not rows:
        return
    job = bq.load_table_from_json(rows, f"{GCP_PROJECT}.{BQ_DATASET}.{table}",
                                  job_config=bigquery.LoadJobConfig(
                                      schema=schema, write_disposition="WRITE_APPEND"))
    job.result()


def main():
    wanted = [r.strip() for r in os.environ.get("RESOURCES", "orders,order_lines,releases").split(",") if r.strip()]
    unknown = [r for r in wanted if r not in RESOURCES]
    if unknown:
        sys.exit(f"unknown RESOURCES: {unknown}; known: {list(RESOURCES)}")
    api = Api(secret("PLEX_API_CONSUMER_KEY", "SECRET_PLEX_API_CONSUMER_KEY", "plex-api-consumer-key"),
              secret("PLEX_API_CONSUMER_SECRET", "SECRET_PLEX_API_CONSUMER_SECRET", "plex-api-consumer-secret"))
    bq = bigquery.Client(project=GCP_PROJECT)
    run_id, started = str(uuid.uuid4()), dt.datetime.now(dt.timezone.utc)
    if not DRY_RUN:
        ensure_tables(bq)
    log.info("run %s -> %s.%s resources=%s dry_run=%s", run_id, GCP_PROJECT, BQ_DATASET, wanted, DRY_RUN)

    fetched_by_res, audit, failed = {}, [], False
    for res in wanted:
        path, parent = RESOURCES[res]
        calls0, errs0 = api.calls, api.errors
        records, detail = [], []
        try:
            if parent is None:
                records = [(None, r) for r in api.list(path)]
            else:
                if parent not in fetched_by_res:
                    raise RuntimeError(f"'{res}' needs '{parent}' in RESOURCES (it is fetched per {parent})")
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
            old = latest_hashes(bq, res)
            for parent_id, r in records:
                body = json.dumps(r, sort_keys=True, separators=(",", ":"))
                h = hashlib.sha256(body.encode("utf-8")).hexdigest()
                rid = str(r.get("id") or f"{parent_id}:{h[:12]}")
                if old.get(rid) != h:
                    rows.append({"resource": res, "record_id": rid, "parent_id": parent_id,
                                 "payload_hash": h, "payload": body, "run_id": run_id,
                                 "fetched_at": now.isoformat()})
            load(bq, PAYLOADS, rows, PAYLOAD_SCHEMA)
        errors = api.errors - errs0
        outcome = "dry_run" if DRY_RUN else ("failed" if detail and not records else "partial" if detail else "ok")
        failed |= outcome == "failed"
        log.info("%-12s fetched=%d inserted=%d calls=%d errors=%d %s", res, len(records), len(rows),
                 api.calls - calls0, errors, outcome)
        audit.append({"run_id": run_id, "started_at": started.isoformat(),
                      "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(), "resource": res,
                      "fetched": len(records), "inserted": len(rows), "calls": api.calls - calls0,
                      "errors": errors, "outcome": outcome,
                      "detail": "; ".join([f"host={urllib.parse.urlparse(BASE).netloc}"] + detail)[:1000]})
    if not DRY_RUN:
        load(bq, AUDIT, audit, AUDIT_SCHEMA)
        ensure_views(bq, wanted)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
