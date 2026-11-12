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
    ("current", "ODBC has every screen record older than 5 h (ODBC refreshes about every 4 h)", "nothing"),
    ("behind", "the oldest record or edit ODBC lacks is older than 5 h (RECON_LAG_TOLERANCE_MIN = 300)", "quiet; email past 6 h (releases) or 12 h (shipments, revenue)"),
    ("diverged", "ODBC changed a value after the screen showed another, a record missing below a later ODBC record for 2 h+, or ODBC has records the screen lacks twice running while ODBC itself is fresh", "email once a day"),
    ("odbc_unreachable", "ODBC connect or query failed, or a query hit its TOP", "email once a day; Label Design keeps taking new lines from the screens"),
    ("pipeline_behind", "ODBC is fine but BigQuery lacks records ODBC had before our last load", "email once a day (our ETL, not Plex)"),
    ("screens_failed", "a screen could not be read, or returned far fewer rows than last time", "email after 2 in a row; Label Design runs on ODBC alone meanwhile"),
]

EMAILS = [
    ("Screens digest", "Emilio, Jennilyn, marketing", "9:20, 13:20, 17:20 MT (just after ODBC refreshes), plus another run needing action at most once per 4 h; a lag under the lines reads \"ODBC catching up\" (info)", "each group's source label, the Label Design lines only the screens have, each screen's verdict, logins, screenshot folder"),
    ("Plex login failed", "Emilio only", "once a day per cause (a new cause mails at once), after one retry for causes that can pass on their own", "the cause (wrong password, password change, MFA, locked, Plex down, network, timeout), what Plex showed, the fix, the streak and last good login, the screenshot"),
    ("ODBC is behind or disagrees / caught up", "Emilio, Jennilyn, marketing", "releases over 6 h behind, shipments or revenue over 12 h (missed the overnight catch-up), or a verdict that is not a delay; once a day per group; caught up once after that", "lag, verdicts, why"),
    ("BigQuery missing records", "Emilio, Jennilyn, marketing", "pipeline_behind, once a day per screen", "examples; details in screen_recon_diff"),
    ("ODBC data is N h old", "Emilio, Jennilyn, marketing", "weekdays 9-5, newest ODBC change 6 h+ old (a missed refresh), once a day", "from every prod ETL run (check_odbc_freshness); kept at 2 h so a freeze like 11-10 is caught"),
    ("Watchdog", "Emilio, Jennilyn, marketing", "a check newly failing, once a day per check", "which part stopped and the usual fix"),
    ("ETL digest health line", "Emilio, Jennilyn, marketing", "every batch digest", "ODBC data 6 h+ old in work hours"),
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
    ("backups", "no full weekly BigQuery snapshot set in the last 8 days (they had failed 10-27 to 11-09; fixed 11-10)"),
    ("test_cascade", "fewer than 12 test jobs ran overnight"),
    ("schedulers", "a Cloud Scheduler job paused or failing"),
    ("image_drift", "a job on a different build"),
    ("odbc_connect", "weekdays, 3 of the last 4 Label Design runs could not connect to ODBC"),
    ("odbc_vs_plex", "Plex's REST API shows order changes our ODBC copy lacks for over 6 h (a missed refresh)"),
]

