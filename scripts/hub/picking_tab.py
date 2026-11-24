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

# Demo videos, second take (2026-11-23 evening, Plex TEST): the real targets from Plex history, the review
# dialog, and undo from the Move log with its limit. The first take (moves to the "... Staging" locations, which
# the team does not use) was withdrawn. Published next to the hub page under videos/ (Artifact `files`; the old
# paths were removed). Durable copies: gs://voxdatalake-plex-screenshots/picking-app/videos/2026-11-23-v2/.
# Re-record: docs/PICKING_STAGING_APP.md, "Demo videos".
VIDEOS = [
    ("videos/picking-app-1-pick-list-and-real-targets.mp4", "1. The pick list, and where material really goes", "1:27"),
    ("videos/picking-app-2-review-and-approve-a-move.mp4", "2. Review, then approve, every move", "1:19"),
    ("videos/picking-app-3-undo-and-its-limit.mp4", "3. Undo from the Move log, and its limit", "1:23"),
    ("videos/picking-app-full-demo-v2.mp4", "All three in one", "4:09"),
]


def videos_html() -> str:
    cards = "".join(
        f'<figure class="pv"><video controls preload="metadata" playsinline src="{src}"></video>'
        f'<figcaption><b>{label}</b> <span class="muted">{dur}</span></figcaption></figure>' for src, label, dur in VIDEOS)
    return (f'<h2>Demo videos (2026-11-23, second take, Plex TEST)</h2><p>Recorded with captions on Plex TEST (a local server running the same code as the deployed app); every container '
            f'moved in them was put back. To save one: the ⋮ menu on the player, or the files in '
            f'gs://voxdatalake-plex-screenshots/picking-app/videos/2026-11-23-v2/.</p>'
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
on Cloud Run since 2026-11-20 (https://picking-app-651304971296.us-central1.run.app; Plex TEST, moves off in production). Audit 2026-11-23: docs/PICKING_AUDIT_2026-11-23.md.</p>
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
