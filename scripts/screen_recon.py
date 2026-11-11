#!/usr/bin/env python3
"""Read Plex's live screens, compare them with ODBC and BigQuery, feed Label Design
the lines ODBC does not have yet, and email only what needs a person.

    python scripts/screen_recon.py                 # full cycle (the Cloud Run job)
    python scripts/screen_recon.py --dry-run       # read and compare; write nothing, mail nothing
    python scripts/screen_recon.py --only releases

Runs as the Cloud Run job `plex-live-screens` (Dockerfile.screens): all three screens every
4 hours, and the releases screen alone hourly on weekdays 6:20 AM-5:20 PM MT
(RECON_ONLY=releases from the second scheduler). All the rules: docs/ODBC_VS_SCREENS.md.
Runbook: docs/PLEX_SCREEN_EXTRACTION.md, "Reconciliation (cloud job)". Design: 2026-11-10,
after Plex ODBC served data frozen 08:10-12:50 MT while every run succeeded.

One cycle:
  1. Read the screens in SCREEN_ORDER (releases, history, revenue since 2026-11-10;
     `--only production` reads the last RECON_PRODUCTION_DAYS days of production).
  2. Append every row to PlexOps.screen_snapshot (key, row hash, fetch time).
  3. Read the same records from ODBC (one connection, cheap filtered queries) and
     from the raw_* tables in BigQuery.
  4. Classify each difference (missing_tail = lag, missing_hole, odbc_extra,
     status/value_diff, odbc_newer, bq_missing) and give each screen a verdict:
       current | behind | diverged | odbc_unreachable | pipeline_behind | screens_failed
     Lag = age of the oldest screen record ODBC lacks (or of an edit ODBC has not
     picked up). Over RECON_LAG_TOLERANCE_MIN (default 120) it is "behind".
  5. Write PlexOps.screen_recon (one row per screen) and screen_recon_diff.
  6. PlexOps.live_source (a view over screen_recon) says, per report group, whether
     ODBC is behind (odbc_behind) and whether the report takes screen rows (use_live).
     Since 2026-11-11: Label Design always does (the releases screen is loaded on
     every read and label_design_view.sql adds the lines ODBC lacks; the push is
     started when there are any); revenue never does (not time critical), so its
     live_* tables are backed up and emptied.
  7. Email only what needs a person, at most once per 24 h per kind: ODBC behind by
     more than RECON_ALERT_LAG_MIN (releases, 6 h) or RECON_REVENUE_ALERT_LAG_MIN
     (shipments/revenue, 12 h: ODBC missed its overnight catch-up), a non-delay
     verdict, a screen that failed twice running; and "caught up" after such a mail.
Exit: 0 when every screen got a verdict, 1 when a screen failed or the cycle broke.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import time
import sys
import traceback
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))  # main.py / email_utils.py (in the image: /app)

from google.cloud import bigquery  # noqa: E402

import plex_live_screens as pls  # noqa: E402

PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
OPS = f"{PROJECT}.PlexOps"
SNAP_TABLE = f"{OPS}.screen_snapshot"
RECON_TABLE = f"{OPS}.screen_recon"
DIFF_TABLE = f"{OPS}.screen_recon_diff"
LIVE_SOURCE = f"{OPS}.live_source"
DEN = ZoneInfo("America/Denver")
UTC = dt.timezone.utc

LAG_TOLERANCE_MIN = int(os.environ.get("RECON_LAG_TOLERANCE_MIN", "120"))
GRACE_MIN = int(os.environ.get("RECON_GRACE_MIN", "15"))
CLEAN_RUNS = int(os.environ.get("RECON_CLEAN_RUNS", "2"))
# 2026-11-11 (Emilio: ease the alerts). On 11-10 ODBC ran 2.5-5.5 h behind the screens
# all afternoon and was current again by the 00:20 and 04:20 checks, after the 4 AM run.
# A lag over LAG_TOLERANCE_MIN still switches the reports to the screens (quietly); only
# a lag over ALERT_LAG_MIN, or a verdict that is not a delay, mails or makes the digest
# say ACTION NEEDED.
ALERT_LAG_MIN = int(os.environ.get("RECON_ALERT_LAG_MIN", "360"))
# 2026-11-11 (Jennilyn): shipments and revenue are not time critical; the data comes
# every day either way. Their reports stay on ODBC, and only a lag that survives the
# overnight catch-up (12 h) mails.
REVENUE_ALERT_LAG_MIN = int(os.environ.get("RECON_REVENUE_ALERT_LAG_MIN", "720"))
ALERT_LAG_BY_SCREEN = {"releases": ALERT_LAG_MIN, "history": REVENUE_ALERT_LAG_MIN,
                       "revenue": REVENUE_ALERT_LAG_MIN}
PRODUCTION_DAYS = int(os.environ.get("RECON_PRODUCTION_DAYS", "2"))
ALERT_REPEAT_HOURS = 24
SHORT_READ = {"releases": 0.5, "production": 0.5, "history": 0.9, "revenue": 0.9}
# 2026-11-10 (Emilio): every 4 hours, Label Design, revenue and shipments only.
# Production can still be compared by hand (--only production).
SCREEN_ORDER = ["releases", "history", "revenue"]
GROUPS = {"label_design": ["releases"], "revenue": ["history", "revenue"]}
LOGIN_TABLE = f"{OPS}.plex_login_log"
SCREENSHOT_BUCKET = os.environ.get("SCREENSHOT_BUCKET", "")
LOGIN_ALERT_EMAILS = os.environ.get("LOGIN_ALERT_EMAILS", "")
LIVE_TABLE = {"releases": pls.RELEASES_TABLE, "production": pls.PRODUCTION_TABLE,
              "history": pls.HISTORY_TABLE, "revenue": pls.REVENUE_TABLE}
ODBC_TOP = 50000
BAD_VERDICTS = ("behind", "diverged", "odbc_unreachable")


# ── Normalising ───────────────────────────────────────────────────────────────

def q4(v):
    return None if v is None else round(float(v), 4)


def cents(v):
    return None if v is None else int(round(float(v) * 100))


def as_int(v):
    try:
        return None if v is None or v == "" else int(float(v))
    except (TypeError, ValueError):
        return None


def utc(s):
    """ISO string / datetime -> aware UTC datetime (or None)."""
    if s is None:
        return None
    if isinstance(s, str):
        s = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return s if s.tzinfo else s.replace(tzinfo=UTC)


def plex_time(v):
    """A naive Plex datetime (Mountain wall time) -> aware UTC."""
    if v is None:
        return None
    if isinstance(v, dt.date) and not isinstance(v, dt.datetime):
        v = dt.datetime(v.year, v.month, v.day)
    return v.replace(tzinfo=DEN).astimezone(UTC)


def bq_plex_time(ns):
    """raw_* date columns: INT64 nanoseconds of Mountain wall time -> aware UTC."""
    if ns is None:
        return None
    return plex_time(dt.datetime(1970, 1, 1) + dt.timedelta(microseconds=int(ns) // 1000))


def row_hash(m):
    return hashlib.sha256(json.dumps(m, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ── Screen rows -> {key: {"m": measures, "event": time or None, "num": int}} ──

def screen_records(screen, rows):
    out = {}
    if screen == "production":
        for r in rows:
            k = as_int(r["production_no"])
            out[str(k)] = {"num": k, "event": utc(r["record_time"]),
                           "m": {"quantity": q4(r["quantity"]), "rejected": int(bool(r["rejected"]))}}
    elif screen == "history":
        for r in rows:
            k = as_int(r["shipper_line_key"])
            out[str(k)] = {"num": k, "event": utc(r["ship_time"]), "m": {"quantity": q4(r["quantity"])}}
    elif screen == "revenue":
        for r in rows:
            link, part = as_int(r["invoice_link"]), as_int(r["part_key"])
            k = f"{link}|{part}"
            o = out.setdefault(k, {"num": link, "event": None, "m": {"revenue_cents": 0}})
            o["m"]["revenue_cents"] += cents(r["revenue"]) or 0
    elif screen == "releases":
        for r in rows:
            k = as_int(r["release_key"])
            out[str(k)] = {"num": k, "event": None,
                           "m": {"status_key": as_int(r["release_status_key"]), "quantity": q4(r["quantity"]),
                                 "order_status": "Pending Fulfillment"}}
    return out


# ── ODBC ──────────────────────────────────────────────────────────────────────

ODBC_SQL = {
    "production": ("SELECT TOP {top} p.Production_No, p.Record_Date, p.Quantity, p.Rejected "
                   "FROM Part_v_Production AS p WHERE p.Record_Date >= '{since}'"),
    "history": ("SELECT TOP {top} sl.Shipper_Line_Key, sl.Quantity, s.Ship_Date, s.Updated_Date, ss.Shipped "
                "FROM Sales_v_Shipper AS s "
                "JOIN Sales_v_Shipper_Line AS sl ON sl.Shipper_Key = s.Shipper_Key "
                "JOIN Sales_v_Shipper_Status AS ss ON ss.Shipper_Status_Key = s.Shipper_Status_Key "
                "WHERE s.Ship_Date >= '{since}'"),
    "revenue": ("SELECT TOP {top} a.Invoice_Link, a.Invoice_Date, a.Updated_Date, d.Part_Key, "
                "SUM(d.Credit) AS Credit, SUM(d.Debit) AS Debit "
                "FROM Accounting_v_AR_Invoice AS a "
                "JOIN Accounting_v_AR_Invoice_Dist AS d ON d.Invoice_Link = a.Invoice_Link "
                "WHERE a.Invoice_Date >= '{since}' AND a.Void = 0 AND d.Account_No LIKE '4%' "
                "GROUP BY a.Invoice_Link, a.Invoice_Date, a.Updated_Date, d.Part_Key"),
    "releases": ("SELECT TOP {top} po.PO_Date, po.Update_Date AS PO_Update, ps.PO_Status, "
                 "r.Release_Key, r.Release_Status_Key, r.Quantity, r.Update_Date AS Rel_Update "
                 "FROM Sales_v_PO AS po "
                 "JOIN Sales_v_PO_Status AS ps ON ps.PO_Status_Key = po.PO_Status_Key "
                 "JOIN Sales_v_PO_Line AS pl ON pl.PO_Key = po.PO_Key "
                 "JOIN Sales_v_Release AS r ON r.PO_Line_Key = pl.PO_Line_Key "
                 "WHERE po.PO_Date >= '{since}'"),
}


def screen_since(screen, today):
    if screen == "production":
        return today - dt.timedelta(days=PRODUCTION_DAYS - 1)
    if screen == "releases":
        return pls.RELEASES_START
    return pls.START


def load_portal_secrets():
    """PLEX_PORTAL_USERNAME / _PASSWORD from Secret Manager when not in the
    environment (the job names the secrets; a job pointing Cloud Run at a secret
    with no version yet could not even be created). Never printed."""
    for env, default in (("PLEX_PORTAL_USERNAME", "plex-portal-username"),
                         ("PLEX_PORTAL_PASSWORD", "plex-portal-password")):
        if not os.environ.get(env):
            try:
                import main as etl
                os.environ[env] = etl.get_secret(os.environ.get("SECRET_" + env, default)).strip()
            except Exception as e:
                print(f"{env}: not in the environment and Secret Manager failed ({type(e).__name__})")


def odbc_connect():
    """The ETL's own connection code and credentials (main.py)."""
    import main as etl
    token = os.environ.get("PLEX_ACCESS_TOKEN") or etl.get_secret(etl.SECRET_TOKEN)
    return etl.get_odbc_connection(os.environ.get("PLEX_ODBC_USER", ""), "", "", token)


