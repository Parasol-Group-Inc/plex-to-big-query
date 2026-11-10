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

Monday push: after a good releases load (with --load, unless --no-push) this starts
the Label Design push job, but only Mon-Fri 5:00-17:50 MT, only while the ETL is not
reaching Plex itself, only when label_design_report reads the live table, and never
while a push is still running. See maybe_start_push().

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


def half_months(start, end):
    """1st-15th and 16th-end windows: a whole month reached the revenue screen's
    500-row cap (two GL rows per line) in mid-November 2026."""
    for beg, nxt in months(start, end):
        mid = beg.replace(day=16) if beg.day < 16 else None
        if mid and mid < nxt:
            yield beg, mid
            yield mid, nxt
        else:
            yield beg, nxt


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
    out, seen_windows = [], {}
    for beg, end in half_months(START, today):
        r = post_json(pg, url + "Search", ctx, f"Shipping Revenue {beg:%Y-%m-%d}", {
            "Security": False, "ShowSubTotals": False, "CommissionReporting": True,
            "InvoiceDateBegin": utc_midnight(beg), "InvoiceDateEnd": utc_midnight(end),
            "PCN": 0, "SortBy": "5"})
        rows = r["Data"]["Rows"]
        if len(rows) >= CAP:
            raise RuntimeError(f"Shipping Revenue {beg:%Y-%m}: {len(rows)} rows, at the screen's cap")
        lines = {}
        for x in rows:
            key = tuple(sorted((k, str(v)) for k, v in x.items() if k not in PER_ACCOUNT))
            if seen_windows.get(key, beg) != beg:
                continue  # an end date Plex treats as inclusive: already read in the previous window
            seen_windows[key] = beg
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
        print(f"  {beg:%Y-%m-%d}: {len(rows)} screen rows -> {len(lines)} lines, "
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


# ── Production records (Job Production Report + Production History) ────────────

PRODUCTION_TABLE = f"{PROJECT}.PlexProd.live_production"
PRODUCTION_SCHEMA = schema([
    ("production_no", "INT64"), ("record_date", "DATE"), ("record_time", "TIMESTAMP"),
    ("report_date", "DATE"), ("shift", "STRING"), ("job_no", "STRING"), ("op_no", "INT64"),
    ("operation_code", "STRING"), ("part_no", "STRING"), ("revision", "STRING"),
    ("workcenter_code", "STRING"), ("serial_no", "STRING"), ("quantity", "FLOAT64"),
    ("rejected", "INT64"), ("employee", "STRING"), ("employee_last_name", "STRING"),
    ("product_type", "STRING"), ("price", "FLOAT64"), ("fetched_at", "TIMESTAMP"),
    ("loaded_at", "TIMESTAMP"),
])
# raw_Part_v_Production is complete through 11-03, and the merge view
# (reports/sql/part_production_current_view.sql) takes ODBC rows before this date.
PRODUCTION_START = dt.date(2026, 11, 1)
PRODUCTION_RECENT_DAYS = 3  # re-read every hour; older days once a Denver day (first run)
JOBS_URL = f"{BASE}/api/MetaDataSource/jpBWrHptieaF_6xmHXP5-w?limit=true&sourceActionKey=6571"
PH_URL = f"{BASE}/ProductionTracking/ProductionHistory/"
PRODUCTION_CAP = 1000


def workcenters(ctx):
    rows = ctx["bq"]().query(
        f"SELECT TRIM(Workcenter_Code) code, SAFE_CAST(Workcenter_Key AS INT64) k "
        f"FROM `{PROJECT}.PlexProd.raw_Part_v_Workcenter`").result()
    wc = {r.code: r.k for r in rows if r.code}
    if not wc:
        raise RuntimeError("raw_Part_v_Workcenter is empty; cannot split a capped day by workcenter")
    return wc


def capped_day(what, ask, wc, by):
    """One day's rows. Both screens stop at 1,000 rows and filter only by whole day,
    so a day at the cap is read again one workcenter at a time (`by` maps a
    workcenter code to the screen's filter). Fails rather than loading a short day."""
    rows, lim = ask({})
    if not lim:
        return rows
    unknown = {x["WorkcenterCode"] for x in rows} - set(wc)
    if unknown:
        raise RuntimeError(f"{what}: workcenter(s) {sorted(unknown)} not in raw_Part_v_Workcenter")
    out = {}
    for code in wc:
        part, lim = ask(by(code))
        if lim:
            raise RuntimeError(f"{what}: workcenter {code} alone is at the {PRODUCTION_CAP}-row cap")
        for x in part:  # the filter matches by prefix: "Blending 5" also returns "Blending 5a"
            if x["WorkcenterCode"] == code:
                out[x["ProductionNo"]] = x
    missing = [x["ProductionNo"] for x in rows if x["ProductionNo"] not in out]
    if missing:
        raise RuntimeError(f"{what}: {len(missing)} record(s) of the capped read missing per workcenter")
    return list(out.values())


def fetch_production(pg, today, ctx):
    """Every production record from PRODUCTION_START, one row per Production_No.

    Job Production Report (VisionPlex 6571; filters on RECORD date, Mountain) is the
    master: it has the rejected flag, op no and revision. Production History (filters
    on REPORT date) adds the employee's full name; 6571 has only the last name, and 17
    of 60 recording users share one. Both matched raw_Part_v_Production record for
    record on 11-02/03 (checked 2026-11-06: job, op, part, workcenter, rejected and
    quantity on every record; full name = First_Name Last_Name).

    Days before the last PRODUCTION_RECENT_DAYS are read on the first run of each
    Denver day and otherwise kept from the current table, so hourly runs stay short."""
    wc = workcenters(ctx)
    c = ctx["bq"]()
    kept, first_run = [], True
    if ctx.get("production_begin"):  # screen_recon.py: a rolling window, independent of live_production
        return _production_read(pg, today, ctx, wc, ctx["production_begin"], [])
    try:
        last = list(c.query(f"SELECT MAX(loaded_at) t FROM `{PRODUCTION_TABLE}`").result())[0].t
        first_run = last is None or last.astimezone(DEN).date() != today
    except Exception:  # table not created yet
        pass
    begin = PRODUCTION_START
    if not first_run:
        begin = max(PRODUCTION_START, today - dt.timedelta(days=PRODUCTION_RECENT_DAYS - 1))
        for r in c.query(
                f"SELECT * EXCEPT (loaded_at) FROM `{PRODUCTION_TABLE}` WHERE record_date < @d",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("d", "DATE", begin)])).result():
            kept.append({k: v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v
                         for k, v in dict(r).items()})
    print(f"  {'all days' if first_run else 'recent days'} from {begin}; keeping {len(kept)} older rows")
    return _production_read(pg, today, ctx, wc, begin, kept)


