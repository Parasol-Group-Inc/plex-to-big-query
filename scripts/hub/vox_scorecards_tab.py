#!/usr/bin/env python3
"""The "Vox Scorecards" tab of the Plex Data Hub (2026-11-19): Jennilyn's VoxScorecardsLive dataset.

Built from the repo backup in custom_views/VoxScorecardsLive/ (refresh it first with
`python scripts/backup_custom_views.py VoxScorecardsLive`): the README table gives each object's type,
rows, last change and builder; each .sql file gives what it reads. No BigQuery at render time.
The dataset is hand-built in the console (mostly by Jennilyn), not by the ETL; this tab exists so we
see what of ours it depends on before we change or drop anything in PlexProd.
"""
from __future__ import annotations

import html
import re
import sys
from collections import defaultdict
from pathlib import Path

START, END = "<!--voxsc-tab-start-->", "<!--voxsc-tab-end-->"
DIR = Path(__file__).resolve().parents[2] / "custom_views" / "VoxScorecardsLive"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "voxsc", "Vox Scorecards"

# Monday boards synced nightly by monday-to-bigquery-vox (NAMED_TABLES=true: table = <name>_<board id>).
MONDAY = {"18405027980": "Opportunities", "18409621334": "Stalled / won / lost",
          "18405028203": "Activities (last 30 days only)", "18415088271": "Forecast"}
