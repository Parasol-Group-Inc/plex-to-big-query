#!/usr/bin/env python3
"""Watchdog: every 30 minutes, check that every part of the ETL actually ran.

    python watchdog.py              # check, log to PlexOps.watchdog_log, email new problems
    python watchdog.py --dry-run    # check and print only

Cloud Run job `plex-etl-watchdog` (ETL image), Cloud Scheduler every 30 min. Added
2026-11-10 after an audit found failures nobody was told about: the weekly backup
had never worked, the manual-data push had stopped, and Plex ODBC served frozen data
while every run reported success. Runbook: docs/OPERATIONS.md, "Watchdog and screen
reconciliation".

Each check returns problems; each problem is logged in PlexOps.watchdog_log and
emailed at most once per 24 h per check (one email lists every new problem). The
watchdog needs no Plex connection. It prints `watchdog heartbeat ok=<n> fail=<m>`
on every pass; a Cloud Monitoring alert (Terraform) emails through Google, not
SendGrid, when that line stops, so a dead watchdog or a dead SendGrid is caught too.
A check that errors is itself a problem ("check broken"), never a silent pass.
"""
import argparse
import datetime as dt
import os
import sys
import traceback
import uuid
from zoneinfo import ZoneInfo

from google.cloud import bigquery

PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
REGION = os.environ.get("GCP_REGION", "us-central1")
LOG_TABLE = f"{PROJECT}.PlexOps.watchdog_log"
DEN = ZoneInfo("America/Denver")
UTC = dt.timezone.utc
REPEAT_HOURS = 24

# Raw tables that legitimately stop changing (orphans).
# (No manual-data check: the live app, deploy/manual_data_app_v2, writes to BigQuery only
# when someone saves, so an old table is not a fault. Removed 2026-11-10, see D34.)
STALE_RAW_ALLOW = {"raw_materials_parts"}

# ODBC health (2026-11-11). That morning ODBC served data frozen at 11-10 16:10 MT until
# ~10:00 and refused 6 sessions, and nobody was mailed: the stale-data alert only looks
# 9-5 inside a run that connected, and the outage alert waits for 6 h of failures. These
# two checks measure from outside the ETL:
#   odbc_connect  - 3 of the last 4 Label Design runs (every 15 min, weekdays) could not
#                   connect ("ODBC connection failed").
#   odbc_vs_plex  - Plex's own REST API (connect.plex.com, read-only, ~1 s) has order
#                   changes our copy of ODBC lacks, the oldest over ODBC_PLEX_LAG_MIN old.
#                   Plex is quiet overnight, so this only fires when work happened and
#                   ODBC did not deliver it. Docs: docs/ODBC_VS_SCREENS.md.
ODBC_PLEX_LAG_MIN = int(os.environ.get("ODBC_PLEX_LAG_MIN", "120"))
PLEX_API_BASE = os.environ.get("PLEX_API_BASE", "https://connect.plex.com")
PLEX_API_SECRETS = (os.environ.get("SECRET_PLEX_API_CONSUMER_KEY", "plex-api-consumer-key"),
                    os.environ.get("SECRET_PLEX_API_CONSUMER_SECRET", "plex-api-consumer-secret"))
# Schedulers that are paused on purpose (none of the plex-* ones today).
PAUSED_OK = {"monday-daily-sync"}


def q(c, sql, **params):
    cfg = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter(k, "STRING" if isinstance(v, str) else "INT64", v)
        for k, v in params.items()])
    return list(c.query(sql, job_config=cfg).result())


def work_hours(now_mt, start=(5, 30), end=(17, 45)):
    t = (now_mt.hour, now_mt.minute)
    return now_mt.weekday() < 5 and start <= t < end


# ── Checks: each (c, now_mt) -> list of problem strings ──────────────────────

def check_dispatch_missed(c, now_mt):
    rows = q(c, f"""
        WITH s AS (
          SELECT job_name, TIMESTAMP(DATETIME(d, PARSE_TIME('%H:%M', run_time)), 'America/Denver') slot
          FROM `{PROJECT}.PlexOps.etl_schedule`,
               UNNEST([CURRENT_DATE('America/Denver'), DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)]) d
          WHERE enabled)
        SELECT s.job_name, s.slot FROM s
        LEFT JOIN `{PROJECT}.PlexOps.etl_dispatch_log` l
          ON l.job_name = s.job_name AND l.scheduled_for = s.slot
        WHERE s.slot BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                         AND TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 35 MINUTE)
          AND l.dispatch_id IS NULL
        ORDER BY s.slot""")
    if not rows:
        return []
    first = rows[0]
    return [f"{len(rows)} scheduled prod run(s) never dispatched in 24 h (first: {first.job_name} at "
            f"{first.slot.astimezone(DEN):%m-%d %H:%M} MT). The etl-dispatcher function or its scheduler is not working."]


