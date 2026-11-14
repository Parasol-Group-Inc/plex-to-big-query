#!/usr/bin/env python3
"""The "Business rules" tab of the Plex Data Hub (2026-11-13).

One place for every choice about what a number MEANS: what is counted, left out, or how it is
computed, who decided it and when, which reports apply it, the SQL lines that enforce it, and a
live number that shows the rule at work.

Source of truth: docs/hub/business_rules.json (committed). Each rule there carries a `measure`
with a read-only SQL; scripts/hub/snapshot_data.py re-runs those queries on every hub build and
stores the results in data_snapshot.json (gitignored), and this tab shows the fresh value, falling
back to the value saved in the JSON when there is no snapshot.

    python scripts/hub/rules_tab.py --md     # regenerate docs/BUSINESS_RULES.md from the JSON

build_hub.py injects the tab like budget_tab.py. When a rule changes (a report's logic, a decision
by Jennilyn), change it in business_rules.json in the same commit as the SQL.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RULES = ROOT / "docs" / "hub" / "business_rules.json"
SNAPSHOT = ROOT / "docs" / "hub" / "data_snapshot.json"
MD = ROOT / "docs" / "BUSINESS_RULES.md"

START, END = "<!--rules-tab-start-->", "<!--rules-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "rules", "Business rules"

AREAS = ["Revenue and shipping", "Sales", "Production", "Inventory", "Label Design", "Goals and scorecard",
         "Operations", "Data sources and freshness", "Customers"]
STATUS_PILL = {"in force": "ok", "open decision": "warn", "partly built": "warn"}


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


def load():
    data = json.loads(RULES.read_text(encoding="utf-8"))
    snap = {}
    if SNAPSHOT.exists():
        snap = json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("rule_measures", {}) or {}
    return data, snap


def fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.2f}"
    try:
        f = float(v)
        return fmt(int(f) if f.is_integer() else f)
    except (TypeError, ValueError):
        return str(v)


def current(rule, snap):
    """The rule's number: fresh from the snapshot when it ran, else the saved one."""
    m = rule.get("measure")
    if not m:
        return None
    s = snap.get(rule["id"])
    if s and "error" not in s:
        return {**m, "value": s.get("value"), "detail": s.get("detail"), "as_of": s.get("as_of"), "fresh": True}
    if s and "error" in s:
        return {**m, "error": s["error"], "fresh": False}
    return {**m, "fresh": False}


def area_order(a):
    return AREAS.index(a) if a in AREAS else len(AREAS)


def render_rule(r, snap, known_reports):
    pill = STATUS_PILL.get(r.get("status"), "warn")
    who = " · ".join(x for x in (r.get("decided_by") if r.get("decided_by") not in (None, "unknown") else "",
                                  r.get("decided_on") or "") if x)
    oi = f' <span class="tag">{esc(r["open_item"])}</span>' if r.get("open_item") else ""
    quote = f'<blockquote class="rq">“{esc(r["quote"])}”</blockquote>' if r.get("quote") else ""
    reps = []
    for name in r.get("reports", []):
        if name in known_reports:
            reps.append(f'<button class="tag" data-open="report:{esc(name)}">{esc(name)}</button>')
        else:
            reps.append(f'<span class="tag">{esc(name)}</span>')
    src = ", ".join(f'<code>{esc(e["file"])}{":" + esc(e["lines"]) if e.get("lines") else ""}</code>'
                    for e in r.get("enforced_in", []))
    m = current(r, snap)
    if m and "error" in m:
        num = f'<div class="rnum"><b>?</b><span>{esc(m.get("label"))}: query failed on this build ({esc(m["error"][:120])})</span></div>'
    elif m:
        when = esc(m.get("as_of") or "")
        num = (f'<div class="rnum"><b>{esc(fmt(m.get("value")))}</b><span>{esc(m.get("label"))}'
               f'{" · " + when if when else ""}{"" if m.get("fresh") else " (saved value)"}</span>'
               + (f'<small>{esc(m["detail"])}</small>' if m.get("detail") else "")
               + (f'<small>{esc(m["effect"])}</small>' if m.get("effect") else "") + "</div>")
    else:
        num = f'<div class="rnum none"><span>{esc(r.get("no_measure_reason") or "no number for this rule")}</span></div>'
    finding = f'<p class="rfind"><span class="pill bad">finding</span> {esc(r["finding"])}</p>' if r.get("finding") else ""
    unverified = "" if r.get("verified", True) else f'<p class="rfind"><span class="pill bad">docs ≠ SQL</span> {esc(r.get("verify_note"))}</p>'
    search = esc(" ".join(str(r.get(k) or "") for k in ("id", "title", "rule", "why", "decided_by", "open_item")) + " " + " ".join(r.get("reports", []))).lower()
    return f"""<article class="rule" data-area="{esc(r['area'])}" data-status="{esc(r.get('status'))}" data-s="{search}">
<header><span class="tag">{esc(r['id'])}</span> <b>{esc(r['title'])}</b> <span class="pill {pill}">{esc(r.get('status'))}</span>{oi}
{f'<span class="rwho">{esc(who)}</span>' if who else ''}</header>
<div class="rbody"><div><p>{esc(r['rule'])}</p><p class="rwhy"><b>Why:</b> {esc(r.get('why'))}</p>{quote}{finding}{unverified}
<p class="rsrc"><b>Reports:</b> {' '.join(reps) or '-'}</p><p class="rsrc"><b>Enforced in:</b> {src or '-'}</p></div>{num}</div>
</article>"""


