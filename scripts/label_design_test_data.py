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
    python scripts/label_design_test_data.py --check      # grades the LOCAL view SQL, PASS/FAIL per case
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
from urllib.parse import quote

from google.cloud import bigquery

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "label_design_service"))
from monday import Monday  # noqa: E402

PROJECT = "voxdatalake"
DATASET = "PlexTest"
BOARD_ID = "18432111755"
KEY_LO, KEY_HI = 991000000, 992000000
ORDER_PREFIX = "ZZTEST-LD-"
VIEW_SQL = os.path.join(os.path.dirname(__file__), "..", "reports", "sql", "label_design_view.sql")
HOST = "https://vox.test.on.plex.com"
# Monday Reason Code labels by code, as the view spells them (reason_code_label).
REASON_LABELS = {1: "Customer Initiated: Label Edit", 2: "Customer initiated: Label review",
                 3: "New label design (Vox design)", 4: "New label review (Customer design)",
                 5: "Vox Initiated: Label Edit/Review", 6: "3D Rendering"}

# ── The cases ──────────────────────────────────────────────────────────────
# One order per case, each carrying what the view must return for it, so
# `--check` can say PASS/FAIL without anyone eyeballing rows. `expect=None`
# means the view must NOT return the order.
#
# Line fields: cp (customer part no, None = no customer part), part_no /
# revision (None = no Part_v_Part row), notes [(Note_Type, Note)] oldest
# first, due [days from today, one per release].
#
# The Reason Code cases are the old label_design_service/test_reason_code.py
# cases, moved here when the rule moved into the view — plus the ones a bare
# "first character" rule gets wrong on real notes (quantities, decimals).
def L(cp, note=None, notes=None, due=(21,), part_no="ZZTEST-P", revision="Rev 00", **exp):
    return dict(cp=cp, notes=notes if notes is not None else ([("Job_Note", note)] if note is not None else []),
                due=list(due), part_no=part_no, revision=revision, exp=exp)


def N(order, note, code, memo, **kw):
    """A Reason Code / Memo case: one line, one note."""
    return dict(order=order, lines=[L(f"ZZTEST-S{order}", note, reason_code=code, memo=memo)], **kw)


