#!/usr/bin/env python3
"""Last-rendered copies of the hub tabs whose inputs live on one machine only (2026-11-12).

Most of the Plex Data Hub builds anywhere from the repo plus read-only BigQuery. Four tabs do not:

| Tab | Its inputs | Where they are |
|---|---|---|
| QuickBooks (`qbo_tab`) | parasoldatalake BigQuery | Emilio's own gcloud login (ADC) |
| Audit (`audit_tab`) | `docs/hub/audit.json` | gitignored, one laptop |
| Screen extraction (`screens_tab`) | `docs/hub/screens/` screenshots | gitignored, the Windows laptop |
| Customer notes (`customer_notes_tab`) | `etl-manual/customer_note/` plan, log, screenshots | gitignored, the primary folder |

Until 11-12 a build without those inputs silently dropped the tab, so the published page was patched
together by hand from builds on different machines. Now `build_hub.py` saves each of these tabs'
rendered HTML here whenever it can render it, and on a machine without the inputs it uses the last
saved copy. One command builds the whole page anywhere:

    python scripts/hub/snapshot_data.py && python scripts/hub/build_hub.py   # -> docs/hub/index_live.html

The store is a private GCS folder in voxdatalake (`HUB_TAB_STORE`, default below: the screenshots bucket,
kept 365 days and rewritten by every build that can render a tab; not the prod config bucket); nothing is committed, because these tabs hold business data (QuickBooks figures, customer
names, screenshots). Reads and writes use the gcloud CLI, so they follow the active login or
`CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT` (Claude: claude-operator; claude-readonly cannot read it).

    python scripts/hub/tab_store.py --seed <published page.html>   # save every stored tab from a page
    python scripts/hub/tab_store.py --list
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

STORE = os.environ.get("HUB_TAB_STORE", "gs://voxdatalake-plex-screenshots/hub-tabs").rstrip("/")
# key -> (start marker, end marker); keep in step with each module's START/END
TABS = {
    "qbo": ("<!--qbo-tab-start-->", "<!--qbo-tab-end-->"),
    "audit": ("<!--audit-tab-start-->", "<!--audit-tab-end-->"),
    "screens": ("<!--screens-tab-start-->", "<!--screens-tab-end-->"),
    "custnotes": ("<!--custnotes-tab-start-->", "<!--custnotes-tab-end-->"),
}


def extract(page: str, key: str) -> str | None:
    """The tab's section, markers included, or None if the page does not have it exactly once."""
    start, end = TABS[key]
    found = re.findall(re.escape(start) + ".*?" + re.escape(end), page, flags=re.S)
    return found[0] if len(found) == 1 else None


def _gcloud(*args: str, data: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["gcloud", "storage", *args], input=data, capture_output=True, timeout=120)


def save(key: str, section: str) -> bool:
    """Store a rendered section. Never raises; says what happened."""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(section)
        r = _gcloud("cp", "--quiet", f.name, f"{STORE}/{key}.html")
        os.unlink(f.name)
        ok = r.returncode == 0
        print(f"tab_store: {'saved' if ok else 'could NOT save'} {key} ({len(section) // 1024} KB)"
              + ("" if ok else f": {r.stderr.decode(errors='replace').strip().splitlines()[-1:]}"))
        return ok
    except Exception as exc:
        print(f"tab_store: could NOT save {key}: {exc}")
        return False


def load(key: str) -> str | None:
    """The last stored section, or None (never raises)."""
    try:
        with tempfile.TemporaryDirectory() as d:
            dst = Path(d) / f"{key}.html"
            r = _gcloud("cp", "--quiet", f"{STORE}/{key}.html", str(dst))
            if r.returncode != 0 or not dst.exists():
                return None
            section = dst.read_text(encoding="utf-8")
        start, end = TABS[key]
        if not (section.startswith(start) and section.rstrip().endswith(end)):
            print(f"tab_store: stored {key} is malformed; ignored")
            return None
        print(f"tab_store: using the stored {key} tab ({len(section) // 1024} KB)")
        return section
    except Exception as exc:
        print(f"tab_store: could not load {key}: {exc}")
        return None


def add_with_store(live: str, key: str, render_add, inject) -> str:
    """render_add(live) renders the tab from local inputs (returns live unchanged without them).
    Rendered: store it. Not rendered: inject the stored copy, if there is one."""
    out = render_add(live)
    section = extract(out, key)
    if section and section not in live:
        save(key, section)
        return out
    stored = load(key)
    if stored is None:
        print(f"WARNING: tab {key}: no local inputs and nothing stored; the page has no {key} tab")
        return out
    return inject(out, stored)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--seed":
        page = Path(sys.argv[2]).read_text(encoding="utf-8")
        for k in TABS:
            s = extract(page, k)
            print(f"{k}: " + ("not in the page" if s is None else ("saved" if save(k, s) else "save failed")))
    elif sys.argv[1:] == ["--list"]:
        print(_gcloud("ls", "-l", f"{STORE}/").stdout.decode())
    else:
        sys.exit(__doc__)
