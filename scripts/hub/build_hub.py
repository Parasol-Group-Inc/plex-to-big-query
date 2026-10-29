#!/usr/bin/env python3
"""Build the Plex Data Hub: one self-contained HTML page over every report,
raw table, pipeline, schedule and the probe/dispatcher logic.

    python scripts/hub/build_hub.py          # writes docs/hub/index.html (+ index_live.html)

index.html carries no BigQuery data and is committed. When data_snapshot.json
exists, the same page is also written with it embedded to index_live.html:
that is the one published as the artifact. data_snapshot.json and
index_live.html are gitignored because they hold real PlexProd rows.

Reads only what's in the repo, so re-run it after any report change:
  reports/*.yaml, reports/test/*.yaml   pipelines, extractions, bq_view lists
  reports/sql/*.sql                     BigQuery view SQL
  reports/plex_sql/*.sql                Plex SQL Developer equivalents
  docs/reports/*.md                     business-facing report docs
  catalog/full_schema_catalog.csv       column names/types of every Plex view
  docs/hub/platform.json                jobs, schedules, probe, infra, history, the Label Design tab
  docs/hub/label_design_colours.json    Label Design colour catalog (scripts/hub/label_colours.py)
  scripts/board/board_data.py           scorecard tiles, decisions, forms, glossary (the Migration Board's content)
  docs/hub/field_manual.json            scorecard teardowns, traps, risks, Plex glossary (Field Manual snapshot)
  docs/hub/data_snapshot.json           (optional, gitignored) row counts, sample rows, run logs, figure values (scripts/hub/snapshot_data.py)
  scripts/hub/template.html             the page; data is injected as JSON
"""
import csv
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
OUT = ROOT / "docs" / "hub" / "index.html"
OUT_LIVE = ROOT / "docs" / "hub" / "index_live.html"

RAW_RE = re.compile(r"\{dataset\}\.(raw_[A-Za-z0-9_]+)")
VIEW_RE = re.compile(r"\{dataset\}\.([A-Za-z0-9_]+)")
HEADER_RE = re.compile(r"^--\s*(plex_equivalent_of|confidence|plex_views|notes):\s*(.*)$", re.M)


def read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def rel(path):
    return path.relative_to(ROOT).as_posix()


def sql_name(sql_file):
    # gs://voxdatalake-report-configs/sql/x_view.sql -> x_view.sql
    return sql_file.rsplit("/", 1)[-1]


def count_views(cfg):
    views = (cfg or {}).get("bq_view") or []
    return 1 if isinstance(views, dict) else len(views)


def plex_header(text):
    meta = {k: v.strip() for k, v in HEADER_RE.findall(text)}
    if "plex_views" in meta:
        meta["plex_views"] = [v.strip() for v in meta["plex_views"].split(",") if v.strip()]
    return meta


def doc_info(path):
    text = read(path)
    if not text:
        return None
    status = re.search(r"^> \*\*Status:\*\*\s*(.*)$", text, re.M)
    status = status.group(1) if status else ""
    mark = next((m for m in ("✅", "🔬", "🛠", "🔍", "⚠️", "❌", "⏸") if status.startswith(m)), "")
    return {"path": rel(path), "status": status, "mark": mark, "markdown": text}