CASES = [
    # Reason Code: a 1-6 first, then an optional separator
    N("1001", "1 Customer wants the new logo on the front panel.", 1, "Customer wants the new logo on the front panel."),
    N("1002", "2 - Review the updated Supplement Facts panel.", 2, "Review the updated Supplement Facts panel."),
    N("1003", "3: Update to current V code. Standard Label.", 3, "Update to current V code. Standard Label."),
    N("1004", "4.Customer supplied artwork", 4, "Customer supplied artwork"),
    N("1005", "5Vox-side edit, barcode to back", 5, "Vox-side edit, barcode to back"),
    N("1006", "6", 6, None),                                     # bare code, no memo
    N("1007", "   1   leading and trailing spaces   ", 1, "leading and trailing spaces"),
    N("1008", "2 line one\nline two", 2, "line one\nline two"),  # multi-line kept
    # No code -> whole note is the Memo, Reason Code stays empty on Monday
    N("1009", "7 Out of range", None, "7 Out of range"),
    N("1010", "0 Zero is not a code", None, "0 Zero is not a code"),
    N("1011", "12ct bottle, new label", None, "12ct bottle, new label"),   # a quantity, not code 1
    N("1012", "3.5 oz jar label", None, "3.5 oz jar label"),              # a decimal, not code 3
    N("1013", "Label Design - White Bopp 3 colors", None, "Label Design - White Bopp 3 colors"),
    N("1014", "", None, None),                                   # empty note
    N("1015", "   ", None, None),                                # blank note
    dict(order="1016", lines=[L("ZZTEST-S1016", notes=[], reason_code=None, memo=None)]),        # no note row at all
    dict(order="1017", lines=[L("ZZTEST-S1017", notes=[("Job_Note", "1 older note"), ("Job_Note", "4 newest note")],
                                reason_code=4, memo="newest note")]),                               # newest wins
    dict(order="1018", lines=[L("ZZTEST-S1018", notes=[("Other_Note", "2 not a job note")],
                                reason_code=None, memo=None)]),                                     # wrong Note_Type

    # Collapse: two releases on one line -> one row, earliest due date
    dict(order="1101", lines=[L("ZZTEST-S1101", "3 two releases", due=(21, 10))]),
    # Two lines with NO customer part number on one order -> two rows, two keys
    dict(order="1102", lines=[L(None, "1 first part, no customer part"), L(None, "2 second part, no customer part")]),
    # Two different customer parts on one order -> two rows
    dict(order="1103", lines=[L("ZZTEST-S1103A", "1 part A"), L("ZZTEST-S1103B", "2 part B")]),

    # Status filters: messy spacing/casing still counts; other statuses don't
    dict(order="1201", release_status="messy", lines=[L("ZZTEST-S1201", "1 messy release status")]),
    dict(order="1202", po_status="messy", lines=[L("ZZTEST-S1202", "1 messy order status")]),
    dict(order="1203", po_status="other", lines=[L("ZZTEST-S1203", "1 order not approved")], expect=None),
    dict(order="1204", release_status="other", lines=[L("ZZTEST-S1204", "1 release not in Label Design")], expect=None),

    # 14-day window on order date (UTC, like CURRENT_DATE())
    dict(order="1301", days_ago=14, lines=[L("ZZTEST-S1301", "1 exactly 14 days old")]),
    dict(order="1302", days_ago=15, lines=[L("ZZTEST-S1302", "1 15 days old")], expect=None),

    # Part URL encoding, and a part with no Part_v_Part row
    dict(order="1401", lines=[L("ZZTEST-S1401", "1 special characters", part_no="ZZTEST 100&A/B#1+2=%", revision="Rev 00")]),
    dict(order="1402", lines=[L("ZZTEST-S1402", "1 no Part_v_Part row", part_no=None, revision=None)]),

    # Sales Rep (`bdm`) = the order's Inside Salesperson, else the customer's
    # Assigned To, else Order_Salesperson Sort_Order 1. Sort_Order 2 is exposed
    # (sales_rep_secondary) but never becomes the bdm.
    dict(order="1501", reps=dict(inside="Ashley Quintana", assigned="Tyler Hall", primary="Kami Butcher"),
         lines=[L("ZZTEST-S1501", "1 order rep wins over customer and salesperson")]),
    dict(order="1502", reps=dict(assigned="Tyler Hall", primary="Kami Butcher"),
         lines=[L("ZZTEST-S1502", "1 no order rep -> customer's Assigned To")]),
    dict(order="1503", reps=dict(primary="Kami Butcher"),
         lines=[L("ZZTEST-S1503", "1 only the salesperson table")]),
    dict(order="1504", reps={}, lines=[L("ZZTEST-S1504", "1 no rep anywhere -> Sales Rep left blank")]),
    dict(order="1505", reps=dict(secondary="Julianni Pacheco"),
         lines=[L("ZZTEST-S1505", "1 only a secondary salesperson -> still no Sales Rep")]),
]
CUSTOMER = ("ZZTEST Sample Nutrition Co", "labels@example.com", "555-0101")
# REAL Plexus users, looked up by name at run time (never injected), so the
# Monday Sales Rep column shows names the board already has. Cases without
# `reps` get one of these as the order's Inside Salesperson, in rotation.
REP_NAMES = ["Ashley Quintana", "Tyler Hall", "Kami Butcher", "Julianni Pacheco"]

