#!/usr/bin/env python3
"""Load live Plex screens into BigQuery while ODBC and SQL Development are stale.

    python scripts/plex_live_screens.py             # fetch, check, print totals; writes nothing
    python scripts/plex_live_screens.py --load      # also replace the live_* tables

Since 2026-11-04 ~18:56 Plex time, ODBC and the SQL Development Environment read
a copy of the data that stopped updating, while Plex's own screens read live
data. This logs into Plex (PLEX_PORTAL_USERNAME / PLEX_PORTAL_PASSWORD, from the
environment or the repo's .env) with headless Chromium and calls each screen's
own Search request, the JSON the screen's grid is drawn from.

Screens:
  Shipping Revenue by Part Group (Shipping/ShippingRevenueByPartGroupReport)
    -> PlexProd.live_shipping_revenue, one row per invoiced shipper line.
    The screen returns one row per line PER GL ACCOUNT (40200-01-01 carries the
    amount; October lines also have a 41000-01-01 row at $0), with Revenue
    repeated on each, so rows are collapsed back to one per line and the account
    amounts kept in `gl_amounts`. Summing the raw rows doubles October.
    It is fetched one calendar month at a time: a long range is capped at 500
    rows and repeats lines. A month that returns 500 rows fails the run.

  Shipper History (VisionPlex actionKey 6776)
    -> PlexProd.live_shipper_history, one row per shipped shipper line (no
    prices: join live_shipping_revenue on shipper_no + part_no for dollars).
    The screen flags RecordLimitExceeded; a flagged month fails the run.

Each run replaces the whole table (go-live 2026-10-01 to today), so reruns are
safe, and a failed fetch writes nothing. Writes use Application Default
Credentials. These tables are not touched by the ETL.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from google.cloud import bigquery
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plex_web_export import creds, login  # noqa: E402

PROJECT = "voxdatalake"
DEN = ZoneInfo("America/Denver")
BASE = "https://vox.on.plex.com"
START = dt.date(2026, 10, 1)  # Plex go-live (cutover 2026-10-19); nothing earlier
CAP = 500

REVENUE_TABLE = f"{PROJECT}.PlexProd.live_shipping_revenue"
REVENUE_SCHEMA = [
    bigquery.SchemaField(n, t) for n, t in [
        ("invoice_date", "DATE"), ("invoice_no", "STRING"), ("invoice_link", "INT64"),
        ("shipper_no", "STRING"), ("order_no", "STRING"), ("po_no", "STRING"), ("po_key", "INT64"),
        ("customer_code", "STRING"), ("customer_no", "INT64"), ("customer_part_no", "STRING"),
        ("part_no", "STRING"), ("revision", "STRING"), ("part_key", "INT64"), ("part_type", "STRING"),
        ("part_group", "STRING"), ("part_group_key", "INT64"), ("product_group", "STRING"),
        ("quantity", "FLOAT64"), ("net_unit_price", "FLOAT64"), ("revenue", "FLOAT64"),
        ("gl_amounts", "STRING"), ("outside_salesperson", "STRING"), ("region", "STRING"),
        ("city", "STRING"), ("state", "STRING"), ("loaded_at", "TIMESTAMP"),
    ]
]
FIELDS = {  # screen JSON -> column
    "InvoiceNo": "invoice_no", "InvoiceLink": "invoice_link", "ARInvoiceReferenceNo": "shipper_no",
    "OrderNo": "order_no", "PONo": "po_no", "POKey": "po_key", "CustomerCode": "customer_code",
    "CustomerNo": "customer_no", "CustomerPartNo": "customer_part_no", "PartNo": "part_no",
    "Revision": "revision", "PartKey": "part_key", "PartType": "part_type", "PartGroup": "part_group",
    "PartGroupKey": "part_group_key", "PartProductGroup": "product_group", "Quantity": "quantity",
    "NetUnitPrice": "net_unit_price", "Revenue": "revenue", "OutsideSalesperson": "outside_salesperson",
    "Region": "region", "City": "city", "State": "state",
}
PER_ACCOUNT = {"AccountNo", "Amount", "UniqueGroupIndex"}


def utc_midnight(d):
    """Plex sends local midnight as UTC, e.g. 2026-11-01T06:00:00.000Z."""
    return dt.datetime(d.year, d.month, d.day, tzinfo=DEN).astimezone(dt.timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%S.000Z")


def months(start, end):
    d = start
    while d <= end:
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield d, min(nxt, end + dt.timedelta(days=1))
        d = nxt


def fetch_revenue(pg, today):
    url = f"{BASE}/Shipping/ShippingRevenueByPartGroupReport/"
    pg.goto(url + "Index", wait_until="networkidle", timeout=90000)
    loaded_at = dt.datetime.now(dt.timezone.utc).isoformat()
    out = []
    for beg, end in months(START, today):
        r = pg.request.post(url + "Search", timeout=300000, data={
            "Security": False, "ShowSubTotals": False, "CommissionReporting": True,
            "InvoiceDateBegin": utc_midnight(beg), "InvoiceDateEnd": utc_midnight(end),
            "PCN": 0, "SortBy": "5"})
        if r.status != 200:
            raise RuntimeError(f"Shipping Revenue {beg:%Y-%m}: HTTP {r.status}")
        rows = r.json()["Data"]["Rows"]
        if len(rows) >= CAP:
            raise RuntimeError(f"Shipping Revenue {beg:%Y-%m}: {len(rows)} rows, at the screen's cap")
        lines = {}
        for x in rows:
            key = tuple(sorted((k, str(v)) for k, v in x.items() if k not in PER_ACCOUNT))
            if key not in lines:
                o = {col: x.get(k) for k, col in FIELDS.items()}
                o["invoice_date"] = dt.datetime.fromisoformat(x["InvoiceDate"].replace("Z", "+00:00")) \
                    .astimezone(DEN).date().isoformat()
                o["loaded_at"] = loaded_at
                o["_gl"] = {}
                lines[key] = o
            gl = lines[key]["_gl"]
            if x["AccountNo"] in gl:  # the same line and account twice: not a GL split
                raise RuntimeError(f"Shipping Revenue {beg:%Y-%m}: repeated row {x['InvoiceNo']} {x['AccountNo']}")
            gl[x["AccountNo"]] = x["Amount"]
        for o in lines.values():
            o["gl_amounts"] = "; ".join(f"{k}: {v}" for k, v in sorted(o.pop("_gl").items()))
            out.append(o)
        print(f"  {beg:%Y-%m}: {len(rows)} screen rows -> {len(lines)} lines, "
              f"revenue {sum(o['revenue'] or 0 for o in lines.values()):,.2f}")
    return out


HISTORY_TABLE = f"{PROJECT}.PlexProd.live_shipper_history"
HISTORY_SCHEMA = [
    bigquery.SchemaField(n, t) for n, t in [
        ("ship_date", "DATE"), ("ship_time", "TIMESTAMP"), ("shipper_no", "STRING"), ("shipper_key", "INT64"),
        ("shipper_line_key", "INT64"), ("shipper_status", "STRING"), ("customer_code", "STRING"),
        ("part_no_revision", "STRING"), ("order_no", "STRING"), ("order_line_no", "STRING"),
        ("po_key", "INT64"), ("po_line_key", "INT64"), ("release_key", "INT64"), ("quantity", "FLOAT64"),
        ("container_net_weight", "FLOAT64"), ("ship_name", "STRING"), ("carrier", "STRING"),
        ("loaded_at", "TIMESTAMP"),
    ]
]
HISTORY_FIELDS = {
    "ShipperNo": "shipper_no", "ShipperKey": "shipper_key", "ShipperLineKey": "shipper_line_key",
    "ShipperStatus": "shipper_status", "CustomerCode": "customer_code", "PartNo": "part_no_revision",
    "OrderNo": "order_no", "OrderLineNo": "order_line_no", "POKey": "po_key", "POLineKey": "po_line_key",
    "ReleaseKey": "release_key", "Quantity": "quantity", "ContainerNetWeight": "container_net_weight",
    "ShipName": "ship_name", "CarrierText": "carrier",
}


def fetch_history(pg, today):
    pg.goto(f"{BASE}/VisionPlex/screen/Index?__actionKey=6776", wait_until="networkidle", timeout=90000)
    url = f"{BASE}/api/MetaDataSource/2kLwnSjUa3C0DB9c5Qibkw?limit=true&sourceActionKey=6776"
    loaded_at = dt.datetime.now(dt.timezone.utc).isoformat()
    out, seen = [], set()
    for beg, end in months(START, today):
        r = pg.request.post(url, timeout=300000, data=[
            {"PCN": 338756, "ShipDateStart": utc_midnight(beg), "ShipDateEnd": utc_midnight(end)}])
        if r.status != 200:
            raise RuntimeError(f"Shipper History {beg:%Y-%m}: HTTP {r.status}")
        data = r.json()["Data"]
        if data.get("RecordLimitExceeded"):
            raise RuntimeError(f"Shipper History {beg:%Y-%m}: record limit exceeded")
        for x in data["Rows"]:
            if x["ShipperLineKey"] in seen:
                raise RuntimeError(f"Shipper History: line {x['ShipperLineKey']} returned twice")
            seen.add(x["ShipperLineKey"])
            o = {col: x.get(k) for k, col in HISTORY_FIELDS.items()}
            t = dt.datetime.fromisoformat(x["ShipDate"].replace("Z", "+00:00"))
            o["ship_time"], o["ship_date"] = t.isoformat(), t.astimezone(DEN).date().isoformat()
            o["carrier"] = o["carrier"] or None
            o["loaded_at"] = loaded_at
            out.append(o)
        print(f"  {beg:%Y-%m}: {len(data['Rows'])} shipped lines")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", action="store_true", help="replace the live_* tables in BigQuery")
    args = ap.parse_args()
    today = dt.datetime.now(DEN).date()
    user, password = creds()
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context().new_page()
        login(pg, user, password)
        print("Shipping Revenue by Part Group")
        revenue = fetch_revenue(pg, today)
        print(f"  total {len(revenue)} lines, last invoice {max(o['invoice_no'] or '' for o in revenue)}")
        print("Shipper History")
        history = fetch_history(pg, today)
        print(f"  total {len(history)} lines, last shipper {max(o['shipper_no'] or '' for o in history)}")
        b.close()
    if not args.load:
        return
    c = bigquery.Client(project=PROJECT)
    for table, rows, schema in [(REVENUE_TABLE, revenue, REVENUE_SCHEMA), (HISTORY_TABLE, history, HISTORY_SCHEMA)]:
        c.load_table_from_json(rows, table, job_config=bigquery.LoadJobConfig(
            schema=schema, write_disposition="WRITE_TRUNCATE")).result()
        print(f"{table} replaced: {c.get_table(table).num_rows} rows")


if __name__ == "__main__":
    main()
