"""Refresh the data inside a published Plex Data Hub page, leaving its tabs untouched.

Usage: refresh_live_data.py <live.html> <out.html>
Reads docs/hub/index.html (fresh build) and docs/hub/data_snapshot.json.
"""
import json
import re
import sys
from pathlib import Path

HUB = Path(__file__).resolve().parents[2] / "docs" / "hub"
PAT = re.compile(r'(<script id="hub-data" type="application/json">)(.*?)(</script>)', re.S)


def load(html, what):
    found = PAT.findall(html)
    if len(found) != 1:
        sys.exit(f"{what}: hub-data script found {len(found)} times, expected exactly 1")
    return json.loads(found[0][1].replace("<\\/", "</"))


def counts(d):
    return {k: len(d.get(k) or []) for k in ("reports", "tables", "pipelines")}


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    live = Path(sys.argv[1]).read_text(encoding="utf-8")
    old = load(live, "live page")
    fresh = load((HUB / "index.html").read_text(encoding="utf-8"), "docs/hub/index.html")
    fresh["snapshot"] = json.loads((HUB / "data_snapshot.json").read_text(encoding="utf-8"))
    blob = json.dumps(fresh, ensure_ascii=False).replace("</", "<\\/")
    out = PAT.sub(lambda m: m.group(1) + blob + m.group(3), live, count=1)
    Path(sys.argv[2]).write_text(out, encoding="utf-8")
    o, n = counts(old), counts(fresh)
    print("built:", old.get("built"), "->", fresh.get("built"))
    print("snapshot taken_at:", (old.get("snapshot") or {}).get("taken_at"), "->", fresh["snapshot"].get("taken_at"))
    for k in o:
        print(f"{k}: {o[k]} -> {n[k]}")
    print("size:", len(live), "->", len(out))


if __name__ == "__main__":
    main()