GROUP_RULES = [
    ("Screen read", "hourly on weekdays 6:20 AM-5:20 PM, and with all screens at 01/05/09/13/17/21:20 (just after ODBC refreshes)", "every 4 h, as an audit"),
    ("What the report reads", "ODBC's lines plus the lines only the screen has (screen read under 3 h old)", "ODBC only (Jennilyn: not time critical, the data comes every day)"),
    ("A new order", "reaches Monday within the hour from the screen, Data Source \"Plex screens, read ...\"", "appears when ODBC delivers it, normally the same day or overnight"),
    ("When ODBC catches up", "the push fills the item's empty cells (reps, email, phone, priority, bottle, label fields) and marks Data Source \"confirmed by ODBC\"; never over the team's values", "nothing to do"),
    ("Email", "releases over 6 h behind, or a real disagreement", "over 12 h behind (missed the overnight catch-up), or a real disagreement"),
    ("If the screens fail", "Label Design runs on ODBC alone, at ODBC's speed; login or screen email", "no effect on the reports"),
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
  LS["live_source&lt;br/&gt;odbc_behind per group"]
  Live[("live_order_releases&lt;br/&gt;lines ODBC lacks feed Label Design")]
  DF["data_freshness&lt;br/&gt;source + as-of per group"]
  Reports["17 reports&lt;br/&gt;data_source, data_as_of, data_label"]
  Monday["Monday: Data Source column&lt;br/&gt;Plex Import Test, Design &amp; QA"]
  WD["plex-etl-watchdog&lt;br/&gt;every 30 min, 14 checks"]
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
    stats = [("3", "Plex screens checked"), ("17", "reports labeled with their source"),
             ("14", "watchdog checks every 30 min (hourly on weekends)"), ("4", "Google alerts outside our code"),
             ("1 h", "a new Label Design order to Monday"), ("6 h / 12 h", "Plex changes ODBC lacks before an email")]
    stats_html = "".join(f'<div class="stat"><b>{esc(v)}</b><span>{esc(l)}</span></div>' for v, l in stats)
    verdicts = table(["Verdict", "When", "What happens"], [(code(v), esc(w), esc(h)) for v, w, h in VERDICTS])
    emails = table(["Email", "To", "When", "What it says"], [tuple(esc(x) for x in r) for r in EMAILS])
    checks = table(["Check", "Fails when"], [(code(c), esc(t)) for c, t in CHECKS])
    labels = table(["Column", "Meaning"], [
        (code("data_source"), "odbc (Plex's database feed, normal) or live (Plex's own screens, while the feed is behind)"),
        (code("data_as_of"), "odbc: the newest change the feed had delivered; live: when the screens were read"),
        (code("data_label"), 'the two in words, e.g. "ODBC, loaded 11-10 13:01, newest change 11-10 11:56 MT" or "Plex screens, read 11-10 13:20 MT"'),
    ])
    rules = (f'<div class="block"><h2>Screens and ODBC working together (2026-11-11)</h2>'
             f'<p class="lede">Measured 11-10/11: ODBC ran 2.5 to 5.5 hours behind Plex\'s screens all afternoon and was '
             f'current again at the 00:20 and 04:20 checks. For Label Design the two now work together instead of '
             f'taking turns: the screen brings a new order to Monday within the hour, ODBC brings its details a little '
             f'later and confirms it. Shipments and revenue stay on ODBC. Nobody is emailed for a normal delay. Full rules: '
             f'{code("docs/ODBC_VS_SCREENS.md")}.</p>' + table(["", "Label Design", "Revenue and shipments"], [
                 (esc(a), esc(b), esc(c)) for a, b, c in GROUP_RULES]) + '</div>')
    measure = ('<div class="block"><h2>No false alarms: one measure for "ODBC is behind" (2026-11-12)</h2>'
               '<p class="lede">Until 11-12 three checks asked how old ODBC\'s newest change was. That age also grows when nobody '
               'works in Plex, so a quiet night or weekend looked like a stuck ODBC: the watchdog fired at 02:11 (6.1 h; we do not load '
               'between 23:00 and 04:00), and the screens digest said "554 min behind" at 07:21 for four lines under an hour old. Now every '
               'check asks Plex\'s own API (every order\'s last change, about 1 s): <b>is there a change in Plex, older than the line, that '
               'ODBC does not have?</b> A quiet Plex gives 0; a frozen ODBC (11-10) still grows minute by minute. Code: '
               f'{code("plex_api_lag.py")}; rules: {code("docs/ODBC_VS_SCREENS.md")}.</p>' + table(["Check", "Compares Plex with", "Mails when"], [
                   (code("watchdog odbc_vs_plex"), esc("our copy, at the last time we asked ODBC (a load or a skipped probe)"), esc("6 h+, two runs in a row, weekdays 6 AM-6 PM; it owns the incident; also mails if Plex's API cannot be read")),
                   (code("stale-data email (main.py)"), esc("ODBC read live in the run"), esc("6 h+, weekdays 9-5, once a day, not if the watchdog already mailed")),
                   (code("screens 'behind'"), esc("ODBC read live"), esc("Label Design 6 h+, revenue 12 h+")),
               ]) + '<p class="lede">If Plex\'s API cannot be read, each check falls back to the old measure. Replay tests from the real days '
               '(a freeze past 6 h must alert; 11-11 afternoon, 11-12 overnight and morning, a quiet weekend must not) run with every build. '
               'Limits by design: it watches sales orders only, and a freeze under the 6 h line (like the real 4.5 h one on 11-10) is not mailed; '
               'Label Design is covered by the screens either way.</p></div>')
    weekend = ('<div class="block"><h2>Weekends and cost (2026-11-12)</h2>'
               '<p class="lede">The project costs about $18-24 a month (estimate: usage x list price; no billing export). About 55% of '
               'Cloud Run time is start-up overhead. Cut on 11-12, about $7 a month:</p>' + table(["Change", "About $/month"], [
                   (esc("Weekends: prod probes only, 04:xx and 23:xx (etl_schedule.days); Monday 04:xx is a full run again"), "0.5"),
                   (esc("Test cascade Monday-Friday; the 12 nightly no-op test retry schedulers removed"), "2.35"),
                   (esc("Label Design test scheduler paused"), "0.6"),
                   (esc("Cloud Build on the default machine (free minutes)"), "3.1"),
                   (esc("Screens 3 times a day on weekends (05:20, 13:20, 21:20); watchdog hourly on weekends"), "0.75"),
               ]) + f'<p class="lede">Next, not done: decide "skip" before starting a container (~$2-5), screens at 1 vCPU / 2 GiB (~$1.7), '
               f'an Artifact Registry cleanup policy (~$1.1). Details: {code("docs/COST_ANALYSIS.md")}.</p></div>')
    return f"""{START}<section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref">
<div class="block"><h2>How we know the data is right</h2>
<p class="lede">On 2026-11-10 Plex's database feed (ODBC) kept answering but served data frozen at 08:10 MT for 4.5 hours, and every
run reported success. Plex's own screens were right. Since then a cloud job compares the two, Label Design takes new lines from the screens while ODBC fills in the details,
every report says where its data came from, and a watchdog checks that every part ran.</p>
<div class="stats" style="margin:0">{stats_html}</div></div>
<div class="block"><h2>The flow</h2><div class="diagram"><pre class="mermaid">{DIAGRAM}</pre></div></div>
<div class="two">
<div class="panel"><h3>The screens check (plex-live-screens)</h3><ol class="steps">
<li>Hourly on weekdays (6:20 AM-5:20 PM, Label Design screen only), every 4 hours on weekdays and at 05:20, 13:20, 21:20 on weekends (all three screens) it logs into Plex's web screens. Every login, and any re-login, is logged with a screenshot; a failed one emails Emilio.</li>
<li>Reads three screens: Label Design order releases, Shipper History and Shipping Revenue by Part Group, and screenshots each.</li>
<li>Reads the same records from ODBC <b>live</b> (its own connection, minutes after the screen read, not our extracted copy) and from our BigQuery tables, and compares them record by record (records under 15 minutes old are skipped). So "ODBC is behind" is Plex's lag, never a sign that our ETL hasn't extracted lately; only the BigQuery comparison depends on our extraction schedule.</li>
<li>Gives each screen a verdict and records every difference.</li>
<li>Loads the Label Design screen for the report to add the lines ODBC lacks, and starts the Monday push when there are any. Shipments and revenue stay on ODBC; their screen tables are kept empty.</li>
<li>Sends the digest and any alert.</li></ol></div>
<div class="panel"><h3>Verdicts</h3>{verdicts}</div></div>
{rules}
{measure}
{weekend}
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
<li>Settings: behind at 300 min, email at 360 min (Label Design and ODBC alerts) / 720 min (shipments, revenue), digest hours 9/13/17; ODBC refreshes about every 4 h (Terraform, job plex-live-screens; hourly scheduler plex-live-screens-releases-sync).</li>
<li>Cost: about $5 a month for the screens job, $1 for the watchdog; the whole project about $18-24 (docs/COST_ANALYSIS.md).</li>
<li>Hand-built datasets: Jennilyn's VoxScorecardsLive (60 views, 25 tables) is backed up in the repo under custom_views/ with a README per object, and its tables are copied to Backups.VoxScorecardsLive__*_20261111 (11-11). Refresh with scripts/backup_custom_views.py.</li>
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