CSS = """<style>
#s-rules,#s-rules .ref,#s-rules .block,#s-rules .rule,#s-rules .rbody>div{min-width:0}
#s-rules code,#s-rules .tag{white-space:normal;overflow-wrap:anywhere}
#s-rules .rule{overflow-wrap:anywhere;border:1px solid var(--line);border-radius:8px;padding:12px 14px;margin:10px 0;background:var(--surface)}
#s-rules .rule header{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
#s-rules .rwho{margin-left:auto;color:var(--muted);font-size:12.5px}
#s-rules .rbody{display:grid;grid-template-columns:minmax(0,1fr) 230px;gap:14px;margin-top:6px}
#s-rules .rbody p{margin:4px 0}
#s-rules .rwhy,#s-rules .rsrc{color:var(--muted);font-size:13px}
#s-rules .rsrc button.tag{border:0;cursor:pointer}
#s-rules .rq{margin:6px 0;padding:4px 10px;border-left:3px solid var(--line);color:var(--muted);font-style:italic;font-size:13px}
#s-rules .rnum{border-left:3px solid var(--line);padding-left:10px;display:flex;flex-direction:column;gap:3px}
#s-rules .rnum b{font-size:22px;font-variant-numeric:tabular-nums}
#s-rules .rnum span,#s-rules .rnum small{color:var(--muted);font-size:12.5px}
#s-rules .rnum.none span{font-style:italic}
#s-rules .rfind{font-size:13px}
#s-rules .rbar{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:8px 0}
#s-rules .rbar input{flex:1 1 220px;padding:6px 10px;border:1px solid var(--line);border-radius:6px;background:var(--surface);color:inherit}
#s-rules .chip[aria-pressed="true"]{background:var(--code-bg);font-weight:600}
@media (max-width:720px){#s-rules .rbody{grid-template-columns:1fr}#s-rules .rwho{margin-left:0}}
</style>"""

JS = """<script>(function(){const s=document.getElementById('s-rules');if(!s)return;let area='',q='';
const apply=()=>{let n=0;s.querySelectorAll('article.rule').forEach(a=>{const ok=(!area||a.dataset.area===area||(area==='__open'&&a.dataset.status!=='in force'))&&(!q||a.dataset.s.includes(q));a.hidden=!ok;if(ok)n++;});
s.querySelectorAll('h2.rarea').forEach(h=>{let e=h.nextElementSibling,any=false;while(e&&e.tagName==='ARTICLE'){if(!e.hidden)any=true;e=e.nextElementSibling;}h.hidden=!any;});s.querySelector('#rcount').textContent=n+' shown';};
s.querySelector('.rbar').addEventListener('click',e=>{const c=e.target.closest('.chip');if(!c)return;area=c.dataset.a;s.querySelectorAll('.rbar .chip').forEach(x=>x.setAttribute('aria-pressed',x===c));apply();});
s.querySelector('#rq').addEventListener('input',e=>{q=e.target.value.trim().toLowerCase();apply();});apply();})();</script>"""


