#!/usr/bin/env python3
"""The "Reliability" tab of the Plex Data Hub (2026-11-10): how we know the data is right.

Documents the screens vs ODBC check (plex-live-screens), the source labels on every report
(PlexOps.data_freshness), the watchdog, the Google alerts and who gets which email. Static
content: the live state is in BigQuery (queries at the bottom of the tab). build_hub.py
injects it into the live page, like customer_notes_tab.py.
"""
from __future__ import annotations

import html
import re
import sys

START, END = "<!--reliability-tab-start-->", "<!--reliability-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "reliability", "Reliability"


def esc(s) -> str:
    return html.escape(str(s))


def table(head, rows):
    h = "".join(f"<th>{esc(x)}</th>" for x in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def code(s):
    return f"<code>{esc(s)}</code>"


VERDICTS = [
    ("current", "ODBC has every screen record older than 2 h", "reports read ODBC"),
    ("behind", "the oldest record or edit ODBC lacks is older than 2 h (RECON_LAG_TOLERANCE_MIN)", "the group switches to the screens"),
    ("diverged", "a gap ODBC never fills, ODBC changed a value after the screen showed another, or ODBC has records the screen lacks twice running", "the group switches to the screens; email"),
    ("odbc_unreachable", "ODBC connect or query failed, or a query hit its TOP", "the group switches to the screens"),
    ("pipeline_behind", "ODBC is fine but BigQuery lacks records ODBC had before our last load", "email; no switch"),
    ("screens_failed", "a screen could not be read, or returned far fewer rows than last time", "ignored for switching; email after 2 in a row"),
]

EMAILS = [
    ("Screens digest", "Emilio, Jennilyn, marketing", "8:20, 12:20, 4:20 PM MT runs, and any run with a problem", "each group's source label, each screen's verdict, rows and timing, logins, screenshot folder"),
    ("Plex login failed", "Emilio only", "once a day per cause (a new cause mails at once), after one retry for causes that can pass on their own", "the cause (wrong password, password change, MFA, locked, Plex down, network, timeout), what Plex showed, the fix, the streak and last good login, the screenshot"),
    ("Reports switched to the screens / back on ODBC", "Emilio, Jennilyn, marketing", "when a group switches", "lag, verdicts, why"),
    ("ODBC disagrees / BigQuery missing records", "Emilio, Jennilyn, marketing", "once a day while it lasts", "examples; details in screen_recon_diff"),
    ("ODBC data is N h old", "Emilio, Jennilyn, marketing", "weekdays 9-5, newest ODBC change 2 h+ old, once a day", "from every prod ETL run (check_odbc_freshness)"),
    ("Watchdog", "Emilio, Jennilyn, marketing", "a check newly failing, once a day per check", "which part stopped and the usual fix"),
    ("ETL digest health line", "Emilio, Jennilyn, marketing", "every batch digest", "a group on the screens, or on ODBC data 2 h+ old in work hours"),
    ("Google Cloud Monitoring", "Emilio (sent by Google, not SendGrid)", "watchdog silent 90 min, screens job silent 9 h, any email failing, 3+ timeout kills an hour", "so an alert arrives even if our code or SendGrid is down"),
]

CHECKS = [
    ("dispatch_missed", "a scheduled prod run older than 35 min was never started"),
    ("dispatch_stuck", "a started run still open after 150 min"),
    ("label_design_running", "weekdays 5:30-5:45 PM, no Label Design run for 40 min"),
    ("label_design_pending", "lines in the report but not on Monday for 30+ min"),
    ("screens_job", "no screens check for 5 h, or a screen failing twice running"),
    ("raw_freshness", "a raw table with rows not refreshed in 30 h"),
    ("msl_daily", "no MSL demand history row for today after 7:30 AM"),
    ("usage_monthly", "last month's part usage not recorded by the 2nd"),
    ("backups", "the weekly BigQuery snapshots missing (they had failed since 10-27)"),
    ("manual_data", "goals or safety incidents not loaded in 3 h (D34)"),
    ("test_cascade", "fewer than 12 test jobs ran overnight"),
    ("schedulers", "a Cloud Scheduler job paused or failing"),
    ("image_drift", "a job on a different build"),
]

QUERIES = """-- which source each report reads now, and how current
SELECT * FROM `voxdatalake.PlexOps.data_freshness` WHERE dataset = 'PlexProd';
-- the screens checks, newest first
SELECT run_started_at, screen, verdict, odbc_lag_min, compared, missing_tail, missing_hole,
       status_diff, value_diff, odbc_extra, bq_missing, fetch_seconds, fetch_error, odbc_error
FROM `voxdatalake.PlexOps.screen_recon` ORDER BY run_started_at DESC LIMIT 20;
-- every Plex web login
SELECT attempted_at, reason, ok, error, seconds, screenshot
FROM `voxdatalake.PlexOps.plex_login_log` ORDER BY attempted_at DESC LIMIT 20;
-- watchdog failures
SELECT checked_at, check_id, detail FROM `voxdatalake.PlexOps.watchdog_log`
WHERE NOT ok ORDER BY checked_at DESC LIMIT 50;"""

DIAGRAM = """flowchart LR
  Screens["Plex screens&lt;br/&gt;Label Design releases, shipments, revenue"]
  ODBC["Plex ODBC"]
  Job["plex-live-screens&lt;br/&gt;every 4 h, Cloud Run"]
  Shots[("screenshots bucket&lt;br/&gt;by date and time")]
  Logins[("plex_login_log")]
  Recon[("screen_recon + diffs")]
  LS["live_source&lt;br/&gt;switch per group"]
  Live[("PlexProd.live_* tables&lt;br/&gt;loaded only while switched")]
  DF["data_freshness&lt;br/&gt;source + as-of per group"]
  Reports["17 reports&lt;br/&gt;data_source, data_as_of, data_label"]
  Monday["Monday: Data Source column&lt;br/&gt;Plex Import Test, Design &amp; QA"]
  WD["plex-etl-watchdog&lt;br/&gt;every 30 min, 13 checks"]
  GM["Google Monitoring&lt;br/&gt;heartbeats, email failures"]
  Screens --&gt; Job
  ODBC --&gt; Job
  Job --&gt; Shots
  Job --&gt; Logins
  Job --&gt; Recon --&gt; LS
  LS --&gt; Live
  LS --&gt; DF
  Live --&gt; Reports
  DF --&gt; Reports
  Reports --&gt; Monday
  Recon --&gt; WD
  WD --&gt; GM
  Job --&gt; GM"""


def render_tab() -> str:
    stats = [("3", "Plex screens checked every 4 h"), ("17", "reports labeled with their source"),
             ("13", "watchdog checks every 30 min"), ("4", "Google alerts outside our code"),
             ("2 h", "ODBC lag tolerated before switching")]
    stats_html = "".join(f'<div class="stat"><b>{esc(v)}</b><span>{esc(l)}</span></div>' for v, l in stats)
    verdicts = table(["Verdict", "When", "What happens"], [(code(v), esc(w), esc(h)) for v, w, h in VERDICTS])
    emails = table(["Email", "To", "When", "What it says"], [tuple(esc(x) for x in r) for r in EMAILS])
    checks = table(["Check", "Fails when"], [(code(c), esc(t)) for c, t in CHECKS])
    labels = table(["Column", "Meaning"], [
        (code("data_source"), "odbc (Plex's database feed, normal) or live (Plex's own screens, while the feed is behind)"),
        (code("data_as_of"), "odbc: the newest change the feed had delivered; live: when the screens were read"),
        (code("data_label"), 'the two in words, e.g. "ODBC, loaded 11-10 13:01, newest change 11-10 11:56 MT" or "Plex screens, read 11-10 13:20 MT"'),
    ])
    return f"""{START}<section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref">
<div class="block"><h2>How we know the data is right</h2>
<p class="lede">On 2026-11-10 Plex's database feed (ODBC) kept answering but served data frozen at 08:10 MT for 4.5 hours, and every
run reported success. Plex's own screens were right. Since then a cloud job compares the two every 4 hours, reports switch to the
screens only while the feed is behind, every report says where its data came from, and a watchdog checks that every part ran.</p>
<div class="stats" style="margin:0">{stats_html}</div></div>
<div class="block"><h2>The flow</h2><div class="diagram"><pre class="mermaid">{DIAGRAM}</pre></div></div>
<div class="two">
<div class="panel"><h3>The screens check (plex-live-screens)</h3><ol class="steps">
<li>Every 4 hours (00:20, 04:20 ... 20:20 MT) it logs into Plex's web screens. Every login, and any re-login, is logged with a screenshot; a failed one emails Emilio.</li>
<li>Reads three screens: Label Design order releases, Shipper History and Shipping Revenue by Part Group, and screenshots each.</li>
<li>Reads the same records from ODBC <b>live</b> (its own connection, minutes after the screen read, not our extracted copy) and from our BigQuery tables, and compares them record by record (records under 15 minutes old are skipped). So "ODBC is behind" is Plex's lag, never a sign that our ETL hasn't extracted lately; only the BigQuery comparison depends on our extraction schedule.</li>
<li>Gives each screen a verdict and records every difference.</li>
<li>Switches Label Design or revenue to the screens after one bad check, and back to ODBC after two clean ones (8 hours), emptying the screen tables (with a backup).</li>
<li>Sends the digest and any alert.</li></ol></div>
<div class="panel"><h3>Verdicts</h3>{verdicts}</div></div>
<div class="block"><h2>Where the data came from: on every report</h2>
<p class="lede">Every report built on the Label Design queue, the shipping revenue report or production records ends with three columns
from {code("PlexOps.data_freshness")}. Production always reads ODBC. On Monday, the push writes {code("data_label")} into the new
<b>Data Source</b> text column on Plex Import Test and Design &amp; QA. An old {code("data_as_of")} on a working day means the feed has
stopped, even when every run succeeded.</p>{labels}</div>
<div class="block"><h2>Who gets which email</h2>{emails}</div>
<div class="two"><div class="panel"><h3>Watchdog checks (plex-etl-watchdog)</h3>{checks}</div>
<div class="panel"><h3>Where things are</h3><ul class="plain">
<li>Screenshots: {code("gs://voxdatalake-plex-screenshots/plex-screens/YYYY/MM/DD/HHMM-MT_<run>/NN_<what>.png")}, kept 365 days.</li>
<li>Tables: {code("PlexOps.screen_recon")}, {code("screen_recon_diff")}, {code("screen_snapshot")}, {code("plex_login_log")}, {code("live_source")}, {code("data_freshness")}, {code("watchdog_log")}.</li>
<li><b>Broken now (D34):</b> the manual-data app's hourly push trigger is not running (no table refreshed since its last form save). Saves still push at once, so typed data arrives; only the hourly retry of a failed push is missing. The watchdog mails it daily.</li>
<li>Settings: lag tolerance 120 min, 2 clean runs to switch back, digest hours 8/12/16 (Terraform, job plex-live-screens).</li>
<li>Cost: about $2.40 a month for the screens job, $1 for the watchdog.</li>
<li>Runbooks: PLEX_SCREEN_EXTRACTION.md "Reconciliation (cloud job)", OPERATIONS.md "Watchdog and screen reconciliation", docs/reports/data_freshness.md.</li>
</ul></div></div>
<div class="two">
<div class="panel"><h3>Plex logins (screens job)</h3><ul class="plain">
<li>Every login is logged with a screenshot; a failed one is diagnosed: wrong password, password change, MFA, locked, Plex down, network, timeout.</li>
<li>Only Plex-down, network and ordinary timeouts are retried (once). A rejected or unclear login is not, and the job then stops logging in for 24 h, so it can never lock the user by repetition.</li>
<li>Emilio gets one email per cause per day with what Plex showed and the fix. After fixing, run the job with <code>--force-login</code>.</li></ul></div>
<div class="panel"><h3>MSL usage, changed 2026-11-10 (Jennilyn)</h3><ul class="plain">
<li><b>NetSuite usage is held for 6 months.</b> Approaching MSL used to switch to Plex usage after 30 days of Plex history (about 11-16); now after 183 days, about 2027-04-18, and Plex is then averaged over the last 6 months. With 30 days, 240 parts would have switched on 3 weeks of data.</li>
<li><b>New: usage by part by month</b> (<code>PlexProd.part_usage_monthly</code>): recorded on the 1st of each month for the month before, with the daily average, measured exactly like the MSL report (matches it on 506/506 parts). October 2026 is in (13 days from go-live).</li>
<li><b>New: month to date</b> (<code>PlexProd.part_usage_month_to_date</code>): the same figures for the current month so far, through yesterday, updated daily. Both come from one function, <code>part_usage_for_month(month)</code>, so they always agree.</li></ul></div></div>
<div class="block"><h2>Check it yourself</h2><pre class="code">{esc(QUERIES)}</pre></div>
</div></section>{END}"""


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace(f', ["{KEY}", "{LABEL}", ""]', "").replace(f'  if (k === "{KEY}") $("#stats").hidden = true;\n', "")
    anchor = '  <section id="s-history"'
    for needle in (anchor, NAV, STATS):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace(NAV, NAV + f', ["{KEY}", "{LABEL}", ""]')
    page = page.replace(STATS, f'  if (k === "{KEY}") $("#stats").hidden = true;\n' + STATS)
    return page


def add(live: str) -> str:
    return inject(live, render_tab())


if __name__ == "__main__":
    sys.exit(__doc__)
