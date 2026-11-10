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

# Raw tables that legitimately stop changing (orphans), and the BigQuery-only
# tables the manual-data app writes every hour (deploy/manual_data_app/Push.gs).
STALE_RAW_ALLOW = {"raw_materials_parts"}
MANUAL_TABLES = ["scorecard_goals_app", "safety_incidents"]
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
    if r.t is None or r.t < dt.datetime.now(UTC) - dt.timedelta(minutes=150):
        return [f"The hourly Plex screens job (plex-live-screens) has not recorded a run since "
                f"{r.t.astimezone(DEN):%m-%d %H:%M} MT. Without it nothing compares ODBC with the screens."
                if r.t else "The Plex screens job has never recorded a run."]
    bad = q(c, f"""
        SELECT screen, COUNTIF(NOT fetch_ok) failed, COUNT(*) n FROM (
          SELECT screen, fetch_ok, ROW_NUMBER() OVER (PARTITION BY screen ORDER BY run_started_at DESC) rn
          FROM `{PROJECT}.PlexOps.screen_recon`
          WHERE run_started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY))
        WHERE rn <= 4 GROUP BY screen HAVING failed = n AND n >= 4""")
    return [f"Plex screen '{b.screen}' failed in its last {b.n} runs." for b in bad]


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


def check_backups(c, now_mt):
    monday = now_mt.date() - dt.timedelta(days=now_mt.weekday())
    if now_mt.date() == monday and now_mt.hour < 2:
        monday -= dt.timedelta(days=7)  # the Monday run is at 06:00 UTC (~midnight MT)
    stamp = monday.strftime("%Y%m%d")
    n = q(c, f"SELECT COUNT(*) n FROM `{PROJECT}.Backups.__TABLES__` WHERE ENDS_WITH(table_id, @s)",
          s=f"_{stamp}")[0].n
    return [] if n >= 20 else [f"Weekly backup for {monday} has {n} snapshot(s) in Backups (expect ~32). "
                               f"The scheduled query backup_snapshots_weekly failed."]


def check_manual_data(c, now_mt):
    rows = q(c, f"""
        SELECT table_id, TIMESTAMP_MILLIS(last_modified_time) m FROM `{PROJECT}.PlexProd.__TABLES__`
        WHERE table_id IN UNNEST(@t)
          AND TIMESTAMP_MILLIS(last_modified_time) < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 HOUR)"""
             .replace("@t", "[" + ",".join(f"'{t}'" for t in MANUAL_TABLES) + "]"))
    return [f"Manual data not reaching BigQuery: {r.table_id} last loaded {r.m.astimezone(DEN):%m-%d %H:%M} MT "
            f"(the app's hourly pushAll trigger should reload it every hour)." for r in rows]


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
    ("raw_freshness", check_raw_freshness),
    ("msl_daily", check_msl_daily),
    ("backups", check_backups),
    ("manual_data", check_manual_data),
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