def odbc_records(conn, screen, since):
    """{key: {"m", "event", "updated", "eligible", "num"}}, plus (max_num, max_event)."""
    cur = conn.cursor()
    try:
        cur.execute(ODBC_SQL[screen].format(top=ODBC_TOP, since=since.isoformat()))
        rows = cur.fetchall()
    finally:
        try:
            cur.close()
        except Exception:
            pass
    if len(rows) >= ODBC_TOP:
        raise RuntimeError(f"ODBC {screen}: {len(rows)} rows, at TOP {ODBC_TOP}; result may be cut off")
    out = {}
    for r in rows:
        if screen == "production":
            k = as_int(r.Production_No)
            out[str(k)] = {"num": k, "event": plex_time(r.Record_Date), "updated": None, "eligible": True,
                           "m": {"quantity": q4(r.Quantity), "rejected": int(bool(r.Rejected))}}
        elif screen == "history":
            k = as_int(r.Shipper_Line_Key)
            out[str(k)] = {"num": k, "event": plex_time(r.Ship_Date), "updated": plex_time(r.Updated_Date),
                           "eligible": bool(r.Shipped), "m": {"quantity": q4(r.Quantity)},
                           "shipped": bool(r.Shipped)}
        elif screen == "revenue":
            part = as_int(r.Part_Key)
            if part is None:
                continue  # freight / tax lines: the screen lists parts only
            link = as_int(r.Invoice_Link)
            k = f"{link}|{part}"
            o = out.setdefault(k, {"num": link, "event": None, "updated": plex_time(r.Updated_Date),
                                   "eligible": True, "m": {"revenue_cents": 0}})
            o["m"]["revenue_cents"] += cents((r.Credit or 0) - (r.Debit or 0)) or 0
        elif screen == "releases":
            k = as_int(r.Release_Key)
            upd = max([t for t in (plex_time(r.PO_Update), plex_time(r.Rel_Update)) if t], default=None)
            out[str(k)] = {"num": k, "event": None, "updated": upd,
                           "eligible": (r.PO_Status or "").strip() == "Pending Fulfillment",
                           "m": {"status_key": as_int(r.Release_Status_Key), "quantity": q4(r.Quantity),
                                 "order_status": (r.PO_Status or "").strip()}}
    nums = [o["num"] for o in out.values() if o["num"] is not None]
    evs = [o["event"] for o in out.values() if o["event"] is not None]
    return out, (max(nums) if nums else None), (max(evs) if evs else None)


def newest_change(odbc):
    """The newest update or event time ODBC holds for a screen (None if none)."""
    ts = [t for o in odbc.values() for t in (o["updated"], o["event"]) if t is not None]
    now = dt.datetime.now(UTC) + dt.timedelta(minutes=10)
    ts = [t for t in ts if t <= now]
    return max(ts) if ts else None


# ── BigQuery raw tables (is our extraction current?) ──────────────────────────

BQ_SQL = {
    "production": ("raw_Part_v_Production",
                   "SELECT CAST(SAFE_CAST(Production_No AS INT64) AS STRING) k FROM `{t}` "
                   "WHERE SAFE_CAST(Record_Date AS INT64) >= @since_ns"),
    "history": ("raw_Sales_v_Shipper_Line",
                "SELECT CAST(SAFE_CAST(Shipper_Line_Key AS INT64) AS STRING) k FROM `{t}`"),
    "releases": ("raw_Sales_v_Release",
                 "SELECT CAST(SAFE_CAST(Release_Key AS INT64) AS STRING) k FROM `{t}`"),
}


