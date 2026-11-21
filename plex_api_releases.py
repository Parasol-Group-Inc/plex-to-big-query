"""Plex's REST API as a third source for Label Design (since 2026-11-20).

Label Design gets its lines from ODBC (every 15 min) plus the Plex releases screen (hourly on
weekdays 6:20 AM-5:20 PM MT, every 4 h otherwise; docs/ODBC_VS_SCREENS.md). The API is the third
source. It is used two ways, and never writes a Label Design line itself:

1. Trigger (main.py, the prod Label Design job, every 15 min on weekdays 5:00 AM-5:50 PM MT).
   If the API has a Label Design line that ODBC does not, changed after the last screen read,
   the job starts a releases-only screen read (plex-live-screens, RECON_ONLY=releases) right away
   instead of waiting up to an hour for the next scheduled one. The screen read brings the
   line with its integer keys, so the push works exactly as for any screen line.
2. Coverage check (watchdog.py, `label_design_coverage`, every 30 min). A Label Design line that
   Plex has had for over 75 min (5 h outside weekday working hours) and that is in neither ODBC
   nor the screens is a line Monday does not have: mailed on two runs in a row.

Why not push straight from the API: Monday items are keyed by ODBC's integer line key
(`<order>|L<po_line_key>`), and the API only has UUIDs. A brand-new line has no integer key until
the screens or ODBC have it, so an API-made item would be a second item for the same line later.

What "a Label Design line" means (same as reports/sql/label_design_view.sql): a release whose
status is "Label Design" on an order whose status is "Pending Fulfillment".

API (GET only, read-only key of the company user gcp.odbc.vox, docs/PLEX_CREDENTIALS.md):
  /sales/v1/orders?status=...     the Pending Fulfillment orders (367 on 11-20; paging is ignored)
  /sales/v1/releases?status=...   the Label Design releases (192; the status filter works, orderId not)
  /sales/v1/orders/{id}/lines     one order's lines (no bulk endpoint); only for new lines
The API's UUIDs equal ODBC's Resource_ID on Sales_v_PO, Sales_v_PO_Line and Sales_v_Release
(1,697 of 1,697 releases matched on 11-20). Probe and findings: docs/PLEX_API_THIRD_SOURCE.md.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.error
import urllib.request

import plex_api_lag

UTC = dt.timezone.utc
PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
LD, PF = "Label Design", "Pending Fulfillment"
MAX_LINE_CALLS = 40   # per pass; new lines are found by asking only the orders that changed
MIN_PF_ORDERS = int(os.environ.get("PLEX_API_MIN_PF_ORDERS", "50"))   # 367 on 11-20


def _ts(v):
    if not v:
        return None
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(UTC)


# ── the API ─────────────────────────────────────────────────────────────────────

def api_client(timeout: int = 90):
    """A GET function for connect.plex.com with the key from Secret Manager. Retries a cut-off
    or 5xx answer twice (11-20: one read of /orders stopped at 179 KB of 757 KB)."""
    from google.cloud import secretmanager
    sm = secretmanager.SecretManagerServiceClient()
    key, sec = (sm.access_secret_version(request={"name": f"projects/{PROJECT}/secrets/{n}/versions/latest"})
                .payload.data.decode("utf-8").strip() for n in plex_api_lag.PLEX_API_SECRETS)

    def get(path):
        last = None
        for attempt in range(3):
            req = urllib.request.Request(f"{plex_api_lag.PLEX_API_BASE}{path}", method="GET", headers={
                "X-Plex-Connect-Api-Key": key, "X-Plex-Connect-Api-Secret": sec, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    raise
                last = e
            except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
                last = e   # ValueError: a cut-off body that is not valid JSON
            time.sleep(3 * (attempt + 1))
        raise last
    return get


# ── what we already have: our ODBC copy and the last screen read ─────────────────

def odbc_state(bq) -> dict:
    """Our ODBC copy (PlexProd raw tables), keyed by the API's UUIDs."""
    rel, line, po = {}, {}, {}
    for r in bq.query(f"""
        SELECT LOWER(r.Resource_ID) id, SAFE_CAST(r.Release_Key AS INT64) k, s.Release_Status st
        FROM `{PROJECT}.PlexProd.raw_Sales_v_Release` r
        LEFT JOIN `{PROJECT}.PlexProd.raw_Sales_v_Release_Status` s
          ON SAFE_CAST(s.Release_Status_Key AS INT64) = SAFE_CAST(r.Release_Status_Key AS INT64)""").result():
        rel[r.id] = (r.k, r.st)
    for r in bq.query(f"""
        SELECT LOWER(l.Resource_ID) id, LOWER(p.Resource_ID) po
        FROM `{PROJECT}.PlexProd.raw_Sales_v_PO_Line` l
        JOIN `{PROJECT}.PlexProd.raw_Sales_v_PO` p ON SAFE_CAST(p.PO_Key AS INT64) = SAFE_CAST(l.PO_Key AS INT64)""").result():
        line[r.id] = r.po
    for r in bq.query(f"""
        SELECT LOWER(p.Resource_ID) id, s.PO_Status st
        FROM `{PROJECT}.PlexProd.raw_Sales_v_PO` p
        LEFT JOIN `{PROJECT}.PlexProd.raw_Sales_v_PO_Status` s
          ON SAFE_CAST(s.PO_Status_Key AS INT64) = SAFE_CAST(p.PO_Status_Key AS INT64)""").result():
        po[r.id] = r.st
    return {"release": rel, "line": line, "po": po}


