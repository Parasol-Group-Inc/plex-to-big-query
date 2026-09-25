#!/usr/bin/env python3
"""Label Design push — `label_design_report` (BigQuery) -> Monday board.

Replaces the Google Sheet + Apps Script hop (deploy/label_design_sync/). Runs
as its own Cloud Run job, scheduled after the Label Design ETL has refreshed
the view:

    python -m label_design_service.push            # in the container
    DRY_RUN=1 python -m label_design_service.push  # show what would be created

ONE ROW, ONE ITEM, ONCE. A row is "already on Monday" when the board holds an
item whose LCR column equals the row's hash — SHA-256 of `dedupe_key`
(order_number|customer_part_no), first 12 lowercase hex chars. No existing
hand-typed LCR is lowercase hex, so a hash can never collide with an old
value. The hash is written INSIDE create_item, so a run that dies straight
after creating an item still leaves the mark that stops the next run
re-creating it. The audit table is checked too, so an LCR someone clears by
hand does not trigger a re-push either.

AUDIT. Every attempt, success or failure, is a row in
`<dataset>.label_design_push_log` (created on first run), written with DML
rather than streaming so test rows can be deleted immediately.

ALARM. More than MAX_NEW_ITEMS new rows in one run means the keys broke, not
that the business had a big day (a real day is single digits to low tens).
Nothing is pushed and the job exits non-zero.

Columns are found by TITLE (and type) at runtime, never by id, so the same
code works on any board shaped like Design & QA. A title the board doesn't
have is skipped and logged, not fatal.

Environment:
    GCP_PROJECT            voxdatalake
    BQ_DATASET             PlexTest | PlexProd
    MONDAY_BOARD_ID        target board
    PLEX_WEB_HOST          Plex UI host for the part/PO links (default: by dataset)
    MONDAY_GROUP_TITLE     group new items land in (created if missing)   [New from Plex]
    MONDAY_API_KEY         token, direct (local runs) ...
    SECRET_MONDAY_API_KEY  ... or its Secret Manager name                 [monday-api-key]
    MAX_NEW_ITEMS          alarm threshold                                 [60]
    DRY_RUN                1 = read everything, write nothing
"""
import datetime as dt
import hashlib
import json
import logging
import os
import sys
import urllib.parse
import uuid

from google.cloud import bigquery

try:  # `python -m label_design_service.push` (container) or run from this folder
    from .monday import Monday
    from .reason_code import REASON_CODE_LABELS, parse_job_note
except ImportError:
    from monday import Monday
    from reason_code import REASON_CODE_LABELS, parse_job_note

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("label_design_push")

GCP_PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
BQ_DATASET = os.environ["BQ_DATASET"]
BOARD_ID = os.environ["MONDAY_BOARD_ID"]
GROUP_TITLE = os.environ.get("MONDAY_GROUP_TITLE", "New from Plex")
MAX_NEW_ITEMS = int(os.environ.get("MAX_NEW_ITEMS", "60"))
DRY_RUN = os.environ.get("DRY_RUN", "") not in ("", "0", "false", "False")
# The browser host, not the ODBC one. Prod is the test host minus ".test".
PLEX_WEB_HOST = os.environ.get("PLEX_WEB_HOST") or (
    "vox.on.plex.com" if BQ_DATASET == "PlexProd" else "vox.test.on.plex.com")

