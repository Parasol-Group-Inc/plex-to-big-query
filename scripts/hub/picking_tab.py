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

# Demo videos (recorded 2026-11-23 on the deployed app, Plex TEST). Published next to the hub page
# under videos/ (Artifact `files`; a rebuild that leaves them out keeps them). Durable copies:
# gs://voxdatalake-plex-screenshots/picking-app/videos/2026-11-23/. Re-record: docs/PICKING_STAGING_APP.md,
# "Demo videos".
VIDEOS = [
    ("videos/picking-app-1-find-and-read-the-pick-list.mp4", "1. Find the pick list and read it", "1:29"),
    ("videos/picking-app-2-stage-an-ingredient-in-one-click.mp4", "2. Stage a whole ingredient in one click", "1:21"),
    ("videos/picking-app-3-safety-rules-and-move-log.mp4", "3. Safety rules and the move log", "1:00"),
    ("videos/picking-app-full-demo.mp4", "All three in one", "3:50"),
]


def videos_html() -> str:
    cards = "".join(
        f'<figure class="pv"><video controls preload="metadata" playsinline src="{src}"></video>'
        f'<figcaption><b>{label}</b> <span class="muted">{dur}</span></figcaption></figure>' for src, label, dur in VIDEOS)
    return (f'<h2>Demo videos (2026-11-23, Plex TEST)</h2><p>Recorded on the deployed app with captions; every container '
            f'moved in them was put back. To save one: the ⋮ menu on the player, or the files in '
            f'gs://voxdatalake-plex-screenshots/picking-app/videos/2026-11-23/.</p>'
            f'<div class="pvs">{cards}</div>')


def render_tab() -> str:
    body = md_to_html(DOC.read_text(encoding="utf-8"))
    return f"""{START}<style>
#s-{KEY} .ref h2 {{ margin-top: 28px; }}
#s-{KEY} td {{ overflow-wrap: anywhere; }}
#s-{KEY} ol.plain {{ padding-left: 20px; }}
#s-{KEY} .pvs {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; margin: 10px 0 18px; }}
#s-{KEY} .pv {{ margin: 0; }}
#s-{KEY} .pv video {{ width: 100%; border-radius: 8px; border: 1px solid var(--line, #ddd); background: #111; }}
#s-{KEY} .pv figcaption {{ font-size: 13px; margin-top: 4px; }}
</style><section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref"><div class="block">
<p class="lede">From docs/PICKING_STAGING_APP.md (rendered when the hub is built). Code: deploy/picking_app/;
live on Cloud Run against Plex TEST since 2026-11-20 (https://picking-app-651304971296.us-central1.run.app).</p>
{videos_html()}{body}</div></div></section>{END}"""


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
