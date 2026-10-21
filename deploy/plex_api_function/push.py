#!/usr/bin/env python3
"""Plex API → Monday push — reads plex_api_label_design_report, creates items.

ARCHIVED 2026-10-20 — NEVER DEPLOYED, DO NOT DEPLOY AS IS. It would write to the
team's live board. See ARCHIVED.md in this folder for what must change first.
The extractor (main.py) is unaffected and stays live.

Cloud Function (Gen 2), companion to main.py (the extractor). Same board as the
ODBC push (18432111755 "Plex Import"), different group (API_Test). Same dedupe
pattern (LCR hash), own audit table (plex_api_push_log).

Deploy:
    gcloud functions deploy plex-api-push-test \
      --gen2 --runtime=python312 --region=us-central1 \
      --source=deploy/plex_api_function \
      --entry-point=plex_api_push \
      --trigger-http --no-allow-unauthenticated \
      --service-account=<etl SA email> \
      --timeout=540 --memory=256Mi \
      --set-env-vars="GCP_PROJECT=voxdatalake,BQ_DATASET=PlexTest,SECRET_MONDAY_API_KEY=monday-api-key,MONDAY_BOARD_ID=18432111755,MONDAY_GROUP_TITLE=API_Test" \
      --project=voxdatalake

Environment:
    GCP_PROJECT          voxdatalake
    BQ_DATASET           PlexTest | PlexProd
    MONDAY_API_KEY       direct (local runs) ...
    SECRET_MONDAY_API_KEY   ... or Secret Manager name   [monday-api-key]
    MONDAY_BOARD_ID      18432111755
    MONDAY_GROUP_TITLE   API_Test
    MAX_NEW_ITEMS        alarm threshold                  [60]
    DRY_RUN              1 = read everything, write nothing
"""
import datetime as dt
import hashlib
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

import functions_framework
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("plex_api_push")

GCP_PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
BQ_DATASET = os.environ.get("BQ_DATASET", "PlexTest")
BOARD_ID = os.environ.get("MONDAY_BOARD_ID", "18432111755")
GROUP_TITLE = os.environ.get("MONDAY_GROUP_TITLE", "API_Test")
MAX_NEW_ITEMS = int(os.environ.get("MAX_NEW_ITEMS", "60"))
DRY_RUN = os.environ.get("DRY_RUN", "") not in ("", "0", "false", "False")