TABLES = {  # table -> key column the delete predicate uses
    "raw_Sales_v_PO": "PO_Key",
    "raw_Sales_v_PO_Line": "PO_Line_Key",
    "raw_Sales_v_Release": "Release_Key",
    "raw_Sales_v_PO_Line_Note": "PO_Line_Note_Key",
    "raw_Part_v_Customer_Part": "Customer_Part_Key",
    "raw_Part_v_Part": "Part_Key",
    "raw_Common_v_Customer": "Customer_No",
    "raw_Sales_v_Order_Salesperson": "PO_Key",
    "raw_Plexus_Control_v_Plexus_User": "Plexus_User_No",
    # Two injected statuses each: a messy-spaced/cased copy of the real one,
    # and one the view must reject.
    "raw_Sales_v_Release_Status": "Release_Status_Key",
    "raw_Sales_v_PO_Status": "PO_Status_Key",
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
            if v is None:  # an untyped NULL fits any column; a NULL STRING param doesn't fit INT64
                ph.append("NULL")
                continue
            t = "INT64" if isinstance(v, int) else "STRING"
            params.append(bigquery.ScalarQueryParameter(f"p{i}_{c}", t, v))
            ph.append(f"@p{i}_{c}")
        tuples.append("(" + ", ".join(ph) + ")")
    bq.query(f"INSERT INTO {fq(table)} ({', '.join(cols)}) VALUES {', '.join(tuples)}",
             job_config=bigquery.QueryJobConfig(query_parameters=params)).result()
    return len(rows)


def ns(d):
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp()) * 1_000_000_000


def utc_today():
    # The view's window is CURRENT_DATE(), which is UTC. A local date here
    # would move the 14/15-day boundary cases by a day in the evening.
    return dt.datetime.now(dt.timezone.utc).date()


def resolve_statuses(bq):
    """name -> (table, column, key, value). The 'real' ones are Plex's own rows."""
    pending = status_key(bq, "raw_Sales_v_PO_Status", "PO_Status", "Pending Fulfillment")
    label_design = status_key(bq, "raw_Sales_v_Release_Status", "Release_Status", "Label Design")
    rel, po = ("raw_Sales_v_Release_Status", "Release_Status"), ("raw_Sales_v_PO_Status", "PO_Status")
    return {
        "rel_real": (*rel, label_design, "Label Design"),
        "rel_messy": (*rel, KEY_LO + 1, "  label DESIGN "),
        "rel_other": (*rel, KEY_LO + 2, "ZZTEST Not Label Design"),
        "po_real": (*po, pending, "Pending Fulfillment"),
        "po_messy": (*po, KEY_LO + 1, " pending FULFILLMENT  "),
        "po_other": (*po, KEY_LO + 2, "ZZTEST Not Approved"),
    }


def resolve_reps(bq):
    """Rep name -> real Plexus_User_No, from PlexTest's own user table."""
    rows = bq.query(
        f"SELECT CONCAT(First_Name, ' ', Last_Name) name, ANY_VALUE(SAFE_CAST(Plexus_User_No AS INT64)) uno "
        f"FROM {fq('raw_Plexus_Control_v_Plexus_User')} WHERE CONCAT(First_Name, ' ', Last_Name) IN UNNEST(@n) "
        f"GROUP BY 1", job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ArrayQueryParameter("n", "STRING", REP_NAMES)])).result()
    found = {r.name: r.uno for r in rows}
    missing = [n for n in REP_NAMES if n not in found]
    if missing:
        raise SystemExit(f"Not in {DATASET} raw_Plexus_Control_v_Plexus_User: {missing} — edit REP_NAMES")
    return found


def pcn_of(bq):
    rows = list(bq.query(f"SELECT ANY_VALUE(PCN) pcn FROM {fq('raw_Sales_v_PO')}").result())
    return int(rows[0].pcn) if rows and rows[0].pcn is not None else None


