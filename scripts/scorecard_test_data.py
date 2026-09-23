#!/usr/bin/env python3
"""
Scorecard test data — inject on demand, delete on demand.
=========================================================

WHAT THIS IS FOR. Most scorecard tiles read a view that reads a Plex table.
When a tile is blank there are two possible reasons and they look identical
from the dashboard: the view is wrong, or the Plex test tenant simply has
nothing of that kind. This script settles it by putting rows in, so a tile
that stays blank with data underneath is a tile we have to fix.

WHAT IT IS NOT. This is not a Plex simulator and the rows are not realistic.
They are shaped to satisfy the views — right columns, right types, right keys
— so the numbers will not resemble Vox's business and should never be read as
if they did. The point is "does anything arrive at all", not "is the figure
right". The test tenant is also wiped nightly (midnight UTC), so anything
injected is gone by morning and can simply be injected again.

    python scripts/scorecard_test_data.py --status
    python scripts/scorecard_test_data.py --inject
    python scripts/scorecard_test_data.py --inject --recipes production,shipping
    python scripts/scorecard_test_data.py --delete

HOW REMOVAL IS GUARANTEED. Two independent mechanisms, because a cleanup that
depends on a record of what was written is a cleanup that fails exactly when
it matters:

  1. Every injected row is MARKED — synthetic integer keys start at 990000000
     and synthetic text keys start with "ZZTEST". Nothing Plex generates comes
     anywhere near either, so the delete predicates below are exact and can be
     run even if this script has never been run on this machine before.
  2. A manifest table `_scorecard_test_data` records every batch, so --status
     can report what is currently injected without inspecting each table.

`--delete` uses the predicates, not the manifest, so losing the manifest does
not strand data. The manifest is then cleared to match.

⚠ REFUSES TO TOUCH PlexProd. Not a flag, not an override — the whole point of
a test-data tool is that it can only ever run against test.

DELETE-vs-streaming note: rows go in with INSERT DML rather than the streaming
API precisely so they can be deleted again immediately. Streamed rows sit in a
buffer that DML cannot touch for up to 90 minutes.
"""

import argparse
import datetime as dt
import sys

from google.cloud import bigquery

PROJECT = "voxdatalake"
TEST_DATASET = "PlexTest"
MANIFEST = "_scorecard_test_data"

# Synthetic key space. Nothing in Plex comes near these.
KEY_BASE = 990000000
TAG = "ZZTEST"


# ── helpers ────────────────────────────────────────────────────────────────

def nanos(d: dt.date) -> int:
    """Plex date columns land as INT64 NANOSECONDS since the epoch — the repo's
    date-conversion pattern divides by 1000 to get micros. Injected dates have
    to match or every view's date branch silently yields NULL."""
    return int(dt.datetime(d.year, d.month, d.day).timestamp()) * 1_000_000_000


def sql_literal(value, bq_type: str) -> str:
    if value is None:
        return "NULL"
    t = bq_type.upper()
    if t in ("INT64", "INTEGER"):
        return str(int(value))
    if t in ("FLOAT64", "FLOAT", "NUMERIC", "BIGNUMERIC"):
        return repr(float(value))
    if t in ("BOOL", "BOOLEAN"):
        return "TRUE" if value else "FALSE"
    if t == "DATE":
        return f"DATE '{value}'"
    if t == "TIMESTAMP":
        return f"TIMESTAMP '{value}'"
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


class Target:
    """One table we write into, with its live schema."""

    def __init__(self, client: bigquery.Client, dataset: str, table: str):
        self.client, self.dataset, self.table = client, dataset, table
        self.fqn = f"`{PROJECT}.{dataset}.{table}`"
        self.types = {}
        try:
            for f in client.get_table(f"{PROJECT}.{dataset}.{table}").schema:
                self.types[f.name] = f.field_type
            self.exists = True
        except Exception:
            self.exists = False

    def insert(self, rows):
        """Rows are dicts of column -> value. Columns the live table does not
        have are dropped with a warning rather than failing the whole batch:
        these raw tables are recreated by the ETL from whatever Plex returns,
        so a column can genuinely come and go."""
        if not rows:
            return 0
        cols = [c for c in rows[0] if c in self.types]
        missing = [c for c in rows[0] if c not in self.types]
        if missing:
            print(f"    note: {self.table} has no column(s) {', '.join(missing)} — skipped")
        if not cols:
            print(f"    SKIP {self.table}: none of the recipe's columns exist")
            return 0
        values = ",\n  ".join(
            "(" + ", ".join(sql_literal(r.get(c), self.types[c]) for c in cols) + ")"
            for r in rows
        )
        sql = f"INSERT INTO {self.fqn} ({', '.join(cols)})\nVALUES\n  {values}"
        self.client.query(sql).result()
        return len(rows)


