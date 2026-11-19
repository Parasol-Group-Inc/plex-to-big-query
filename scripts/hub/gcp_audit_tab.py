#!/usr/bin/env python3
"""The "GCP audit" tab of the Plex Data Hub (2026-11-19): infrastructure audits of the voxdatalake project.

First audit: Jennilyn's move of the project into a folder (2026-11-18). The findings live in
docs/hub/folder_move_audit.json (gitignored: it names people and their access). Without the file the
build uses the last stored render (tab_store key "gcpaudit"). Shape: generated_at, move {when, from, to,
evidence}, verdict, checks [{area, status ok|warn|fail|unknown, finding, evidence, next}],
permission_gaps [{call, error, role, command}], org_policies [{constraint, effective}].
Different from the "Audit" tab, which reviews what prod ran and produced (2026-11-12).
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

START, END = "<!--gcpaudit-tab-start-->", "<!--gcpaudit-tab-end-->"
FILE = Path(__file__).resolve().parents[2] / "docs" / "hub" / "folder_move_audit.json"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "gcpaudit", "GCP audit"
PILL = {"ok": "ok", "warn": "warn", "fail": "bad", "unknown": "none"}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def render_tab(a: dict) -> str:
    m = a.get("move", {})
    checks = a.get("checks", [])
    counts = {s: sum(1 for c in checks if c.get("status") == s) for s in ("ok", "warn", "fail", "unknown")}
    stats = "".join(f'<div class="stat"><b>{n}</b><span>{lbl}</span></div>' for n, lbl in (
        (counts["ok"], "checks ok"), (counts["warn"], "warnings"), (counts["fail"], "failures"),
        (len(a.get("permission_gaps", [])), "reads Claude was refused")))
    rows = "".join(
        f'<tr><td>{esc(c.get("area"))}</td><td><span class="pill {PILL.get(c.get("status"), "none")}">{esc(c.get("status"))}</span></td>'
        f'<td>{esc(c.get("finding"))}<div class="ga-ev">{esc(c.get("evidence"))}</div></td><td>{esc(c.get("next"))}</td></tr>'
        for c in sorted(checks, key=lambda c: ["fail", "warn", "unknown", "ok"].index(c.get("status", "ok"))
                        if c.get("status") in ("fail", "warn", "unknown", "ok") else 4))
    gaps = "".join(
        f'<tr><td>{esc(g.get("call"))}</td><td>{esc(g.get("role"))}</td><td>{esc(g.get("error"))}</td></tr>'
        for g in a.get("permission_gaps", []))
    cmds = "\n".join(g["command"] for g in a.get("permission_gaps", []) if g.get("command"))
    pol = "".join(f'<tr><td><code>{esc(p.get("constraint"))}</code></td><td>{esc(p.get("effective"))}</td></tr>'
                  for p in a.get("org_policies", []) if isinstance(p, dict))
    return f"""{START}<style>
#s-gcpaudit .ga-ev {{ color: var(--muted); font-size: 12px; margin-top: 4px; overflow-wrap: anywhere; }}
#s-gcpaudit td {{ min-width: 120px; }}
</style><section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref">
<div class="block"><h2>Folder move audit</h2>
<p class="lede"><b>{esc(a.get("verdict"))}</b> Checked {esc(a.get("generated_at"))}, read-only, as claude-readonly
(and claude-operator only for reads it was refused). Open follow-ups are on the Pending tab.</p>
<div class="stats" style="margin:0">{stats}</div></div>
<div class="block"><h2>The move</h2><div class="panel"><dl class="kv">
<dt>When</dt><dd>{esc(m.get("when"))}</dd><dt>From</dt><dd>{esc(m.get("from"))}</dd>
<dt>To</dt><dd>{esc(m.get("to"))}</dd><dt>Evidence</dt><dd>{esc(m.get("evidence"))}</dd></dl></div></div>
<div class="block"><h2>Checks</h2><div class="tbl-wrap"><table><thead><tr><th>Area</th><th>Status</th><th>Finding and evidence</th><th>Next</th></tr></thead><tbody>{rows}</tbody></table></div></div>
<div class="block"><h2>Reads Claude was refused</h2>
<p class="lede">Read-only roles; with them Claude checks these without the write account. Run with your own login.</p>
<div class="tbl-wrap"><table><thead><tr><th>Call</th><th>Role that fixes it</th><th>Error</th></tr></thead><tbody>{gaps}</tbody></table></div>
<pre class="code"><code>{esc(cmds)}</code></pre></div>
<div class="block"><h2>Organization policies in force on the project</h2>
<div class="tbl-wrap"><table><thead><tr><th>Constraint</th><th>Effective</th></tr></thead><tbody>{pol}</tbody></table></div></div>
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
    if not FILE.exists():
        return live
    return inject(live, render_tab(json.loads(FILE.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    sys.exit(__doc__)