def screen_state(bq) -> dict:
    """The last releases screen read: its Label Design rows and when that read started."""
    rows = [dict(r.items()) for r in bq.query(f"""
        SELECT release_key, order_no, part_no, part_no_revision
        FROM `{PROJECT}.PlexProd.live_order_releases`
        WHERE UPPER(TRIM(release_status)) = 'LABEL DESIGN'""").result()]
    last = list(bq.query(f"""
        SELECT MAX(run_started_at) t FROM `{PROJECT}.PlexOps.screen_recon`
        WHERE screen = 'releases' AND fetch_ok""").result())
    return {"keys": {r["release_key"] for r in rows if r["release_key"] is not None},
            "order_parts": {(str(r["order_no"]), p) for r in rows for p in (r["part_no"], r["part_no_revision"]) if p},
            "read_started_at": last[0].t if last else None}


# ── the comparison ──────────────────────────────────────────────────────────────

def label_design_lines(orders: list, releases: list, odbc: dict, screen: dict, get_lines=None) -> list[dict]:
    """Every Label Design line in Plex (API), and whether ODBC and the screens have it.

    A release's order comes from our ODBC copy when we know its line. A line we do not know is
    new; its order is found by asking /orders/{id}/lines of the Pending Fulfillment orders that
    changed since that release was created (at most MAX_LINE_CALLS calls)."""
    by_id = {o["id"].lower(): o for o in orders}
    ld = [r for r in releases if r.get("status") == LD]
    line_po = dict(odbc["line"])
    unknown = [r for r in ld if r["orderLineId"].lower() not in line_po]
    if unknown and get_lines:
        since = min(_ts(r.get("createdDate")) or _ts(r.get("modifiedDate")) for r in unknown) - dt.timedelta(minutes=15)
        cand = sorted((o for o in orders if o.get("status") == PF and (_ts(o.get("modifiedDate")) or since) >= since),
                      key=lambda o: o.get("modifiedDate") or "", reverse=True)[:MAX_LINE_CALLS]
        want = {r["orderLineId"].lower() for r in unknown}
        for o in cand:
            for ln in get_lines(o["id"]) or []:
                if ln["id"].lower() in want:
                    line_po[ln["id"].lower()] = o["id"].lower()
    out = []
    for r in ld:
        po_id = line_po.get(r["orderLineId"].lower())
        o = by_id.get(po_id) if po_id else None
        if o is None or o.get("status") != PF:
            continue   # a quote, deposit review, ... : not a Label Design line (yet)
        k, st = odbc["release"].get(r["id"].lower(), (None, None))
        in_odbc = st == LD and odbc["po"].get(po_id) == PF
        in_screen = (k in screen["keys"]) if k is not None else (
            (str(o.get("orderNumber")), r.get("partNumber")) in screen["order_parts"])
        changed = max(t for t in (_ts(r.get("modifiedDate")), _ts(o.get("modifiedDate")), _ts(r.get("createdDate"))) if t)
        out.append({"release_id": r["id"], "order_no": str(o.get("orderNumber")), "part_no": r.get("partNumber"),
                    "changed_at": changed, "in_odbc": in_odbc, "in_screen": in_screen, "release_key": k})
    return out


def fetch(bq, get=None) -> dict:
    """One full pass: the API, our ODBC copy, the last screen read, and the comparison."""
    get = get or api_client()
    # The status filter works (orderId does not): 367 orders and 192 releases on 11-20, ~2 s each.
    orders = get("/sales/v1/orders?status=Pending%20Fulfillment")
    releases = get("/sales/v1/releases?status=Label%20Design")
    # A short or odd answer would read as "nothing missing", so treat it as unreadable instead.
    if not isinstance(orders, list) or len(orders) < MIN_PF_ORDERS or not isinstance(releases, list):
        raise ValueError(f"Plex API returned an odd answer ({len(orders) if isinstance(orders, list) else type(orders).__name__} "
                         f"Pending Fulfillment orders, expected {MIN_PF_ORDERS}+; {type(releases).__name__} releases)")
    odbc, screen = odbc_state(bq), screen_state(bq)
    lines = label_design_lines(orders, releases, odbc, screen, get_lines=lambda oid: get(f"/sales/v1/orders/{oid}/lines"))
    return {"lines": lines, "screen_read_started_at": screen["read_started_at"], "orders": len(orders),
            "releases": len(releases)}


def missing(lines: list[dict]) -> list[dict]:
    """Label Design lines Plex has and neither ODBC nor the screens have."""
    return [x for x in lines if not x["in_odbc"] and not x["in_screen"]]


