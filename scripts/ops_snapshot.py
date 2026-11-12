#!/usr/bin/env python3
"""One read-only snapshot of the ETL and the Plex screens: the big picture and the details.

    python scripts/ops_snapshot.py                 # print it
    python scripts/ops_snapshot.py --log ~/plex-monitor   # also append to <dir>/YYYY-MM-DD.log

Reads BigQuery only (works as claude-readonly); writes nothing to Google Cloud.
Ends with a FLAGS line: what a person should look at, or "none". Added 2026-11-11 for
the hourly monitoring Emilio asked for; the rules it checks are docs/ODBC_VS_SCREENS.md.
"""
import argparse
import datetime as dt
import os
import sys
from zoneinfo import ZoneInfo

from google.cloud import bigquery

P = "voxdatalake"
DEN = ZoneInfo("America/Denver")
flags, out = [], []


def say(s=""):
    out.append(s)


def q(c, sql):
    try:
        return [dict(r) for r in c.query(sql).result()]
    except Exception as e:
        flags.append(f"query failed: {str(e).splitlines()[0][:120]}")
        return []


def mt(t):
    return t.astimezone(DEN).strftime("%m-%d %H:%M") if t else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", help="directory to append the snapshot to (one file per MT day)")
    args = ap.parse_args()
    c = bigquery.Client(project=P)
    now = dt.datetime.now(dt.timezone.utc)
    say(f"=== Plex ETL + screens snapshot {now.astimezone(DEN):%Y-%m-%d %H:%M} MT ===")

    # ── Prod dispatcher: today's runs ───────────────────────────────────────────
    d = q(c, f"""SELECT outcome, COUNT(*) n FROM `{P}.PlexOps.etl_dispatch_log`
        WHERE DATE(dispatched_at, 'America/Denver') = CURRENT_DATE('America/Denver')
          AND reason IN ('schedule', 'followup', 'recovery') GROUP BY 1 ORDER BY 2 DESC""")
    say("Prod runs today: " + (", ".join(f"{r['outcome'] or 'running'} {r['n']}" for r in d) or "none yet"))
    bad = q(c, f"""SELECT job_name, mode, reason, outcome, dispatched_at, LEFT(IFNULL(detail, ''), 140) detail
        FROM `{P}.PlexOps.etl_dispatch_log`
        WHERE dispatched_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR)
          AND (outcome IN ('failed', 'partial', 'lost') OR reason IN ('held-outage', 'stale-alert', 'screens-alert', 'login-alert'))
        ORDER BY dispatched_at DESC LIMIT 8""")
    for r in bad:
        say(f"  ! {mt(r['dispatched_at'])} {r['job_name']} {r['reason']}/{r['outcome']}: {r['detail']}")
    if any(r["outcome"] in ("failed", "partial", "lost") for r in bad):
        flags.append("prod run failed/partial in the last 2 h")
    if any(r["reason"] == "held-outage" for r in bad):
        flags.append("Plex outage breaker is holding runs")

    # ── ODBC health (Label Design runs every 15 min on weekdays) ───────────────
    ld = q(c, f"""SELECT status, COUNT(*) n, MAX(started_at) last FROM `{P}.PlexProd.job_run_log`
        WHERE report_name = 'label_design' AND job_name NOT LIKE '%test%'
          AND started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 3 HOUR) GROUP BY 1""")
    say("Label Design ETL, 3 h: " + (", ".join(f"{r['status']} {r['n']} (last {mt(r['last'])})" for r in ld) or "no runs"))
    fails = sum(r["n"] for r in ld if r["status"] == "failed")
    if fails >= 3:
        flags.append(f"ODBC: {fails} Label Design runs failed in 3 h")
    fr = q(c, f"""SELECT report_group, data_source, data_label, odbc_lag_min, latest_verdicts
        FROM `{P}.PlexOps.data_freshness` WHERE dataset = 'PlexProd' ORDER BY 1""")
    for r in fr:
        say(f"  {r['report_group']:<13} {r['data_source']:<5} {r['data_label']}"
            + (f" | lag {r['odbc_lag_min']:.0f} min" if r.get("odbc_lag_min") is not None else ""))
    newest = q(c, f"""SELECT MAX(odbc_data_as_of) t FROM `{P}.PlexOps.data_freshness` WHERE dataset = 'PlexProd'""")
    if newest and newest[0]["t"]:
        age_h = (now - newest[0]["t"]).total_seconds() / 3600
        loc = now.astimezone(DEN)
        if loc.weekday() < 5 and 9 <= loc.hour < 17 and age_h >= 6:   # 6 h = a missed 4-hourly refresh (11-11)
            flags.append(f"ODBC newest change is {age_h:.1f} h old in work hours")

    # ── Screens job ─────────────────────────────────────────────────────────────
    sr = q(c, f"""SELECT run_started_at, screen, verdict, odbc_lag_min, screen_rows, fetch_seconds,
          LEFT(IFNULL(fetch_error, odbc_error), 120) err, alert
        FROM `{P}.PlexOps.screen_recon`
        WHERE run_started_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 HOUR)
        ORDER BY run_started_at DESC, screen""")
    say("Screens, 5 h:")
    for r in sr:
        say(f"  {mt(r['run_started_at'])} {r['screen']:<9} {r['verdict']:<16} lag {r['odbc_lag_min'] or 0:>5.0f} "
            f"rows {r['screen_rows']:>4} {r['fetch_seconds'] or 0:>5.0f}s"
            + (f" | {r['err']}" if r["err"] else "") + (f" | alert {r['alert']}" if r["alert"] else ""))
    if not sr:
        flags.append("no screens check in 5 h")
    last = {}
    for r in sr:
        last.setdefault(r["screen"], r)
    for s, r in last.items():
        if r["verdict"] in ("diverged", "screens_failed", "pipeline_behind"):
            flags.append(f"screen {s}: {r['verdict']}")
    ls = q(c, f"SELECT * FROM `{P}.PlexOps.live_source` ORDER BY 1")
    say("live_source: " + "; ".join(f"{r['report_group']} odbc_behind={r['odbc_behind']} use_live={r['use_live']}" for r in ls))
    lg = q(c, f"""SELECT ok, COUNT(*) n, MAX(attempted_at) last, ANY_VALUE(IF(ok, NULL, LEFT(error, 100))) err
        FROM `{P}.PlexOps.plex_login_log` WHERE attempted_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR) GROUP BY 1""")
    say("Plex logins, 24 h: " + (", ".join(f"{'ok' if r['ok'] else 'FAILED'} {r['n']} (last {mt(r['last'])})"
                                         + (f" {r['err']}" if r["err"] else "") for r in lg) or "none"))
    if any(not r["ok"] for r in lg):
        flags.append("a Plex web login failed in 24 h")

    # ── Label Design: what Monday gets ──────────────────────────────────────────
    src = q(c, f"""SELECT data_source, COUNT(*) n, STRING_AGG(DISTINCT CAST(order_number AS STRING), ',' LIMIT 12) o
        FROM `{P}.PlexProd.label_design_report` GROUP BY 1""")
    say("Label Design queue: " + ", ".join(f"{r['data_source']} {r['n']}" + (f" (orders {r['o']})" if r["data_source"] == "live" else "")
                                           for r in src))
    pending = q(c, f"""SELECT COUNT(*) n FROM `{P}.PlexProd.label_design_report` v
        WHERE NOT EXISTS (SELECT 1 FROM `{P}.PlexProd.label_design_push_log` a
                          WHERE a.outcome IN ('created', 'partial') AND a.dedupe_key = v.dedupe_key)""")
    n_pending = pending[0]["n"] if pending else 0
    say(f"  not on Monday yet: {n_pending}")
    push = q(c, f"""SELECT outcome, COUNT(*) n, STRING_AGG(DISTINCT order_number, ',' LIMIT 10) o
        FROM `{P}.PlexProd.label_design_push_log`
        WHERE pushed_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR) GROUP BY 1""")
    say("  push, last hour: " + (", ".join(f"{r['outcome']} {r['n']} ({r['o']})" for r in push) or "nothing"))
    if any(r["outcome"] in ("failed", "partial") for r in push):
        flags.append("Label Design push had failed/partial items")
    if n_pending and now.astimezone(DEN).weekday() < 5 and 6 <= now.astimezone(DEN).hour < 18:
        stale = q(c, f"""SELECT COUNT(*) n FROM `{P}.PlexProd.label_design_report` v
            WHERE NOT EXISTS (SELECT 1 FROM `{P}.PlexProd.label_design_push_log` a
                              WHERE a.outcome IN ('created', 'partial') AND a.dedupe_key = v.dedupe_key)
              AND v.order_date >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 1 DAY)""")
        if stale and stale[0]["n"]:
            flags.append(f"{stale[0]['n']} recent Label Design line(s) in the queue but not on Monday")

    # ── Watchdog ────────────────────────────────────────────────────────────────
    wd = q(c, f"""SELECT check_id, ok, LEFT(detail, 140) detail, checked_at FROM `{P}.PlexOps.watchdog_log`
        WHERE run_id = (SELECT ARRAY_AGG(run_id ORDER BY checked_at DESC LIMIT 1)[OFFSET(0)] FROM `{P}.PlexOps.watchdog_log`)""")
    okn = sum(1 for r in wd if r["ok"])
    say(f"Watchdog ({mt(wd[0]['checked_at']) if wd else '-'}): {okn}/{len(wd)} ok")
    for r in wd:
        if not r["ok"]:
            say(f"  ! {r['check_id']}: {r['detail']}")
            flags.append(f"watchdog {r['check_id']} failing")
    if wd and (now - wd[0]["checked_at"]).total_seconds() > 5400:
        flags.append("watchdog silent for 90 min+")

    say("FLAGS: " + ("; ".join(dict.fromkeys(flags)) if flags else "none"))
    text = "\n".join(out)
    print(text)
    if args.log:
        d = os.path.expanduser(args.log)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{now.astimezone(DEN):%Y-%m-%d}.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