def build(pcn, statuses, today, rep_nos):
    """Every row to insert, the expected view rows keyed by (order, part_key),
    and the orders the view must leave out. Keys are deterministic, so
    --check rebuilds the same expectations without storing anything."""
    data = {t: [] for t in TABLES}
    expected, absent = {}, []
    # One customer with no Assigned To, plus one per rep used as Assigned To.
    customers = {}

    def customer(assigned):
        if assigned not in customers:
            no = KEY_LO + 1 + len(customers)
            customers[assigned] = no
            data["raw_Common_v_Customer"].append(dict(
                Customer_No=no, Customer_Code=f"ZZTEST-LD-C{len(customers) - 1}", Name=CUSTOMER[0],
                Email=CUSTOMER[1], Phone=CUSTOMER[2], Customer_Status="Active",
                Assigned_To=rep_nos[assigned] if assigned else None))
        return customers[assigned]

    for table, col, key, value in statuses.values():
        if KEY_LO <= key < KEY_HI:
            data[table].append({f"{col}_Key": key, col: value})

    k = KEY_LO + 1000
    for i, case in enumerate(CASES):
        order = f"{ORDER_PREFIX}{case['order']}"
        po_no = f"ZZTEST-PO-{case['order']}"
        reps = case.get("reps", dict(inside=REP_NAMES[i % len(REP_NAMES)]))
        cust_no = customer(reps.get("assigned"))
        k += 1
        po_key, days = k, case.get("days_ago", 1)
        data["raw_Sales_v_PO"].append(dict(
            PCN=pcn, PO_Key=po_key, Customer_No=cust_no, PO_No=po_no,
            PO_Status_Key=statuses["po_" + case.get("po_status", "real")][2],
            PO_Date=ns(today - dt.timedelta(days=days)), Order_No=order,
            Inside_Sales=rep_nos[reps["inside"]] if "inside" in reps else None))
        for sort_order, role in ((1, "primary"), (2, "secondary")):
            if role in reps:
                data["raw_Sales_v_Order_Salesperson"].append(dict(
                    PCN=pcn, PO_Key=po_key, Plexus_User_No=rep_nos[reps[role]], Sort_Order=sort_order))
        excluded = "expect" in case and case["expect"] is None
        if excluded:
            absent.append(order)
        for line in case["lines"]:
            k += 1
            line_key, cp = k, line["cp"]
            if cp is not None:
                data["raw_Part_v_Customer_Part"].append(dict(
                    Customer_Part_Key=line_key, Part_Key=line_key, Customer_No=cust_no, Customer_Part_No=cp,
                    Customer_Part_Description=f"ZZTEST description {case['order']}", Active=1))
            if line["part_no"] is not None:
                data["raw_Part_v_Part"].append(dict(Part_Key=line_key, Part_No=line["part_no"], Revision=line["revision"]))
            data["raw_Sales_v_PO_Line"].append(dict(
                PCN=pcn, PO_Line_Key=line_key, PO_Key=po_key, Part_Key=line_key,
                Customer_Part_Key=line_key if cp is not None else None, Line_No=str(line_key - KEY_LO), Active=1))
            for d in line["due"]:
                k += 1
                data["raw_Sales_v_Release"].append(dict(
                    PCN=pcn, Release_Key=k, Release_No=f"ZZTEST-R{k - KEY_LO}", PO_Line_Key=line_key,
                    Due_Date=ns(today + dt.timedelta(days=d)),
                    Release_Status_Key=statuses["rel_" + case.get("release_status", "real")][2]))
            for note_type, note in line["notes"]:
                k += 1
                data["raw_Sales_v_PO_Line_Note"].append(dict(
                    PCN=pcn, PO_Line_Note_Key=k, PO_Line_Key=line_key, Note_Type=note_type, Note=note))
            if excluded:
                continue
            e = dict(
                customer_po=po_no, order_date=str(today - dt.timedelta(days=days)),
                customer_part_no=cp, part_no=line["part_no"], part_revision=line["revision"], po_key=po_key,
                due_date=str(today + dt.timedelta(days=min(line["due"]))), release_count=len(line["due"]),
                dedupe_key=f"{order}|{cp if cp is not None else f'PK{line_key}'}",
                # quote(safe='') is an independent encoder, so this also checks the SQL's hand-rolled one
                part_url=(f"{HOST}/Engineering/Part/ViewForm?__sk=5&__sak=2&FromPartMenu=True&PartKey={line_key}"
                          f"&PartNo={quote(line['part_no'] or '', safe='')}"
                          f"&Revision={quote(line['revision'] or '', safe='')}"),
                customer_po_url=f"{HOST}/SalesAndCRM/SalesOrders/PoFormView?OriginLocation=SalesOrders&POKey={po_key}",
                sales_order_url=f"{HOST}/SalesAndCRM/OrderEntry/ViewOrderForm?POKey={po_key}",
                sales_rep_inside=reps.get("inside"), customer_account_rep=reps.get("assigned"),
                sales_rep_primary=reps.get("primary"), sales_rep_secondary=reps.get("secondary"),
                bdm=reps.get("inside") or reps.get("assigned") or reps.get("primary"))
            # Only cases that state a reason_code grade the label; the structural
            # cases (1101+) test other things and leave their note's code alone.
            if "reason_code" in line["exp"]:
                e["reason_code_label"] = REASON_LABELS.get(line["exp"]["reason_code"])
            e.update(line["exp"])
            expected[(order, line_key)] = e
    return data, expected, absent


