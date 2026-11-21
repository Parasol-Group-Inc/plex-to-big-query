#!/usr/bin/env python3
"""The "Picking & staging" tab of the Plex Data Hub (2026-11-20): docs/PICKING_STAGING_APP.md, rendered.

The doc is the single text: this tab converts its Markdown (headings, paragraphs, lists, tables,
code) at build time, so the hub never drifts from the repo. No BigQuery at render time.
build_hub.py injects it like dr_tab.py, in the Business tools group. The Markdown converter is
api_source_tab.md_to_html.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_source_tab import md_to_html  # noqa: E402

DOC = Path(__file__).resolve().parents[2] / "docs" / "PICKING_STAGING_APP.md"
START, END = "<!--picking-tab-start-->", "<!--picking-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "picking", "Picking & staging"


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