def render_tab(known_reports=frozenset()) -> str:
    data, snap = load()
    rules = sorted(data["rules"], key=lambda r: (area_order(r["area"]), r["id"]))
    n = len(rules)
    open_n = sum(1 for r in rules if r.get("status") != "in force")
    measured = [r for r in rules if r.get("measure")]
    fresh = sum(1 for r in measured if (snap.get(r["id"]) or {}).get("value") is not None)
    findings = sum(1 for r in rules if r.get("finding")) + len(data.get("disagreements", []))
    stats = [(n, "rules, each checked against the SQL that runs today"),
             (len(measured), f"with a live number ({fresh} refreshed on this build)"),
             (open_n, "open decisions or partly built"),
             (findings, "docs-vs-code disagreements and findings")]
    stats_html = "".join(f'<div class="stat"><b>{esc(v)}</b><span>{esc(l)}</span></div>' for v, l in stats)
    areas = sorted({r["area"] for r in rules}, key=area_order)
    chips = ('<button class="chip" data-a="" aria-pressed="true">All</button>'
             '<button class="chip" data-a="__open" aria-pressed="false">Open decisions</button>'
             + "".join(f'<button class="chip" data-a="{esc(a)}" aria-pressed="false">{esc(a)} '
                       f'<span class="tag">{sum(1 for r in rules if r["area"] == a)}</span></button>' for a in areas))
    body = ""
    for a in areas:
        body += f'<h2 class="rarea">{esc(a)}</h2>' + "".join(render_rule(r, snap, known_reports) for r in rules if r["area"] == a)
    dis = data.get("disagreements", [])
    dis_html = ""
    if dis:
        rows = "".join(f"<tr><td>{esc(d.get('topic'))}</td><td>{esc(d.get('detail'))}</td><td>{esc(d.get('status'))}</td></tr>" for d in dis)
        dis_html = (f'<div class="block"><h2>Where the docs and the code disagree</h2><p class="lede">Found while collecting the rules '
                    f'({esc(data.get("collected_on"))}). The rule cards above follow the code; these are the texts or reports to fix or decide.</p>'
                    f'<div class="tbl-wrap"><table><thead><tr><th>Topic</th><th>What differs</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></div></div>')
    spots = data.get("spot_checks", [])
    spot_html = ""
    if spots:
        spot_html = '<div class="block"><h2>Measured side checks</h2><ul class="plain">' + "".join(
            f"<li><b>{esc(s.get('title'))}:</b> {esc(s.get('explanation'))}</li>" for s in spots) + "</ul></div>"
    return f"""{START}<section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref">{CSS}
<div class="block"><h2>Business rules</h2>
<p class="lede">Every choice about what a number means: what is counted or left out, how it is computed, who decided it and when.
Each rule was checked against the SQL that runs today (file and lines below), and most carry a number measured in BigQuery on this
build, so you can see the rule at work. Source: <code>docs/hub/business_rules.json</code>; readable copy
<code>docs/BUSINESS_RULES.md</code>.</p><div class="stats" style="margin:0">{stats_html}</div></div>
<div class="rbar">{chips}<input id="rq" type="search" placeholder="Search rules, reports, open items"><span id="rcount" class="tag"></span></div>
{body}{dis_html}{spot_html}</div></section>{JS}{END}"""


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
    if not RULES.exists():
        return live
    known = frozenset(re.findall(r'"name":\s*"([a-z0-9_]+)"', live))
    return inject(live, render_tab(known))


def write_md() -> None:
    data, snap = load()
    rules = sorted(data["rules"], key=lambda r: (area_order(r["area"]), r["id"]))
    out = ["# Business rules", "",
           f"*Generated from `docs/hub/business_rules.json` by `python scripts/hub/rules_tab.py --md`. Do not edit by hand.* "
           f"Collected {data.get('collected_on')}; {len(rules)} rules. The hub's Business rules tab shows the same rules with live numbers.", ""]
    for a in sorted({r["area"] for r in rules}, key=area_order):
        out += [f"## {a}", ""]
        for r in (r for r in rules if r["area"] == a):
            who = ", ".join(x for x in (r.get("decided_by"), r.get("decided_on")) if x and x != "unknown")
            out.append(f"### {r['id']} {r['title']}")
            out.append("")
            out.append(f"- **Rule:** {r['rule']}")
            out.append(f"- **Why:** {r.get('why')}")
            if who or r.get("open_item"):
                out.append(f"- **Decided:** {who or 'not recorded'}{' · ' + r['open_item'] if r.get('open_item') else ''} · status: {r.get('status')}")
            if r.get("quote"):
                out.append(f"- **In her words:** \"{r['quote']}\"")
            out.append(f"- **Reports:** {', '.join('`' + x + '`' for x in r.get('reports', [])) or '-'}")
            out.append("- **Enforced in:** " + ", ".join(f"`{e['file']}`" + (f" lines {e['lines']}" if e.get('lines') else "") for e in r.get("enforced_in", [])))
            m = current(r, snap)
            if m and "error" not in m:
                out.append(f"- **Measured:** {fmt(m.get('value'))}: {m.get('label')} ({m.get('as_of')})" + (f". {m['effect']}" if m.get("effect") else ""))
            if r.get("finding"):
                out.append(f"- **Finding:** {r['finding']}")
            out.append("")
    if data.get("disagreements"):
        out += ["## Where the docs and the code disagree", "", "| Topic | What differs | Status |", "|---|---|---|"]
        out += [f"| {d.get('topic')} | {d.get('detail')} | {d.get('status')} |" for d in data["disagreements"]]
        out.append("")
    MD.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(f"{MD.relative_to(ROOT)}: {len(rules)} rules")


if __name__ == "__main__":
    if "--md" in sys.argv:
        write_md()
    else:
        sys.exit(__doc__)