def bq_keys(c, screen, since):
    """(set of keys in the raw table, its last-modified time), or (None, None)."""
    if screen not in BQ_SQL:
        return None, None
    table, sql = BQ_SQL[screen]
    full = f"{PROJECT}.PlexProd.{table}"
    since_ns = int(dt.datetime(since.year, since.month, since.day, tzinfo=UTC).timestamp()) * 10**9
    rows = c.query(sql.format(t=full), job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("since_ns", "INT64", since_ns)])).result()
    keys = {r.k for r in rows if r.k}
    modified = c.get_table(full).modified
    return keys, modified


# ── Comparing ─────────────────────────────────────────────────────────────────

def compare(screen, scr, odbc, odbc_max_num, odbc_max_event, first_seen, fetch_at,
            prev_extra=frozenset(), raw=None, raw_modified=None, grace_min=GRACE_MIN,
            tolerance_min=LAG_TOLERANCE_MIN, odbc_newest_change=None):
    """Pure: returns (counts, diffs, verdict, lag_min). See the module docstring."""
    cut = fetch_at - dt.timedelta(minutes=grace_min)
    counts = {k: 0 for k in ("compared", "excluded_recent", "missing_tail", "missing_hole", "odbc_extra",
                             "status_diff", "value_diff", "odbc_newer", "bq_missing")}
    diffs, lag_ages, diverged = [], [], []

    def age_min(t):
        return round((fetch_at - t).total_seconds() / 60, 1) if t else 0.0

    for key, s in scr.items():
        ref = s["event"] or first_seen.get(key) or fetch_at
        if ref > cut:
            # A record first seen now (releases and revenue have no time of their own)
            # that ODBC lacks while ODBC's newest change is already older than the
            # tolerance: ODBC is stale now, not in 4 h (the 11-10 order-675 case).
            stale_at = odbc_newest_change if (odbc_newest_change and key not in odbc and s["event"] is None
                       and odbc_newest_change < fetch_at - dt.timedelta(minutes=tolerance_min)) else None
            if stale_at is None:
                counts["excluded_recent"] += 1
                continue
            ref = stale_at
        counts["compared"] += 1
        o = odbc.get(key)
        if o is None:
            tail = ((s["num"] is not None and odbc_max_num is not None and s["num"] > odbc_max_num)
                    or (s["event"] is not None and odbc_max_event is not None and s["event"] >= odbc_max_event)
                    or odbc_max_num is None)
            kind = "missing_tail" if tail else "missing_hole"
            counts[kind] += 1
            a = age_min(ref)
            lag_ages.append(a)
            if kind == "missing_hole" and a > tolerance_min:
                diverged.append(f"{key} missing in ODBC for {a:.0f} min below ODBC's newest record")
            diffs.append({"key": key, "kind": kind, "field": None, "screen_value": json.dumps(s["m"]),
                          "odbc_value": None, "event_time": s["event"], "first_seen_at": first_seen.get(key),
                          "odbc_updated_at": None, "age_min": a})
            continue
        for f, sv in s["m"].items():
            ov = o["m"].get(f)
            if sv == ov:
                continue
            if o["updated"] and o["updated"] > fetch_at:
                counts["odbc_newer"] += 1
                continue
            kind = "status_diff" if f in ("status_key", "order_status") else "value_diff"
            counts[kind] += 1
            seen = first_seen.get(key) or ref
            a = age_min(seen)
            if o["updated"] and o["updated"] >= seen and a > grace_min:
                diverged.append(f"{key}.{f}: screen {sv}, ODBC {ov} (ODBC updated after the screen showed it)")
            else:
                lag_ages.append(a)
            diffs.append({"key": key, "kind": kind, "field": f, "screen_value": str(sv), "odbc_value": str(ov),
                          "event_time": s["event"], "first_seen_at": first_seen.get(key),
                          "odbc_updated_at": o["updated"], "age_min": a})
    extras = []
    for key, o in odbc.items():
        if key in scr or not o["eligible"]:
            continue
        if (o["event"] and o["event"] > cut) or (o["updated"] and o["updated"] > cut):
            continue
        extras.append(key)
        counts["odbc_extra"] += 1
        diffs.append({"key": key, "kind": "odbc_extra", "field": None, "screen_value": None,
                      "odbc_value": json.dumps(o["m"]), "event_time": o["event"], "first_seen_at": None,
                      "odbc_updated_at": o["updated"], "age_min": None})
    lag = max(lag_ages, default=0.0)
    persistent = [k for k in extras if k in prev_extra]
    # Extras are a lag sign too while ODBC is stale: on 11-10 five releases ODBC still
    # showed as open (Plex had moved on) stayed "extra" through two runs and cleared when
    # ODBC caught up overnight. Only extras while ODBC is fresh mean disagreement.
    odbc_fresh = odbc_newest_change is None or odbc_newest_change >= fetch_at - dt.timedelta(minutes=tolerance_min)
    if persistent and lag <= tolerance_min and odbc_fresh:
        diverged.append(f"{len(persistent)} record(s) in ODBC but not on the screen in two runs, e.g. {persistent[0]}")
    if raw is not None and raw_modified is not None:
        for key, o in odbc.items():
            t = o["event"] or o["updated"]
            # older than our last load by more than the lag tolerance: ODBC had it in time
            if o["eligible"] and key not in raw and t and t < raw_modified - dt.timedelta(minutes=tolerance_min):
                counts["bq_missing"] += 1
                if counts["bq_missing"] <= 20:
                    diffs.append({"key": key, "kind": "bq_missing", "field": None, "screen_value": None,
                                  "odbc_value": json.dumps(o["m"]), "event_time": o["event"], "first_seen_at": None,
                                  "odbc_updated_at": o["updated"], "age_min": None})
    if diverged:
        verdict = "diverged"
    elif lag > tolerance_min:
        verdict = "behind"
    elif counts["bq_missing"]:
        verdict = "pipeline_behind"
    else:
        verdict = "current"
    return counts, diffs, verdict, lag, diverged


# ── BigQuery state ────────────────────────────────────────────────────────────

def previous_counts(c):
    rows = c.query(f"""
        SELECT screen, ARRAY_AGG(screen_rows ORDER BY run_started_at DESC LIMIT 1)[OFFSET(0)] n
        FROM `{RECON_TABLE}` WHERE fetch_ok AND run_started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)
        GROUP BY screen""").result()
    return {r.screen: r.n for r in rows}


def short_twice(c, screen, n):
    """The previous run of this screen was also short with a similar count: accept
    it as the new normal (a real drop must not wedge the screen for 3 days)."""
    try:
        rows = list(c.query(f"""
            SELECT fetch_error FROM `{RECON_TABLE}` WHERE screen = @s
            ORDER BY run_started_at DESC LIMIT 1""", job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("s", "STRING", screen)])).result())
        err = (rows[0].fetch_error or "") if rows else ""
        m = __import__("re").match(r"short read: (\d+) rows", err)
        return bool(m) and abs(int(m.group(1)) - n) <= max(5, 0.1 * n)
    except Exception:
        return False


def login_suspended(c):
    """A credential-type failure (wrong password, password change, MFA, locked, unknown,
    sign-in timeout) in the last 24 h: don't log in again until a person fixes it and
    starts a run with --force-login. Returns the reason, or None. Never raises."""
    try:
        rows = list(c.query(f"""
            SELECT ok, error, attempted_at FROM `{LOGIN_TABLE}`
            WHERE attempted_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            ORDER BY attempted_at DESC LIMIT 1""").result())
    except Exception as e:
        print(f"login history unreadable ({str(e).splitlines()[0][:150]}); logging in")
        return None
    if not rows or rows[0].ok:
        return None
    cause = (rows[0].error or "").split(":", 1)[0]
    if cause in CREDENTIAL_CAUSES or cause == "timeout_on_signin":
        return f"{cause} at {rows[0].attempted_at.astimezone(DEN):%m-%d %H:%M} MT"
    return None


