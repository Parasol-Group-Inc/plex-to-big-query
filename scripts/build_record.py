#!/usr/bin/env python3
"""Build "Plex ETL Record": every CHANGELOG entry on a calendar, searchable, as one HTML page.

    python scripts/build_record.py [out.html]      # default: docs/hub/record.html (gitignored is fine)

Reads CHANGELOG.md only. Each "## <date> - <title>" (or "## <date> to <date> — <title>") is one
entry; its body is shown as written. Republish the page after each day's CHANGELOG entries.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEAD = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?:\s*(?:to|–|—|-)\s*(\d{4}-\d{2}-\d{2}))?\s*(?:\(([^)]*)\))?\s*[—–:-]*\s*(.*)$")


def entries():
    out, cur = [], None
    for line in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        m = HEAD.match(line)
        if m:
            cur = {"start": m.group(1), "end": m.group(2) or m.group(1), "tag": m.group(3) or "", "title": m.group(4).strip(), "body": []}
            out.append(cur)
        elif line.startswith("## "):
            cur = None
        elif cur is not None:
            cur["body"].append(line)
    for e in out:
        e["body"] = "\n".join(e["body"]).strip()
        if not e["title"]:   # older entries: "## <date>" with the topics as ### headings
            subs = [l[4:].strip() for l in e["body"].splitlines() if l.startswith("### ")]
            e["title"] = "; ".join(subs[:3]) + (" ..." if len(subs) > 3 else "") if subs else "Changes"
    return out


PAGE = r"""<title>Plex ETL Record</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js"></script>
<style>
/* Layout: summary strip, a month-by-month calendar heat map of changelog entries, then the entries newest first. */
:root{--bg:#f3f5f6;--surface:#fff;--ink:#17222b;--muted:#5c6a76;--line:#d7dee3;--code:#edf1f3;
  --h1:#dcebe2;--h2:#a9d3b8;--h3:#5fae80;--h4:#2d7a50;--accent:#2d6aa8;--mark:#ffe69a;
  --sans:"IBM Plex Sans","Segoe UI",system-ui,sans-serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#0f1417;--surface:#161d22;--ink:#e1e8ed;--muted:#94a2ad;--line:#27323a;--code:#0c1114;
  --h1:#1a3326;--h2:#235238;--h3:#2f7d52;--h4:#55b783;--accent:#86b2ea;--mark:#6b5513;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0f1417;--surface:#161d22;--ink:#e1e8ed;--muted:#94a2ad;--line:#27323a;--code:#0c1114;
  --h1:#1a3326;--h2:#235238;--h3:#2f7d52;--h4:#55b783;--accent:#86b2ea;--mark:#6b5513;color-scheme:dark}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font:15px/1.6 var(--sans)}
.wrap{max-width:1100px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:20px 60px}
h1{font-size:24px;margin:0 0 4px;text-wrap:balance}
.lede{color:var(--muted);margin:0 0 16px;max-width:70ch}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:8px;overflow:hidden;margin-bottom:20px}
.stat{background:var(--surface);padding:10px 14px}.stat b{display:block;font-size:22px;font-variant-numeric:tabular-nums}.stat span{color:var(--muted);font-size:12px}
.months{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,230px),1fr));gap:14px;margin-bottom:24px}
.month{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-width:0}
.month h3{margin:0 0 6px;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}
.dow{font-size:10px;color:var(--muted);text-align:center}
.day{aspect-ratio:1;border-radius:4px;background:var(--code);font-size:11px;display:flex;align-items:flex-start;justify-content:flex-end;padding:2px 4px;color:var(--muted);border:0;font-family:inherit;font-variant-numeric:tabular-nums}
.day.blank{background:none}
.day.l1{background:var(--h1)}.day.l2{background:var(--h2)}.day.l3{background:var(--h3);color:#fff}.day.l4{background:var(--h4);color:#fff}
.day.has{cursor:pointer}.day.has:hover,.day.has:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.legend{display:flex;gap:6px;align-items:center;font-size:12px;color:var(--muted);margin:-12px 0 20px}.legend i{width:14px;height:14px;border-radius:3px;display:inline-block}
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:3;background:var(--bg);padding-block:8px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.bar input{flex:1 1 240px;min-width:0;font:inherit;padding:7px 10px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:var(--ink)}
.bar span{color:var(--muted);font-size:13px}
.day-h{font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:22px 0 8px;padding-bottom:4px;border-bottom:1px solid var(--line)}
details.e{background:var(--surface);border:1px solid var(--line);border-radius:6px;margin-bottom:8px;min-width:0}
details.e summary{cursor:pointer;padding:9px 14px;font-weight:500;list-style:none}
details.e summary::-webkit-details-marker{display:none}
details.e summary small{color:var(--muted);font-weight:400;margin-left:6px}
.body{padding:0 16px 12px;overflow-wrap:anywhere}
.body pre{background:var(--code);padding:10px;border-radius:5px;overflow-x:auto;font:12.5px/1.5 var(--mono)}
.body code{font-family:var(--mono);font-size:13px;background:var(--code);padding:1px 4px;border-radius:3px}.body pre code{background:none;padding:0}
.body table{border-collapse:collapse;display:block;overflow-x:auto;font-size:13.5px}.body th,.body td{border:1px solid var(--line);padding:4px 8px;text-align:left}
.body h3,.body h4{font-size:14px;margin:12px 0 4px}
mark{background:var(--mark);color:inherit}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
</style>
<div class="wrap">
<h1>Plex ETL record</h1>
<p class="lede">Everything done on the Plex → BigQuery project, from the first CHANGELOG entry to now: a calendar of active days and every entry as written. Built __BUILT__ from CHANGELOG.md. Pick a day to jump to it.</p>
<div class="stats" id="stats"></div>
<div class="months" id="months"></div>
<div class="legend">Fewer <i style="background:var(--h1)"></i><i style="background:var(--h2)"></i><i style="background:var(--h3)"></i><i style="background:var(--h4)"></i> more entries that day</div>
<div class="bar"><input id="q" type="search" placeholder="Search every entry" aria-label="Search every entry"><span id="shown"></span></div>
<div id="list"></div>
</div>
<script type="application/json" id="data">__DATA__</script>
<script>
const E = JSON.parse(document.getElementById("data").textContent);
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
if (window.marked) marked.use({renderer:{html(t){return esc(typeof t === "string" ? t : (t && t.text) || "");}}});
const md = s => window.marked ? marked.parse(s) : "<pre>" + esc(s) + "</pre>";
const D = d => new Date(d + "T12:00:00");
const iso = d => d.toISOString().slice(0, 10);
const perDay = {};
E.forEach((e, i) => { for (let d = D(e.start); d <= D(e.end); d.setDate(d.getDate() + 1)) (perDay[iso(d)] = perDay[iso(d)] || []).push(i); });
const days = Object.keys(perDay).sort();
const first = days[0], last = days[days.length - 1];
document.getElementById("stats").innerHTML = [[E.length, "changelog entries"], [days.length, "days with work"], [first, "first entry"], [last, "latest entry"]]
  .map(([v, l]) => `<div class="stat"><b>${esc(v)}</b><span>${l}</span></div>`).join("");
const lvl = n => n >= 6 ? 4 : n >= 4 ? 3 : n >= 2 ? 2 : 1;
let m = D(first.slice(0, 8) + "01"), endM = D(last.slice(0, 8) + "01"), html = [];
while (m <= endM) {
  const y = m.getFullYear(), mo = m.getMonth(), start = new Date(y, mo, 1).getDay(), n = new Date(y, mo + 1, 0).getDate();
  let cells = ["S","M","T","W","T","F","S"].map(x => `<div class="dow">${x}</div>`).join("") + '<div class="day blank"></div>'.repeat(start);
  for (let d = 1; d <= n; d++) {
    const k = `${y}-${String(mo + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`, c = (perDay[k] || []).length;
    cells += c ? `<button class="day has l${lvl(c)}" data-day="${k}" title="${k}: ${c} entr${c > 1 ? "ies" : "y"}: ${esc(perDay[k].map(i => E[i].title).join(" · "))}">${d}</button>`
               : `<div class="day">${d}</div>`;
  }
  html.push(`<div class="month"><h3>${m.toLocaleDateString(undefined, {month: "long", year: "numeric"})}</h3><div class="grid">${cells}</div></div>`);
  m = new Date(y, mo + 1, 1);
}
document.getElementById("months").innerHTML = html.join("");
function render() {
  const q = document.getElementById("q").value.trim().toLowerCase();
  const shown = E.map((e, i) => i).filter(i => !q || (E[i].title + " " + E[i].body).toLowerCase().includes(q))
    .sort((a, b) => (E[b].start + b).localeCompare(E[a].start + a) || a - b);
  let out = [], lastDay = "";
  shown.forEach(i => {
    const e = E[i];
    if (e.start !== lastDay) { out.push(`<div class="day-h" id="day-${e.start}">${D(e.start).toLocaleDateString(undefined, {weekday: "long", year: "numeric", month: "short", day: "numeric"})}</div>`); lastDay = e.start; }
    let body = md(e.body);
    if (q) body = body.replace(new RegExp("(" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + ")(?![^<]*>)", "gi"), "<mark>$1</mark>");
    out.push(`<details class="e"${q ? " open" : ""}><summary>${esc(e.title)}${e.end !== e.start ? `<small>${e.start} to ${e.end}</small>` : ""}</summary><div class="body">${body}</div></details>`);
  });
  document.getElementById("list").innerHTML = out.join("") || "<p>Nothing matches.</p>";
  document.getElementById("shown").textContent = `${shown.length} of ${E.length} entries`;
}
document.getElementById("q").addEventListener("input", render);
document.getElementById("months").addEventListener("click", ev => {
  const b = ev.target.closest(".day.has"); if (!b) return;
  document.getElementById("q").value = ""; render();
  const t = document.getElementById("day-" + b.dataset.day) || document.getElementById("day-" + E[perDay[b.dataset.day][0]].start);
  if (t) { t.scrollIntoView({behavior: "smooth", block: "start"}); const d = t.nextElementSibling; if (d && d.tagName === "DETAILS") d.open = true; }
});
render();
</script>
"""


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "hub" / "record.html"
    es = entries()
    data = json.dumps(es, ensure_ascii=False).replace("</", "<\\/").replace("�", "\\ufffd")
    built = dt.datetime.now(dt.timezone(dt.timedelta(hours=-7))).strftime("%Y-%m-%d %H:%M MT")
    out.write_text(PAGE.replace("__DATA__", data).replace("__BUILT__", built), encoding="utf-8")
    days = {e["start"] for e in es}
    print(f"{len(es)} entries, {len(days)} start dates, {min(days)} to {max(days)} -> {out}")


if __name__ == "__main__":
    main()
