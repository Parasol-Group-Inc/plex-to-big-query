#!/usr/bin/env python3
"""The "Screen extraction" tab of the Plex Data Hub: Plex screens read by Playwright instead of ODBC.

    python scripts/hub/screens_tab.py --refresh   # write docs/hub/screens/status.json from BigQuery + the task log

Since 2026-11-04 ~18:56 MT Plex's ODBC feed (and SQL Development) returns a frozen copy, while
Plex's own screens stay live. scripts/plex_live_screens.py (run hourly by a Windows task during the 11-04 to 11-08 outage; that task is disabled and the Cloud Run job plex-live-screens does the reading now) reads
three screens into PlexProd.live_*; docs/PLEX_SCREEN_EXTRACTION.md is the runbook. This tab
explains it for the team, with a screenshot of each screen and the latest status.

Everything with customer data stays out of git: docs/hub/screens/ (gitignored) holds the
screenshots (*.jpg) and status.json. build_hub.py injects the tab into the live page only,
embedding the screenshots as data URIs; with no screens folder there is no tab. The prose
below is the committed part and names no customer.
"""

from __future__ import annotations

import base64
import datetime as dt
import html
import json
import re
import subprocess
import sys
from pathlib import Path

START, END = "<!--screens-tab-start-->", "<!--screens-tab-end-->"
ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "docs" / "hub" / "screens"
STATUS = DIR / "status.json"
PRIMARY_LOG = ROOT.parent / "plex-to-big-query" / "etl-manual" / "live_screens.log"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
TABLES = {"releases": "live_order_releases", "revenue": "live_shipping_revenue", "history": "live_shipper_history"}


def esc(s) -> str:
    return html.escape(str(s))


# --------------------------------------------------------------------------- status refresh

def refresh() -> None:
    """Reads freshness and outcomes (counts only, no customer rows) into status.json."""
    from google.cloud import bigquery
    c = bigquery.Client(project="voxdatalake")
    q = lambda sql: [dict(r) for r in c.query(sql).result()]
    st = {"taken_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "tables": {}}
    for k, t in TABLES.items():
        r = q(f"SELECT COUNT(*) n, FORMAT_TIMESTAMP('%Y-%m-%d %H:%M', MAX(loaded_at), 'America/Denver') loaded "
              f"FROM `voxdatalake.PlexProd.{t}`")[0]
        st["tables"][k] = {"table": t, "rows": r["n"], "loaded_mt": r["loaded"]}
    st["releases_by_status"] = q("SELECT release_status s, COUNT(*) n FROM `voxdatalake.PlexProd.live_order_releases` "
                                 "GROUP BY 1 ORDER BY 2 DESC")
    try:
        st["label_design_source"] = q("SELECT data_source s, COUNT(*) n FROM `voxdatalake.PlexProd.label_design_report` GROUP BY 1")
    except Exception as e:  # before the view has data_source
        st["label_design_source"] = [{"s": f"unavailable ({str(e).splitlines()[0][:80]})", "n": ""}]
    st["push_today"] = q("SELECT outcome s, COUNT(*) n FROM `voxdatalake.PlexProd.label_design_push_log` "
                         "WHERE DATE(pushed_at, 'America/Denver') = CURRENT_DATE('America/Denver') GROUP BY 1 ORDER BY 2 DESC")
    st["etl_label_design"] = q("SELECT FORMAT_TIMESTAMP('%Y-%m-%d %H:%M', started_at, 'America/Denver') started_mt, status, "
                               "SUBSTR(IFNULL(detail, ''), 1, 90) detail FROM `voxdatalake.PlexProd.job_run_log` "
                               "WHERE report_name = 'label_design' AND NOT ENDS_WITH(job_name, '-test') "
                               "ORDER BY started_at DESC LIMIT 3")
    st["runs"] = log_runs()
    st["task"] = task_info()
    DIR.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(st, indent=1, default=str), encoding="utf-8")
    print(f"{STATUS.relative_to(ROOT)}: written ({len(st['runs'])} runs from the task log)")


def log_runs(n: int = 8) -> list[dict]:
    """The last n runs from the task log: start, result line, push line, exit code. No row data."""
    if not PRIMARY_LOG.exists():
        return []
    runs, cur = [], None
    for line in PRIMARY_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("=== "):
            cur = {"start": line[4:].strip(), "done": "", "push": "", "exit": ""}
            runs.append(cur)
        elif cur is None:
            continue
        elif line.startswith("done in"):
            cur["done"] = line.strip()[:120]
        elif " replaced: " in line and not cur["done"].startswith("done"):  # older runs had no "done" line
            t = line.split("PlexProd.")[-1].split(" replaced: ")
            cur["done"] = (cur["done"] + "; " if cur["done"] else "") + f"{t[0]} {t[1].strip()}"
        elif "push" in line and ("started " in line or "not started" in line or "FAILED" in line):
            cur["push"] = line.strip()[:120]
        elif re.match(r"^exit -?\d+", line.strip()):
            cur["exit"] = line.strip()[5:]
    return runs[-n:][::-1]