def scalar(client, sql, default=None):
    rows = list(client.query(sql).result())
    return rows[0][0] if rows else default


def column_list(client, dataset, table):
    try:
        return {f.name for f in client.get_table(f"{PROJECT}.{dataset}.{table}").schema}
    except Exception:
        return set()


# ── recipes ────────────────────────────────────────────────────────────────
#
# Each recipe returns (rows_written, [(table, delete_predicate), ...]).
# A predicate must be exact enough to stand alone: --delete runs it without
# consulting the manifest.

def recipe_production(client, ds, days):
    """Feeds: production_monthly_by_workcenter_group_report, the three daily
    tiles (encap / packaging / labeling), production_vs_goal_report and
    quality_fpy_by_area_month_report — all five read raw_Part_v_Production."""
    t = Target(client, ds, "raw_Part_v_Production")
    if not t.exists:
        print("    SKIP production: raw_Part_v_Production does not exist")
        return 0, []

    # Real work centres, so the group names match what the views group by.
    # ONE per group is enough to light every tile, and keeps the volume sane —
    # the first run wrote 836 rows because this took every work centre in the
    # tenant, which proves nothing extra and just makes the cleanup bigger.
    wcs = list(client.query(f"""
        SELECT ANY_VALUE(Workcenter_Key) AS Workcenter_Key, Workcenter_Group
        FROM `{PROJECT}.{ds}.raw_Part_v_Workcenter`
        WHERE Workcenter_Group IS NOT NULL
        GROUP BY Workcenter_Group
        ORDER BY Workcenter_Group
    """).result())
    if not wcs:
        print("    SKIP production: no work centres with a group")
        return 0, []

    part_key = scalar(client, f"""
        SELECT Part_Key FROM `{PROJECT}.{ds}.raw_Part_v_Part`
        WHERE Part_No IS NOT NULL ORDER BY Part_Key LIMIT 1
    """)

    rows, n, today = [], 0, dt.date.today()
    for day_offset in range(days):
        d = today - dt.timedelta(days=day_offset)
        for wc in wcs:
            # A good run and, every third day, a small scrap run — so scrap
            # rate and FPY are non-zero but not alarming.
            rows.append(dict(
                Production_No=KEY_BASE + n, Serial_No=f"{TAG}-{n}",
                Report_Date=nanos(d), Record_Date=nanos(d),
                Quantity=1000.0 + (n % 7) * 125.0,
                Part_Key=part_key, Workcenter_Key=wc.Workcenter_Key,
                Rejected=0, Note=f"{TAG} synthetic production",
            ))
            n += 1
            if day_offset % 3 == 0:
                rows.append(dict(
                    Production_No=KEY_BASE + n, Serial_No=f"{TAG}-{n}",
                    Report_Date=nanos(d), Record_Date=nanos(d),
                    Quantity=10.0 + (n % 5),
                    Part_Key=part_key, Workcenter_Key=wc.Workcenter_Key,
                    Rejected=-1, Note=f"{TAG} synthetic scrap",
                ))
                n += 1

    written = t.insert(rows)
    return written, [("raw_Part_v_Production", f"Production_No >= {KEY_BASE}")]


