#!/usr/bin/env python3
"""
Build the scorecard sandbox: a stable, full-year copy of every table the Vox
scorecard reads, for designing the Looker Studio report against.

    python scripts/scorecard_sandbox/build.py            # full rebuild
    python scripts/scorecard_sandbox/build.py --views    # recreate views only
    python scripts/scorecard_sandbox/build.py --verify   # tile check only

WHY A SEPARATE DATASET. PlexProd holds almost nothing until the 19 Oct cutover,
and PlexTest is overwritten by every ETL run and wiped nightly, so injected
test data is gone by the next morning. Looker Studio work spans days. The
sandbox is never touched by the ETL.

HOW EVERY TILE IS FED — the rule this build does not break:
  * Plex tiles read the SAME views, created from the SAME SQL files in
    reports/sql/, over raw_* tables shaped exactly like the ETL's. Nothing is
    written into a view's output.
  * Manual tiles (goals, safety) read the same tables the manual-data app
    writes, with the app's columns.
  * Synthetic Plex rows are clones of real PlexTest rows (see common.py), at
    the scale of Vox's own live scorecard (see scale.py).
So a Looker report built here swaps to PlexProd by changing the dataset and
nothing else: same view names, same columns.

Rebuilding is safe and idempotent: every base table is re-copied from PlexTest
first, which discards the previous build's synthetic rows.
"""

import argparse
import glob
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts", "board"))

from google.cloud import bigquery  # noqa: E402

from common import PROJECT, SANDBOX, SOURCE, Sandbox  # noqa: E402

REF = re.compile(r"\{gcp_project\}\.\{dataset\}\.([A-Za-z0-9_]+)")

# THE SNAPSHOT. Plex tables are copied from PlexTest AS IT WAS at this
# instant (BigQuery time travel, 7-day window), not as it is now. Checked with
# snapshot_check.py on 2026-09-24: at this moment every key the tile views
# join on resolves — 2,119/2,119 customer part prices, 2,120/2,120 customer
# parts, 182 customers (150 with an account rep), 160 jobs. By the evening of
# the 24th the tenant had been cut back to 24 customers and 312 unpriced
# customer parts, and the ETL's keep-yesterday-on-zero-rows rule left a price
# table pointing at keys that no longer existed: 0/2,119 joined.
# If time travel no longer reaches this instant, pick a new one with
# snapshot_check.py — never build on an instant that fails it.
SNAPSHOT = "2026-09-23 12:00:00+00"

# Copied as they are NOW: the real Quality records (Vox's Quality team keeps
# adding to them) and everything a person enters by hand.
COPY_CURRENT = re.compile(r"^(raw_Quality_v_|scorecard_goals|safety_incidents|turnaround_standards)")

# Rows left in PlexTest by scripts/scorecard_test_data.py. Stripped after the
# copy: they are exactly the "one part, one customer, $1.25" rows the sandbox
# exists to replace.
LEGACY_INJECTOR_ROWS = {
    "raw_Part_v_Production": "SAFE_CAST(Production_No AS INT64) >= 990000000",
    "raw_Part_v_Cycle_Inventory": "SAFE_CAST(Cycle_Inventory_Key AS INT64) >= 990000000",
    "raw_Sales_v_Shipper": "SAFE_CAST(Shipper_Key AS INT64) >= 990000000",
    "raw_Sales_v_Shipper_Line": "SAFE_CAST(Shipper_Line_Key AS INT64) >= 990000000",
    "raw_Part_v_Cell_Production": "Cell_Production_Key LIKE '99%'",
    "raw_Part_v_Cell_Depletion": "Cell_Depletion_Key LIKE '99%'",
    "safety_incidents": "updated_by LIKE 'ZZTEST%'",
}


# ── what the scorecard reads ───────────────────────────────────────────────

def scorecard_views():
    """Every tile view plus everything it depends on, in creation order,
    with the SQL file each comes from. Read from the prod YAMLs so the
    sandbox always matches what is actually deployed."""
    from board_data import TILES

    sql_of = {}
    for y in glob.glob(os.path.join(ROOT, "reports", "*.yaml")):
        cfg = yaml.safe_load(open(y, encoding="utf-8"))
        bv = cfg.get("bq_view") or []
        for v in bv if isinstance(bv, list) else [bv]:
            if v.get("sql_file"):
                sql_of[v["name"]] = os.path.join(
                    ROOT, "reports", "sql", os.path.basename(v["sql_file"]))

    def refs(v):
        return sorted(set(REF.findall(open(sql_of[v], encoding="utf-8").read())))

    order, base = [], set()

    def walk(v):
        if v in order or v in base:
            return
        if v not in sql_of:
            base.add(v)
            return
        for d in refs(v):
            walk(d)
        order.append(v)

    for t in TILES:
        for v in re.split(r"\s*·\s*", t["v"]):
            v = v.replace("(manual form)", "").strip()
            if v:
                walk(v)
    return order, sorted(base), sql_of


# ── steps ──────────────────────────────────────────────────────────────────