def check_dispatch_stuck(c, now_mt):
    rows = q(c, f"""
        SELECT job_name, dispatched_at FROM `{PROJECT}.PlexOps.etl_dispatch_log`
        WHERE outcome IS NULL AND dispatched_at < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 150 MINUTE)
          AND dispatched_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 DAY)""")
    return [f"{len(rows)} dispatched run(s) still open after 150 min (e.g. {rows[0].job_name}); the dispatcher "
            f"should have closed them as lost at 120 min, so it is not ticking."] if rows else []


def check_label_design_running(c, now_mt):
    if not work_hours(now_mt):
        return []
    r = q(c, f"""
        SELECT MAX(logged_at) t FROM `{PROJECT}.PlexProd.job_run_log`
        WHERE report_name = 'label_design' AND job_name NOT LIKE '%test%'""")[0]
    if r.t is None or r.t < dt.datetime.now(UTC) - dt.timedelta(minutes=40):
        return [f"Label Design has not finished a run since {r.t.astimezone(DEN):%m-%d %H:%M} MT "
                f"(it runs every 15 min, Mon-Fri 5 AM-5:45 PM). Runs killed by the timeout leave no log row."
                if r.t else "Label Design has never logged a run."]
    return []


def check_label_design_pending(c, now_mt, prev):
    """Lines in label_design_report not on Monday, in two watchdog passes running."""
    if not work_hours(now_mt):
        return []
    n = q(c, f"""
        SELECT COUNT(*) n FROM (
          SELECT SUBSTR(TO_HEX(SHA256(v.dedupe_key)), 1, 12) lcr FROM `{PROJECT}.PlexProd.label_design_report` v) cand
        LEFT JOIN (SELECT DISTINCT a.lcr FROM `{PROJECT}.PlexProd.label_design_push_log` a
                   WHERE a.outcome IN ('created', 'partial')) seen ON seen.lcr = cand.lcr
        WHERE seen.lcr IS NULL""")[0].n
    if n and prev.get("label_design_pending"):
        return [f"{n} Label Design line(s) have been in the report but not on the Monday board for 30+ min."]
    return [f"pending:{n}"] if n else []


def check_screens_job(c, now_mt):
    r = q(c, f"SELECT MAX(run_started_at) t FROM `{PROJECT}.PlexOps.screen_recon`")[0]
    if r.t is None or r.t < dt.datetime.now(UTC) - dt.timedelta(minutes=300):
        return [f"The Plex screens job (every 4 h) (plex-live-screens) has not recorded a run since "
                f"{r.t.astimezone(DEN):%m-%d %H:%M} MT. Without it nothing compares ODBC with the screens."
                if r.t else "The Plex screens job has never recorded a run."]
    bad = q(c, f"""
        SELECT screen, COUNTIF(NOT fetch_ok) failed, COUNT(*) n FROM (
          SELECT screen, fetch_ok, ROW_NUMBER() OVER (PARTITION BY screen ORDER BY run_started_at DESC) rn
          FROM `{PROJECT}.PlexOps.screen_recon`
          WHERE run_started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY))
        WHERE rn <= 2 GROUP BY screen HAVING failed = n AND n >= 2""")
    return [f"Plex screen '{b.screen}' failed in its last {b.n} runs." for b in bad]


def connect_failures(rows):
    """rows: the last Label Design runs, newest first, each (status, detail, started_at).
    Returns (failed, looked_at, first_failed_at, error) for the newest 4."""
    last = rows[:4]
    bad = [r for r in last if r[0] == "failed" and (r[1] or "").startswith("ODBC connection failed")]
    first = min((r[2] for r in bad), default=None)
    return len(bad), len(last), first, (bad[0][1] if bad else "")