def task_info() -> dict:
    if sys.platform != "win32":
        return {}
    ps = ('$i = Get-ScheduledTaskInfo -TaskName "Plex live screens"; '
          '"{0:yyyy-MM-dd HH:mm}|{1}|{2:yyyy-MM-dd HH:mm}" -f $i.LastRunTime, $i.LastTaskResult, $i.NextRunTime')
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, timeout=60).stdout.strip()
        last, result, nxt = out.split("|")
        return {"last_run_local": last, "last_result": result, "next_run_local": nxt}
    except Exception:
        return {}


# --------------------------------------------------------------------------- rendering

SCREENS = [
    {"key": "revenue", "img": "revenue.jpg", "title": "Shipping Revenue by Part Group",
     "path": "Shipping › Shipping Revenue by Part Group",
     "how": "Same Search request the screen sends, one invoice month at a time (cap 500 rows; a month at the cap fails). "
            "The grid repeats a line once per GL account, so rows are collapsed back to one per invoiced line; "
            "the account amounts are kept as text.",
     "gives": "One row per invoiced shipper line: invoice, shipper, order, PO, customer, part, quantity, net price, revenue, salesperson."},
    {"key": "history", "img": "history.jpg", "title": "Shipper History",
     "path": "VisionPlex › Shipper History",
     "how": "The screen's data source request, one ship month at a time. A month Plex flags as over its record limit fails the screen.",
     "gives": "One row per shipped line: ship date and time, shipper, customer, part, order and line, quantity, carrier. No prices "
              "(join the revenue table on shipper and part)."},
    {"key": "releases", "img": "orders.jpg", "title": "Sales Orders (Pending Fulfillment)",
     "path": "Sales › Sales Orders",
     "how": "The Search request with Status = Pending Fulfillment and one order-date month at a time, from 18 Oct 2026. "
            "It lists each order's lines; the release detail comes from the next screen.",
     "gives": "Order header: order no, customer PO, order date, status, customer, Inside Sales."},
    {"key": "releases", "img": "rapid_entry.jpg", "title": "Order Line Rapid Entry (one per order)",
     "path": "Sales Order › Order Line Rapid Entry",
     "how": "The page carries its grid as JSON inside the page. That is read for every Pending Fulfillment order (about 160, "
            "~3 minutes). It is the only order screen with the Job Note.",
     "gives": "One row per release: release status (Label Design, Open, ...), priority, due date, quantity, part, customer part, Job Note."},
]

FLOW = [
    ("Since 11-10: Cloud Run", "The job <code>plex-live-screens</code> reads the screens every 4 h on weekdays (Label Design hourly 6:20-16:20) and 3 times a day on weekends. The laptop task used during the 11-04 to 11-08 outage is disabled."),
    ("Log in like a person", "Headless Chromium (Playwright) signs in to Plex with the integration login kept in <code>.env</code>."),
    ("Ask the screens", "It sends the exact requests each screen makes when you click Search, month by month, and checks every answer."),
    ("Load BigQuery", "Each screen replaces its own <code>PlexProd.live_*</code> table, after a daily backup copy and a size check."),
    ("Label Design switches", "<code>label_design_report</code> reads the fresh releases instead of the frozen ODBC copy (<code>data_source = live</code>)."),
    ("Monday push", "If the ETL has not pushed, the task starts the Label Design push, which creates only items not already on the board."),
]

SAFEGUARDS = [
    ("One run at a time", "An operating-system lock shared with every Plex web script. A second run exits at once (code 75); a killed run frees it."),
    ("A broken screen breaks only itself", "Each screen loads or fails alone. A failed one keeps its last good table."),
    ("Retries and re-login", "Each request is tried 3 times; an expired session logs in again."),
    ("No silent truncation", "One month per request. A month at a screen's row cap, an unknown status or a duplicate key fails the screen."),
    ("No big drops", "A load that would shrink a table below 90% (50% for releases, which drop as orders ship) is refused."),
    ("Verified writes", "After each load, BigQuery's row count must equal the rows sent."),
    ("Backups", "First load of each day copies the table to <code>Backups</code> (7 days); time travel covers every hourly load."),
    ("Goes stale safely", "Label Design uses the screen copy only while it is under 3 hours old, then falls back to ODBC by itself."),
]