def first_seen_map(c, screen, recs):
    """For each key, when its current row hash was first snapshotted (last 3 days)."""
    pairs = [f"{k}|{row_hash(v['m'])}" for k, v in recs.items()]
    if not pairs:
        return {}
    rows = c.query(f"""
        SELECT record_key, MIN(fetch_started_at) t FROM `{SNAP_TABLE}`
        WHERE screen = @s AND fetch_started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 DAY)
          AND CONCAT(record_key, '|', row_hash) IN UNNEST(@p)
        GROUP BY record_key""", job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("s", "STRING", screen),
        bigquery.ArrayQueryParameter("p", "STRING", pairs)])).result()
    return {r.record_key: r.t for r in rows}


def previous_extras(c, screen):
    rows = c.query(f"""
        SELECT d.record_key FROM `{DIFF_TABLE}` d
        WHERE d.screen = @s AND d.kind = 'odbc_extra'
          AND d.run_id = (SELECT ARRAY_AGG(r.run_id ORDER BY r.run_started_at DESC LIMIT 1)[OFFSET(0)]
                          FROM `{RECON_TABLE}` r WHERE r.screen = @s AND r.odbc_ok
                            AND r.run_started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 9 HOUR))""",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("s", "STRING", screen)])).result()
    return frozenset(r.record_key for r in rows)


def insert(c, table, rows):
    if not rows:
        return
    def ser(v):
        if isinstance(v, (dt.datetime, dt.date)):
            return v.isoformat()
        return v
    rows = [{k: ser(v) for k, v in r.items()} for r in rows]
    for i in range(0, len(rows), 5000):
        job = c.load_table_from_json(rows[i:i + 5000], table, job_config=bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND", schema=c.get_table(table).schema))
        job.result()


def live_source(c):
    return {r.report_group: dict(r) for r in c.query(f"SELECT * FROM `{LIVE_SOURCE}`").result()}


def empty_live(c, screen, today):
    """Back up then empty a live_* table (D30: a stale screen copy must not linger)."""
    table = LIVE_TABLE[screen]
    t = c.get_table(table)
    if not t.num_rows:
        return f"{table}: already empty"
    stamp = dt.datetime.now(DEN).strftime("%Y%m%d%H%M")
    backup = f"{PROJECT}.Backups.PlexProd__{table.rsplit('.', 1)[1]}_{stamp}"
    c.copy_table(table, backup).result()
    b = c.get_table(backup)
    b.expires = dt.datetime.now(UTC) + dt.timedelta(days=pls.BACKUP_DAYS)
    c.update_table(b, ["expires"])
    c.query(f"DELETE FROM `{table}` WHERE TRUE").result()
    return f"{table}: backed up to {backup} and emptied ({t.num_rows} rows)"


def alert_sent_recently(c, kind, hours=ALERT_REPEAT_HOURS):
    rows = list(c.query(f"""
        SELECT COUNT(*) n FROM `{RECON_TABLE}`
        WHERE @k IN UNNEST(SPLIT(IFNULL(alert, ''), ',')) AND run_started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {int(hours)} HOUR)""",
        job_config=bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("k", "STRING", kind)])).result())
    return rows[0].n > 0


def send(alert):
    try:
        from email_utils import send_ops_alert
        return send_ops_alert(alert)
    except Exception:
        print("alert email failed:\n" + traceback.format_exc())
        return False


# ── Login and screenshot audit (2026-11-10) ───────────────────────────────────
# Every Plex login the job makes (the first one and any re-login in the middle of
# a screen) is timed, logged to PlexOps.plex_login_log and screenshotted; a failed
# one is emailed on its own to LOGIN_ALERT_EMAILS. Screenshots go to
# gs://SCREENSHOT_BUCKET/plex-screens/YYYY/MM/DD/HHMM-MT_<run>/NN_<what>.png.

# Why a Plex web login failed. Credential, MFA and lock causes are read from the TEXT
# OF THE PAGE the login stopped on (never from links like "Reset password" that are on
# every login page); transport causes from the ERROR string. First match wins.
# retry = may pass on its own a minute later. Only plex_down, network, and a timeout
# that did not stop on Plex's sign-in page are retried: a retry after a rejected
# password can lock the user, so anything unclear is NOT retried (audit 2026-11-10).
CREDENTIAL_CAUSES = {"wrong_credentials", "password_change", "verification", "locked", "unknown"}
LOGIN_CAUSES = [
    ("locked", "page", r"\b(account|user)\b.{0,30}\b(locked|disabled|deactivated|suspended)\b|\btoo many\b.{0,25}\battempts\b|"
                       r"\bmaximum\b.{0,20}\battempts\b|\binactive user\b",
     False, "The portal user is locked or disabled in Plex.",
     ["Ask the Plex admin to unlock the user. The job stops logging in for 24 h after this (no further attempts can make it worse)."]),
    ("verification", "page", r"\bverification code\b|\bone[- ]time (pass)?code\b|\bauthenticator\b|\bmulti-factor\b|"
                             r"\btwo[- ](factor|step)\b|\b2fa\b|\bmfa\b|\bverify (it'?s you|your identity)\b",
     False, "Plex asked for an extra verification step (MFA or a code), which a job cannot answer.",
     ["Ask the Plex admin to exempt the portal user from MFA, or use a service user without it."]),
    ("password_change", "page", r"\bpassword (has )?expired\b|\b(must|need to|please) change (your )?password\b|"
                                r"\bchoose a new password\b|\bcreate a new password\b",
     False, "Plex wants the portal user's password changed.",
     ["Log in by hand, set a new password, then store it: printf '%s' \"$NEW\" | gcloud secrets versions add plex-portal-password --data-file=- --project=voxdatalake"]),
    ("wrong_credentials", "page", r"\bincorrect\b|\binvalid (login|user(name)?|password|credentials?|email)\b|\bwrong password\b|"
                                  r"\bnot recogni[sz]ed\b|\bdoes(n't| not) match\b|\bunable to sign in\b|"
                                  r"\bauthentication failed\b|\bsign[- ]?in failed\b|\blogin failed\b",
     False, "Plex rejected the username or password.",
     ["Log into https://vox.on.plex.com as the portal user by hand to confirm the password.",
      "Put the right one in Secret Manager: printf '%s' \"$NEW\" | gcloud secrets versions add plex-portal-password --data-file=- --project=voxdatalake"]),
    ("plex_down", "either", r"\bmaintenance\b|\bservice unavailable\b|\bbad gateway\b|\bgateway time-?out\b|"
                            r"\b(http|error|status) ?(502|503|504)\b|\btemporarily unavailable\b",
     True, "Plex's web site answered with an error or a maintenance page.",
     ["Nothing to do if it passes on the next run; if it lasts, check https://status.plex.com or tell Plex support."]),
    ("network", "error", r"net::err_|\bname not resolved\b|\bconnection (refused|reset|closed)\b|\beconn\w+|"
                         r"\bssl\b|\bcertificate\b",
     True, "The job could not reach Plex over the network.",
     ["Usually transient. If it lasts, check that vox.on.plex.com opens from the office."]),
    ("timeout", "error", r"\btimeout\b|\btimed out\b",
     True, "The login pages did not answer in time.",
     ["Usually transient (a slow Plex). If several runs fail, open the screenshot to see where it stopped."]),
]
LOGIN_UNKNOWN = ("unknown", "none", None, False,
                 "The login stopped somewhere unexpected (Plex may have changed its login page, or rejected the login in words we don't know).",
                 ["Open the screenshot and the page text below. If Plex changed its login page, "
                  "scripts/plex_web_export.py login() needs its selectors updated; if it rejected the password, fix the secret."])