def check_odbc_connect(c, now_mt):
    if not work_hours(now_mt):
        return []
    rows = [(r.status, r.detail, r.started_at) for r in q(c, f"""
        SELECT status, detail, started_at FROM `{PROJECT}.PlexProd.job_run_log`
        WHERE report_name = 'label_design' AND job_name NOT LIKE '%test%'
          AND started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 MINUTE)
        ORDER BY started_at DESC LIMIT 4""")]
    n, of, first, err = connect_failures(rows)
    if of >= 4 and n >= 3:
        return [f"Plex ODBC refused {n} of the last {of} Label Design runs (since "
                f"{first.astimezone(DEN):%H:%M} MT): {err[:160]}. The ETL cannot read Plex; Label Design "
                f"still gets new lines from the Plex screens. If it lasts, tell Plex support (OPEN_ITEMS D33)."]
    return []


def odbc_plex_lag(changes, odbc_newest, now, slack_min=5):
    """changes: Plex REST modification times (UTC). odbc_newest: newest change in our ODBC
    copy. Returns (lag_min, unseen_count, oldest_unseen): how long the oldest Plex change
    our copy lacks has been waiting. Pure."""
    if odbc_newest is None:
        return None, 0, None
    unseen = sorted(t for t in changes if t > odbc_newest + dt.timedelta(minutes=slack_min))
    if not unseen:
        return 0.0, 0, None
    return round((now - unseen[0]).total_seconds() / 60, 1), len(unseen), unseen[0]


