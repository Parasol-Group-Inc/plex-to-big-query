#!/usr/bin/env python3
"""The "Audit" tab of the Plex Data Hub: findings from a review of what prod ran and produced.

The findings live in docs/hub/audit.json (gitignored: it quotes live business figures and names).
build_hub.py injects the tab into the live page only, after the QuickBooks tab, and skips it when
the file is absent. Each finding's `outcome` says whether it was fixed, documented or needs a decision.
"""

from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

START, END = "<!--audit-tab-start-->", "<!--audit-tab-end-->"
FILE = Path(__file__).resolve().parents[2] / "docs" / "hub" / "audit.json"
SEV = {"High": "bad", "Medium": "warn", "Low": "none"}
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '


def esc(s) -> str:
    return html.escape(str(s))


def finding(f: dict) -> str:
    q = f'<p class="au-q"><b>Question for you:</b> {esc(f["question"])}</p>' if f.get("question") else ""
    return (f'<div class="au-card" data-sev="{esc(f["sev"])}" data-area="{esc(f["area"])}">'
            f'<div class="au-head"><span class="tag">{esc(f["id"])}</span>'
            f'<span class="pill {SEV[f["sev"]]}">{esc(f["sev"])}</span>'
            f'<span class="pill {"none" if f["status"] == "Suspected" else "ok"}">{esc(f["status"])}</span>'
            f'<span class="tag">{esc(f["area"])}</span>'
            f'<span class="pill {"ok" if f.get("outcome", "").startswith("Fixed") else "warn"} au-dec">'
            f'{esc(f.get("outcome", "Fix not applied · awaiting review"))}</span></div>'
            f'<h3>{esc(f["title"])}</h3>'
            f'<dl class="kv"><dt>Affects</dt><dd>{esc(f["where"])}</dd>'
            f'<dt>Evidence</dt><dd>{esc(f["evidence"])}</dd>'
            f'<dt>Code</dt><dd><code>{esc(f["code"])}</code></dd>'
            f'<dt>Proposed fix</dt><dd>{esc(f["fix"])}</dd>'
            f'<dt>Checked by</dt><dd>{esc(f["verified"])}</dd>'
            + (f'<dt>Outcome</dt><dd>{esc(f["outcome_note"])}</dd>' if f.get("outcome_note") else "")
            + f'</dl>{q}</div>')


def render_tab(a: dict) -> str:
    fs = a["findings"]
    count = lambda s: sum(f["sev"] == s for f in fs)
    stats = "".join(f'<div class="stat"><b>{n}</b><span>{esc(l)}</span></div>' for n, l in [
        (len(fs), "findings"), (count("High"), "high"), (count("Medium"), "medium"), (count("Low"), "low"),
        (sum(f["status"] == "Suspected" for f in fs), "suspected, not proven"), (sum(f.get("outcome", "").startswith("Fixed") for f in fs), "fixed in code")])
    seg = "".join(f'<button data-af="{k}" aria-pressed="{str(k == "all").lower()}">{l}</button>'
                  for k, l in [("all", "All"), ("High", "High"), ("Medium", "Medium"), ("Low", "Low"),
                               ("ETL runs", "ETL runs"), ("Reports", "Reports")])
    ul = lambda xs: '<ul class="plain">' + "".join(f"<li>{esc(x)}</li>" for x in xs) + "</ul>"
    css = """
#s-audit .au-card { border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; margin: 0 0 12px; }
#s-audit .au-card[data-sev="High"] { border-left: 4px solid var(--bad); }
#s-audit .au-card[data-sev="Medium"] { border-left: 4px solid var(--warn); }
#s-audit .au-head { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
#s-audit .au-dec { margin-left: auto; }
#s-audit .au-card h3 { margin: 8px 0 8px; font-size: 15px; }
#s-audit .au-card dd { overflow-wrap: anywhere; }
#s-audit .au-q { margin: 8px 0 0; padding: 6px 10px; background: var(--warn-soft); border-radius: 6px; }
#s-audit .au-card[hidden] { display: none; }
"""
    js = """
(() => {
  const root = document.getElementById("s-audit"); if (!root) return;
  root.querySelector("#audit-seg").addEventListener("click", e => {
    const b = e.target.closest("button"); if (!b) return;
    const k = b.dataset.af;
    root.querySelectorAll("#audit-seg button").forEach(x => x.setAttribute("aria-pressed", x === b));
    root.querySelectorAll(".au-card").forEach(c => c.hidden = !(k === "all" || c.dataset.sev === k || c.dataset.area === k));
  });
})();
"""
    return (f'{START}<style>{css}</style><section id="s-audit" data-tab="audit" hidden><div class="ref">'
            f'<div class="block"><h2>{esc(a["title"])}</h2><p class="lede">{esc(a["period"])}. {esc(a["lede"])}</p>'
            f'<p class="lede">{esc(a["context"])}</p><div class="stats" style="margin:0">{stats}</div></div>'
            f'<div class="block"><h2>Findings</h2>'
            f'<div class="vb-tools" style="margin-bottom:12px"><div class="seg" id="audit-seg">{seg}</div></div>'
            + "".join(finding(f) for f in fs) + '</div>'
            f'<div class="two"><div class="block"><h2>Checked and clean</h2>{ul(a["clean"])}</div>'
            f'<div class="block"><h2>Not checked / could not verify</h2>{ul(a["gaps"])}</div></div>'
            f'</div></section><script>{js}</script>{END}')


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace(', ["audit", "Audit", ""]', "").replace('  if (k === "audit") $("#stats").hidden = true;\n', "")
    anchor = '  <section id="s-history"'
    for needle in (anchor, NAV, STATS):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace(NAV, NAV + ', ["audit", "Audit", ""]')
    # after the QuickBooks tab's own `#stats` line, so this one wins for the audit tab
    page = page.replace(STATS, '  if (k === "audit") $("#stats").hidden = true;\n' + STATS)
    return page


def add(live: str) -> str:
    if not FILE.exists():
        return live
    return inject(live, render_tab(json.loads(FILE.read_text(encoding="utf-8"))))