def recipe_cycle_count(client, ds, days):
    """Feeds: part_cycle_count_report."""
    t = Target(client, ds, "raw_Part_v_Cycle_Inventory")
    if not t.exists:
        print("    SKIP cycle_count: raw_Part_v_Cycle_Inventory does not exist")
        return 0, []

    rows, today = [], dt.date.today()
    for i in range(days * 4):
        d = today - dt.timedelta(days=i // 4)
        # Roughly one location in six has something unaccounted for, so the
        # per-location hit rate is neither 100% nor obviously fake.
        miss = (i % 6 == 0)
        rows.append(dict(
            Cycle_Inventory_Key=KEY_BASE + i,
            Cycle_Inventory_No=f"{TAG}-CI-{i}",
            Location=KEY_BASE + (i % 9),
            Location_Key=KEY_BASE + (i % 9),
            Cycle_Inventory_Date=nanos(d),
            Cycle_Inventory_By=KEY_BASE,
            Accuracy=0.0 if miss else 100.0,
            Accounted_For=0 if miss else 100,
            Unaccounted_For=5 if miss else 0,
            Moved=0,
            Complete=1,
        ))
    written = t.insert(rows)
    return written, [("raw_Part_v_Cycle_Inventory", f"Cycle_Inventory_Key >= {KEY_BASE}")]


def recipe_shipping(client, ds, days):
    """Feeds: shipping_daily_report, shipping_revenue_report,
    sales_revenue_summary_report, sales_revenue_run_rate_report,
    revenue_vs_goal_report — and shipping_pending_revenue_report, which needs
    shipments that have NOT shipped, so both kinds are written."""
    head = Target(client, ds, "raw_Sales_v_Shipper")
    line = Target(client, ds, "raw_Sales_v_Shipper_Line")
    if not (head.exists and line.exists):
        print("    SKIP shipping: shipper tables do not exist")
        return 0, []

    shipped_key = scalar(client, f"""
        SELECT Shipper_Status_Key FROM `{PROJECT}.{ds}.raw_Sales_v_Shipper_Status`
        WHERE SAFE_CAST(Shipped AS INT64) = 1 LIMIT 1
    """)
    pending_key = scalar(client, f"""
        SELECT Shipper_Status_Key FROM `{PROJECT}.{ds}.raw_Sales_v_Shipper_Status`
        WHERE COALESCE(SAFE_CAST(Shipped AS INT64), 0) != 1
          AND COALESCE(SAFE_CAST(Cancel_Status AS INT64), 0) != 1 LIMIT 1
    """)
    if shipped_key is None:
        print("    SKIP shipping: no shipper status lookup rows")
        return 0, []

    part_key = scalar(client, f"""
        SELECT Part_Key FROM `{PROJECT}.{ds}.raw_Part_v_Part`
        WHERE Part_No IS NOT NULL ORDER BY Part_Key LIMIT 1
    """)
    customer_no = scalar(client, f"""
        SELECT Customer_No FROM `{PROJECT}.{ds}.raw_Sales_v_Shipper`
        WHERE Customer_No IS NOT NULL LIMIT 1
    """) or KEY_BASE

    heads, lines, today = [], [], dt.date.today()
    for i in range(days):
        d = today - dt.timedelta(days=i)
        # One shipped, and every fourth day one still sitting in the dock.
        for kind, status in (("S", shipped_key), ("P", pending_key)):
            if kind == "P" and (i % 4 or pending_key is None):
                continue
            key = KEY_BASE + i * 2 + (0 if kind == "S" else 1)
            heads.append(dict(
                Shipper_Key=key, Shipper_No=f"{TAG}-{kind}{i}",
                Customer_No=customer_no, Ship_Date=nanos(d),
                Shipper_Status_Key=status, Add_Date=nanos(d),
                Note=f"{TAG} synthetic shipment",
            ))
            lines.append(dict(
                Shipper_Line_Key=key, Shipper_Key=key, Part_Key=part_key,
                Quantity=500.0 + (i % 5) * 100.0,
                Primary_Containers=10 + (i % 4),
                Price=1.25, Shipment_Price=1.25,
                Note=f"{TAG} synthetic shipment line",
            ))

    written = head.insert(heads) + line.insert(lines)
    return written, [
        ("raw_Sales_v_Shipper", f"Shipper_Key >= {KEY_BASE}"),
        ("raw_Sales_v_Shipper_Line", f"Shipper_Line_Key >= {KEY_BASE}"),
    ]


def recipe_activity(client, ds, days):
    """Feeds: inventory_activity_report and inventory_avg_daily_usage_report,
    which is depletion divided by days in the month."""
    prod = Target(client, ds, "raw_Part_v_Cell_Production")
    depl = Target(client, ds, "raw_Part_v_Cell_Depletion")
    if not (prod.exists and depl.exists):
        print("    SKIP activity: cell production/depletion tables do not exist")
        return 0, []

    part_key = scalar(client, f"""
        SELECT Part_Key FROM `{PROJECT}.{ds}.raw_Part_v_Part`
        WHERE Part_No IS NOT NULL ORDER BY Part_Key LIMIT 1
    """)

    # These two tables are all-STRING (they were autodetected while empty), so
    # dates go in as text here rather than as nanosecond integers. The view's
    # COALESCE handles both shapes — which is exactly why it has three branches.
    pr, dp, today = [], [], dt.date.today()
    for i in range(days):
        d = (today - dt.timedelta(days=i)).isoformat()
        pr.append(dict(
            Cell_Production_Key=str(KEY_BASE + i), Part_Key=str(part_key),
            Quantity=str(800 + i * 10), Serial_No=f"{TAG}-CP-{i}",
            Production_No=str(KEY_BASE + i), Production_Date=d,
        ))
        dp.append(dict(
            Cell_Depletion_Key=str(KEY_BASE + i), Cell_Production_Key=str(KEY_BASE + i),
            Part_Key=str(part_key), Quantity=str(300 + i * 5),
            Serial_No=f"{TAG}-CD-{i}", Production_No=str(KEY_BASE + i),
            Production_Date=d, Is_Source="1",
        ))

    written = prod.insert(pr) + depl.insert(dp)
    return written, [
        ("raw_Part_v_Cell_Production", f"Cell_Production_Key LIKE '99%'"),
        ("raw_Part_v_Cell_Depletion", f"Cell_Depletion_Key LIKE '99%'"),
    ]


def recipe_safety(client, ds, days):
    """Feeds: the Safe Days tile. This one is NOT a Plex table — it is the
    manual-data app's own table, which does not exist until somebody saves an
    incident. Created here if missing, with the app's column names."""
    table = f"{PROJECT}.{ds}.safety_incidents"
    client.query(f"""
        CREATE TABLE IF NOT EXISTS `{table}` (
          incident_date DATE, area STRING, incident_type STRING,
          recordable BOOL, days_lost INT64, description STRING,
          updated_by STRING, updated_at TIMESTAMP, is_deleted BOOL
        )
    """).result()

    t = Target(client, ds, "safety_incidents")
    today = dt.date.today()
    rows = [dict(
        incident_date=(today - dt.timedelta(days=21)).isoformat(),
        area="Bottling", incident_type="Near miss", recordable=False,
        days_lost=0, description=f"{TAG} synthetic incident — not a real event",
        updated_by=f"{TAG}-injector", updated_at=dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"),
        is_deleted=False,
    )]
    written = t.insert(rows)
    return written, [("safety_incidents", f"updated_by = '{TAG}-injector'")]


RECIPES = {
    "production": recipe_production,
    "cycle_count": recipe_cycle_count,
    "shipping": recipe_shipping,
    "activity": recipe_activity,
    "safety": recipe_safety,
}

# Known but deliberately not covered, so the gap is a decision rather than an
# oversight: inventory valuation needs Part_v_Snapshot plus two cost-breakdown
# tables including a history table, and a fabricated cost is the one number on
# this scorecard that would be actively misleading. Quality needs nothing —
# it already holds 22 real records entered by Quality themselves.
NOT_COVERED = {
    "inventory_valuation_total_report":
        "needs three joined cost tables; a fabricated cost would mislead rather than prove anything",
    "quality_*":
        "already has 22 real nonconformance records from Quality — nothing to prove",
}


# ── manifest ───────────────────────────────────────────────────────────────

def ensure_manifest(client, ds):
    client.query(f"""
        CREATE TABLE IF NOT EXISTS `{PROJECT}.{ds}.{MANIFEST}` (
          batch_id STRING, recipe STRING, table_name STRING,
          delete_predicate STRING, rows_written INT64, injected_at TIMESTAMP
        )
    """).result()


def record(client, ds, batch, recipe, targets, rows):
    if not targets:
        return
    # Predicates contain single quotes (LIKE '99%'), so they have to be escaped
    # like any other literal — building this INSERT by f-string broke on
    # exactly that the first time it ran.
    values = ",\n  ".join(
        "(" + ", ".join([
            sql_literal(batch, "STRING"),
            sql_literal(recipe, "STRING"),
            sql_literal(tbl, "STRING"),
            sql_literal(pred, "STRING"),
            str(int(rows)),
            "CURRENT_TIMESTAMP()",
        ]) + ")"
        for tbl, pred in targets
    )
    client.query(f"""
        INSERT INTO `{PROJECT}.{ds}.{MANIFEST}`
          (batch_id, recipe, table_name, delete_predicate, rows_written, injected_at)
        VALUES
          {values}
    """).result()


# ── commands ───────────────────────────────────────────────────────────────

def cmd_inject(client, ds, recipes, days):
    ensure_manifest(client, ds)
    batch = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    total = 0
    print(f"Injecting into {PROJECT}.{ds}  (batch {batch}, {days} days)\n")
    for name in recipes:
        print(f"  {name}")
        written, targets = RECIPES[name](client, ds, days)
        record(client, ds, batch, name, targets, written)
        total += written
        print(f"    {written} rows")
    print(f"\n{total} rows injected. Remove them with --delete.")
    print("The test tenant is wiped nightly, so this is gone by morning anyway.")


def cmd_delete(client, ds):
    print(f"Deleting marked test rows from {PROJECT}.{ds}\n")
    # Predicates first, from the recipes themselves — so this works even if the
    # manifest was lost, or the rows were injected from another machine.
    targets = []
    for name, fn in RECIPES.items():
        targets += [
            ("raw_Part_v_Production", f"Production_No >= {KEY_BASE}"),
            ("raw_Part_v_Cycle_Inventory", f"Cycle_Inventory_Key >= {KEY_BASE}"),
            ("raw_Sales_v_Shipper", f"Shipper_Key >= {KEY_BASE}"),
            ("raw_Sales_v_Shipper_Line", f"Shipper_Line_Key >= {KEY_BASE}"),
            ("raw_Part_v_Cell_Production", "Cell_Production_Key LIKE '99%'"),
            ("raw_Part_v_Cell_Depletion", "Cell_Depletion_Key LIKE '99%'"),
            ("safety_incidents", f"updated_by = '{TAG}-injector'"),
        ]
        break  # the list above is the complete set; the loop is just for clarity

    total = 0
    for tbl, pred in targets:
        try:
            job = client.query(f"DELETE FROM `{PROJECT}.{ds}.{tbl}` WHERE {pred}")
            job.result()
            n = job.num_dml_affected_rows or 0
            total += n
            print(f"  {tbl:35s} {n} rows")
        except Exception as e:
            msg = str(e).split("\n")[0]
            print(f"  {tbl:35s} skipped ({msg[:70]})")

    try:
        client.query(f"DELETE FROM `{PROJECT}.{ds}.{MANIFEST}` WHERE TRUE").result()
    except Exception:
        pass
    print(f"\n{total} rows deleted.")


def cmd_status(client, ds):
    print(f"Test data currently in {PROJECT}.{ds}\n")
    checks = [
        ("raw_Part_v_Production", f"Production_No >= {KEY_BASE}"),
        ("raw_Part_v_Cycle_Inventory", f"Cycle_Inventory_Key >= {KEY_BASE}"),
        ("raw_Sales_v_Shipper", f"Shipper_Key >= {KEY_BASE}"),
        ("raw_Sales_v_Shipper_Line", f"Shipper_Line_Key >= {KEY_BASE}"),
        ("raw_Part_v_Cell_Production", "Cell_Production_Key LIKE '99%'"),
        ("raw_Part_v_Cell_Depletion", "Cell_Depletion_Key LIKE '99%'"),
        ("safety_incidents", f"updated_by = '{TAG}-injector'"),
    ]
    any_found = False
    for tbl, pred in checks:
        try:
            n = scalar(client, f"SELECT COUNT(*) FROM `{PROJECT}.{ds}.{tbl}` WHERE {pred}", 0)
            if n:
                any_found = True
            print(f"  {tbl:35s} {n}")
        except Exception:
            print(f"  {tbl:35s} (table not present)")
    if not any_found:
        print("\nNothing injected. The nightly tenant wipe also clears it.")
    print("\nNot covered on purpose:")
    for k, v in NOT_COVERED.items():
        print(f"  {k:35s} {v}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--inject", action="store_true")
    g.add_argument("--delete", action="store_true")
    g.add_argument("--status", action="store_true")
    ap.add_argument("--dataset", default=TEST_DATASET)
    ap.add_argument("--recipes", default=",".join(RECIPES),
                    help="comma-separated: " + ", ".join(RECIPES))
    ap.add_argument("--days", type=int, default=14,
                    help="how many days back to generate (default 14)")
    args = ap.parse_args()

    if args.dataset != TEST_DATASET:
        sys.exit(f"Refusing to run against {args.dataset}. This tool only ever "
                 f"touches {TEST_DATASET} — that is the whole point of it.")

    names = [r.strip() for r in args.recipes.split(",") if r.strip()]
    unknown = [n for n in names if n not in RECIPES]
    if unknown:
        sys.exit(f"Unknown recipe(s): {', '.join(unknown)}. "
                 f"Known: {', '.join(RECIPES)}")

    client = bigquery.Client(project=PROJECT)
    if args.inject:
        cmd_inject(client, args.dataset, names, args.days)
    elif args.delete:
        cmd_delete(client, args.dataset)
    else:
        cmd_status(client, args.dataset)


if __name__ == "__main__":
    main()