VIEW = "plex_api_label_design_report"
AUDIT_TABLE = "plex_api_push_log"
AUDIT_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("pushed_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("board_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("dedupe_key", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("lcr", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("order_number", "STRING"),
    bigquery.SchemaField("part_no", "STRING"),
    bigquery.SchemaField("monday_item_id", "STRING"),
    bigquery.SchemaField("outcome", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("detail", "STRING"),
    bigquery.SchemaField("column_values", "STRING"),
]

MONDAY_API_VERSION = "2024-10"

REPORT_VIEW_SQL = open(os.path.join(os.path.dirname(__file__), "views.sql")).read()


def lcr_hash(dedupe_key):
    return hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:12]


def _secret(env_value, env_name, default):
    if os.environ.get(env_value):
        return os.environ[env_value]
    from google.cloud import secretmanager
    name = f"projects/{GCP_PROJECT}/secrets/{os.environ.get(env_name, default)}/versions/latest"
    return secretmanager.SecretManagerServiceClient().access_secret_version(
        name=name).payload.data.decode("utf-8").strip()


# ── Monday GraphQL client (minimal, same as label_design_service/monday.py) ──

class Monday:
    def __init__(self, api_key):
        self.api_key = api_key

    def __call__(self, query, variables=None, tries=5):
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        for attempt in range(tries):
            req = urllib.request.Request("https://api.monday.com/v2", data=payload, method="POST",
                                         headers={"Authorization": self.api_key,
                                                  "Content-Type": "application/json",
                                                  "API-Version": MONDAY_API_VERSION})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code != 429 and e.code < 500:
                    raise RuntimeError(f"Monday HTTP {e.code}: {e.read().decode('utf-8','replace')[:300]}")
                time.sleep(2 ** attempt)
                continue
            except (urllib.error.URLError, TimeoutError):
                time.sleep(2 ** attempt)
                continue
            if body.get("errors"):
                msgs = [e.get("message", "") for e in body["errors"]]
                if any("rate limit" in m.lower() or "complexity" in m.lower() for m in msgs):
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"Monday errors: {'; '.join(msgs)[:500]}")
            return body.get("data", body)
        raise RuntimeError(f"Monday API failed after {tries} tries")


# ── Row -> Monday column values ──────────────────────────────────────────────

def _text(field):
    return lambda r: (str(r[field]).strip() or None) if r.get(field) not in (None, "") else None

def _sales_order(r):
    s = str(r.get("order_number") or "").strip()
    return f"Sales Order #{s}" if s else None

def _date(r):
    d = r.get("order_date")
    return {"date": str(d)[:10]} if d else None

def _email(r):
    e = (r.get("customer_email") or "").strip()
    return {"email": e, "text": e} if e else None

def _label(field):
    return lambda r: {"label": str(r[field]).strip()} if (r.get(field) or "").strip() else None

COLUMNS = [
    ("Customer Name", "text", _text("customer_name")),
    ("Date", "date", _date),
    ("Description", "text", _text("line_description")),
    ("Sales Order", "text", _sales_order),
    ("Email", "email", _email),
    ("Phone Number", "text", _text("customer_phone")),
    ("Bottle Material", "status", _label("bottle_material")),
    ("Label Part #", "text", _text("label_part_no")),
    ("Customer PO", "text", _text("customer_po")),
    ("Item", "text", _text("part_no")),
    ("LCR", "text", _text("_lcr")),
]


# ── Monday reads ─────────────────────────────────────────────────────────────

def resolve_board(api):
    b = api("""query ($b: [ID!]) { boards(ids: $b) { name
               columns { id title type } groups { id title } } }""", {"b": [BOARD_ID]})["boards"]
    if not b:
        raise SystemExit(f"Board {BOARD_ID} not found")
    b = b[0]
    by_title = {(c["title"], c["type"]): c["id"] for c in b["columns"]}
    col_ids, missing = {}, []
    for title, ctype, _ in COLUMNS:
        if (title, ctype) in by_title:
            col_ids[title] = by_title[(title, ctype)]
        else:
            missing.append(f"{title} ({ctype})")
    if "LCR" not in col_ids:
        raise SystemExit("Board has no text column 'LCR' — dedupe impossible")
    group = next((g["id"] for g in b["groups"] if g["title"] == GROUP_TITLE), None)
    return b["name"], col_ids, missing, group


def existing_lcrs(api, lcr_col):
    fields = 'cursor items { column_values(ids: ["%s"]) { text } }' % lcr_col
    page = api("query ($b: [ID!]) { boards(ids: $b) { items_page(limit: 200) { %s } } }" % fields,
               {"b": [BOARD_ID]})["boards"][0]["items_page"]
    seen = set()
    while True:
        for it in page["items"]:
            for cv in it["column_values"]:
                if cv["text"]:
                    seen.add(cv["text"].strip())
        if not page["cursor"]:
            return seen
        page = api("query ($c: String!) { next_items_page(cursor: $c, limit: 200) { %s } }" % fields,
                   {"c": page["cursor"]})["next_items_page"]


# ── BigQuery ─────────────────────────────────────────────────────────────────

def ensure_report_view(bq):
    bq.query(REPORT_VIEW_SQL.format(p=GCP_PROJECT, d=BQ_DATASET)).result()


def ensure_audit_table(bq):
    table = bigquery.Table(f"{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}", schema=AUDIT_SCHEMA)
    bq.create_table(table, exists_ok=True)


def audited_lcrs(bq):
    q = (f"SELECT DISTINCT lcr FROM `{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}` "
         f"WHERE board_id = @b AND outcome IN ('created', 'partial')")
    job = bq.query(q, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("b", "STRING", BOARD_ID)]))
    return {r.lcr for r in job.result()}


