#!/usr/bin/env python3
"""Load live Plex screens into BigQuery while ODBC and SQL Development are stale.

    python scripts/plex_live_screens.py                    # fetch, check, print totals; writes nothing
    python scripts/plex_live_screens.py --load             # also replace the live_* tables
    python scripts/plex_live_screens.py --load --only releases   # one screen (revenue, history, releases)

Runbook, design and recovery: docs/PLEX_SCREEN_EXTRACTION.md.

Since 2026-11-04 ~18:56 Plex time, ODBC and the SQL Development Environment read
a copy of the data that stopped updating, while Plex's own screens read live
data. This logs into Plex (PLEX_PORTAL_USERNAME / PLEX_PORTAL_PASSWORD, from the
environment or the repo's .env) with headless Chromium (Playwright) and reads
the same JSON each screen draws its grid from.

Screens (each one -> one BigQuery table, replaced whole on every run):

  revenue   Shipping Revenue by Part Group (Shipping/ShippingRevenueByPartGroupReport)
            -> PlexProd.live_shipping_revenue, one row per invoiced shipper line.
            The screen returns one row per line PER GL ACCOUNT (40200-01-01 carries
            the amount; October lines also have a 41000-01-01 row at $0), with
            Revenue repeated on each, so rows are collapsed back to one per line and
            the account amounts kept in `gl_amounts`. Summing the raw rows doubles
            October. Fetched one calendar month at a time: a long range is capped at
            500 rows and repeats lines. A month that returns 500 rows fails the screen.

  history   Shipper History (VisionPlex actionKey 6776)
            -> PlexProd.live_shipper_history, one row per shipped shipper line (no
            prices: join live_shipping_revenue on shipper_no + part_no for dollars).
            The screen flags RecordLimitExceeded; a flagged month fails the screen.

  releases  Sales Orders (SalesAndCRM/OrderEntry) + each order's Rapid Entry line page
            -> PlexProd.live_order_releases, one row per RELEASE of every Pending
            Fulfillment order dated 2026-10-18 or later, with its status, priority,
            due date and Job Note. `label_design_report` reads it (see
            reports/sql/label_design_view.sql, "Live source"). Two steps:
              1. the Order Entry search (POST .../SearchJobShopOrder), status Pending
                 Fulfillment, one month of order dates per request: one row per order
                 line with the order header (order no, PO, customer, order date);
              2. GET .../OrderLineRapidEntry?PoKey=<k> for each order: the page embeds
                 its grid as `plex.parsing.parseJSON('...')`, one row per release with
                 POLineKey, ReleaseKey, ReleaseStatusKey, PriorityKey, DueDate, PartKey,
                 CustomerPartKey and JobNote. The Line Items page (OrderLineEntry) has
                 the status text but no Job Note, so Rapid Entry is the one used.
            Release status arrives as a key; it is named from
            PlexProd.raw_Sales_v_Release_Status, and a key not in that table fails the
            screen (a new status must be looked at, not guessed).

Safety (details in the runbook):
  - One run at a time: a lock file shared with plex_web_export.py (etl-manual/plex_web.lock).
  - Each screen succeeds or fails on its own; a failed screen writes nothing, its table
    keeps the previous load, and the run exits 1.
  - Page reads retry 3 times and log in again if Plex sent the login page.
  - A screen whose row count falls below its floor versus the current table is not
    loaded (`--force` overrides): revenue/history 90%, releases 50%.
  - Before the first replace of each Denver day, the table is copied to
    Backups.PlexProd__<table>_<yyyymmdd> (expires in 7 days). Within a day, BigQuery
    time travel (FOR SYSTEM_TIME AS OF) recovers any earlier hourly load.

Writes use Application Default Credentials. The ETL never touches these tables, and
nothing here touches a table the ETL writes, so the two cannot collide.
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from google.cloud import bigquery
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plex_web_export import creds, login, run_lock  # noqa: E402

PROJECT = "voxdatalake"
DEN = ZoneInfo("America/Denver")
BASE = "https://vox.on.plex.com"
START = dt.date(2026, 10, 1)  # Plex go-live (cutover 2026-10-19); nothing earlier
CAP = 500
BACKUP_DAYS = 7


def utc_midnight(d):
    """Plex sends local midnight as UTC, e.g. 2026-11-01T06:00:00.000Z."""
    return dt.datetime(d.year, d.month, d.day, tzinfo=DEN).astimezone(dt.timezone.utc) \
        .strftime("%Y-%m-%dT%H:%M:%S.000Z")


def den_date(s):
    """A Plex UTC timestamp string ('2026-11-13T07:00:00Z') -> its Mountain-time date."""
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(DEN).date().isoformat()


def months(start, end):
    d = start
    while d <= end:
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield d, min(nxt, end + dt.timedelta(days=1))
        d = nxt


def schema(cols):
    return [bigquery.SchemaField(n, t) for n, t in cols]


# ── Shipping Revenue by Part Group ──────────────────────────────────────────────

REVENUE_TABLE = f"{PROJECT}.PlexProd.live_shipping_revenue"
REVENUE_SCHEMA = schema([
    ("invoice_date", "DATE"), ("invoice_no", "STRING"), ("invoice_link", "INT64"),
    ("shipper_no", "STRING"), ("order_no", "STRING"), ("po_no", "STRING"), ("po_key", "INT64"),
    ("customer_code", "STRING"), ("customer_no", "INT64"), ("customer_part_no", "STRING"),
    ("part_no", "STRING"), ("revision", "STRING"), ("part_key", "INT64"), ("part_type", "STRING"),
    ("part_group", "STRING"), ("part_group_key", "INT64"), ("product_group", "STRING"),
    ("quantity", "FLOAT64"), ("net_unit_price", "FLOAT64"), ("revenue", "FLOAT64"),
    ("gl_amounts", "STRING"), ("outside_salesperson", "STRING"), ("region", "STRING"),
    ("city", "STRING"), ("state", "STRING"), ("loaded_at", "TIMESTAMP"),
])
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


def fetch_revenue(pg, today, ctx):
    url = f"{BASE}/Shipping/ShippingRevenueByPartGroupReport/"
    pg.goto(url + "Index", wait_until="networkidle", timeout=90000)
    out = []
    for beg, end in months(START, today):
        r = post_json(pg, url + "Search", ctx, f"Shipping Revenue {beg:%Y-%m}", {
            "Security": False, "ShowSubTotals": False, "CommissionReporting": True,
            "InvoiceDateBegin": utc_midnight(beg), "InvoiceDateEnd": utc_midnight(end),
            "PCN": 0, "SortBy": "5"})
        rows = r["Data"]["Rows"]
        if len(rows) >= CAP:
            raise RuntimeError(f"Shipping Revenue {beg:%Y-%m}: {len(rows)} rows, at the screen's cap")
        lines = {}
        for x in rows:
            key = tuple(sorted((k, str(v)) for k, v in x.items() if k not in PER_ACCOUNT))
            if key not in lines:
                o = {col: x.get(k) for k, col in FIELDS.items()}
                o["invoice_date"] = den_date(x["InvoiceDate"])
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
    print(f"  total {len(out)} lines, last invoice {max((o['invoice_no'] or '' for o in out), default='-')}")
    return out


# ── Shipper History ─────────────────────────────────────────────────────────────

HISTORY_TABLE = f"{PROJECT}.PlexProd.live_shipper_history"
HISTORY_SCHEMA = schema([
    ("ship_date", "DATE"), ("ship_time", "TIMESTAMP"), ("shipper_no", "STRING"), ("shipper_key", "INT64"),
    ("shipper_line_key", "INT64"), ("shipper_status", "STRING"), ("customer_code", "STRING"),
    ("part_no_revision", "STRING"), ("order_no", "STRING"), ("order_line_no", "STRING"),
    ("po_key", "INT64"), ("po_line_key", "INT64"), ("release_key", "INT64"), ("quantity", "FLOAT64"),
    ("container_net_weight", "FLOAT64"), ("ship_name", "STRING"), ("carrier", "STRING"),
    ("loaded_at", "TIMESTAMP"),
])
HISTORY_FIELDS = {
    "ShipperNo": "shipper_no", "ShipperKey": "shipper_key", "ShipperLineKey": "shipper_line_key",
    "ShipperStatus": "shipper_status", "CustomerCode": "customer_code", "PartNo": "part_no_revision",
    "OrderNo": "order_no", "OrderLineNo": "order_line_no", "POKey": "po_key", "POLineKey": "po_line_key",
    "ReleaseKey": "release_key", "Quantity": "quantity", "ContainerNetWeight": "container_net_weight",
    "ShipName": "ship_name", "CarrierText": "carrier",
}


def fetch_history(pg, today, ctx):
    pg.goto(f"{BASE}/VisionPlex/screen/Index?__actionKey=6776", wait_until="networkidle", timeout=90000)
    url = f"{BASE}/api/MetaDataSource/2kLwnSjUa3C0DB9c5Qibkw?limit=true&sourceActionKey=6776"
    out, seen = [], set()
    for beg, end in months(START, today):
        data = post_json(pg, url, ctx, f"Shipper History {beg:%Y-%m}", [
            {"PCN": 338756, "ShipDateStart": utc_midnight(beg), "ShipDateEnd": utc_midnight(end)}])["Data"]
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
            out.append(o)
        print(f"  {beg:%Y-%m}: {len(data['Rows'])} shipped lines")
    print(f"  total {len(out)} lines, last shipper {max((o['shipper_no'] or '' for o in out), default='-')}")
    return out


# ── Sales order releases (Label Design) ─────────────────────────────────────────

RELEASES_TABLE = f"{PROJECT}.PlexProd.live_order_releases"
RELEASES_SCHEMA = schema([
    # order header, from the Order Entry search
    ("po_key", "INT64"), ("order_no", "STRING"), ("po_no", "STRING"), ("order_date", "DATE"),
    ("po_status", "STRING"), ("customer_no", "INT64"), ("customer_code", "STRING"),
    ("customer_name", "STRING"), ("inside_sales", "STRING"),
    # one release, from the order's Rapid Entry page
    ("po_line_key", "INT64"), ("release_key", "INT64"), ("release_status_key", "INT64"),
    ("release_status", "STRING"), ("priority_key", "INT64"), ("due_date", "DATE"),
    ("quantity", "FLOAT64"), ("part_key", "INT64"), ("part_no_revision", "STRING"),
    ("part_no", "STRING"), ("part_revision", "STRING"), ("part_name", "STRING"),
    ("customer_part_key", "INT64"), ("customer_part_no_revision", "STRING"),
    ("job_note", "STRING"), ("loaded_at", "TIMESTAMP"),
])
# Same floor as label_design_view.sql: nothing ordered before the cutover weekend.
RELEASES_START = dt.date(2026, 10, 18)
PENDING_FULFILLMENT = "2073"  # POStatusKey of "Pending Fulfillment" (checked against the search's own list)
SEARCH_URL = f"{BASE}/SalesAndCRM/OrderEntry/SearchJobShopOrder?limit=true&sourceActionKey=9925"
# The Order Entry screen's own search body, captured from a click on Search with only the
# Status filter set (Pending Fulfillment). Order dates are filled in per month below; the
# screen refuses a search with no filter at all.
SEARCH_BODY = {
    "Subtotal": "0", "UseTypeDorpdown": True, "WarehouseCustomerNo": 0, "WarehouseShipTo": 0,
    "UserBuildingKey": 0, "PartLinkExists": False, "IsWarehouseCustomer": False, "IsActiveOnly": 1,
    "AccountingJobKey": 0, "ActiveOnly": 1, "BuildingKey": 0, "CreditCardOnly": False,
    "CustomerAddressNo": 0, "CustomerParentKey": 0, "FreightTermsKey": 0, "ITAR": 0,
    "NewMRROnly": False, "OrderAddBy": 0, "PartOfContract": False, "PCN": 0, "PIELines": False,
    "PIELinesNotPriced": False, "POStatusKey": PENDING_FULFILLMENT, "ProductTypeKey": 0, "PUN": 0,
    "RecurringRevenueType": -1, "RegionKey": 0, "SortBy": 0,
}
MODEL_RE = re.compile(r"plex\.parsing\.parseJSON\('((?:[^'\\]|\\.)*)'")


def page_models(html):
    """The JSON a classic Plex page embeds as plex.parsing.parseJSON('<JS string>', ...)."""
    out = []
    for m in MODEL_RE.finditer(html):
        s = m.group(1).replace("\\'", "'")  # JS allows \' ; JSON does not
        out.append(json.loads(json.loads('"' + s + '"')))
    return out


def rapid_rows(o):
    """Every release row in a Rapid Entry page model (a dict with JobNote and a ReleaseKey)."""
    if isinstance(o, dict):
        if "JobNote" in o and o.get("ReleaseKey"):
            yield o
        for v in o.values():
            yield from rapid_rows(v)
    elif isinstance(o, list):
        for v in o:
            yield from rapid_rows(v)


def release_statuses(ctx):
    rows = ctx["bq"]().query(
        f"SELECT SAFE_CAST(Release_Status_Key AS INT64) k, Release_Status s "
        f"FROM `{PROJECT}.PlexProd.raw_Sales_v_Release_Status`").result()
    names = {r.k: r.s for r in rows}
    if not names:
        raise RuntimeError("raw_Sales_v_Release_Status is empty; cannot name release statuses")
    return names


def fetch_releases(pg, today, ctx):
    statuses = release_statuses(ctx)
    pg.goto(f"{BASE}/SalesAndCRM/OrderEntry", wait_until="networkidle", timeout=120000)
    orders, parts = {}, {}
    for beg, end in months(RELEASES_START, today):
        data = post_json(pg, SEARCH_URL, ctx, f"Order Entry search {beg:%Y-%m}",
                         {**SEARCH_BODY, "OrderBeginDate": utc_midnight(beg), "OrderEndDate": utc_midnight(end)})["Data"]
        if data.get("RecordLimitExceeded"):
            raise RuntimeError(f"Order Entry search {beg:%Y-%m}: record limit exceeded")
        for x in data["Rows"]:
            if x["POStatus"] != "Pending Fulfillment":
                raise RuntimeError(f"Order Entry search returned order {x['OrderNo']} in status {x['POStatus']!r}")
            orders[x["POKey"]] = {
                "po_key": x["POKey"], "order_no": x["OrderNo"], "po_no": x["PONo"],
                "order_date": den_date(x["PODate"]), "po_status": x["POStatus"],
                "customer_no": x["CustomerNo"], "customer_code": x["CustomerCode"],
                "customer_name": x["CustomerName"], "inside_sales": (x.get("InsideSales") or "").strip() or None}
            if x.get("PartKey"):
                parts[x["PartKey"]] = (x.get("PartNo"), x.get("Revision"), x.get("PartName"))
        print(f"  {beg:%Y-%m}: {len(data['Rows'])} order lines")
    out, unknown = [], set()
    for i, (k, hdr) in enumerate(sorted(orders.items())):
        rel = {}
        for x in get_rows(pg, f"{BASE}/SalesAndCRM/OrderLineRapidEntry?PoKey={k}", ctx, f"order {hdr['order_no']}"):
            rel.setdefault(x["ReleaseKey"], x)  # the page carries each row in two models
        for x in rel.values():
            sk = x.get("ReleaseStatusKey")
            if sk not in statuses:
                unknown.add(sk)
            pn = parts.get(x.get("PartKey"), (None, None, None))
            out.append({**hdr,
                        "po_line_key": x["POLineKey"], "release_key": x["ReleaseKey"],
                        "release_status_key": sk, "release_status": statuses.get(sk),
                        "priority_key": x.get("PriorityKey") or None, "due_date": den_date(x.get("DueDate")),
                        "quantity": x.get("Quantity"), "part_key": x.get("PartKey") or None,
                        "part_no_revision": x.get("PartNoRevision"), "part_no": pn[0],
                        "part_revision": pn[1], "part_name": pn[2],
                        "customer_part_key": x.get("CustomerPartKey") or None,
                        "customer_part_no_revision": x.get("CustomerPartNoRevision") or None,
                        "job_note": x.get("JobNote") or None})
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(orders)} orders read")
    if unknown:
        raise RuntimeError(f"release status key(s) {sorted(unknown, key=str)} not in raw_Sales_v_Release_Status")
    keys = [o["release_key"] for o in out]
    if len(keys) != len(set(keys)):
        raise RuntimeError("a release key appears on two orders' pages")
    counts = {}
    for o in out:
        counts[o["release_status"]] = counts.get(o["release_status"], 0) + 1
    print(f"  total {len(orders)} orders, {len(out)} releases: "
          + ", ".join(f"{s} {n}" for s, n in sorted(counts.items(), key=lambda kv: -kv[1])))
    return out


# ── Plex requests with retry and re-login ───────────────────────────────────────

def _relogin(pg, ctx, what, why):
    print(f"  {what}: {why}; logging in again")
    login(pg, *ctx["creds"])


def post_json(pg, url, ctx, what, body, tries=3):
    for n in range(1, tries + 1):
        try:
            r = pg.request.post(url, data=body, timeout=300000)
            if r.status == 200 and "json" in (r.headers.get("content-type") or ""):
                return r.json()
            if "accounts.plex.com" in r.url or r.status in (401, 403):
                _relogin(pg, ctx, what, f"HTTP {r.status}, session ended")
            elif n == tries:
                raise RuntimeError(f"{what}: HTTP {r.status} {r.headers.get('content-type')}")
        except RuntimeError:
            raise
        except Exception as e:  # network / timeout
            if n == tries:
                raise RuntimeError(f"{what}: {str(e).splitlines()[0][:200]}") from None
            print(f"  {what}: attempt {n} failed ({str(e).splitlines()[0][:120]})")
        time.sleep(5 * n)
    raise RuntimeError(f"{what}: no answer after {tries} attempts")


def get_rows(pg, url, ctx, what, tries=3):
    """Release rows from a classic Plex page; a page with no model or no rows is retried."""
    for n in range(1, tries + 1):
        try:
            r = pg.request.get(url, timeout=120000)
            if "accounts.plex.com" in r.url:
                _relogin(pg, ctx, what, "Plex sent the login page")
            elif r.status != 200:
                print(f"  {what}: attempt {n}: HTTP {r.status}")
            else:
                rows = [x for m in page_models(r.text()) for x in rapid_rows(m)]
                if rows:
                    return rows
                print(f"  {what}: attempt {n}: page had no release rows")
        except Exception as e:
            print(f"  {what}: attempt {n} failed ({str(e).splitlines()[0][:120]})")
        time.sleep(5 * n)
    raise RuntimeError(f"{what}: no release rows after {tries} attempts ({url.split('/')[-1]})")


# ── Load ────────────────────────────────────────────────────────────────────────

SCREENS = {  # name: (title, fetch, table, schema, minimum share of the current table's rows)
    "revenue": ("Shipping Revenue by Part Group", fetch_revenue, REVENUE_TABLE, REVENUE_SCHEMA, 0.9),
    "history": ("Shipper History", fetch_history, HISTORY_TABLE, HISTORY_SCHEMA, 0.9),
    "releases": ("Sales order releases (Label Design)", fetch_releases, RELEASES_TABLE, RELEASES_SCHEMA, 0.5),
}


def current_rows(c, table):
    try:
        return c.get_table(table).num_rows
    except Exception:  # not created yet
        return None


def backup_once_a_day(c, table, today):
    """Copy the table to Backups before its first replace of the (Denver) day."""
    name = table.split(".")[-1]
    bak = f"{PROJECT}.Backups.PlexProd__{name}_{today:%Y%m%d}"
    try:
        c.get_table(bak)
        return None  # today's copy exists; time travel covers the hours since
    except Exception:
        pass
    c.copy_table(table, bak).result()
    t = c.get_table(bak)
    t.expires = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=BACKUP_DAYS)
    c.update_table(t, ["expires"])
    return bak


def load(c, table, rows, sch, floor, force, today):
    have = current_rows(c, table)
    if have and not force and len(rows) < floor * have:
        raise RuntimeError(f"{len(rows)} rows is under {floor:.0%} of the {have} now in {table}; "
                           f"not loaded (rerun with --force if the drop is real)")
    bak = backup_once_a_day(c, table, today) if have is not None else None
    c.load_table_from_json(rows, table, job_config=bigquery.LoadJobConfig(
        schema=sch, write_disposition="WRITE_TRUNCATE")).result()
    n = c.get_table(table).num_rows
    if n != len(rows):
        raise RuntimeError(f"{table} has {n} rows after the load, expected {len(rows)}")
    return f"{table} replaced: {n} rows (was {have})" + (f"; backup {bak}" if bak else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", action="store_true", help="replace the live_* tables in BigQuery")
    ap.add_argument("--only", help="comma-separated screens: " + ", ".join(SCREENS))
    ap.add_argument("--force", action="store_true", help="load even if a table would shrink past its floor")
    args = ap.parse_args()
    names = args.only.split(",") if args.only else list(SCREENS)
    bad = [n for n in names if n not in SCREENS]
    if bad:
        sys.exit(f"unknown screen(s) {bad}; choose from {list(SCREENS)}")
    today = dt.datetime.now(DEN).date()
    started = dt.datetime.now(dt.timezone.utc)
    client = {}

    def bq():  # created on first use, so a dry run of revenue/history needs no BigQuery login
        if "c" not in client:
            client["c"] = bigquery.Client(project=PROJECT)
        return client["c"]

    ctx = {"creds": creds(), "bq": bq}
    failed, fetched = {}, {}
    with run_lock(), sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context().new_page()
        login(pg, *ctx["creds"])
        for n in names:
            title = SCREENS[n][0]
            print(f"{title}")
            try:
                rows = SCREENS[n][1](pg, today, ctx)
                loaded_at = started.isoformat()
                for o in rows:
                    o["loaded_at"] = loaded_at
                fetched[n] = rows
            except Exception as e:  # one screen must not stop the others
                failed[n] = str(e).splitlines()[0][:300]
                print(f"  FAILED: {failed[n]}")
        b.close()
    if args.load:
        c = ctx["bq"]()
        for n, rows in fetched.items():
            _, _, table, sch, floor = SCREENS[n]
            try:
                print(load(c, table, rows, sch, floor, args.force, today))
            except Exception as e:
                failed[n] = str(e).splitlines()[0][:300]
                print(f"{table}: NOT LOADED: {failed[n]}")
    took = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
    print(f"done in {took:.0f}s: {len(names) - len(failed)}/{len(names)} screens ok"
          + (f"; FAILED {failed}" if failed else "") + ("" if args.load else " (dry run, nothing written)"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
