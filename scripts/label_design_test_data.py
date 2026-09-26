#!/usr/bin/env python3
"""
Label Design test data — inject on demand, delete on demand, PlexTest only.
===========================================================================

Plex test has no release in "Label Design" status, so `label_design_report`
is empty and the Monday push has nothing to push. This puts a handful of
marked orders into the PlexTest raw tables so the view returns them, the push
can be run end to end, and Ashley can see what a Plex-created item looks like
on the board.

    python scripts/label_design_test_data.py --status
    python scripts/label_design_test_data.py --inject
    python scripts/label_design_test_data.py --delete     # BigQuery rows AND Monday items

Then run the push against PlexTest (see label_design_service/push.py).

HOW REMOVAL IS GUARANTEED — by marks, not by memory:
  - every injected BigQuery row has a key in [991000000, 992000000). Plex keys
    come nowhere near it, and the scorecard injector (scripts/
    scorecard_test_data.py) uses 990000000+ in different tables, so neither
    tool's delete can touch the other's rows.
  - every order number starts "ZZTEST-LD-". On Monday that shows up in the
    Sales Order column ("Sales Order #ZZTEST-LD-1001"), which is how --delete
    finds the items again even with the audit table gone. Audit rows for those
    orders are deleted too.

LINKS (2026-09-26). Each line points at a REAL Plex test part (a 93… finished
good from raw_Part_v_Part), so the "Plex Part URL" column opens a real part
page. That is safe for --delete, which matches Customer_Part_Key / PO_Line_Key,
never Part_Key. The orders stay fake (PO_Key 991…), so "PO URL" opens an order
that doesn't exist in Plex. The link's shape is right; the order is not real.

The rows are NOT realistic business data — shaped to satisfy the view's joins
and filters, nothing more. They also don't last: every Label Design / Sales
Orders test ETL run (WRITE_TRUNCATE) and the nightly Plex-test wipe replace the
raw tables. Items already pushed to Monday stay until --delete.

REFUSES TO TOUCH PlexProd. Rows go in with INSERT DML, not streaming, so
--delete works immediately (streamed rows are DML-locked for up to 90 min).
"""
import argparse
import datetime as dt
import os
import sys

from google.cloud import bigquery

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "label_design_service"))
from monday import Monday  # noqa: E402

PROJECT = "voxdatalake"
DATASET = "PlexTest"
BOARD_ID = "18432111755"
KEY_LO, KEY_HI = 991000000, 992000000
ORDER_PREFIX = "ZZTEST-LD-"

# (order, part, customer, job note) — one per Reason Code 1-6, a note with no
# code, and one order carrying two parts (two Monday items, same order).
ORDERS = [
    ("1001", "ZZTEST-S1001", 0, "1 Customer wants the new logo on the front panel."),
    ("1002", "ZZTEST-S1002", 1, "2 Review the customer's updated Supplement Facts panel."),
    ("1003", "ZZTEST-S1003", 2, "3 Update to current V code. Standard Label."),
    ("1004", "ZZTEST-S1004", 0, "4 Customer supplied artwork, needs review."),
    ("1004", "ZZTEST-S1005", 0, "5 Vox-side edit: move the barcode to the back panel."),
    ("1005", "ZZTEST-S1006", 1, "6 3D rendering for the sales deck."),
    ("1006", "ZZTEST-S1007", 2, "Label Design - White Bopp"),
]
CUSTOMERS = [
    ("ZZTEST Sample Nutrition Co", "labels@example.com", "555-0101"),
    ("ZZTEST Peak Wellness LLC", "design@example.com", "555-0102"),
    ("ZZTEST Green Leaf Labs", "orders@example.com", "555-0103"),
]
DESCRIPTIONS = {
    "ZZTEST-S1001": "ZZTEST Creatine Powder 300g - Standard Label",
    "ZZTEST-S1002": "ZZTEST Magnesium Glycinate 120ct - 250cc White HDPE",
    "ZZTEST-S1003": "ZZTEST Whey Protein Vanilla 2lb - V3R0 Template",
    "ZZTEST-S1004": "ZZTEST Ashwagandha 60ct - Customer Artwork",
    "ZZTEST-S1005": "ZZTEST Ashwagandha 90ct - Customer Artwork",
    "ZZTEST-S1006": "ZZTEST Collagen Peptides 450g - Pouch",
    "ZZTEST-S1007": "ZZTEST Vitamin D3 K2 60ct - White Bopp",
}
# user_name in the view is CONCAT(First, ' ', Last) -> "Test " -> the push
# strips it to "Test", which is a Sales Rep label the board already has.
REP = ("Test", "")