def _plex_api_orders():
    import json
    import urllib.request
    from google.cloud import secretmanager
    sm = secretmanager.SecretManagerServiceClient()
    key, sec = (sm.access_secret_version(request={"name": f"projects/{PROJECT}/secrets/{n}/versions/latest"})
                .payload.data.decode("utf-8").strip() for n in PLEX_API_SECRETS)
    req = urllib.request.Request(f"{PLEX_API_BASE}/sales/v1/orders", method="GET", headers={
        "X-Plex-Connect-Api-Key": key, "X-Plex-Connect-Api-Secret": sec, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def check_odbc_vs_plex(c, now_mt):
    r = q(c, f"""SELECT odbc_data_as_of t, odbc_loaded_at l FROM `{PROJECT}.PlexOps.data_freshness`
                 WHERE dataset = 'PlexProd' AND report_group = 'label_design'""")
    odbc_newest = r[0].t if r else None
    try:
        orders = _plex_api_orders()
    except Exception as e:   # the API being down is not an ODBC problem; say so, do not fail
        print(f"  odbc_vs_plex: Plex REST API unreachable ({type(e).__name__}: {str(e)[:150]}); skipped")
        return []
    changes = []
    for o in orders:
        m = o.get("modifiedDate")
        if m:
            try:
                changes.append(dt.datetime.fromisoformat(m.replace("Z", "+00:00")))
            except ValueError:
                pass
    lag, n, oldest = odbc_plex_lag(changes, odbc_newest, dt.datetime.now(UTC))
    if lag is not None and lag > ODBC_PLEX_LAG_MIN:
        return [f"Our Plex order data is {lag / 60:.1f} h behind Plex: Plex's API shows {n} order change(s) "
                f"since {oldest.astimezone(DEN):%m-%d %H:%M} MT that ODBC has not delivered (our newest is "
                f"{odbc_newest.astimezone(DEN):%m-%d %H:%M} MT, loaded {r[0].l.astimezone(DEN):%m-%d %H:%M}). "
                f"Every report built on ODBC is that far behind; Label Design takes new lines from the screens. "
                f"If ODBC also connects fine, it is serving frozen data: tell Plex support (OPEN_ITEMS D33)."]
    return []


def check_raw_freshness(c, now_mt):
    rows = q(c, f"""
        SELECT table_id, TIMESTAMP_MILLIS(last_modified_time) m, row_count
        FROM `{PROJECT}.PlexProd.__TABLES__`
        WHERE STARTS_WITH(table_id, 'raw_') AND row_count > 0
          AND TIMESTAMP_MILLIS(last_modified_time) < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 HOUR)""")
    rows = [r for r in rows if r.table_id not in STALE_RAW_ALLOW]
    if not rows:
        return []
    names = ", ".join(r.table_id for r in rows[:8]) + (" ..." if len(rows) > 8 else "")
    return [f"{len(rows)} raw table(s) not refreshed in 30 h although they hold rows: {names}. "
            f"Plex returned 0 rows (the ETL keeps yesterday's) or the extraction stopped."]


def check_msl_daily(c, now_mt):
    if (now_mt.hour, now_mt.minute) < (7, 30):
        return []
    r = q(c, f"""
        SELECT COUNTIF(snapshot_date = CURRENT_DATE('America/Denver')) n
        FROM `{PROJECT}.PlexProd.msl_demand_daily`
        WHERE snapshot_date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 2 DAY)""")[0]
    return [] if r.n else ["PlexProd.msl_demand_daily has no row for today (scheduled query msl_demand_daily, 6 AM MT)."]


def check_usage_monthly(c, now_mt):
    """From the 2nd of each month, last month must be in part_usage_monthly (the
    scheduled query part_usage_monthly runs on the 1st, 13:30 UTC)."""
    if now_mt.day < 2:
        return []
    last_month = (now_mt.date().replace(day=1) - dt.timedelta(days=1)).replace(day=1)
    n = q(c, f"SELECT COUNT(*) n FROM `{PROJECT}.PlexProd.part_usage_monthly` WHERE usage_month = DATE(@m)",
          m=last_month.isoformat())[0].n
    return [] if n else [f"Monthly part usage for {last_month:%Y-%m} was not recorded (scheduled query "
                         f"part_usage_monthly failed, or the month had no production records)."]


def check_backups(c, now_mt):
    """A full weekly snapshot set (20+ tables with the same _YYYYMMDD stamp, live_* backups
    not counted) dated within the last 8 days. A hand run on another day counts too."""
    rows = q(c, f"""
        SELECT REGEXP_EXTRACT(table_id, r'_(\\d{{8}})$') AS stamp, COUNT(*) AS n
        FROM `{PROJECT}.Backups.__TABLES__`
        WHERE REGEXP_CONTAINS(table_id, r'_\\d{{8}}$') AND NOT STARTS_WITH(table_id, 'PlexProd__live_')
        GROUP BY stamp ORDER BY stamp DESC""")
    since = (now_mt.date() - dt.timedelta(days=8)).strftime("%Y%m%d")
    full = [r for r in rows if r.stamp and r.stamp >= since and r.n >= 20]
    if full:
        return []
    last = rows[0] if rows else None
    return [f"No full weekly backup in Backups in the last 8 days (newest set: "
            f"{(last.stamp + ' with ' + str(last.n) + ' tables') if last else 'none'}; expect ~32). "
            f"The scheduled query backup_snapshots_weekly failed."]


def check_test_cascade(c, now_mt):
    if now_mt.hour < 7:
        return []
    since = dt.datetime.combine(now_mt.date() - dt.timedelta(days=1), dt.time(19, 0), DEN)
    rows = q(c, f"""
        SELECT COUNT(DISTINCT job_name) n FROM `{PROJECT}.PlexTest.job_run_log`
        WHERE job_name LIKE '%-test' AND logged_at >= TIMESTAMP(@s)""", s=since.isoformat())
    return [] if rows[0].n >= 12 else [f"Only {rows[0].n} test job(s) logged a run since 7 PM yesterday (expect 15)."]


def _run_api(path):
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    cred, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    r = AuthorizedSession(cred).get(path, timeout=60)
    r.raise_for_status()
    return r.json()


def check_schedulers(c, now_mt):
    data = _run_api(f"https://cloudscheduler.googleapis.com/v1/projects/{PROJECT}/locations/{REGION}/jobs?pageSize=500")
    out = []
    for j in data.get("jobs", []):
        name = j["name"].rsplit("/", 1)[-1]
        if j.get("state") != "ENABLED" and name not in PAUSED_OK:
            out.append(f"Cloud Scheduler job {name} is {j.get('state')}.")
        st = j.get("status") or {}
        last = j.get("lastAttemptTime")
        if st.get("code") and last and dt.datetime.fromisoformat(last.replace("Z", "+00:00")) > \
                dt.datetime.now(UTC) - dt.timedelta(hours=2):
            out.append(f"Cloud Scheduler job {name}: last attempt failed (code {st['code']}).")
    return out


def check_image_drift(c, now_mt):
    data = _run_api(f"https://run.googleapis.com/v2/projects/{PROJECT}/locations/{REGION}/jobs?pageSize=200")
    shas = {}
    for j in data.get("jobs", []):
        name = j["name"].rsplit("/", 1)[-1]
        img = j["template"]["template"]["containers"][0]["image"]
        if "/plex-pipeline/" in img:
            shas.setdefault(img.rsplit(":", 1)[-1], []).append(name)
    if len(shas) <= 1:
        return []
    main_sha = max(shas, key=lambda s: len(shas[s]))
    odd = [f"{n} ({s})" for s, ns in shas.items() if s != main_sha for n in ns]
    return [f"Jobs on a different build than {main_sha}: {', '.join(odd[:8])}."]


CHECKS = [
    ("dispatch_missed", check_dispatch_missed),
    ("dispatch_stuck", check_dispatch_stuck),
    ("label_design_running", check_label_design_running),
    ("label_design_pending", None),  # needs the previous pass
    ("screens_job", check_screens_job),
    ("odbc_connect", check_odbc_connect),
    ("odbc_vs_plex", check_odbc_vs_plex),
    ("raw_freshness", check_raw_freshness),
    ("msl_daily", check_msl_daily),
    ("usage_monthly", check_usage_monthly),
    ("backups", check_backups),
    ("test_cascade", check_test_cascade),
    ("schedulers", check_schedulers),
    ("image_drift", check_image_drift),
]


def previous_state(c):
    rows = q(c, f"""
        SELECT check_id, ARRAY_AGG(STRUCT(ok, detail) ORDER BY checked_at DESC LIMIT 1)[OFFSET(0)] last
        FROM `{LOG_TABLE}` WHERE checked_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 50 MINUTE)
        GROUP BY check_id""")
    return {r.check_id: (not r.last["ok"]) or (r.last["detail"] or "").startswith("pending:") for r in rows}


def alerted_recently(c):
    rows = q(c, f"""
        SELECT DISTINCT check_id FROM `{LOG_TABLE}`
        WHERE alerted AND checked_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {REPEAT_HOURS} HOUR)""")
    return {r.check_id for r in rows}


def run(dry_run=False):
    c = bigquery.Client(project=PROJECT)
    now_mt = dt.datetime.now(DEN)
    run_id = uuid.uuid4().hex[:12]
    prev = {} if dry_run else previous_state(c)
    results = []
    for cid, fn in CHECKS:
        try:
            probs = check_label_design_pending(c, now_mt, prev) if cid == "label_design_pending" else fn(c, now_mt)
            info = [p for p in probs if p.startswith("pending:")]
            probs = [p for p in probs if not p.startswith("pending:")]
            results.append((cid, not probs, "; ".join(probs) or (info[0] if info else "")))
        except Exception as e:
            results.append((cid, False, f"check broken: {str(e).splitlines()[0][:300]}"))
    failing = [(cid, d) for cid, ok, d in results if not ok]
    for cid, ok, d in results:
        print(f"  {'ok  ' if ok else 'FAIL'} {cid}: {d}")
    if dry_run:
        print(f"watchdog dry run ok={len(results) - len(failing)} fail={len(failing)}")
        return 0
    already = alerted_recently(c)
    new = [(cid, d) for cid, d in failing if cid not in already]
    sent = False
    if new:
        try:
            from email_utils import send_ops_alert
            sent = send_ops_alert({
                "headline": (f"Watchdog: {new[0][1][:90]}" if len(new) == 1
                             else f"Watchdog: {len(new)} problems in the Plex ETL"),
                "summary": ("The watchdog checks every 30 minutes that each part of the ETL ran and that its "
                            "data is current. These problems are new in the last 24 hours:"),
                "facts": [(cid, d) for cid, d in new] + [("Still failing (already mailed)", cid)
                                                         for cid, _ in failing if cid in already],
                "steps": ["Each line names what stopped; the runbook lists the usual cause and fix per check.",
                          "History: SELECT * FROM `voxdatalake.PlexOps.watchdog_log` WHERE NOT ok "
                          "ORDER BY checked_at DESC LIMIT 50"],
                "source": "plex-etl-watchdog"})
        except Exception:
            print("watchdog email failed:\n" + traceback.format_exc())
    now = dt.datetime.now(UTC).isoformat()
    newset = {cid for cid, _ in new}
    rows = [{"run_id": run_id, "checked_at": now, "check_id": cid, "ok": ok, "detail": d[:2000],
             "alerted": bool(sent and cid in newset)} for cid, ok, d in results]
    errs = c.insert_rows_json(LOG_TABLE, rows)
    if errs:
        print(f"watchdog_log insert errors: {errs}")
    print(f"watchdog heartbeat ok={len(results) - len(failing)} fail={len(failing)} "
          f"new={len(new)} email={'sent' if sent else 'none'}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try:
        sys.exit(run(args.dry_run))
    except Exception:
        print("watchdog FAILED:\n" + traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