def load_columns(views):
    cols = defaultdict(list)
    with open(ROOT / "catalog" / "full_schema_catalog.csv", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["view_name"] in views and not row["column_name"].startswith("__ERROR__"):
                cols[row["view_name"]].append([row["column_name"], row["data_type"]])
    return cols


def tile_views(v):
    # "a · b · c", "safety_incidents (manual form)", "v2_x_report" -> view names
    names = [re.sub(r"\s*\(.*\)$", "", n).strip() for n in v.split("·")]
    return [n[3:] if n.startswith("v2_") else n for n in names if n]


# Lineage Navigator figure (data-id) -> Migration Board tile title it maps to
FIGURE_TILES = {
    "rev-mtd": "MTD Revenue", "rev-into-month": "% into month & run rate",
    "rev-goal": "Revenue goal & % to goal", "rev-to-goal": "Revenue goal & % to goal",
    "shipping": "Total in Shipping / Ready to Ship", "safe-days": "Safe days", "oos": "Out of stock", "wip": "WIP",
    "sales-mtd": "Sales MTD / YTD", "sales-ytd": "Sales MTD / YTD",
    "sales-to-goal": "Sales goal & % to goal", "sales-goal": "Sales goal & % to goal",
    "pipeline-funnel": "Opportunities & forecast stages", "pipeline-total": "Total pipeline",
    "reworks": "Reworks", "deviations": "Deviations", "destruction": "Destruction $ / Rework $",
    "tat": "30-day rolling TAT", "open-caps": "Open caps", "open-bottles": "Open bottles",
    **{f"{s}-bar": "Actual vs goal — all areas" for s in ("encap", "bottling", "labeling")},
    **{f"{s}-yday": "Encapsulation / Bottling / Labeling — yesterday" for s in ("encap", "bottling", "labeling")},
    **{f"{s}-goal": "Production goals & % to goal" for s in ("encap", "bottling", "labeling")},
    **{f"fpy-{s}": "FPY by area" for s in ("encap", "bottling", "labeling")},
}


def load_figures(tiles):
    """The Lineage Navigator's chart-level Looker audit, read from its HTML (owned by
    the scorecard project), each figure tied to the board tile that replaces it."""
    m = re.search(r'<script type="application/json" id="tile-data">(.*?)</script>',
                  read(ROOT / "score-card-reference" / "vox_scorecard_navigator.html") or "", re.S)
    by_title = {t["tile"]: t["id"] for t in tiles}
    figures = {}
    for f in json.loads(m.group(1)) if m else []:
        tile = by_title.get(FIGURE_TILES.get(f["id"], ""))
        if not tile:
            print(f"navigator figure {f['id']} maps to no board tile")
        figures[f["id"]] = {**f, "tile_id": tile}
    return figures


def load_scorecard(reports, other_inputs):
    """The Migration Board's content, imported from its own data file so the two
    pages can't disagree, plus the Field Manual snapshot matched by view name."""
    spec = importlib.util.spec_from_file_location("board_data", ROOT / "scripts" / "board" / "board_data.py")
    board = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(board)
    manual = json.loads(read(ROOT / "docs" / "hub" / "field_manual.json") or "{}")
    teardowns = {}
    for td in manual.get("teardowns", []):
        for v in td["views"]:
            for n in tile_views(v):
                teardowns.setdefault(n, td)

    manual_tables = sorted({f["table"] for f in board.FORMS} | {t["name"] for t in board.TABLES})
    tiles = []
    for i, t in enumerate(board.TILES):
        views = tile_views(t["v"])
        tile = {"id": f"t{i}", "section": t["s"], "tile": t["t"], "question": t["q"],
                "today": t["today"], "today_status": t["todayst"], "rows": t["rows"],
                "kind": t["kind"], "open": t["open"], "views": views,
                "missing": [v for v in views if v not in reports and v not in other_inputs and v not in manual_tables],
                "teardown": next((teardowns[v] for v in views if v in teardowns), None)}
        tiles.append(tile)
        for v in views:
            if v in reports:
                reports[v].setdefault("tiles", []).append(tile["id"])
    return {
        "figures": load_figures(tiles),
        "board_url": "https://claude.ai/code/artifact/89e5211a-10c8-4a59-bf3d-c92f188c47a9",
        "manual_url": manual.get("source", ""),
        "manual_snapshot": manual.get("snapshot", ""),
        "tiles": tiles,
        "manual_tables": manual_tables,
        "flags": board.FLAGS,
        "forms": board.FORMS,
        "tables": board.TABLES,
        "recent": [{"date": d, "title": t, "summary": s} for d, t, s in board.RECENT],
        "glossary": [{"term": t, "meaning": m, "why": w} for t, m, w in board.GLOSSARY],
        "asks": manual.get("asks", []),
        "traps": manual.get("traps", []),
        "risks": manual.get("risks", []),
        "plex_glossary": manual.get("plex_glossary", []),
    }


def add_qbo_tab(live):
    """Put the QuickBooks tab into the page that gets published.

    The tab is not part of the template: its figures come from BigQuery in parasoldatalake (Kaya and ODF
    books), so it is injected only into the live page, never the committed index.html. Publishing a page
    without it deletes the tab from the artifact, which happened on 2026-10-22, so a live page that cannot
    get the tab is an error rather than a quiet omission. `--no-qbo` is the explicit way out.
    """
    if "--no-qbo" in sys.argv:
        print("WARNING: --no-qbo: the live page has no QuickBooks tab. Publishing it deletes the tab from the artifact.")
        return live
    import qbo_tab
    try:
        from google.cloud import bigquery
        data = qbo_tab.gather(bigquery.Client(project=qbo_tab.BQ_PROJECT))
    except Exception as exc:
        sys.exit(f"Cannot build the QuickBooks tab: {exc}\n"
                 "It reads parasoldatalake with your own gcloud login (configuration `default`, "
                 "`gcloud auth application-default login`), not claude-readonly. "
                 "Fix that, or rerun with --no-qbo and do NOT publish index_live.html.")
    return qbo_tab.inject(live, qbo_tab.render_tab(data))


def main():
    pipelines, reports, tables = {}, {}, {}

    for yml in sorted(REPORTS.glob("*.yaml")):
        cfg = yaml.safe_load(read(yml))
        name = cfg["report_name"]
        test = REPORTS / "test" / yml.name
        test_cfg = yaml.safe_load(read(test)) if test.exists() else {}
        exts = cfg.get("extractions") or []
        views = cfg.get("bq_view") or []
        views = [views] if isinstance(views, dict) else views  # same as main.bq_view_configs
        pipelines[name] = {
            "name": name,
            "category": cfg.get("category", ""),
            "description": cfg.get("description", ""),
            "probe_mode": cfg.get("probe_mode", ""),
            "yaml": rel(yml),
            "yaml_text": read(yml),
            "test_yaml": rel(test) if test.exists() else "",
            "extraction_count": len(exts),
            "test_extraction_count": len((test_cfg or {}).get("extractions") or []),
            "view_count": len(views),
            "test_view_count": count_views(test_cfg),
            "tables": [e.get("bq_table") or "raw_" + e["plex_view"] for e in exts],
            "views": [v["name"] for v in views],
        }
        for e in exts:
            bq = e.get("bq_table") or "raw_" + e["plex_view"]
            t = tables.setdefault(bq, {
                "bq_table": bq, "plex_view": e["plex_view"], "pipelines": [],
                "extraction": {}, "used_by": [],
            })
            t["pipelines"].append(name)
            # first pipeline that extracts it wins; record any differing filter
            if not t["extraction"]:
                t["extraction"] = {k: v for k, v in e.items() if k not in ("plex_view", "bq_table")}
        for v in views:
            r = reports.setdefault(v["name"], {
                "name": v["name"], "display_name": v.get("display_name", v["name"]),
                "sql_file": sql_name(v["sql_file"]), "pipelines": [], "category": cfg.get("category", ""),
            })
            r["pipelines"].append(name)

    for r in reports.values():
        bq_path = REPORTS / "sql" / r["sql_file"]
        plex_path = REPORTS / "plex_sql" / r["sql_file"]
        bq_sql, plex_sql = read(bq_path), read(plex_path)
        raw = sorted(set(RAW_RE.findall(bq_sql)))
        others = sorted({m for m in VIEW_RE.findall(bq_sql) if not m.startswith("raw_")})
        r.update({
            "bq_sql_path": rel(bq_path), "bq_sql": bq_sql,
            "plex_sql_path": rel(plex_path) if plex_sql else "", "plex_sql": plex_sql,
            "plex_meta": plex_header(plex_sql),
            "raw_tables": raw,
            "upstream_views": [o for o in others if o in reports and o != r["name"]],
            "other_inputs": [o for o in others if o not in reports],
            "doc": doc_info(ROOT / "docs" / "reports" / f"{r['name']}.md"),
        })
        for t in raw:
            if t in tables:
                tables[t]["used_by"].append(r["name"])
            else:  # read but extracted nowhere: flag it rather than drop it
                tables[t] = {"bq_table": t, "plex_view": t[4:], "pipelines": [],
                             "extraction": {}, "used_by": [r["name"]], "orphan": True}
    for r in reports.values():
        r["downstream_views"] = sorted(o["name"] for o in reports.values() if r["name"] in o["upstream_views"])

    columns = load_columns({t["plex_view"] for t in tables.values()})
    for t in tables.values():
        t["columns"] = columns.get(t["plex_view"], [])
        t["used_by"] = sorted(set(t["used_by"]))

    # other inputs (goals tables, plex_api_*) get their doc if one exists
    other_inputs = {}
    for r in reports.values():
        for o in r["other_inputs"]:
            other_inputs.setdefault(o, {"name": o, "used_by": [], "doc": doc_info(ROOT / "docs" / "reports" / f"{o}.md")})
            other_inputs[o]["used_by"].append(r["name"])

    platform = json.loads(read(ROOT / "docs" / "hub" / "platform.json") or "{}")
    scorecard = load_scorecard(reports, other_inputs)

    data = {
        "built": date.today().isoformat(),
        "pipelines": sorted(pipelines.values(), key=lambda p: p["name"]),
        "reports": sorted(reports.values(), key=lambda r: (r["category"], r["display_name"].lower())),
        "tables": sorted(tables.values(), key=lambda t: t["plex_view"]),
        "other_inputs": sorted(other_inputs.values(), key=lambda o: o["name"]),
        "platform": platform,
        "scorecard": scorecard,
        # the Label Design tab: platform.json's hand-written part plus the colour
        # catalog written by scripts/hub/label_colours.py
        "label_colours": json.loads(read(ROOT / "docs" / "hub" / "label_design_colours.json") or "{}"),
        "snapshot": {},
    }
    # live data, refreshed only by scripts/hub/snapshot_data.py; never in the committed page
    snapshot = json.loads(read(ROOT / "docs" / "hub" / "data_snapshot.json") or "{}")

    template = read(ROOT / "scripts" / "hub" / "template.html")
    mermaid = platform.get("mermaid", {})
    for key in ("architecture", "env_paths", "probe_flow", "dispatch_sequence", "deploy_flow", "label_design_flow"):
        src = mermaid.get(key, "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        template = template.replace(f"<!--MERMAID:{key}-->", src)
    page = lambda d: template.replace("/*__HUB_DATA__*/", json.dumps(d, ensure_ascii=False).replace("</", "<\\/"))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = page(data)
    OUT.write_text(html, encoding="utf-8", newline="\n")
    if snapshot:
        import audit_tab  # findings in docs/hub/audit.json (gitignored); no file, no tab
        live = audit_tab.add(add_qbo_tab(page({**data, "snapshot": snapshot})))
        OUT_LIVE.write_text(live, encoding="utf-8", newline="\n")
        print(f"{rel(OUT_LIVE)}: {len(live) // 1024} KB with the data snapshot of {snapshot.get('taken_at')} (publish this one)")
    missing = [r["name"] for r in reports.values() if not r["plex_sql"]]
    print(f"{rel(OUT)}: {len(reports)} reports, {len(tables)} raw tables, {len(pipelines)} pipelines, "
          f"{len(html) // 1024} KB; Plex SQL missing for {len(missing)}: {', '.join(missing) or '-'}")
    unmatched = sorted({v for t in scorecard["tiles"] for v in t["missing"]})
    print(f"scorecard: {len(scorecard['tiles'])} tiles; views not in any pipeline: {', '.join(unmatched) or '-'}")


if __name__ == "__main__":
    main()
