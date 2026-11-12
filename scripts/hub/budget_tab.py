#!/usr/bin/env python3
"""The "Budget" tab of the Plex Data Hub (2026-11-12): what the project costs a month, before
and after the 11-12 cuts, and what the next cuts would bring.

The figures are an ESTIMATE (usage x list price, steady state 11-08 to 11-12): there is no
billing export, and BigQuery job history and Logging ingestion are not readable with our
accounts. Source and method: docs/COST_ANALYSIS.md. build_hub.py injects the tab like
reliability_tab.py and label_api_tab.py; update the numbers here and in that doc together.
"""
from __future__ import annotations

import html
import re
import sys

START, END = "<!--budget-tab-start-->", "<!--budget-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "budget", "Budget"

# (service, before 11-12, after 11-12, what changed)   $/month, midpoints
SERVICES = [
    ("Cloud Run jobs", 10.4, 6.9,
     "weekend probes only; test cascade Mon-Fri; test retries removed; Label Design test paused; "
     "screens 3x and watchdog hourly on weekends; probe runs re-extract only changed tables"),
    ("Cloud Build", 3.2, 0.1, "default machine, inside the 2,500 free minutes"),
    ("Cloud Scheduler", 3.0, 2.0, "33 jobs to 23 (12 retries removed, 2 weekend schedulers added; 3 free)"),
    ("Artifact Registry", 1.2, 1.2, "no change yet (cleanup policy is next)"),
    ("Secret Manager", 0.75, 0.8, "a few more reads: the alerts now ask Plex's API"),
    ("BigQuery storage and queries", 0.0, 0.0, "1.85 GiB stored (10 free); queries likely under 1 TiB free"),
    ("Cloud Functions, GCS, Logging", 0.0, 0.0, "within free tiers"),
]

DONE = [
    ("Cloud Build on the default machine (timeout 3600 s)", 3.1),
    ("12 nightly test retry schedulers removed", 1.75),
    ("Label Design test scheduler paused (run by hand)", 0.6),
    ("Test cascade Monday-Friday only", 0.6),
    ("Weekends: prod probes only at 04:xx and 23:xx", 0.5),
    ("Watchdog hourly on weekends", 0.4),
    ("Screens 3 times a day on weekends (was 6)", 0.35),
    ("Probe runs re-extract only changed tables (PR #149; measured $0.10-1.0, mostly less Plex load)", 0.5),
]

NEXT = [
    ("Decide \"skip\" before a container starts (Label Design: 78% of runs skip after an ~80 s boot)", "2-5", "medium", "low-medium"),
    ("Screens job at 1 vCPU / 2 GiB (now 2 / 4)", "1.7", "1 Terraform line", "medium: watch timeouts"),
    ("Artifact Registry cleanup policy (keep ~10 images); delete the unused cloud-run-source-deploy repository", "1.1", "policy JSON", "low"),
    ("Watchdog hourly at night on weekdays too", "0.4", "cron", "low"),
]


def esc(s) -> str:
    return html.escape(str(s))


def table(head, rows, num_cols=()):
    h = "".join(f'<th{" class=num" if i in num_cols else ""}>{esc(x)}</th>' for i, x in enumerate(head))
    b = "".join("<tr>" + "".join(f'<td{" class=num" if i in num_cols else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>"
                for r in rows)
    return f'<div class="tbl-wrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def money(v) -> str:
    return f"${v:,.2f}" if v else "$0"


def bar(v, top):
    w = 0 if not top else max(0.0, min(100.0, 100 * v / top))
    return f'<div class="hbar"><i style="width:{w:.0f}%"></i><span>{money(v)}</span></div>'


def render_tab() -> str:
    before = sum(b for _, b, _, _ in SERVICES)
    after = sum(a for _, _, a, _ in SERVICES)
    done = sum(v for _, v in DONE)
    stats = [(f"${before:,.0f}", "a month before 11-12 (estimate; range $18-24)"),
             (f"${after:,.0f}", "a month projected now (range $10-16)"),
             (f"${done:,.1f}", "a month cut on 11-12 (per-table probe included once #149 ships)"),
             ("$6-10", "a month if the next cuts are made"),
             ("~55%", "of Cloud Run time is container start-up")]
    stats_html = "".join(f'<div class="stat"><b>{esc(v)}</b><span>{esc(l)}</span></div>' for v, l in stats)
    top = max(b for _, b, _, _ in SERVICES)
    svc = table(["Service", "Before 11-12", "Now (projected)", "What changed"], [
        (esc(n), bar(b, top), bar(a, top), esc(w)) for n, b, a, w in SERVICES
    ] + [("<b>Total</b>", f"<b>{money(before)}</b>", f"<b>{money(after)}</b>", esc("midpoints; see the ranges above"))])
    done_t = table(["Cut on 11-12 (PR #147)", "About $/month"],
                   [(esc(n), f"{v:.2f}") for n, v in DONE] + [("<b>Total</b>", f"<b>{done:.2f}</b>")], num_cols=(1,))
    next_t = table(["Next cut (not done)", "About $/month", "Effort", "Risk"],
                   [tuple(esc(x) for x in r) for r in NEXT])
    runs = table(["Cloud Run job", "Wall seconds a month", "Note"], [
        (esc("Prod ETL (14 jobs)"), "~218k", esc("about 80 s of start-up per run (boot, ODBC driver, connect, probe)")),
        (esc("Watchdog"), "~122k", esc("48 runs a weekday x 85 s; 24 a weekend day since 11-12")),
        (esc("Label Design"), "~117k", esc("40 runs a weekday x 96 s; 78% skip")),
        (esc("Test cascade"), "~107k", esc("weekdays only since 11-12; retries removed")),
        (esc("Plex screens"), "~93k", esc("2 vCPU / 4 GiB, so 186k vCPU-s: the most expensive per second")),
        (esc("Label Design test"), "~27k", esc("paused since 11-12")),
        (esc("Label Design push"), "~18k", ""),
    ])
    return f"""{START}<section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref">
<div class="block"><h2>What the Plex ETL costs</h2>
<p class="lede">An <b>estimate</b> from usage x Google's list prices, steady state 11-08 to 11-12. There is no billing export, and BigQuery
job history and log volume are not readable with our accounts, so BigQuery queries (Looker Studio) are the one unknown. Turning on the
billing export to BigQuery is free and would make these exact. Method and evidence: <code>docs/COST_ANALYSIS.md</code>.</p>
<div class="stats" style="margin:0">{stats_html}</div></div>
<div class="block"><h2>Before and after, by service ($ a month)</h2>{svc}</div>
<div class="two"><div class="panel"><h3>Cut on 11-12</h3>{done_t}</div>
<div class="panel"><h3>Where Cloud Run time goes</h3>{runs}</div></div>
<div class="block"><h2>Next cuts, ranked</h2>{next_t}
<p class="lede">The biggest lever is the first: most runs end "nothing changed" after paying for a full container start. Deciding that
before starting the container (a cheap check in the dispatcher, or the Plex API trigger planned for Label Design, D38) removes most
of that cost.</p></div>
<div class="block"><h2>What is not counted</h2><ul class="plain">
<li>BigQuery queries from Looker Studio dashboards (VoxScorecardsLive, plex_mirror): not readable; likely inside the 1 TiB free.</li>
<li>Cloud Logging ingestion: not readable; likely inside 50 GiB free.</li>
<li>Free tiers are per billing account: if other projects use them, Cloud Run is nearer $15.7 before and $11 now.</li>
</ul></div>
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