VIEW = "label_design_report"
AUDIT_TABLE = "label_design_push_log"
AUDIT_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("pushed_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("board_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("dedupe_key", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("lcr", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("order_number", "STRING"),
    bigquery.SchemaField("customer_part_no", "STRING"),
    bigquery.SchemaField("monday_item_id", "STRING"),
    bigquery.SchemaField("outcome", "STRING", mode="REQUIRED"),  # created | partial | failed
    bigquery.SchemaField("detail", "STRING"),
    bigquery.SchemaField("column_values", "STRING"),
]


def lcr_hash(dedupe_key):
    return hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:12]


def get_api_key():
    direct = os.environ.get("MONDAY_API_KEY")
    if direct:
        return direct
    from google.cloud import secretmanager
    name = f"projects/{GCP_PROJECT}/secrets/{os.environ.get('SECRET_MONDAY_API_KEY', 'monday-api-key')}/versions/latest"
    return secretmanager.SecretManagerServiceClient().access_secret_version(
        request={"name": name}).payload.data.decode("utf-8").strip()


# ── Row -> Monday values ───────────────────────────────────────────────────
# (board column title, column type, builder(row) -> value or None). Everything
# not listed is left for the team to fill in on the board.

def _text(field):
    return lambda r: (str(r[field]).strip() or None) if r.get(field) not in (None, "") else None


def _sales_order(r):
    s = str(r.get("order_number") or "").strip()
    if not s:
        return None
    # The board's own convention, kept from the Apps Script flow.
    return s if s.lower().startswith("sales order") else f"Sales Order #{s}"


def _date(r):
    d = r.get("order_date")
    return {"date": str(d)[:10]} if d else None


def _email(r):
    e = (r.get("customer_email") or "").strip()
    return {"email": e, "text": e} if e else None


def _label(field):
    return lambda r: {"label": str(r[field]).strip()} if (r.get(field) or "").strip() else None


def _plex_part_url(r):
    key = r.get("part_key")
    if key is None:
        return None
    q = {"__sk": 5, "__sak": 2, "FromPartMenu": "True", "PartKey": key}
    # Plex opens the part from PartKey alone; No/Revision are passed as the
    # part menu itself does, when the part master row is there to supply them.
    if r.get("part_no"):
        q["PartNo"] = r["part_no"]
        q["Revision"] = r.get("part_revision") or ""
    url = f"https://{PLEX_WEB_HOST}/Engineering/Part/ViewForm?" + urllib.parse.urlencode(
        q, quote_via=urllib.parse.quote)
    text = " ".join(str(x).strip() for x in (r.get("part_no"), r.get("part_revision")) if x) or str(key)
    return {"url": url, "text": text}


def _plex_po_url(r):
    key = r.get("po_key")
    if key is None:
        return None
    url = f"https://{PLEX_WEB_HOST}/SalesAndCRM/OrderEntry/ViewOrderForm?POKey={key}"
    return {"url": url, "text": f"SO {r.get('order_number') or key}"}


def _reason_code(r):
    return {"label": REASON_CODE_LABELS[r["_reason_index"]]} if r.get("_reason_index") is not None else None


COLUMNS = [
    ("Customer Name", "text", _text("customer_name")),
    ("Date", "date", _date),
    ("Description", "text", _text("customer_part_description")),
    ("Sales Order", "text", _sales_order),
    ("Memo", "text", _text("_memo")),
    ("Reason Code", "status", _reason_code),
    ("Email", "email", _email),
    ("Phone Number", "text", _text("customer_phone")),
    # `bdm`: the order's Inside Sales, else the customer's Assigned To, else
    # Order_Salesperson — see label_design_view.sql.
    ("Sales Rep", "status", _label("bdm")),
    # The text "Item" column next to Design File (the product), NOT the item
    # name column, which on Design & QA holds the label code the team assigns.
    ("Item", "text", _text("customer_part_no")),
    ("LCR", "text", _text("_lcr")),
    ("Plex Part URL", "link", _plex_part_url),
    ("PO URL", "link", _plex_po_url),
]


# ── Monday reads ───────────────────────────────────────────────────────────

def resolve_board(api):
    b = api("""query ($b: [ID!]) { boards(ids: $b) { name
               columns { id title type } groups { id title } } }""", {"b": [BOARD_ID]})["boards"]
    if not b:
        raise SystemExit(f"Board {BOARD_ID} not found or not visible to this token")
    b = b[0]
    by_title = {(c["title"], c["type"]): c["id"] for c in b["columns"]}
    col_ids, missing = {}, []
    for title, ctype, _ in COLUMNS:
        if (title, ctype) in by_title:
            col_ids[title] = by_title[(title, ctype)]
        else:
            missing.append(f"{title} ({ctype})")
    if "LCR" not in col_ids:
        raise SystemExit("Board has no text column titled 'LCR' — dedupe impossible, refusing to push")
    group = next((g["id"] for g in b["groups"] if g["title"] == GROUP_TITLE), None)
    return b["name"], col_ids, missing, group


def existing_lcrs(api, lcr_col):
    fields = "cursor items { column_values(ids: [\"%s\"]) { text } }" % lcr_col
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


# ── BigQuery ───────────────────────────────────────────────────────────────

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


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    run_id = uuid.uuid4().hex[:12]
    log.info(f"Label Design push {run_id}: {GCP_PROJECT}.{BQ_DATASET}.{VIEW} -> board {BOARD_ID}"
             f"{' (DRY RUN)' if DRY_RUN else ''}")
    bq = bigquery.Client(project=GCP_PROJECT)
    api = Monday(get_api_key())

    board_name, col_ids, missing, group_id = resolve_board(api)
    log.info(f"Board '{board_name}': {len(col_ids)}/{len(COLUMNS)} mapped columns found")
    for m in missing:
        log.warning(f"Board has no column {m} — that field will not be written")

    rows = [dict(r) for r in bq.query(f"SELECT * FROM `{GCP_PROJECT}.{BQ_DATASET}.{VIEW}`").result()]
    if not DRY_RUN:
        ensure_audit_table(bq)
    on_board = existing_lcrs(api, col_ids["LCR"])
    try:
        in_audit = audited_lcrs(bq)
    except Exception as e:  # table absent on a first dry run
        log.info(f"No audit history read ({type(e).__name__}); relying on the board's LCRs")
        in_audit = set()

    fresh = []
    for r in rows:
        r["_lcr"] = lcr_hash(r["dedupe_key"])
        if r["_lcr"] in on_board or r["_lcr"] in in_audit:
            continue
        r["_reason_index"], r["_memo"] = parse_job_note(r.get("job_note"))
        fresh.append(r)
    log.info(f"{len(rows)} row(s) in the view, {len(rows) - len(fresh)} already on the board, "
             f"{len(fresh)} new")

    if len(fresh) > MAX_NEW_ITEMS:
        log.error(f"ALARM: {len(fresh)} new rows exceeds MAX_NEW_ITEMS={MAX_NEW_ITEMS}. The keys have "
                  f"probably changed shape; nothing pushed. Check dedupe_key in {VIEW}.")
        sys.exit(2)

    if not fresh:
        return
    if DRY_RUN:
        for r in fresh:
            log.info(f"  would create: {r.get('customer_part_no')!r}  {r['dedupe_key']}  lcr={r['_lcr']}")
        return

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
        name = (r.get("customer_part_no") or "").strip() or f"(no part #) {r.get('order_number')}"
        entry = {"run_id": run_id, "pushed_at": dt.datetime.now(dt.timezone.utc), "board_id": BOARD_ID,
                 "dedupe_key": r["dedupe_key"], "lcr": r["_lcr"], "order_number": r.get("order_number"),
                 "customer_part_no": r.get("customer_part_no"), "column_values": json.dumps(values)}
        try:
            item_id = api(create, {"b": BOARD_ID, "g": group_id, "n": name, "v": json.dumps(values)})["create_item"]["id"]
            entry.update(monday_item_id=item_id, outcome="created")
        except RuntimeError as whole:
            # One bad value (say, a malformed email) rejects the whole item.
            # Create it with just the LCR — the dedupe mark matters most — then
            # set the rest one column at a time so only the bad value is lost.
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
                    lost.append(f"{col}={json.dumps(v)[:80]}: {str(e)[:200]}")
            entry.update(monday_item_id=item_id, outcome="partial" if lost else "created",
                         detail=("; ".join(lost) or f"retried column-by-column after: {str(whole)[:300]}")[:1000])
            if lost:
                failures += 1
                log.warning(f"PARTIAL {r['dedupe_key']} (item {item_id}): {'; '.join(lost)}")
        log.info(f"  created item {entry['monday_item_id']} for {r['dedupe_key']}")
        audit.append(entry)

    write_audit(bq, audit)
    created = sum(1 for a in audit if a["outcome"] != "failed")
    log.info(f"Done: {created} item(s) created, {failures} with problems. Audit: {BQ_DATASET}.{AUDIT_TABLE}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