LOGIN_CAUSES = [(c[0], c[1], c[2], c[3], c[4], c[5]) for c in LOGIN_CAUSES]


def classify_login(error, page_text, url):
    """(name, where, regex, retry, why, steps). A timeout that stopped on Plex's sign-in
    page (accounts.plex.com) is treated as a rejected login, not retried."""
    err, text = (error or "").lower(), (page_text or "").lower()
    for cause in LOGIN_CAUSES:
        where = cause[1]
        hay = text if where == "page" else err if where == "error" else err + " " + text
        if re.search(cause[2], hay):
            if cause[0] == "timeout" and "accounts.plex.com" in (url or ""):
                return ("timeout_on_signin", "error", None, False,
                        "The sign-in page did not move on after the password was entered: usually a rejected "
                        "login that Plex did not put into words.", LOGIN_CAUSES[3][5])
            return cause
    return LOGIN_UNKNOWN


class LoginFailed(RuntimeError):
    """A login that must not be retried within this run (the fetchers re-raise RuntimeError)."""


def page_text(pg, limit=600):
    """Visible text of the page the login stopped on, collapsed; never raises."""
    try:
        t = pg.evaluate("() => document.body ? document.body.innerText : ''") or ""
        return re.sub(r"\s+", " ", t).strip()[:limit]
    except Exception:
        return ""


class Audit:
    def __init__(self, run_id, started, dry_run):
        self.run_id, self.dry_run, self.n = run_id, dry_run, 0
        self.logins, self.shots = [], []
        mt = started.astimezone(DEN)
        self.prefix = f"plex-screens/{mt:%Y/%m/%d}/{mt:%H%M}-MT_{run_id}"
        self.bucket = None
        if SCREENSHOT_BUCKET and not dry_run:
            try:
                from google.cloud import storage
                self.bucket = storage.Client(project=PROJECT).bucket(SCREENSHOT_BUCKET)
            except Exception as e:
                print(f"screenshots off: {str(e).splitlines()[0][:150]}")

    def shot(self, pg, what):
        """Full-page PNG to the bucket; returns its gs:// path or ''. Never raises."""
        self.n += 1
        name = f"{self.prefix}/{self.n:02d}_{what}.png"
        try:
            png = pg.screenshot(full_page=True, timeout=30000)
            if self.bucket is None:
                return ""
            blob = self.bucket.blob(name)
            blob.metadata = {"run_id": self.run_id, "what": what, "url": (pg.url or "").split("?")[0][:500]}
            blob.upload_from_string(png, content_type="image/png")
            path = f"gs://{SCREENSHOT_BUCKET}/{name}"
            self.shots.append(path)
            return path
        except Exception as e:
            print(f"  screenshot {what} failed: {str(e).splitlines()[0][:150]}")
            return ""

    def wrap_login(self, real_login):
        def login(pg, user, password):
            reason = "first" if not self.logins else "re-login"
            t0 = dt.datetime.now(UTC)
            try:
                real_login(pg, user, password)
            except Exception as e:
                scrub = (lambda t: t.replace(password, "***") if password else t)
                err = scrub(str(e).splitlines()[0][:400])
                text = scrub(page_text(pg))
                cause = classify_login(err, text, (pg.url or "").split("?")[0])
                # error column: "<cause>: <first line> | page: <visible text>" (no new columns needed)
                rec = {"ok": False, "error": f"{cause[0]}: {err} | page: {text[:300]}"[:1000],
                       "cause": cause[0], "retryable": cause[3], "page_text": text}
                print(f"PLEX LOGIN FAILED ({reason}) as {user}: cause={cause[0]} retry={cause[3]}: {err}")
                if text:
                    print(f"  page said: {text[:300]}")
                # never re-raise the original: its text may hold the password (a fill() call log)
                raise_it = RuntimeError(f"{cause[0]}: {err}") if cause[3] else LoginFailed(f"{cause[0]}: {err}")
            else:
                rec, raise_it = {"ok": True, "error": None}, None
                print(f"Plex login ok ({reason}) as {user} in "
                      f"{(dt.datetime.now(UTC) - t0).total_seconds():.1f}s")
            rec.update(run_id=self.run_id, attempted_at=t0, reason=reason, user=user,
                       seconds=round((dt.datetime.now(UTC) - t0).total_seconds(), 1),
                       job=os.environ.get("CLOUD_RUN_JOB", "local"),
                       execution=os.environ.get("CLOUD_RUN_EXECUTION", ""),
                       final_url=(pg.url or "").split("?")[0][:500])
            rec["screenshot"] = self.shot(pg, f"login_{'ok' if rec['ok'] else 'FAILED_' + rec.get('cause', '')}")
            self.logins.append(rec)
            if raise_it is not None:
                raise raise_it
        return login

    def save(self, c):
        if self.dry_run or not self.logins:
            return
        cols = ("run_id", "attempted_at", "reason", "user", "ok", "error", "seconds", "final_url",
                "screenshot", "job", "execution")
        try:
            errs = c.insert_rows_json(LOGIN_TABLE, [
                {k: (r[k].isoformat() if isinstance(r.get(k), dt.datetime) else r.get(k)) for k in cols}
                for r in self.logins])
            if errs:
                print(f"plex_login_log insert errors: {errs}")
        except Exception as e:
            print(f"plex_login_log not written: {str(e).splitlines()[0][:200]}")

    def mail_failed_logins(self, c):
        """One email per failure cause per 24 h (a new cause mails at once), to
        LOGIN_ALERT_EMAILS only, with the diagnosis and what to do. Never raises."""
        failed = [r for r in self.logins if not r["ok"]]
        if self.dry_run or not failed or self.logins[-1]["ok"]:
            return  # the last attempt in this run logged in: nothing to fix
        last = failed[-1]
        cause = next((x for x in LOGIN_CAUSES if x[0] == last.get("cause")), None) or (
            classify_login(last.get("error"), last.get("page_text"), last.get("final_url"))
            if last.get("cause") == "timeout_on_signin" else LOGIN_UNKNOWN)
        streak, last_ok = 0, None
        table = os.environ.get("OUTAGE_BREAKER_TABLE") or "PlexOps.etl_dispatch_log"
        try:
            rows = list(c.query(f"""
                SELECT
                  (SELECT MAX(attempted_at) FROM `{LOGIN_TABLE}` WHERE ok) AS last_ok,
                  (SELECT COUNT(DISTINCT run_id) FROM `{LOGIN_TABLE}`
                   WHERE NOT ok AND attempted_at > IFNULL((SELECT MAX(attempted_at) FROM `{LOGIN_TABLE}` WHERE ok),
                                                         TIMESTAMP '2026-01-01')) AS streak,
                  (SELECT COUNT(*) FROM `{PROJECT}.{table}` WHERE reason = 'login-alert'
                     AND detail = CONCAT(@cause, ': sent')
                     AND dispatched_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)) AS mailed""",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("cause", "STRING", cause[0])])).result())[0]
            last_ok, streak, mailed = rows.last_ok, rows.streak, rows.mailed
        except Exception as e:
            print(f"login history unreadable ({str(e).splitlines()[0][:150]}); mailing anyway")
            mailed = 0
        if mailed:
            print(f"failed-login email: already sent for '{cause[0]}' in the last 24 h")
            return
        to = [e.strip() for e in LOGIN_ALERT_EMAILS.split(",") if e.strip()]
        if not to:
            print("failed-login email: LOGIN_ALERT_EMAILS is empty; not sending (it must go to one person only)")
            return
        alert = {
            "headline": f"Plex login failed: {cause[4].rstrip('.')}",
            "summary": (f"{cause[4]} The screens job could not log into Plex's web screens, so this run compared "
                        f"nothing and no report can switch to the screens until it can. "
                        + ("It retried once a minute later and that failed too. " if len(failed) > 1 else "")
                        + ("It did not retry, and it will not try to log in again for 24 h (retrying a rejected "
                           "login can lock the user); after fixing it, start a run with --force-login. "
                           if not cause[3] else "")
                        + f"Logins have failed in {streak or 1} run(s) in a row; the last good one was "
                        + (f"{last_ok.astimezone(DEN):%a %m-%d %H:%M} MT." if last_ok else "never recorded.")),
            "facts": [("Cause", cause[0]),
                      ("Plex said", last.get("page_text") or "(no text on the page)"),
                      ("Error", (last.get("error") or "").split(" | page:")[0])]
                     + [(f"Attempt {r['attempted_at'].astimezone(DEN):%m-%d %H:%M} MT", f"{r.get('cause')} after {r['seconds']} s, "
                         f"page {r['final_url'][:100]}") for r in failed]
                     + [("Screenshot", r["screenshot"]) for r in failed if r["screenshot"]]
                     + [("Execution", last["execution"] or last["job"])],
            "steps": cause[5] + [
                "Then test it: gcloud run jobs execute plex-live-screens --region=us-central1 "
                "--args=python,scripts/screen_recon.py,--force-login",
                "History: SELECT attempted_at, ok, error FROM `voxdatalake.PlexOps.plex_login_log` "
                "ORDER BY attempted_at DESC LIMIT 20"],
            "source": "plex-live-screens"}
        try:
            from email_utils import send_ops_alert
            sent = send_ops_alert(alert, to=to)
            print(f"failed-login email ({cause[0]}): {'sent' if sent else 'not sent (email off)'}")
            c.query(f"""INSERT INTO `{PROJECT}.{table}`
                  (dispatch_id, job_name, mode, reason, dispatched_at, outcome, finished_at, detail)
                VALUES (@id, 'plex-live-screens', 'probe', 'login-alert', CURRENT_TIMESTAMP(), 'alert',
                        CURRENT_TIMESTAMP(), @d)""", job_config=bigquery.QueryJobConfig(query_parameters=[
                bigquery.ScalarQueryParameter("id", "STRING", "login-" + uuid.uuid4().hex[:12]),
                bigquery.ScalarQueryParameter("d", "STRING", f"{cause[0]}: {'sent' if sent else 'not sent'}")])).result()
        except Exception:
            print("failed-login email failed:\n" + traceback.format_exc())