def _production_read(pg, today, ctx, wc, begin, kept):

    # Neither screen's day filter is the record date in Mountain time (6571 asked for
    # 11-01 returned 11-02's records: the DST change). So read every day from the day
    # before `begin` to tomorrow, de-duplicate by Production_No, and keep records by
    # their own record date.
    pg.goto(f"{BASE}/VisionPlex/screen/Index?__actionKey=6571", wait_until="networkidle", timeout=120000)
    jobs = {}
    d = begin - dt.timedelta(days=1)
    while d <= today + dt.timedelta(days=1):
        def ask(f, d=d):
            r = post_json(pg, JOBS_URL, ctx, f"Job Production {d}", [
                {"DateBegin": utc_midnight(d), "DateEnd": utc_midnight(d), "PCN": 338756, **f}])["Data"]
            return r["Rows"], r.get("RecordLimitExceeded")
        rows = capped_day(f"Job Production {d}", ask, wc, lambda code: {"WorkcenterCode": code})
        for x in rows:
            if jobs.get(x["ProductionNo"], x) != x:
                raise RuntimeError(f"Job Production: record {x['ProductionNo']} differs between two days' reads")
            jobs[x["ProductionNo"]] = x
        print(f"  read {d}: {len(rows)} records")
        d += dt.timedelta(days=1)

    pg.goto(PH_URL + "Index", wait_until="networkidle", timeout=120000)
    names = {}
    d = begin - dt.timedelta(days=2)  # a record's report date can be the day before its record date
    while d <= today + dt.timedelta(days=1):
        def ask(f, d=d):
            r = post_json(pg, PH_URL + "SearchProductionHistoryGrid?limit=true&sourceActionKey=13891", ctx,
                          f"Production History {d}",
                          {"StartDate": utc_midnight(d), "EndDate": utc_midnight(d), "PCN": 0, **f})["Data"]
            return r["Rows"], r.get("RecordLimitExceeded")
        for x in capped_day(f"Production History {d}", ask, wc, lambda code: {"WorkcenterKey": wc[code]}):
            names[x["ProductionNo"]] = x
        d += dt.timedelta(days=1)

    fetched = dt.datetime.now(dt.timezone.utc).isoformat()
    out = []
    for k, x in jobs.items():
        h = names.get(k, {})
        t = dt.datetime.fromisoformat(x["RecordDate"].replace("Z", "+00:00"))
        if t.astimezone(DEN).date() < begin:
            continue  # an older day: kept from the table, or before PRODUCTION_START
        out.append({
            "production_no": k, "record_date": t.astimezone(DEN).date().isoformat(),
            "record_time": t.isoformat(), "report_date": den_date(h.get("ReportDate")),
            "shift": x.get("Shift"), "job_no": x.get("JobNo"), "op_no": x.get("OpNo"),
            "operation_code": x.get("OperationCode"), "part_no": x.get("PartNo"),
            "revision": x.get("Revision"), "workcenter_code": x.get("WorkcenterCode"),
            "serial_no": x.get("TrackingNo"), "quantity": x.get("Quantity"),
            "rejected": x.get("Rejected"), "employee": h.get("Employee"),
            "employee_last_name": x.get("Employee"), "product_type": x.get("ProductType"),
            "price": x.get("Price"), "fetched_at": fetched})
    no_name = sum(1 for o in out if o["employee"] is None)
    if no_name > 0.02 * len(out) + 5:  # only records entered between the two reads may lack one
        raise RuntimeError(f"{no_name} of {len(out)} records have no Production History match")
    days = {}
    for o in out:
        n, q = days.get(o["record_date"], (0, 0.0))
        days[o["record_date"]] = (n + 1, q + (o["quantity"] or 0))
    for k in sorted(days):
        print(f"  {k}: {days[k][0]} records, quantity {days[k][1]:,.2f}")
    print(f"  total {len(out)} read + {len(kept)} kept; {no_name} without a full employee name")
    return kept + out


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
                models = page_models(r.text())
                rows = [x for m in models for x in rapid_rows(m)]
                if rows:
                    return rows
                if models:  # the page drew its grid and it is empty: a line with no release yet
                    print(f"  {what}: no releases on the page")
                    return []
                print(f"  {what}: attempt {n}: page had no grid model")
        except Exception as e:
            print(f"  {what}: attempt {n} failed ({str(e).splitlines()[0][:120]})")
        time.sleep(5 * n)
    raise RuntimeError(f"{what}: no page model after {tries} attempts ({url.split('/')[-1]})")


