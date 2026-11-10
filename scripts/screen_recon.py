#!/usr/bin/env python3
"""Every 4 hours: read Plex's live screens, compare them with ODBC and BigQuery, and
switch reports to the screens only while ODBC is behind or disagrees.

    python scripts/screen_recon.py                 # full cycle (the Cloud Run job)
    python scripts/screen_recon.py --dry-run       # read and compare; write nothing, mail nothing
    python scripts/screen_recon.py --only releases

Runs as the Cloud Run job `plex-live-screens` (Dockerfile.screens), every 4 hours. Runbook:
docs/PLEX_SCREEN_EXTRACTION.md, "Reconciliation (cloud job)". Design: 2026-11-10,
after Plex ODBC served data frozen 08:10-12:50 MT while every run succeeded.

One cycle:
  1. Read the four screens (plex_live_screens.py fetchers). Production: only the
     last RECON_PRODUCTION_DAYS days.
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
     to read the screens: yes after one bad run, no after RECON_CLEAN_RUNS clean
     runs. When yes, load that group's PlexProd.live_* tables (and start the Label
     Design push); when no, back up and empty them (the D30 lesson).
  7. Email a change of state (a group going live or back to ODBC), and a screen
     that failed twice running. Each at most once per 24 h per kind.
Exit: 0 when every screen got a verdict, 1 when a screen failed or the cycle broke.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
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
                    or (s["event"] is not None and odbc_max_event is not None and s["event"] > odbc_max_event)
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
    if persistent and lag <= tolerance_min:
        diverged.append(f"{len(persistent)} record(s) in ODBC but not on the screen in two runs, e.g. {persistent[0]}")
    if raw is not None and raw_modified is not None:
        for key, o in odbc.items():
            t = o["event"] or o["updated"]
            if o["eligible"] and key not in raw and t and t < raw_modified - dt.timedelta(minutes=grace_min):
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
                err = str(e).splitlines()[0][:500]
                rec = {"ok": False, "error": err}
                print(f"PLEX LOGIN FAILED ({reason}) as {user}: {err}")
                raise_it = e
            else:
                rec, raise_it = {"ok": True, "error": None}, None
                print(f"Plex login ok ({reason}) as {user} in "
                      f"{(dt.datetime.now(UTC) - t0).total_seconds():.1f}s")
            rec.update(run_id=self.run_id, attempted_at=t0, reason=reason, user=user,
                       seconds=round((dt.datetime.now(UTC) - t0).total_seconds(), 1),
                       job=os.environ.get("CLOUD_RUN_JOB", "local"),
                       execution=os.environ.get("CLOUD_RUN_EXECUTION", ""),
                       final_url=(pg.url or "").split("?")[0][:500])
            rec["screenshot"] = self.shot(pg, f"login_{'ok' if rec['ok'] else 'FAILED'}")
            self.logins.append(rec)
            if raise_it is not None:
                raise raise_it
        return login

    def save(self, c):
        if self.dry_run or not self.logins:
            return
        try:
            errs = c.insert_rows_json(LOGIN_TABLE, [
                {k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in r.items()}
                for r in self.logins])
            if errs:
                print(f"plex_login_log insert errors: {errs}")
        except Exception as e:
            print(f"plex_login_log not written: {str(e).splitlines()[0][:200]}")

    def mail_failed_logins(self):
        failed = [r for r in self.logins if not r["ok"]]
        if self.dry_run or not failed:
            return
        to = [e.strip() for e in LOGIN_ALERT_EMAILS.split(",") if e.strip()]
        alert = {
            "headline": f"Plex login failed ({len(failed)} attempt{'s' if len(failed) > 1 else ''})",
            "summary": ("The screens job could not log into Plex's web screens as the portal user. Until it "
                        "can, nothing compares ODBC with the screens and no report can switch to them. A wrong "
                        "or expired password, a locked user or a changed login page are the usual causes."),
            "facts": [(f"{r['attempted_at'].astimezone(DEN):%m-%d %H:%M} MT ({r['reason']})",
                       f"{r['error']} | after {r['seconds']} s | page {r['final_url'][:120]}") for r in failed]
                     + [("Screenshot", r["screenshot"]) for r in failed if r["screenshot"]]
                     + [("Execution", failed[0]["execution"] or failed[0]["job"])],
            "steps": ["Log into https://vox.on.plex.com as the portal user by hand to see what Plex shows.",
                      "If the password changed: printf '%s' \"$NEW\" | gcloud secrets versions add "
                      "plex-portal-password --data-file=-",
                      "History: SELECT * FROM `voxdatalake.PlexOps.plex_login_log` ORDER BY attempted_at DESC"],
            "source": "plex-live-screens"}
        try:
            from email_utils import send_ops_alert
            print(f"failed-login email: {'sent' if send_ops_alert(alert, to=to or None) else 'not sent'}")
        except Exception:
            print("failed-login email failed:\n" + traceback.format_exc())


# ── The cycle ─────────────────────────────────────────────────────────────────

def run(args):
    run_id = uuid.uuid4().hex[:12]
    started = dt.datetime.now(UTC)
    today = dt.datetime.now(DEN).date()
    names = args.only.split(",") if args.only else SCREEN_ORDER
    c = bigquery.Client(project=PROJECT)
    load_portal_secrets()
    audit = Audit(run_id, started, args.dry_run)
    pls.login = audit.wrap_login(pls.login)  # _relogin() inside the fetchers uses it too
    ctx = {"creds": pls.creds(), "bq": lambda: c, "production_begin": screen_since("production", today)}
    prev = previous_counts(c) if not args.dry_run else {}
    fetched, fetch_err, fetch_at, fetch_secs = {}, {}, {}, {}

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context().new_page()
        try:
            pls.login(pg, *ctx["creds"])
        except Exception as e:
            for n in names:
                fetch_err[n] = f"login failed: {str(e).splitlines()[0][:250]}"
        for n in names:
            if n in fetch_err:
                continue
            print(pls.SCREENS[n][0])
            fetch_at[n] = dt.datetime.now(UTC)
            try:
                rows = pls.SCREENS[n][1](pg, today, ctx)
                if prev.get(n) and len(rows) < SHORT_READ[n] * prev[n]:
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
    audit.mail_failed_logins()

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


DIGEST_HOURS = {int(h) for h in os.environ.get("RECON_DIGEST_HOURS", "8,12,16").split(",") if h.strip()}


def send_digest(c, run_id, started, took, summary, audit, after):
    """The screens digest to REPORT_TO_EMAILS: on the RECON_DIGEST_HOURS runs (MT),
    and on any run with a problem (a verdict other than current, a failed login).
    Never raises."""
    try:
        problems = sum(1 for r in summary.values() if r["verdict"] != "current") \
            + sum(1 for r in audit.logins if not r["ok"])
        if started.astimezone(DEN).hour not in DIGEST_HOURS and not problems:
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
        from email_utils import send_screens_digest
        ok = send_screens_digest({"run_id": run_id, "took": took, "problems": problems, "groups": groups,
                                  "screens": screens, "logins_ok": sum(r["ok"] for r in audit.logins),
                                  "logins_failed": sum(not r["ok"] for r in audit.logins), "screenshots": folder})
        print(f"screens digest: {'sent' if ok else 'not sent (email off)'}")
    except Exception:
        print("screens digest failed:\n" + traceback.format_exc())


def decide_alerts(c, before, after, summary):
    out = []
    for group, screens in GROUPS.items():
        was, now = bool(before.get(group, {}).get("use_live")), bool(after.get(group, {}).get("use_live"))
        recs = [summary[s] for s in screens if s in summary]
        if not recs:
            continue
        lag = max((r.get("odbc_lag_min") or 0) for r in recs)
        verdicts = ", ".join(f"{r['screen']} {r['verdict']}" for r in recs)
        why = []
        for r in recs:
            try:
                why += json.loads(r.get("detail") or "{}").get("why", [])
            except ValueError:
                pass
        if now != was and alert_sent_recently(c, f"live-{'on' if now else 'off'}:{group}", hours=8):
            continue  # flapping: one mail per direction per 8 h
        if now and not was:
            out.append((f"live-on:{group}", {
                "_screen": recs[0]["screen"],
                "headline": f"Plex ODBC is behind the screens: {group.replace('_', ' ')} now reads the screens",
                "summary": (f"The screens check found ODBC {lag / 60:.1f} h behind Plex's screens, or "
                            f"disagreeing with them ({verdicts}). The {group.replace('_', ' ')} report now reads "
                            f"the screens and goes back to ODBC by itself after {CLEAN_RUNS} clean checks (4 h apart). "
                            f"Nothing to start by hand."),
                "facts": [("Verdicts", verdicts), ("ODBC lag", f"{lag:.0f} min")] + [("Why", w) for w in why[:5]],
                "steps": ["Tell Plex support (customercare@plex.com) that ODBC data is behind the screens, "
                          "with the time above, if it lasts more than a few hours.",
                          "Check: SELECT * FROM `voxdatalake.PlexOps.screen_recon` ORDER BY run_started_at DESC LIMIT 20"],
                "source": "plex-live-screens"}))
        elif was and not now:
            out.append((f"live-off:{group}", {
                "_screen": recs[0]["screen"], "severity": "info",
                "headline": f"Plex ODBC caught up: {group.replace('_', ' ')} is back on ODBC",
                "summary": f"{CLEAN_RUNS} clean comparisons in a row. The live table was backed up and emptied.",
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
        elif r["verdict"] in ("diverged", "pipeline_behind"):
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
    args = ap.parse_args()
    try:
        code = run(args)
    except Exception:
        print("recon cycle FAILED:\n" + traceback.format_exc())
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