TABLES = {  # table -> key column the delete predicate uses
    "raw_Sales_v_PO": "PO_Key",
    "raw_Sales_v_PO_Line": "PO_Line_Key",
    "raw_Sales_v_Release": "Release_Key",
    "raw_Sales_v_PO_Line_Note": "PO_Line_Note_Key",
    "raw_Part_v_Customer_Part": "Customer_Part_Key",
    "raw_Common_v_Customer": "Customer_No",
    "raw_Sales_v_Order_Salesperson": "PO_Key",
    "raw_Plexus_Control_v_Plexus_User": "Plexus_User_No",
}


def fq(t):
    return f"`{PROJECT}.{DATASET}.{t}`"


def monday_key():
    if os.environ.get("MONDAY_API_KEY"):
        return os.environ["MONDAY_API_KEY"]
    env = os.path.join(os.path.dirname(__file__), "..", ".env")
    for line in open(env, encoding="utf-8"):
        if line.startswith("MONDAY_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("MONDAY_API_KEY not set and not in .env")


def status_key(bq, table, col, name):
    rows = list(bq.query(f"SELECT {col}_Key k FROM {fq(table)} WHERE {col} = '{name}' LIMIT 1").result())
    if not rows:
        raise SystemExit(f"{table} has no '{name}' status in {DATASET} — can't make rows the view accepts")
    return int(rows[0].k)


def insert(bq, table, rows):
    cols = sorted({c for r in rows for c in r})
    params, tuples = [], []
    for i, r in enumerate(rows):
        ph = []
        for c in cols:
            v = r.get(c)
            t = "INT64" if isinstance(v, int) else "STRING"
            params.append(bigquery.ScalarQueryParameter(f"p{i}_{c}", t, v))
            ph.append(f"@p{i}_{c}")
        tuples.append("(" + ", ".join(ph) + ")")
    bq.query(f"INSERT INTO {fq(table)} ({', '.join(cols)}) VALUES {', '.join(tuples)}",
             job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    return len(rows)


def ns(d):
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp()) * 1_000_000_000


def inject(bq):
    pcn_rows = list(bq.query(f"SELECT ANY_VALUE(PCN) pcn FROM {fq('raw_Sales_v_PO')}").result())
    pcn = int(pcn_rows[0].pcn) if pcn_rows and pcn_rows[0].pcn is not None else None
    pending = status_key(bq, "raw_Sales_v_PO_Status", "PO_Status", "Pending Fulfillment")
    label_design = status_key(bq, "raw_Sales_v_Release_Status", "Release_Status", "Label Design")
    today = dt.date.today()
    user_no = KEY_LO
    parts = [int(r.k) for r in bq.query(
        f"SELECT SAFE_CAST(Part_Key AS INT64) k FROM {fq('raw_Part_v_Part')} "
        f"WHERE Part_No LIKE '93%' AND Revision IS NOT NULL "
        f"ORDER BY k DESC LIMIT {len(ORDERS)}").result()]
    if len(parts) < len(ORDERS):
        raise SystemExit(f"raw_Part_v_Part has only {len(parts)} usable 93… part(s) in {DATASET} — "
                         f"run the Label Design test ETL first")

    data = {t: [] for t in TABLES}
    data["raw_Plexus_Control_v_Plexus_User"].append(
        dict(Plexus_User_No=user_no, First_Name=REP[0], Last_Name=REP[1], User_ID="zztest.ld.rep", Active=1))
    for c, (name, email, phone) in enumerate(CUSTOMERS):
        data["raw_Common_v_Customer"].append(dict(
            Customer_No=KEY_LO + c, Customer_Code=f"ZZTEST-LD-C{c}", Name=name, Email=email,
            Phone=phone, Customer_Status="Active"))

    orders_seen = {}
    for n, (order, part, cust, note) in enumerate(ORDERS, start=1):
        po_key = KEY_LO + int(order)
        if order not in orders_seen:
            orders_seen[order] = True
            order_date = today - dt.timedelta(days=len(orders_seen))
            data["raw_Sales_v_PO"].append(dict(
                PCN=pcn, PO_Key=po_key, Customer_No=KEY_LO + cust, PO_No=f"ZZTEST-PO-{order}",
                PO_Status_Key=pending, PO_Date=ns(order_date), Order_No=f"{ORDER_PREFIX}{order}"))
            data["raw_Sales_v_Order_Salesperson"].append(dict(
                PCN=pcn, PO_Key=po_key, Plexus_User_No=user_no, Sort_Order=1))
        key = KEY_LO + n
        part_key = parts[n - 1]
        data["raw_Part_v_Customer_Part"].append(dict(
            Customer_Part_Key=key, Part_Key=part_key, Customer_No=KEY_LO + cust, Customer_Part_No=part,
            Customer_Part_Description=DESCRIPTIONS[part], Active=1))
        data["raw_Sales_v_PO_Line"].append(dict(
            PCN=pcn, PO_Line_Key=key, PO_Key=po_key, Part_Key=part_key, Customer_Part_Key=key,
            Line_No=str(n), Active=1))
        data["raw_Sales_v_Release"].append(dict(
            PCN=pcn, Release_Key=key, Release_No=f"ZZTEST-R{n}", PO_Line_Key=key,
            Due_Date=ns(today + dt.timedelta(days=21)), Release_Status_Key=label_design))
        data["raw_Sales_v_PO_Line_Note"].append(dict(
            PCN=pcn, PO_Line_Note_Key=key, PO_Line_Key=key, Note_Type="Job_Note", Note=note))

    for t, rows in data.items():
        print(f"  {t}: +{insert(bq, t, rows)}")
    status(bq, None)


def status(bq, api):
    for t, col in TABLES.items():
        n = list(bq.query(f"SELECT COUNT(*) n FROM {fq(t)} WHERE {col} >= {KEY_LO} AND {col} < {KEY_HI}").result())[0].n
        print(f"  {t}: {n} test row(s)")
    v = list(bq.query(f"SELECT COUNT(*) n FROM {fq('label_design_report')} "
                      f"WHERE order_number LIKE '{ORDER_PREFIX}%'").result())[0].n
    print(f"  label_design_report: {v} test row(s) visible")
    if api:
        print(f"  Monday board {BOARD_ID}: {len(test_items(api))} test item(s)")


def test_items(api):
    b = api("query ($b: [ID!]) { boards(ids: $b) { columns { id title type } } }", {"b": [BOARD_ID]})["boards"][0]
    so = next(c["id"] for c in b["columns"] if c["title"] == "Sales Order" and c["type"] == "text")
    fields = 'cursor items { id name column_values(ids: ["%s"]) { text } }' % so
    page = api("query ($b: [ID!]) { boards(ids: $b) { items_page(limit: 200) { %s } } }" % fields,
               {"b": [BOARD_ID]})["boards"][0]["items_page"]
    found = []
    while True:
        found += [i for i in page["items"] if ORDER_PREFIX in (i["column_values"][0]["text"] or "")]
        if not page["cursor"]:
            return found
        page = api("query ($c: String!) { next_items_page(cursor: $c, limit: 200) { %s } }" % fields,
                   {"c": page["cursor"]})["next_items_page"]


def delete(bq, api):
    items = test_items(api)
    for i in items:
        api("mutation ($i: ID!) { delete_item(item_id: $i) { id } }", {"i": i["id"]})
    print(f"  Monday: deleted {len(items)} item(s)")
    for t, col in TABLES.items():
        j = bq.query(f"DELETE FROM {fq(t)} WHERE {col} >= {KEY_LO} AND {col} < {KEY_HI}")
        j.result()
        print(f"  {t}: -{j.num_dml_affected_rows or 0}")
    try:
        j = bq.query(f"DELETE FROM {fq('label_design_push_log')} WHERE order_number LIKE '{ORDER_PREFIX}%'")
        j.result()
        print(f"  label_design_push_log: -{j.num_dml_affected_rows or 0}")
    except Exception as e:
        print(f"  label_design_push_log: not cleaned ({type(e).__name__}: {str(e)[:120]})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true")
    g.add_argument("--delete", action="store_true")
    g.add_argument("--status", action="store_true")
    args = ap.parse_args()
    assert DATASET == "PlexTest", "this tool only ever writes to PlexTest"

    bq = bigquery.Client(project=PROJECT)
    if args.inject:
        existing = list(bq.query(f"SELECT COUNT(*) n FROM {fq('raw_Sales_v_PO')} "
                                 f"WHERE PO_Key >= {KEY_LO} AND PO_Key < {KEY_HI}").result())[0].n
        if existing:
            raise SystemExit(f"{existing} test order(s) already injected — run --delete first")
        inject(bq)
    elif args.delete:
        delete(bq, Monday(monday_key()))
    else:
        status(bq, Monday(monday_key()))


if __name__ == "__main__":
    main()