# ── Load ────────────────────────────────────────────────────────────────────────

SCREENS = {  # name: (title, fetch, table, schema, minimum share of the current table's rows)
    "revenue": ("Shipping Revenue by Part Group", fetch_revenue, REVENUE_TABLE, REVENUE_SCHEMA, 0.9),
    "history": ("Shipper History", fetch_history, HISTORY_TABLE, HISTORY_SCHEMA, 0.9),
    "releases": ("Sales order releases (Label Design)", fetch_releases, RELEASES_TABLE, RELEASES_SCHEMA, 0.5),
    "production": ("Production records (Job Production + Production History)", fetch_production,
                   PRODUCTION_TABLE, PRODUCTION_SCHEMA, 0.9),
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


# ── Monday push while the ETL cannot run ───────────────────────────────────────
# Normally the label_design ETL job starts the push (POST_RUN_JOB) after a run
# that extracted. While Plex's ODBC is down that job is held by the outage
# breaker, so nothing starts the push except its 6:05 PM sweep. After a good
# releases load this starts plex-etl-label-design-push itself, but only when ALL
# of these hold, so it never doubles up with the ETL or the sweep:
#   1. Mon-Fri 5:00 AM - 5:49 PM Mountain: the ETL's own window. The sweep runs at
#      6:05 PM, and two pushes running at once would both create the same item.
#   2. The ETL is NOT reaching Plex: its newest label_design run in the last 40
#      minutes is not success/partial, nor a 'skipped' run its change probe ended
#      (only breaker-held skips, detail "Held — ...", count as not reaching Plex).
#      Once ODBC is back, the ETL pushes and this steps aside on its own.
#   3. label_design_report is reading the live table (data_source = 'live').
#   4. No execution of the push job is still running.
PUSH_JOB = "plex-etl-label-design-push"
PUSH_REGION = "us-central1"
PUSH_WINDOW = (dt.time(5, 0), dt.time(17, 50))


def etl_reached_plex(status, detail):
    """Gate 2: did this label_design run reach Plex? success/partial did. So did a
    'skipped' run: its change probe asked Plex and found nothing new. Only a skip
    the outage breaker made (detail "Held — Plex outage breaker open ...") did not.
    Until 2026-11-09 only success/partial counted, so after ODBC recovered a healthy
    ETL whose probe kept skipping left this task starting the push every hour."""
    if status in ("success", "partial"):
        return True
    return status == "skipped" and not (detail or "").startswith("Held")


def maybe_start_push(c, live_mode=False):
    """Start the Label Design push if every gate above passes. Returns what it did.
    live_mode (screen_recon.py, 2026-11-10): the reconciliation found ODBC behind,
    so a "successful" ETL run proves nothing (11-10: it ran on 08:10 data and the
    push never saw order 675). Gate 2 is skipped; gates 1, 3 and 4 still apply."""
    now = dt.datetime.now(DEN)
    if now.weekday() >= 5 or not (PUSH_WINDOW[0] <= now.time() < PUSH_WINDOW[1]):
        return f"push not started: {now:%a %H:%M} MT is outside Mon-Fri 05:00-17:50 (the 6:05 PM sweep covers the day)"
    etl = list(c.query(f"""
        SELECT status, detail, started_at FROM `{PROJECT}.PlexProd.job_run_log`
        WHERE report_name = 'label_design' AND job_name NOT LIKE '%test%'
          AND started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 40 MINUTE)
        ORDER BY started_at DESC LIMIT 1""").result())
    if etl and etl_reached_plex(etl[0].status, etl[0].detail) and not live_mode:
        return f"push not started: the ETL reached Plex at {etl[0].started_at:%H:%M} UTC and starts the push itself"
    src = list(c.query(f"SELECT ARRAY_AGG(DISTINCT data_source) s FROM `{PROJECT}.PlexProd.label_design_report`").result())[0].s
    if src != ["live"]:
        return f"push not started: label_design_report is not reading the live screens (data_source {src})"
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    cred, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    s = AuthorizedSession(cred)
    job = f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{PUSH_REGION}/jobs/{PUSH_JOB}"
    r = s.get(f"{job}/executions", params={"pageSize": 5}, timeout=60)
    r.raise_for_status()
    running = [e["name"].rsplit("/", 1)[-1] for e in r.json().get("executions", []) if not e.get("completionTime")]
    if running:
        return f"push not started: {running[0]} is still running"
    r = s.post(f"{job}:run", json={}, timeout=60)
    r.raise_for_status()
    return f"started {PUSH_JOB}: {r.json().get('metadata', {}).get('name', '').rsplit('/', 1)[-1]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--load", action="store_true", help="replace the live_* tables in BigQuery")
    ap.add_argument("--no-push", action="store_true",
                    help="with --load, do not start the Label Design push after the releases load")
    ap.add_argument("--only", help="comma-separated screens: " + ", ".join(SCREENS))
    ap.add_argument("--force", action="store_true", help="load even if a table would shrink past its floor")
    ap.add_argument("--dump", help="also write each screen's rows to <DIR>/<screen>.json (for checking)")
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
    if args.dump:
        Path(args.dump).mkdir(parents=True, exist_ok=True)
        for n, rows in fetched.items():
            (Path(args.dump) / f"{n}.json").write_text(json.dumps(rows, default=str), encoding="utf-8")
    if args.load:
        c = ctx["bq"]()
        for n, rows in fetched.items():
            _, _, table, sch, floor = SCREENS[n]
            try:
                print(load(c, table, rows, sch, floor, args.force, today))
            except Exception as e:
                failed[n] = str(e).splitlines()[0][:300]
                print(f"{table}: NOT LOADED: {failed[n]}")
        if "releases" in fetched and "releases" not in failed and not args.no_push:
            try:
                print(maybe_start_push(c))
            except Exception as e:  # the tables are loaded; only the push start failed
                failed["push"] = str(e).splitlines()[0][:300]
                print(f"push: FAILED TO START: {failed['push']}")
    took = (dt.datetime.now(dt.timezone.utc) - started).total_seconds()
    print(f"done in {took:.0f}s: {len(names) - len(failed)}/{len(names)} screens ok"
          + (f"; FAILED {failed}" if failed else "") + ("" if args.load else " (dry run, nothing written)"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
