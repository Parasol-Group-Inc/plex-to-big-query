#!/usr/bin/env python3
"""Snapshot live BigQuery data for the Plex Data Hub.

    python scripts/hub/snapshot_data.py      # writes docs/hub/data_snapshot.json
    python scripts/hub/build_hub.py          # then rebuild the page

Read-only. For PlexProd and PlexTest it records every report view's row count,
columns and first SAMPLE_ROWS rows, every raw_* table's row count and last
change, the newest probe_log and job_run_log rows, and each scorecard figure's
current value (scripts/hub/figure_queries.py). From PlexOps it takes the newest
etl_dispatch_log rows. The page shows the snapshot's timestamp: it is a picture
of the moment this ran, not live data.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from google.cloud import bigquery

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_queries import FIGURES  # noqa: E402

PROJECT = "voxdatalake"
DATASETS = ("PlexProd", "PlexTest")
SAMPLE_ROWS = 25
LOG_ROWS = 60
OUT = ROOT / "docs" / "hub" / "data_snapshot.json"


def cell(v):
    # JSON-safe and short: the page shows samples, not full payloads
    if v is None or isinstance(v, (bool, int)):
        return v
    if isinstance(v, float):
        return round(v, 4)
    if isinstance(v, Decimal):
        return float(round(v, 4))
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    s = json.dumps(v, default=str) if isinstance(v, (dict, list)) else str(v)
    s = s.replace("�", "?")  # Plex already stores some names with lost characters
    return s if len(s) <= 160 else s[:157] + "..."


def rows(client, sql):
    res = client.query(sql).result()
    cols = [f.name for f in res.schema]
    return cols, [[cell(r[c]) for c in cols] for r in res]


def view_info(client, ds, name):
    try:
        cols, sample = rows(client, f"SELECT * FROM `{PROJECT}.{ds}.{name}` LIMIT {SAMPLE_ROWS}")
        n = rows(client, f"SELECT COUNT(*) AS n FROM `{PROJECT}.{ds}.{name}`")[1][0][0]
        return name, {"rows": n, "columns": cols, "sample": sample}
    except Exception as exc:  # a broken view is worth showing, not fatal
        return name, {"error": str(exc).splitlines()[0][:300]}


def log_rows(client, table, order, select="*"):
    try:
        cols, data = rows(client, f"SELECT {select} FROM `{table}` ORDER BY {order} DESC LIMIT {LOG_ROWS}")
        return {"columns": cols, "rows": data}
    except Exception as exc:
        return {"error": str(exc).splitlines()[0][:300]}


def figure_value(client, ds, fid, spec):
    if not spec.get("sql"):
        return fid, None
    try:
        cols, data = rows(client, spec["sql"].format(ds=ds))
        return fid, dict(zip(cols, data[0])) if data else {"error": "no row"}
    except Exception as exc:
        return fid, {"error": str(exc).splitlines()[0][:300]}


def snapshot_dataset(client, pool, ds):
    tables = list(client.list_tables(f"{PROJECT}.{ds}"))
    views = [t.table_id for t in tables if t.table_type == "VIEW"]
    meta = rows(client, f"SELECT table_id, row_count, last_modified_time FROM `{PROJECT}.{ds}.__TABLES__`")[1]
    raw = {t: {"rows": n, "modified": datetime.fromtimestamp(m / 1000, timezone.utc).isoformat(timespec="minutes")}
           for t, n, m in meta if t.startswith("raw_")}
    return {
        "views": dict(pool.map(lambda v: view_info(client, ds, v), views)),
        "raw": raw,
        "probe_log": log_rows(client, f"{PROJECT}.{ds}.probe_log", "probed_at", "* EXCEPT (snapshot)"),
        "job_run_log": log_rows(client, f"{PROJECT}.{ds}.job_run_log", "logged_at"),
        "figures": dict(pool.map(lambda kv: figure_value(client, ds, *kv), FIGURES.items())),
    }


def main():
    client = bigquery.Client(project=PROJECT)
    with ThreadPoolExecutor(max_workers=8) as pool:
        envs = {ds: snapshot_dataset(client, pool, ds) for ds in DATASETS}
    snap = {
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "envs": envs,
        "dispatch_log": log_rows(client, f"{PROJECT}.PlexOps.etl_dispatch_log", "dispatched_at"),
        "figure_specs": {k: {x: v.get(x) for x in ("sql", "format", "pct_scale", "view", "note")} for k, v in FIGURES.items()},
    }
    OUT.write_text(json.dumps(snap, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    for ds, e in envs.items():
        bad = [v for v, i in e["views"].items() if "error" in i]
        print(f"{ds}: {len(e['views'])} views, {len(e['raw'])} raw tables; view errors: {', '.join(bad) or '-'}")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