NO_COLLISION = [
    "Writes only its own <code>live_*</code> tables (and their backups). Never a <code>raw_*</code> table, a view, or an ETL log.",
    "Talks to Plex's web servers (<code>vox.on.plex.com</code>), not the ODBC host the ETL uses.",
    "Starts the Monday push only when the ETL's own Label Design run has not succeeded in the last 40 minutes, no push is running, "
    "and it is a weekday between 5 AM and 5:50 PM MT. That keeps it clear of the ETL's pushes and the 6:05 PM sweep.",
    "When ODBC returns, the ETL takes over the push by itself; disabling the task then returns the view to ODBC within 3 hours.",
]


def img(name: str) -> str:
    p = DIR / name
    if not p.exists():
        return '<div class="sx-noimg">screenshot not captured</div>'
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f'<img loading="lazy" alt="" src="data:image/jpeg;base64,{b64}">'


def table(rows: list[dict], a: str = "s", b: str = "n") -> str:
    if not rows:
        return '<p class="lede">none</p>'
    return ('<table class="sx-t"><tbody>' + "".join(f"<tr><td>{esc(r[a])}</td><td class='n'>{esc(r[b])}</td></tr>" for r in rows)
            + "</tbody></table>")


def render_tab(st: dict) -> str:
    t = st.get("tables", {})
    stats = "".join(f'<div class="stat"><b>{esc(t[k]["rows"]) if k in t else "-"}</b><span>{esc(l)}</span></div>'
                    for k, l in [("releases", "order releases"), ("revenue", "invoiced lines"), ("history", "shipped lines")])
    src = {r["s"]: r["n"] for r in st.get("label_design_source", [])}
    stats += (f'<div class="stat"><b>{esc(src.get("live", 0))}</b><span>Label Design lines from screens</span></div>'
              f'<div class="stat"><b>{esc((t.get("releases") or {}).get("loaded_mt", "-"))}</b><span>last load (MT)</span></div>')
    task = st.get("task") or {}
    task_line = (f'Task last ran {esc(task.get("last_run_local"))} laptop time (result {esc(task.get("last_result"))}), '
                 f'next {esc(task.get("next_run_local"))}.' if task else "")
    flow = "".join(f'<li><b>{h}</b><span>{d}</span></li>' for h, d in FLOW)
    cards = "".join(
        f'<figure class="sx-card"><div class="sx-img">{img(s["img"])}</div><figcaption>'
        f'<h3>{esc(s["title"])}</h3><p class="sx-path">{esc(s["path"])} → <code>PlexProd.{TABLES[s["key"]]}</code></p>'
        f'<dl class="kv"><dt>How it is read</dt><dd>{esc(s["how"])}</dd><dt>What it gives</dt><dd>{esc(s["gives"])}</dd></dl>'
        f'</figcaption></figure>' for s in SCREENS)
    guards = "".join(f"<dt>{h}</dt><dd>{d}</dd>" for h, d in SAFEGUARDS)
    runs = st.get("runs", [])
    runs_html = ('<table class="sx-t"><thead><tr><th>Started (laptop)</th><th>Result</th><th>Push</th><th>Exit</th></tr></thead><tbody>'
                 + "".join(f'<tr><td>{esc(r["start"])}</td><td>{esc(r["done"])}</td><td>{esc(r["push"])}</td>'
                           f'<td><span class="pill {"ok" if r["exit"] == "0" else "warn"}">{esc(r["exit"] or "?")}</span></td></tr>'
                           for r in runs) + "</tbody></table>") if runs else '<p class="lede">No runs logged yet.</p>'
    etl = st.get("etl_label_design", [])
    etl_html = ('<table class="sx-t"><tbody>' + "".join(f'<tr><td>{esc(r["started_mt"])}</td><td>{esc(r["status"])}</td><td>{esc(r["detail"])}</td></tr>'
                                                       for r in etl) + "</tbody></table>") if etl else ""
    css = """
#s-screens .sx-flow { list-style: none; counter-reset: sx; padding: 0; margin: 0; display: grid; gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
#s-screens .sx-flow li { counter-increment: sx; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }
#s-screens .sx-flow li b { display: block; margin-bottom: 4px; }
#s-screens .sx-flow li b::before { content: counter(sx) ". "; color: var(--muted); }
#s-screens .sx-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); }
#s-screens .sx-card { margin: 0; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
#s-screens .sx-img { background: var(--line); max-height: 300px; overflow: hidden; cursor: zoom-in; }
#s-screens .sx-img.open { max-height: none; cursor: zoom-out; }
#s-screens .sx-img img { display: block; width: 100%; height: auto; }
#s-screens .sx-noimg { padding: 40px; text-align: center; color: var(--muted); }
#s-screens figcaption { padding: 12px 14px; }
#s-screens figcaption h3 { margin: 0 0 4px; font-size: 15px; }
#s-screens .sx-path { margin: 0 0 8px; color: var(--muted); font-size: 13px; }
#s-screens .sx-t { border-collapse: collapse; width: 100%; font-size: 13px; }
#s-screens .sx-t td, #s-screens .sx-t th { border-bottom: 1px solid var(--line); padding: 4px 8px; text-align: left; vertical-align: top; }
#s-screens .sx-t td.n { text-align: right; font-variant-numeric: tabular-nums; }
#s-screens .sx-scroll { overflow-x: auto; }
#s-screens dd { overflow-wrap: anywhere; }
"""
    js = """
(() => {
  const root = document.getElementById("s-screens"); if (!root) return;
  root.addEventListener("click", e => { const b = e.target.closest(".sx-img"); if (b) b.classList.toggle("open"); });
})();
"""
    return (
        f'{START}<style>{css}</style><section id="s-screens" data-tab="screens" hidden><div class="ref">'
        f'<div class="block"><h2>Automated extraction: Plex screens instead of ODBC</h2>'
        f'<p class="lede">Since 4 Nov 2026 about 6:56 PM MT, Plex\'s database feed (ODBC, and SQL Development with it) '
        f'answers from a copy that stopped updating. Plex\'s own screens kept working. So, while the feed was down (11-04 to 11-08), a '
        f'program reads three screens the way a person would and loads what they show into BigQuery. Label Design '
        f'runs on it and new Label Design orders reach Monday again.</p>'
        f'<p class="lede">Status as of {esc(st.get("taken_at", "?"))} UTC. {task_line}</p>'
        f'<div class="stats" style="margin:0">{stats}</div></div>'
        f'<div class="block"><h2>How a run works</h2><ol class="sx-flow">{flow}</ol></div>'
        f'<div class="block"><h2>The screens it reads</h2><p class="lede">Screenshots from 5 Nov 2026; click one to see it whole.</p>'
        f'<div class="sx-grid">{cards}</div></div>'
        f'<div class="two"><div class="block"><h2>Safeguards</h2><dl class="kv">{guards}</dl></div>'
        f'<div class="block"><h2>Why it cannot collide with the ETL</h2><ul class="plain">'
        + "".join(f"<li>{x}</li>" for x in NO_COLLISION) + '</ul></div></div>'
        f'<div class="two"><div class="block"><h2>Releases by status</h2>{table(st.get("releases_by_status", []))}'
        f'<h2 style="margin-top:16px">Label Design reads</h2>{table(st.get("label_design_source", []))}</div>'
        f'<div class="block"><h2>Monday push today</h2>{table(st.get("push_today", []))}'
        f'<h2 style="margin-top:16px">Label Design ETL, newest runs</h2><div class="sx-scroll">{etl_html}</div></div></div>'
        f'<div class="block"><h2>Recent runs (task log)</h2><div class="sx-scroll">{runs_html}</div></div>'
        f'<div class="block"><h2>When ODBC is back</h2><ol>'
        f'<li>Nothing has to happen at once: the ETL resumes the Monday push and the task stops starting it.</li>'
        f'<li>Disable the task: <code>Disable-ScheduledTask -TaskName "Plex live screens"</code>.</li>'
        f'<li>Three hours later <code>label_design_report</code> reads ODBC again (<code>data_source = odbc</code>), no deploy.</li>'
        f'<li>Close OPEN_ITEMS D30. Runbook: <code>docs/PLEX_SCREEN_EXTRACTION.md</code>.</li></ol>'
        f'<p class="lede">Known gap while it runs: an order created after the freeze has no BDM until ODBC returns.</p></div>'
        f'</div></section><script>{js}</script>{END}')


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace(', ["screens", "Screen extraction", ""]', "").replace('  if (k === "screens") $("#stats").hidden = true;\n', "")
    anchor = '  <section id="s-history"'
    for needle in (anchor, NAV, STATS):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace(NAV, NAV + ', ["screens", "Screen extraction", ""]')
    page = page.replace(STATS, '  if (k === "screens") $("#stats").hidden = true;\n' + STATS)
    return page


def add(live: str) -> str:
    if not DIR.is_dir():
        return live
    st = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    return inject(live, render_tab(st))


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        refresh()
    else:
        sys.exit(__doc__)