# ── The cycle ─────────────────────────────────────────────────────────────────

def run(args):
    run_id = uuid.uuid4().hex[:12]
    started = dt.datetime.now(UTC)
    today = dt.datetime.now(DEN).date()
    only = args.only or os.environ.get("RECON_ONLY", "").strip()
    names = only.split(",") if only else SCREEN_ORDER
    c = bigquery.Client(project=PROJECT)
    load_portal_secrets()
    audit = Audit(run_id, started, args.dry_run)
    pls.login = audit.wrap_login(pls.login)  # _relogin() inside the fetchers uses it too
    ctx = {"creds": pls.creds(), "bq": lambda: c, "production_begin": screen_since("production", today)}
    prev = previous_counts(c) if not args.dry_run else {}
    fetched, fetch_err, fetch_at, fetch_secs = {}, {}, {}, {}

    suspended = None if (args.dry_run or args.force_login) else login_suspended(c)
    if suspended:
        print(f"Plex login SUSPENDED: {suspended} (start a run with --force-login after fixing it)")
        for n in names:
            fetch_err[n] = f"login suspended: {suspended}"

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        cx = b.new_context()
        pg = cx.new_page()
        try:
            if suspended:
                raise LoginFailed(suspended)
            pls.login(pg, *ctx["creds"])
        except Exception as e:
            last = audit.logins[-1] if audit.logins else {}
            if last.get("retryable") and not isinstance(e, LoginFailed):
                print("  retrying the login once in 60 s on a fresh page")
                time.sleep(60)
                try:
                    cx.close()
                except Exception:
                    pass
                cx = b.new_context()
                pg = cx.new_page()
                try:
                    pls.login(pg, *ctx["creds"])
                    e = None
                except Exception as e2:
                    e = e2
            if e is not None:
                for n in names:
                    fetch_err[n] = f"login failed: {str(e).splitlines()[0][:250]}"
        for n in names:
            if n in fetch_err:
                continue
            print(pls.SCREENS[n][0])
            fetch_at[n] = dt.datetime.now(UTC)
            try:
                rows = pls.SCREENS[n][1](pg, today, ctx)
                if prev.get(n) and len(rows) < SHORT_READ[n] * prev[n] and not short_twice(c, n, len(rows)):
                    raise RuntimeError(f"short read: {len(rows)} rows against {prev[n]} last run")
                fetched[n] = rows
                audit.shot(pg, f"{n}_ok_{len(rows)}rows")
            except Exception as e:
                fetch_err[n] = str(e).splitlines()[0][:300]
                print(f"  FAILED: {fetch_err[n]}")
                audit.shot(pg, f"{n}_FAILED")
            fetch_secs[n] = round((dt.datetime.now(UTC) - fetch_at[n]).total_seconds(), 1)
            print(f"  extraction {n}: {'ok' if n in fetched else 'FAILED'}, "
                  f"{len(fetched.get(n, []))} rows, {fetch_secs[n]}s")
        b.close()
    audit.save(c)
    audit.mail_failed_logins(c)

    conn, odbc_err = None, ""
    try:
        conn = odbc_connect()
    except Exception as e:
        odbc_err = f"ODBC connection failed: {str(e).splitlines()[0][:250]}"
        print(odbc_err)

    recon_rows, diff_rows, snap_rows, summary = [], [], [], {}
    for n in names:
        rec = {"run_id": run_id, "screen": n, "run_started_at": started, "fetch_started_at": fetch_at.get(n),
               "fetch_ok": n in fetched, "fetch_error": fetch_err.get(n), "screen_rows": len(fetched.get(n, [])),
               "fetch_seconds": fetch_secs.get(n), "screenshots": len([s for s in audit.shots if f"_{n}_" in s]),
               "prev_screen_rows": prev.get(n), "odbc_ok": False, "odbc_error": None, "odbc_rows": None,
               "odbc_max_key": None, "odbc_max_time": None, "odbc_lag_min": None, "bq_modified_at": None,
               "verdict": None, "detail": None, "tolerance_min": LAG_TOLERANCE_MIN, "grace_min": GRACE_MIN,
               "live_action": "none", "alert": None, "recorded_at": None}
        if n not in fetched:
            rec["verdict"] = "screens_failed"
            recon_rows.append(rec)
            summary[n] = rec
            continue
        scr = screen_records(n, fetched[n])
        for k, v in scr.items():
            snap_rows.append({"run_id": run_id, "screen": n, "record_key": k, "row_hash": row_hash(v["m"]),
                              "event_time": v["event"], "fetch_started_at": fetch_at[n],
                              "payload": json.dumps(v["m"], sort_keys=True)})
        since = screen_since(n, today)
        try:
            if conn is None:
                raise RuntimeError(odbc_err)
            odbc, max_num, max_ev = odbc_records(conn, n, since)
            rec.update(odbc_ok=True, odbc_rows=len(odbc), odbc_max_key=max_num, odbc_max_time=max_ev)
        except Exception as e:
            rec.update(odbc_error=str(e).splitlines()[0][:300], verdict="odbc_unreachable")
            recon_rows.append(rec)
            summary[n] = rec
            continue
        first_seen = {} if args.dry_run else first_seen_map(c, n, scr)
        prev_extra = frozenset() if args.dry_run else previous_extras(c, n)
        try:
            raw, raw_mod = bq_keys(c, n, since)
        except Exception as e:
            raw, raw_mod = None, None
            print(f"  {n}: BigQuery comparison skipped ({str(e).splitlines()[0][:150]})")
        counts, diffs, verdict, lag, why = compare(n, scr, odbc, max_num, max_ev, first_seen, fetch_at[n],
                                                   prev_extra, raw, raw_mod,
                                                   odbc_newest_change=newest_change(odbc))
        rec.update(counts)
        rec.update(verdict=verdict, odbc_lag_min=lag, bq_modified_at=raw_mod,
                   detail=json.dumps({"why": why[:5], "examples": [
                       {k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in d.items()}
                       for d in diffs[:10]]}, default=str)[:9000])
        for d in diffs[:500]:
            diff_rows.append({"run_id": run_id, "screen": n, "record_key": d["key"], "kind": d["kind"],
                              "field": d["field"], "screen_value": d["screen_value"], "odbc_value": d["odbc_value"],
                              "event_time": d["event_time"], "first_seen_at": d["first_seen_at"],
                              "odbc_updated_at": d["odbc_updated_at"], "age_min": d["age_min"],
                              "recorded_at": started})
        recon_rows.append(rec)
        summary[n] = rec
        print(f"  {n}: {verdict}; lag {lag:.0f} min; " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass

    if args.dry_run:
        for r in recon_rows:
            print(json.dumps({k: r[k] for k in ("screen", "verdict", "odbc_lag_min", "fetch_error", "odbc_error")},
                             default=str))
        return 1 if fetch_err else 0

    now = dt.datetime.now(UTC)
    for r in recon_rows:
        r["recorded_at"] = now
    before = live_source(c)
    insert(c, SNAP_TABLE, snap_rows)
    insert(c, DIFF_TABLE, diff_rows)
    insert(c, RECON_TABLE, recon_rows)
    after = live_source(c)

    actions, push_note = [], ""
    for group, screens in GROUPS.items():
        if not any(s in names for s in screens):
            continue   # not read this run (the hourly releases-only run)
        use = bool(after.get(group, {}).get("use_live"))
        if use:
            if all(s in fetched for s in screens):
                for s in screens:
                    _, _, table, sch, floor = pls.SCREENS[s]
                    rows = [dict(r, loaded_at=started.isoformat()) for r in fetched[s]]
                    try:
                        actions.append(pls.load(c, table, rows, sch, floor, False, today))
                    except Exception as e:
                        actions.append(f"{table}: NOT LOADED: {str(e).splitlines()[0][:200]}")
                if group == "label_design":
                    try:
                        push_note = pls.maybe_start_push(c, live_mode=True)
                    except Exception as e:
                        push_note = f"push: FAILED TO START: {str(e).splitlines()[0][:200]}"
            else:
                actions.append(f"{group}: live mode, but a screen failed; the live tables keep their last load")
        else:
            for s in screens:
                try:
                    actions.append(empty_live(c, s, today))
                except Exception as e:
                    actions.append(f"{LIVE_TABLE[s]}: could not empty: {str(e).splitlines()[0][:200]}")
    for a in actions + ([push_note] if push_note else []):
        print(a)
    for group, screens in GROUPS.items():
        if not any(s in names for s in screens):
            continue
        act = "load" if after.get(group, {}).get("use_live") else "empty"
        try:
            c.query(f"UPDATE `{RECON_TABLE}` SET live_action = @a WHERE run_id = @r AND screen IN UNNEST(@s)",
                    job_config=bigquery.QueryJobConfig(query_parameters=[
                        bigquery.ScalarQueryParameter("a", "STRING", act),
                        bigquery.ScalarQueryParameter("r", "STRING", run_id),
                        bigquery.ArrayQueryParameter("s", "STRING", screens)])).result()
        except Exception as e:
            print(f"live_action not recorded: {str(e).splitlines()[0][:150]}")

    alerts = decide_alerts(c, before, after, summary)
    for kind, alert in alerts:
        sent = send(alert)
        print(f"alert {kind}: {'sent' if sent else 'not sent (email off or failed)'}")
        c.query(f"UPDATE `{RECON_TABLE}` SET alert = IF(alert IS NULL, @k, CONCAT(alert, ',', @k)) "
                f"WHERE run_id = @r AND screen = @s",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("k", "STRING", kind),
                    bigquery.ScalarQueryParameter("r", "STRING", run_id),
                    bigquery.ScalarQueryParameter("s", "STRING", alert["_screen"])])).result()
    took = (dt.datetime.now(UTC) - started).total_seconds()
    send_digest(c, run_id, started, took, summary, audit, after)
    print(f"recon heartbeat run={run_id} took={took:.0f}s logins_ok="
          f"{sum(r['ok'] for r in audit.logins)} logins_failed={sum(not r['ok'] for r in audit.logins)} "
          f"screenshots={len(audit.shots)} " + " ".join(
        f"{n}={summary[n]['verdict']}" for n in names))
    return 1 if fetch_err else 0


