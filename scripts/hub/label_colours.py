#!/usr/bin/env python3
"""Label Design colour catalog for the Data Hub: every status label the push
writes, with its colour on the push board and on Design & QA, and what a board
move turns it into. Read-only (Monday reads, one BigQuery query).

    python scripts/hub/label_colours.py            # writes docs/hub/label_design_colours.json
    python scripts/hub/label_colours.py --check    # same, exits 1 if a label Plex sends would move wrong

Why colours: a Monday board move carries a status value across by the label's
COLOUR, not its name (proven 2026-10-27; label_design_service/labels.py). The
destination shows its label of that colour, or the column's default when it
has none. The push aligns colours itself before creating items; this file
shows the state of both boards so anyone can see it, and flags drift.

The pushed status columns are read from COLUMNS in label_design_service/push.py
(parsed, not imported), so the catalog follows the push. Needs MONDAY_API_KEY
(env, or the MONDAY_API_KEY= line in .env) and BigQuery read access for the
"sent by Plex" counts (skipped with --no-bq).
"""
import argparse
import ast
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "label_design_service"))
from monday import Monday  # noqa: E402
import labels  # noqa: E402

OUT = ROOT / "docs" / "hub" / "label_design_colours.json"
PUSH_BOARD, DEST_BOARD = "18437236736", "18395121955"   # Plex Import Test, Design & QA
OLD_PUSH_BOARD = "18432111755"                          # "Plex Import", retired 2026-10-27 (earlier push log rows)


def pushed_status_titles():
    tree = ast.parse((ROOT / "label_design_service" / "push.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "COLUMNS" for t in node.targets):
            return [e.elts[0].value for e in node.value.elts
                    if isinstance(e, ast.Tuple) and e.elts[1].value == "status"]
    raise SystemExit("COLUMNS not found in push.py")


def api_key():
    if os.environ.get("MONDAY_API_KEY"):
        return os.environ["MONDAY_API_KEY"]
    for env in (ROOT / ".env", ROOT.parent / "plex-to-big-query" / ".env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("MONDAY_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("MONDAY_API_KEY not set and not found in .env")


def sent_counts(api, titles):
    """{title: Counter(label)} over every item the prod push created."""
    from google.cloud import bigquery
    col_title = {}
    for b in (PUSH_BOARD, OLD_PUSH_BOARD):
        try:
            for c in api("query ($b: [ID!]) { boards(ids: $b) { columns { id title type } } }",
                         {"b": [b]})["boards"][0]["columns"]:
                if c["type"] == "status" and c["title"] in titles:
                    col_title.setdefault(c["id"], c["title"])
        except Exception:
            pass
    rows = bigquery.Client(project="voxdatalake").query(
        "SELECT column_values FROM `voxdatalake.PlexProd.label_design_push_log` "
        "WHERE outcome IN ('created', 'partial')").result()
    out = {t: Counter() for t in titles}
    for r in rows:
        for cid, v in json.loads(r.column_values or "{}").items():
            if cid in col_title and isinstance(v, dict) and v.get("label"):
                out[col_title[cid]][v["label"]] += 1
    return out


def build(api, titles, counts):
    push = labels._status_columns(api, PUSH_BOARD, set(titles))
    dest = labels._status_columns(api, DEST_BOARD, set(titles))
    names = {b: api("query ($b: [ID!]) { boards(ids: $b) { name } }", {"b": [b]})["boards"][0]["name"]
             for b in (PUSH_BOARD, DEST_BOARD)}
    columns, problems = [], []
    for title in titles:
        p_labels = [l for l in push[title]["settings"]["labels"] if l["label"]] if title in push else []
        d_labels = [l for l in dest[title]["settings"]["labels"] if l["label"]] if title in dest else []
        p, d = labels._by_name(p_labels), labels._by_name(d_labels)
        by_colour = {}
        for l in d_labels:   # an active label wins a colour over a deactivated one
            if l["color"] not in by_colour or not l["is_deactivated"]:
                by_colour[l["color"]] = l["label"]
        rows = []
        for name in sorted(set(p) | set(d), key=str.lower):
            pl, dl = p.get(name), d.get(name)
            lands = by_colour.get(pl["color"]) if pl else None
            if pl and dl:
                state = "ok" if pl["color"] == dl["color"] else "wrong"
            elif pl:
                state = "blank" if lands is None else "wrong"
            else:
                state = "dqa_only"
            sent = counts.get(title, {}).get(name, 0) if counts is not None else None
            if state == "wrong" or (state == "blank" and sent):
                problems.append(f"{title}: {name!r} would arrive as {lands or 'blank'}")
            rows.append({
                "label": name, "state": state, "lands_as": lands if pl else None, "sent": sent,
                "push": {"hex": pl["hex"], "id": pl["id"], "off": pl["is_deactivated"]} if pl else None,
                "dqa": {"hex": dl["hex"], "id": dl["id"], "off": dl["is_deactivated"]} if dl else None,
            })
        columns.append({"title": title, "push_column": push.get(title, {}).get("id"),
                        "dqa_column": dest.get(title, {}).get("id"), "labels": rows})
    return {
        "taken_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "push_board": {"id": PUSH_BOARD, "name": names[PUSH_BOARD]},
        "dqa_board": {"id": DEST_BOARD, "name": names[DEST_BOARD]},
        "sent_counted": counts is not None,
        "columns": columns,
        "problems": problems,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if a pushed label would move wrong")
    ap.add_argument("--no-bq", action="store_true", help="skip the 'sent by Plex' counts")
    a = ap.parse_args()
    api = Monday(api_key())
    titles = pushed_status_titles()
    counts = None if a.no_bq else sent_counts(api, titles)
    data = build(api, titles, counts)
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    n = sum(len(c["labels"]) for c in data["columns"])
    states = Counter(l["state"] for c in data["columns"] for l in c["labels"])
    print(f"{OUT.relative_to(ROOT)}: {len(titles)} columns, {n} labels {dict(states)}")
    for p in data["problems"]:
        print("  MOVES WRONG:", p)
    if a.check and data["problems"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