def inject(bq):
    data, expected, absent = build(pcn_of(bq), resolve_statuses(bq), utc_today(), resolve_reps(bq))
    for t, rows in data.items():
        if rows:
            print(f"  {t}: +{insert(bq, t, rows)}")
    print(f"  {len(CASES)} cases: {len(expected)} row(s) the view should return, {len(absent)} order(s) it must not")
    print("  Next: --check (grades the LOCAL view SQL, no deploy needed)")


def check(bq):
    """Run the LOCAL reports/sql/label_design_view.sql against PlexTest and grade every case."""
    sql = open(VIEW_SQL, encoding="utf-8").read().replace("{gcp_project}", PROJECT).replace("{dataset}", DATASET)
    got = {(r["order_number"], r["part_key"]): dict(r) for r in bq.query(
        f"SELECT * FROM ({sql}) WHERE STARTS_WITH(order_number, '{ORDER_PREFIX}')").result()}
    if not got:
        raise SystemExit("No test rows returned. Run --inject first (any Label Design / Sales Orders test ETL run wipes them).")
    _, expected, absent = build(pcn_of(bq), resolve_statuses(bq), utc_today(), resolve_reps(bq))
    passed = failed = 0
    for key, e in expected.items():
        r = got.get(key)
        bad = ["missing from the view"] if r is None else [
            f"{c}: got {r.get(c)!r}, want {v!r}" for c, v in e.items()
            if (str(r[c]) if c in ("order_date", "due_date") and r.get(c) is not None else r.get(c)) != v]
        print(f"  {'FAIL' if bad else 'PASS'}  {key[0]}  {e['customer_part_no'] or '(no customer part)'}"
              + "".join(f"\n          {b}" for b in bad))
        passed, failed = passed + (not bad), failed + bool(bad)
    for order in absent:
        leaked = any(k[0] == order for k in got)
        print(f"  {'FAIL' if leaked else 'PASS'}  {order}  excluded" + ("  <- but the view returned it" if leaked else ""))
        passed, failed = passed + (not leaked), failed + leaked
    for k in got:
        if k not in expected and k[0] not in absent:
            print(f"  FAIL  unexpected row {k}")
            failed += 1
    print(f"\n  {passed} passed, {failed} failed")
    if failed:
        sys.exit(1)


def status(bq, api):
    for t, col in TABLES.items():
        n = list(bq.query(f"SELECT COUNT(*) n FROM {fq(t)} WHERE {col} >= {KEY_LO} AND {col} < {KEY_HI}").result())[0].n
        print(f"  {t}: {n} test row(s)")
    v = list(bq.query(f"SELECT COUNT(*) n FROM {fq('label_design_report')} "
                      f"WHERE order_number LIKE '{ORDER_PREFIX}%'").result())[0].n
    print(f"  label_design_report (the DEPLOYED view): {v} test row(s) visible")
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
    g.add_argument("--check", action="store_true", help="grade the LOCAL view SQL against the injected cases")
    args = ap.parse_args()
    assert DATASET == "PlexTest", "this tool only ever writes to PlexTest"

    bq = bigquery.Client(project=PROJECT)
    if args.inject:
        existing = list(bq.query(f"SELECT COUNT(*) n FROM {fq('raw_Sales_v_PO')} "
                                 f"WHERE PO_Key >= {KEY_LO} AND PO_Key < {KEY_HI}").result())[0].n
        if existing:
            raise SystemExit(f"{existing} test order(s) already injected — run --delete first")
        inject(bq)
    elif args.check:
        check(bq)
    elif args.delete:
        delete(bq, Monday(monday_key()))
    else:
        status(bq, Monday(monday_key()))


if __name__ == "__main__":
    main()