def describe(xs: list[dict], now: dt.datetime | None = None) -> str:
    now = now or dt.datetime.now(UTC)
    return "; ".join(f"order {x['order_no']} {x['part_no']} ({(now - x['changed_at']).total_seconds() / 60:.0f} min)"
                     for x in sorted(xs, key=lambda x: x["changed_at"])[:8])


# ── the trigger (main.py, prod Label Design job) ───────────────────────────────

SCREENS_JOB = os.environ.get("SCREENS_JOB", "plex-live-screens")
TRIGGER_LOG = f"{PROJECT}.PlexOps.api_trigger_log"
RECENT_READ_MIN = 12   # a screens login this recent: a read is running or just ran
REPEAT_MIN = 20        # at most one trigger per 20 min


def trigger_window(now_mt: dt.datetime) -> bool:
    """Weekdays 5:00 AM-5:50 PM MT: when the push runs (it starts from the screens job)."""
    return now_mt.weekday() < 5 and (5, 0) <= (now_mt.hour, now_mt.minute) < (17, 50)


def hourly_read_soon(now_mt: dt.datetime) -> bool:
    """The scheduled releases read runs at :20 from 6:20 to 5:20 PM on weekdays; from :08 it is
    close enough to wait for (two Plex logins at once can end each other's session)."""
    return now_mt.weekday() < 5 and 6 <= now_mt.hour <= 17 and 8 <= now_mt.minute < 20


def decide(lines: list[dict], read_started_at, now_mt: dt.datetime, last_login, last_trigger) -> tuple[bool, str]:
    """(start a screens read?, why). Pure, for tests."""
    read = _ts(read_started_at)
    new = [x for x in missing(lines) if read is None or x["changed_at"] > read]
    if not new:
        return False, "nothing new"
    now = now_mt.astimezone(UTC)
    what = describe(new, now)
    if not trigger_window(now_mt):
        return False, f"outside the push window: {what}"
    if hourly_read_soon(now_mt):
        return False, f"the hourly read is due at :20: {what}"
    if last_login and now - _ts(last_login) < dt.timedelta(minutes=RECENT_READ_MIN):
        return False, f"a screens read started at {_ts(last_login):%H:%M} UTC: {what}"
    if last_trigger and now - _ts(last_trigger) < dt.timedelta(minutes=REPEAT_MIN):
        return False, f"triggered at {_ts(last_trigger):%H:%M} UTC already: {what}"
    return True, what


def start_screens_read(region: str) -> str:
    """Start plex-live-screens with RECON_ONLY=releases, as plex-live-screens-releases-sync does
    (needs run.jobs.runWithOverrides: the ETL account's custom role, terraform/main.tf)."""
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    url = f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{region}/jobs/{SCREENS_JOB}:run"
    body = {"overrides": {"containerOverrides": [{"env": [{"name": "RECON_ONLY", "value": "releases"}]}]}}
    r = AuthorizedSession(credentials).post(url, json=body, timeout=60)
    r.raise_for_status()
    return r.json().get("metadata", {}).get("name", "")


def maybe_trigger_screens(region: str, log) -> None:
    """Called at the start of every prod Label Design run (API_SCREENS_TRIGGER=1), before ODBC is
    touched, so it also works while ODBC is down. Never raises: the ETL run is what matters."""
    try:
        from zoneinfo import ZoneInfo
        from google.cloud import bigquery
        now_mt = dt.datetime.now(ZoneInfo("America/Denver"))
        if not trigger_window(now_mt):
            return
        bq = bigquery.Client(project=PROJECT)
        bq.create_table(bigquery.Table(TRIGGER_LOG, schema=[
            bigquery.SchemaField("checked_at", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("started", "BOOL"),
            bigquery.SchemaField("execution", "STRING"),
            bigquery.SchemaField("reason", "STRING"),
            bigquery.SchemaField("ld_lines", "INT64"),
            bigquery.SchemaField("missing", "INT64")]), exists_ok=True)
        res = fetch(bq)
        lines = res["lines"]
        meta = list(bq.query(f"""
            SELECT (SELECT MAX(attempted_at) FROM `{PROJECT}.PlexOps.plex_login_log` WHERE job = '{SCREENS_JOB}') login,
                   (SELECT MAX(checked_at) FROM `{TRIGGER_LOG}` WHERE started) trig""").result())[0]
        go, why = decide(lines, res["screen_read_started_at"], now_mt, meta.login, meta.trig)
        execution = start_screens_read(region) if go else ""
        log.info(f"API third source: {len(lines)} Label Design lines in Plex, {len(missing(lines))} in neither "
                 f"ODBC nor the screens; {'started ' + execution if go else 'no screens read'} ({why})")
        if go or why != "nothing new":
            bq.insert_rows_json(TRIGGER_LOG, [{"checked_at": dt.datetime.now(UTC).isoformat(), "started": go,
                                               "execution": execution, "reason": why[:1000], "ld_lines": len(lines),
                                               "missing": len(missing(lines))}])
    except Exception as e:
        log.warning(f"API third source skipped ({type(e).__name__}: {str(e)[:200]})")