def write_audit(bq, rows):
    if not rows:
        return
    cols = [f.name for f in AUDIT_SCHEMA]
    params, values = [], []
    for i, r in enumerate(rows):
        ph = []
        for c, f in zip(cols, AUDIT_SCHEMA):
            name = f"p{i}_{c}"
            params.append(bigquery.ScalarQueryParameter(name, f.field_type, r.get(c)))
            ph.append(f"@{name}")
        values.append("(" + ", ".join(ph) + ")")
    q = (f"INSERT INTO `{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}` ({', '.join(cols)}) "
         f"VALUES {', '.join(values)}")
    bq.query(q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


# ── Main ─────────────────────────────────────────────────────────────────────

def _run():
    run_id = uuid.uuid4().hex[:12]
    log.info(f"Plex API push {run_id}: {GCP_PROJECT}.{BQ_DATASET}.{VIEW} -> board {BOARD_ID} group '{GROUP_TITLE}'"
             f"{' (DRY RUN)' if DRY_RUN else ''}")
    bq = bigquery.Client(project=GCP_PROJECT)

    # Ensure the report view exists (created from views.sql)
    ensure_report_view(bq)

    if not DRY_RUN:
        ensure_audit_table(bq)

    api = Monday(_secret("MONDAY_API_KEY", "SECRET_MONDAY_API_KEY", "monday-api-key"))

    board_name, col_ids, missing, group_id = resolve_board(api)
    log.info(f"Board '{board_name}': {len(col_ids)}/{len(COLUMNS)} mapped columns")
    for m in missing:
        log.warning(f"Board has no column {m} — skipping")

    rows = [dict(r) for r in bq.query(f"SELECT * FROM `{GCP_PROJECT}.{BQ_DATASET}.{VIEW}`").result()]
    on_board = existing_lcrs(api, col_ids["LCR"])
    try:
        in_audit = audited_lcrs(bq)
    except Exception:
        in_audit = set()

    fresh = []
    for r in rows:
        r["_lcr"] = lcr_hash(r["dedupe_key"])
        if r["_lcr"] in on_board or r["_lcr"] in in_audit:
            continue
        fresh.append(r)
    log.info(f"{len(rows)} row(s) in view, {len(rows) - len(fresh)} already on board, {len(fresh)} new")

    if len(fresh) > MAX_NEW_ITEMS:
        msg = f"ALARM: {len(fresh)} new > MAX_NEW_ITEMS={MAX_NEW_ITEMS}. Nothing pushed."
        log.error(msg)
        return False, msg

    if not fresh:
        return True, f"{len(rows)} rows, 0 new"
    if DRY_RUN:
        for r in fresh:
            log.info(f"  would create: {r.get('part_no')!r} {r['dedupe_key']} lcr={r['_lcr']}")
        return True, f"DRY RUN: {len(fresh)} would be created"

    if not group_id:
        group_id = api("mutation ($b: ID!, $n: String!) { create_group(board_id: $b, group_name: $n) { id } }",
                       {"b": BOARD_ID, "n": GROUP_TITLE})["create_group"]["id"]
        log.info(f"Created group '{GROUP_TITLE}'")

    create = """mutation ($b: ID!, $g: String!, $n: String!, $v: JSON) {
        create_item(board_id: $b, group_id: $g, item_name: $n, column_values: $v,
                    create_labels_if_missing: true) { id } }"""
    change = """mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(
        board_id: $b, item_id: $i, column_values: $v, create_labels_if_missing: true) { id } }"""

    audit, failures = [], 0
    for r in fresh:
        values = {}
        for title, _, build in COLUMNS:
            if title in col_ids:
                v = build(r)
                if v is not None:
                    values[col_ids[title]] = v
        name = ((r.get("part_no") or "").strip()
                or (r.get("line_description") or "").strip()
                or f"(no part) {r.get('order_number')}")
        entry = {"run_id": run_id, "pushed_at": dt.datetime.now(dt.timezone.utc), "board_id": BOARD_ID,
                 "dedupe_key": r["dedupe_key"], "lcr": r["_lcr"], "order_number": r.get("order_number"),
                 "part_no": r.get("part_no"), "column_values": json.dumps(values)}
        try:
            item_id = api(create, {"b": BOARD_ID, "g": group_id, "n": name,
                                   "v": json.dumps(values)})["create_item"]["id"]
            entry.update(monday_item_id=item_id, outcome="created")
        except RuntimeError as whole:
            try:
                lcr_only = {col_ids["LCR"]: r["_lcr"]}
                item_id = api(create, {"b": BOARD_ID, "g": group_id, "n": name,
                                       "v": json.dumps(lcr_only)})["create_item"]["id"]
            except RuntimeError as e:
                entry.update(outcome="failed", detail=str(e)[:1000])
                failures += 1
                log.error(f"FAILED {r['dedupe_key']}: {e}")
                audit.append(entry)
                continue
            lost = []
            for col, v in values.items():
                if col == col_ids["LCR"]:
                    continue
                try:
                    api(change, {"b": BOARD_ID, "i": item_id, "v": json.dumps({col: v})})
                except RuntimeError as e:
                    lost.append(f"{col}: {str(e)[:200]}")
            entry.update(monday_item_id=item_id, outcome="partial" if lost else "created",
                         detail=("; ".join(lost) or str(whole)[:300])[:1000])
            if lost:
                failures += 1
        log.info(f"  created item {entry.get('monday_item_id')} for {r['dedupe_key']}")
        audit.append(entry)

    write_audit(bq, audit)
    created = sum(1 for a in audit if a["outcome"] != "failed")
    summary = f"{created} created, {failures} failed. Audit: {BQ_DATASET}.{AUDIT_TABLE}"
    log.info(summary)
    return failures == 0, summary


@functions_framework.http
def plex_api_push(request):
    """HTTP entry point for Cloud Functions / Cloud Scheduler."""
    ok, summary = _run()
    return (summary, 200 if ok else 500)


if __name__ == "__main__":
    ok, summary = _run()
    print(summary)
    sys.exit(0 if ok else 1)
