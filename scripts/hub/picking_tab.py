#!/usr/bin/env python3
"""The "Picking & staging" tab of the Plex Data Hub (2026-11-20): docs/PICKING_STAGING_APP.md, rendered.

The doc is the single text: this tab converts its Markdown (headings, paragraphs, lists, tables,
code) at build time, so the hub never drifts from the repo. No BigQuery at render time.
build_hub.py injects it like dr_tab.py, in the Business tools group. The Markdown converter is the
same as api_source_tab.py's (PR #159); fold the two into one module once both are on main.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs" / "PICKING_STAGING_APP.md"
START, END = "<!--picking-tab-start-->", "<!--picking-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "picking", "Picking & staging"


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def md_to_html(md: str) -> str:
    out, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            out.append(f'<pre class="code"><code>{html.escape(chr(10).join(lines[i + 1:j]))}</code></pre>')
            i = j + 1
        elif ln.startswith("#"):
            lvl = min(len(ln) - len(ln.lstrip("#")), 3)
            out.append(f"<h{lvl + 1}>{inline(ln.lstrip('#').strip())}</h{lvl + 1}>")
            i += 1
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                if not re.match(r"^\|[\s\-|:]+\|$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f'<div class="tbl-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
        elif re.match(r"^(\s*)([-*]|\d+\.) ", ln):
            ordered = bool(re.match(r"^\d+\.", ln.strip()))
            items = []
            while i < len(lines) and lines[i].strip() and not lines[i].startswith(("#", "|", "```")):
                m = re.match(r"^\s*(?:[-*]|\d+\.) (.*)", lines[i])
                if m:
                    items.append(m.group(1))
                elif items:
                    items[-1] += " " + lines[i].strip()
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f'<{tag} class="plain">' + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
        elif ln.strip():
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||```|\s*([-*]|\d+\.) )", lines[i]):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
        else:
            i += 1
    return "\n".join(out)


def render_tab() -> str:
    body = md_to_html(DOC.read_text(encoding="utf-8"))
    return f"""{START}<style>
#s-{KEY} .ref h2 {{ margin-top: 28px; }}
#s-{KEY} td {{ overflow-wrap: anywhere; }}
#s-{KEY} ol.plain {{ padding-left: 20px; }}
</style><section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref"><div class="block">
<p class="lede">From docs/PICKING_STAGING_APP.md (rendered when the hub is built). Code: deploy/picking_app/;
tested against Plex TEST on 2026-11-20; not deployed.</p>
{body}</div></div></section>{END}"""


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
    return inject(live, render_tab()) if DOC.exists() else live


if __name__ == "__main__":
    sys.exit(__doc__)