# Digests ride the full reads just after ODBC refreshes (~09:00, 13:00, 17:00 MT), since 11-11.
DIGEST_HOURS = {int(h) for h in os.environ.get("RECON_DIGEST_HOURS", "9,13,17").split(",") if h.strip()}


def needs_action(r):
    """A verdict worth a person's look: not a delay under ALERT_LAG_MIN."""
    v = r.get("verdict")
    if v == "current":
        return False
    if v == "behind":
        return (r.get("odbc_lag_min") or 0) > ALERT_LAG_BY_SCREEN.get(r.get("screen"), ALERT_LAG_MIN)
    return True


def send_digest(c, run_id, started, took, summary, audit, after):
    """The screens digest to REPORT_TO_EMAILS: on the RECON_DIGEST_HOURS runs (MT),
    and on another run with a problem (needs_action, a failed login), at most once per
    4 h for those (the hourly releases runs must not mail every hour). Never raises."""
    try:
        problems = sum(1 for r in summary.values() if needs_action(r)) \
            + sum(1 for r in audit.logins if not r["ok"])
        quiet_behind = sum(1 for r in summary.values() if r["verdict"] == "behind" and not needs_action(r))
        scheduled = started.astimezone(DEN).hour in DIGEST_HOURS and len(summary) > 1
        if not scheduled:
            if not problems:
                return
            if alert_sent_recently(c, "digest-problem", hours=4):
                print("screens digest: a problem digest went out in the last 4 h; not repeated")
                return
        try:
            fresh = {r.report_group: dict(r) for r in c.query(
                f"SELECT * FROM `{OPS}.data_freshness` WHERE dataset = 'PlexProd'").result()}
        except Exception:
            fresh = {}
        names = {"label_design": "Label Design", "revenue": "Revenue and shipments"}
        groups = [{"name": names[g], "label": (fresh.get(g) or {}).get("data_label") or "?",
                   "lag": (after.get(g) or {}).get("latest_lag_min")} for g in GROUPS]
        screens = [{"screen": n, "verdict": r["verdict"], "rows": r["screen_rows"], "seconds": r.get("fetch_seconds"),
                    "compared": r.get("compared"), "missing": (r.get("missing_tail") or 0) + (r.get("missing_hole") or 0),
                    "differ": (r.get("status_diff") or 0) + (r.get("value_diff") or 0),
                    "error": r.get("fetch_error") or r.get("odbc_error")} for n, r in summary.items()]
        folder = f"gs://{SCREENSHOT_BUCKET}/{audit.prefix}/" if audit.shots else ""
        # Label Design lines on Monday's way that only the screens have so far
        try:
            lines = [dict(r) for r in c.query(f"""
                SELECT order_number, COUNT(*) n FROM `{PROJECT}.PlexProd.label_design_report`
                WHERE data_source = 'live' GROUP BY 1 ORDER BY 1""").result()]
            screen_lines = (f"{sum(r['n'] for r in lines)} line(s) not in ODBC yet, orders "
                            + ", ".join(str(r["order_number"]) for r in lines[:15])) if lines else "none: ODBC has every line"
        except Exception as e:
            screen_lines = f"? ({str(e).splitlines()[0][:100]})"
        from email_utils import send_screens_digest
        ok = send_screens_digest({"run_id": run_id, "took": took, "problems": problems, "groups": groups,
                                  "quiet_behind": quiet_behind, "alert_lag_min": ALERT_LAG_MIN,
                                  "revenue_alert_lag_min": REVENUE_ALERT_LAG_MIN, "screen_lines": screen_lines,
                                  "screens": screens, "logins_ok": sum(r["ok"] for r in audit.logins),
                                  "logins_failed": sum(not r["ok"] for r in audit.logins), "screenshots": folder})
        print(f"screens digest: {'sent' if ok else 'not sent (email off)'}")
        if ok and not scheduled:
            try:
                c.query(f"UPDATE `{RECON_TABLE}` SET alert = IF(alert IS NULL, 'digest-problem', "
                        f"CONCAT(alert, ',digest-problem')) WHERE run_id = @r",
                        job_config=bigquery.QueryJobConfig(query_parameters=[
                            bigquery.ScalarQueryParameter("r", "STRING", run_id)])).result()
            except Exception as e:
                print(f"digest-problem not recorded: {str(e).splitlines()[0][:150]}")
    except Exception:
        print("screens digest email failed:\n" + traceback.format_exc())