REF = re.compile(r"`?(?:voxdatalake\.)?(PlexProd|PlexTest|VoxScorecardsLive)\.([A-Za-z0-9_]+)`?")


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def objects() -> list[dict]:
    rows = []
    for line in (DIR / "README.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[0].startswith("`") and cells[1] in ("table", "view"):
            name = cells[0].strip("`")
            sql = DIR / f"{name}.sql"
            text = sql.read_text(encoding="utf-8") if sql.exists() else ""
            reads = sorted({f"{d}.{t}" for d, t in REF.findall(text)} - {f"VoxScorecardsLive.{name}"})
            rows.append({"name": name, "type": cells[1], "rows": cells[2], "changed": cells[3],
                         "by": cells[4], "has_sql": bool(text), "reads": reads, "sql": text})
    return rows


def source(o: dict) -> str:
    m = re.search(r"_(\d{11})$", o["name"])
    if m and m.group(1) in MONDAY:
        return "Monday sync"
    if o["type"] == "table" and not o["has_sql"]:
        return "Uploaded (NetSuite / sheet)"
    if any(r.startswith("PlexProd.") for r in o["reads"]):
        return "Reads Plex (PlexProd)"
    return "Built from other VoxScorecardsLive objects"


def render_tab() -> str:
    objs = objects()
    if not objs:
        return ""
    by_src = defaultdict(list)
    for o in objs:
        by_src[source(o)].append(o)
    plex_dep = defaultdict(list)
    for o in objs:
        for r in o["reads"]:
            if r.startswith("PlexProd."):
                plex_dep[r[9:]].append(o["name"])
    v2 = {k: v for k, v in plex_dep.items() if k.startswith("v2_")}
    n_views = sum(o["type"] == "view" for o in objs)
    stats = "".join(f'<div class="stat"><b>{n}</b><span>{l}</span></div>' for n, l in (
        (n_views, "views"), (len(objs) - n_views, "tables"), (len(by_src["Reads Plex (PlexProd)"]), "read our PlexProd objects"),
        (len(plex_dep), "PlexProd objects they depend on"), (len(by_src["Monday sync"]), "tables from Monday")))
    warn = ""
    if v2:
        lst = "".join(f"<li><code>PlexProd.{esc(k)}</code>: {', '.join(f'<code>{esc(x)}</code>' for x in sorted(v))}</li>" for k, v in sorted(v2.items()))
        warn = (f'<div class="callout watch"><b class="l">Do not drop the v2_* views</b>{sum(len(v) for v in v2.values())} of her views read '
                f'PlexProd <code>v2_*</code> views (OPEN_ITEMS D36 planned to drop them):<ul class="plain">{lst}</ul>'
                'They stay until she repoints these to <code>scorecard_goals_resolved</code> / <code>production_vs_goal_report</code>.</div>')
    dep_rows = "".join(f'<tr><td><code>{esc(k)}</code></td><td class="num">{len(v)}</td><td>{", ".join(esc(x) for x in sorted(v))}</td></tr>'
                       for k, v in sorted(plex_dep.items(), key=lambda kv: (-len(kv[1]), kv[0])))
    mon_rows = "".join(f'<tr><td>{esc(lbl)}</td><td><code>{esc(b)}</code></td><td>{esc(", ".join(o["name"] for o in objs if o["name"].endswith(b)))}</td></tr>'
                       for b, lbl in MONDAY.items())
    order = ["Monday sync", "Uploaded (NetSuite / sheet)", "Reads Plex (PlexProd)", "Built from other VoxScorecardsLive objects"]
    obj_rows = []
    for s in order:
        for o in sorted(by_src[s], key=lambda o: o["name"]):
            sql = (f'<details><summary>SQL</summary><pre class="code"><code>{esc(o["sql"])}</code></pre></details>' if o["sql"] else "")
            obj_rows.append(f'<tr data-src="{esc(s)}"><td><code>{esc(o["name"])}</code>{sql}</td><td>{esc(o["type"])}</td><td>{esc(s)}</td>'
                            f'<td class="num">{esc(o["rows"])}</td><td>{esc(o["changed"])}</td><td>{esc(", ".join(o["reads"]))}</td></tr>')
    return f"""{START}<style>
#s-voxsc details summary {{ cursor: pointer; font-size: 12px; color: var(--muted); }}
#s-voxsc details pre.code {{ max-height: 320px; margin-top: 6px; }}
#s-voxsc td {{ overflow-wrap: anywhere; }}
</style><section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref">
<div class="block"><h2>Vox Scorecards (VoxScorecardsLive)</h2>
<p class="lede">Jennilyn's dataset behind the Vox scorecards in Looker Studio. It is built by hand in the BigQuery console, not by our ETL,
so the ETL never recreates it; but many of its views read our PlexProd reports and raw tables, so changing or dropping one of ours can
break her scorecard. Backed up in the repo (custom_views/VoxScorecardsLive/, SQL of every object) and its table data in
Backups.VoxScorecardsLive__*_20261111. Inventory as of the last backup refresh.</p>
<div class="stats" style="margin:0">{stats}</div>{warn}</div>
<div class="block"><h2>Where its data comes from</h2><div class="two">
<div class="panel"><h3>Monday.com, nightly</h3><ul class="plain">
<li>Scheduler <code>monday-daily-sync-VoxScorecardsLive</code> at 01:00 UTC (6 PM MT) calls Cloud Run service <code>monday-to-bigquery-vox</code> (built by Emilio 2026-05-19).</li>
<li>It writes one table per Monday board (below) and emails Emilio, Jennilyn and marketing@ ("Vox Scorecards Live").</li>
<li>Its Monday token is a plain environment variable on the service, not in Secret Manager (the SendGrid key is). Worth moving.</li>
<li>The older <code>monday-daily-sync</code> / <code>monday-sync-flattened</code> (paused since June) was deleted 2026-11-19.</li></ul>
<div class="tbl-wrap"><table><thead><tr><th>Board</th><th>Board id</th><th>Table</th></tr></thead><tbody>{mon_rows}</tbody></table></div></div>
<div class="panel"><h3>Everything else</h3><ul class="plain">
<li><b>Uploaded tables</b> (no SQL in 180 days of job history): NetSuite exports and sheets such as Overstock_NS, SalesDB_YTD, DN_15_MO_Expiring.</li>
<li><b>Hand-built tables</b>: snapshots she rebuilds with SQL (scorecard_monthly_history, shipping_revenue_daily, ...).</li>
<li><b>Views on Plex</b>: read our PlexProd reports and raw tables live, so they refresh with each ETL run.</li>
<li><b>Goals</b>: read the PlexProd goals resolver (see the warning above if it names v2_* views).</li></ul></div></div></div>
<div class="block"><h2>What of ours it depends on</h2>
<p class="lede">Check this list before renaming, dropping or changing the columns of any of these PlexProd objects.</p>
<div class="tbl-wrap"><table><thead><tr><th>PlexProd object</th><th class="num">Her objects</th><th>Which</th></tr></thead><tbody>{dep_rows}</tbody></table></div></div>
<div class="block"><h2>Every object</h2>
<div class="tbl-wrap"><table><thead><tr><th>Object</th><th>Type</th><th>Source</th><th class="num">Rows</th><th>Last changed</th><th>Reads</th></tr></thead><tbody>{"".join(obj_rows)}</tbody></table></div></div>
</div></section>{END}"""


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace(f', ["{KEY}", "{LABEL}", ""]', "").replace(f'  if (k === "{KEY}") $("#stats").hidden = true;\n', "")
    if not tab:
        return page
    anchor = '  <section id="s-history"'
    for needle in (anchor, NAV, STATS):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace(NAV, NAV + f', ["{KEY}", "{LABEL}", ""]')
    page = page.replace(STATS, f'  if (k === "{KEY}") $("#stats").hidden = true;\n' + STATS)
    return page


def add(live: str) -> str:
    return inject(live, render_tab()) if (DIR / "README.md").exists() else live


if __name__ == "__main__":
    sys.exit(__doc__)