def ensure_dataset(sb):
    ds = bigquery.Dataset(f"{PROJECT}.{SANDBOX}")
    ds.location = "US"
    ds.description = ("Scorecard sandbox: a full simulated year for designing the "
                      "Looker Studio report. NOT REAL DATA. Built by "
                      "scripts/scorecard_sandbox/build.py; never written by the ETL.")
    sb.client.create_dataset(ds, exists_ok=True)


def copy_base_tables(sb, base):
    print(f"Copying {len(base)} base tables {SOURCE} -> {SANDBOX} (Plex tables as of {SNAPSHOT})")
    for t in base:
        src = f"{PROJECT}.{SOURCE}.{t}"
        dst = f"{PROJECT}.{SANDBOX}.{t}"
        try:
            sb.client.get_table(src)
        except Exception:
            print(f"  ! {t} missing in {SOURCE} — the view that reads it will fail")
            continue
        copy_now = COPY_CURRENT.match(t)
        if not copy_now:
            try:
                sb.client.query(
                    f"CREATE OR REPLACE TABLE `{dst}` AS "
                    f"SELECT * FROM `{src}` FOR SYSTEM_TIME AS OF TIMESTAMP '{SNAPSHOT}'").result()
            except Exception as e:
                # A table first extracted AFTER the snapshot instant has no
                # version to travel back to (raw_Part_v_Part_Group, added
                # 2026-09-24). Master/lookup tables like that are copied as
                # they are now — say so, since it breaks the one-instant rule.
                if "SYSTEM_TIME" not in str(e) and "time travel" not in str(e).lower() \
                        and "before" not in str(e).lower():
                    raise
                print(f"  ~ {t} did not exist at {SNAPSHOT}; copied as it is now")
                copy_now = True
        if copy_now:
            sb.client.copy_table(src, dst, job_config=bigquery.CopyJobConfig(
                write_disposition="WRITE_TRUNCATE")).result()
        pred = LEGACY_INJECTOR_ROWS.get(t)
        if pred:
            sb.exec(f"DELETE FROM `{{ds}}.{t}` WHERE {pred}")
    sb._schemas.clear()


PROPOSED = os.path.join(HERE, "proposed_sql")


def create_views(sb, order, sql_of):
    """Views come from reports/sql/ — the deployed SQL — unless proposed_sql/
    holds a file of the same name: a fix the sandbox found, NOT yet approved
    or deployed. Each one is printed on every build so nobody designs against
    it believing production already behaves that way."""
    print(f"Creating {len(order)} views")
    failed = []
    for name in order:
        path = sql_of[name]
        proposed = os.path.join(PROPOSED, os.path.basename(path))
        if os.path.exists(proposed):
            print(f"  ⚠ {name}: using PROPOSED SQL (not deployed) — {os.path.relpath(proposed, ROOT)}")
            path = proposed
        sql = (open(path, encoding="utf-8").read()
               .replace("{gcp_project}", PROJECT).replace("{dataset}", SANDBOX))
        try:
            sb.client.query(
                f"CREATE OR REPLACE VIEW `{PROJECT}.{SANDBOX}.{name}` AS\n{sql}").result()
        except Exception as e:
            failed.append((name, str(e).split("\n")[0][:200]))
    for name, err in failed:
        print(f"  ✗ {name}: {err}")
    return failed


def verify(sb, order):
    """Row count, month span and error per view — an error and an empty view
    look identical on a dashboard, so both are reported, never just counts."""
    import re as _re
    print(f"\n{'view':52} {'rows':>7}  span")
    for name in order:
        try:
            t = sb.client.get_table(f"{PROJECT}.{SANDBOX}.{name}")
            dc = [f.name for f in t.schema if f.field_type in ("DATE", "TIMESTAMP")
                  and _re.search(r"month|date|period", f.name, _re.I)]
            extra = ""
            if dc:
                extra = (f", COUNT(DISTINCT DATE_TRUNC(DATE({dc[0]}), MONTH)) m,"
                         f" MIN(DATE({dc[0]})) lo, MAX(DATE({dc[0]})) hi")
            r = sb.query(f"SELECT COUNT(*) n{extra} FROM `{{ds}}.{name}`")[0]
            span = f"{r['m']} mo {r['lo']}..{r['hi']}" if dc else ""
            print(f"{name:52} {r['n']:>7}  {span}")
        except Exception as e:
            print(f"{name:52} {'ERROR':>7}  {str(e).splitlines()[0][:90]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--views", action="store_true", help="recreate views only")
    ap.add_argument("--verify", action="store_true", help="tile check only")
    args = ap.parse_args()

    sb = Sandbox()
    order, base, sql_of = scorecard_views()

    if not (args.views or args.verify):
        import generators  # noqa: E402
        ensure_dataset(sb)
        copy_base_tables(sb, base)
        generators.run_all(sb)
    if not args.verify:
        create_views(sb, order, sql_of)
    verify(sb, order + ["safety_incidents"])


if __name__ == "__main__":
    main()