GROUP_TEXT = {
    "label_design": ("Label Design",
                     "Monday keeps getting new lines from the Plex screens within the hour; their reps, "
                     "contact and label details fill in by themselves once ODBC has them."),
    "revenue": ("shipments and revenue",
                "These reports stay on ODBC (not time critical). ODBC normally catches up overnight; "
                "this lag survived that, so the shipping and revenue figures are out of date."),
}


def decide_alerts(c, before, after, summary):
    """Since 2026-11-11 a delay is not news: ODBC runs hours behind most afternoons and
    catches up overnight. Mail when a group needs a person (needs_action: a lag over its
    threshold or a verdict that is not a delay), once a day, and say "caught up" once
    after such a mail. Kinds: odbc-behind:<group>, odbc-caught-up:<group>."""
    out = []
    for group, screens in GROUPS.items():
        recs = [summary[s] for s in screens if s in summary]
        if not recs:
            continue
        name, effect = GROUP_TEXT[group]
        lag = max((r.get("odbc_lag_min") or 0) for r in recs)
        verdicts = ", ".join(f"{r['screen']} {r['verdict']}" for r in recs)
        why = []
        for r in recs:
            try:
                why += json.loads(r.get("detail") or "{}").get("why", [])
            except ValueError:
                pass
        serious = [r for r in recs if needs_action(r) and r["verdict"] not in ("screens_failed", "pipeline_behind")]
        threshold = max(ALERT_LAG_BY_SCREEN.get(r["screen"], ALERT_LAG_MIN) for r in recs)
        if serious:
            if not alert_sent_recently(c, f"odbc-behind:{group}", hours=ALERT_REPEAT_HOURS):
                out.append((f"odbc-behind:{group}", {
                    "_screen": serious[0]["screen"],
                    "headline": f"Plex ODBC is behind or disagrees with the screens: {name}",
                    "summary": (f"The screens check found ODBC {lag / 60:.1f} h behind Plex's screens, past the "
                                f"{threshold / 60:.0f} h line, or disagreeing with them in a way a delay does not "
                                f"explain ({verdicts}). {effect}"),
                    "facts": [("Verdicts", verdicts), ("ODBC lag", f"{lag:.0f} min")] + [("Why", w) for w in why[:5]],
                    "steps": ["If it lasts into tomorrow, tell Plex support (customercare@plex.com) that ODBC "
                              "data is behind the screens, with the times above.",
                              "Check: SELECT * FROM `voxdatalake.PlexOps.screen_recon` ORDER BY run_started_at DESC LIMIT 20"],
                    "source": "plex-live-screens"}))
        elif all(r["verdict"] == "current" for r in recs) \
                and alert_sent_recently(c, f"odbc-behind:{group}", hours=72) \
                and not alert_sent_recently(c, f"odbc-caught-up:{group}", hours=72):
            out.append((f"odbc-caught-up:{group}", {
                "_screen": recs[0]["screen"], "severity": "info",
                "headline": f"Plex ODBC caught up: {name}",
                "summary": "The screens and ODBC agree again. Nothing to do.",
                "facts": [("Verdicts", verdicts)], "source": "plex-live-screens"}))
    for n, r in summary.items():
        if r["verdict"] == "screens_failed":
            kind = f"screens-failed:{n}"
            failed_before = list(c.query(f"""
                SELECT LOGICAL_AND(NOT fetch_ok) bad FROM (
                  SELECT fetch_ok FROM `{RECON_TABLE}` WHERE screen = @s
                  ORDER BY run_started_at DESC LIMIT 2)""",
                job_config=bigquery.QueryJobConfig(query_parameters=[
                    bigquery.ScalarQueryParameter("s", "STRING", n)])).result())[0].bad
            if failed_before and not alert_sent_recently(c, kind):
                out.append((kind, {
                    "_screen": n, "headline": f"Plex screen '{n}' could not be read twice running",
                    "summary": ("The screens job (every 4 h) could not read this Plex screen in its last two runs, so "
                                "it cannot check ODBC against it, and a report already on the screens keeps its "
                                "last load (it falls back to ODBC after 5 h)."),
                    "facts": [("Error", r.get("fetch_error") or "?")],
                    "steps": ["Open the screen in Plex as the portal user; a changed password, a locked user "
                              "or a changed screen are the usual causes.",
                              "gcloud run jobs executions list --job=plex-live-screens --region=us-central1"],
                    "source": "plex-live-screens"}))
        elif r["verdict"] == "pipeline_behind":   # our ETL, not Plex (diverged: the group mail above)
            kind = f"{r['verdict']}:{n}"
            if not alert_sent_recently(c, kind):
                out.append((kind, {
                    "_screen": n,
                    "headline": (f"Plex ODBC disagrees with the '{n}' screen" if r["verdict"] == "diverged"
                                 else f"BigQuery is missing '{n}' records that ODBC has"),
                    "summary": ("Records differ in a way that is not a delay: see the examples. "
                                if r["verdict"] == "diverged" else
                                "ODBC has these records, but the last extraction into BigQuery does not. ")
                               + "Details in PlexOps.screen_recon_diff.",
                    "facts": [("Detail", (r.get("detail") or "")[:600])],
                    "steps": [f"SELECT * FROM `voxdatalake.PlexOps.screen_recon_diff` WHERE run_id = '{r['run_id']}'"],
                    "source": "plex-live-screens"}))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="read and compare only; write and mail nothing")
    ap.add_argument("--only", help="comma-separated screens: " + ", ".join(SCREEN_ORDER))
    ap.add_argument("--force-login", action="store_true",
                    help="log in even though a rejected login in the last 24 h suspended it")
    args = ap.parse_args()
    try:
        code = run(args)
    except Exception:
        print("recon cycle FAILED:\n" + traceback.format_exc())
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
