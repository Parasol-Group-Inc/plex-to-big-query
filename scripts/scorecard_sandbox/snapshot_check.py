"""
Which moment of PlexTest is internally consistent enough to build on?

PlexTest's raw tables are written by thirteen pipelines at different times,
and the tenant's master data changes between days (and the ETL keeps
yesterday's rows when Plex returns none), so "the current PlexTest" can join
nothing to nothing. BigQuery time travel lets us read every table as of one
instant; this scores each candidate instant by the foreign keys the scorecard
views actually join on.

    python scripts/scorecard_sandbox/snapshot_check.py "2026-09-23 03:00:00+00" ...
"""

import sys

from common import PROJECT, SOURCE, Sandbox

# (child table, child column, parent table, parent column) — the joins the
# tile views depend on most.
RELATIONS = [
    ("raw_Part_v_Customer_Part_Price", "Customer_Part_Key", "raw_Part_v_Customer_Part", "Customer_Part_Key"),
    ("raw_Part_v_Customer_Part", "Part_Key", "raw_Part_v_Part", "Part_Key"),
    ("raw_Part_v_Customer_Part", "Customer_No", "raw_Common_v_Customer", "Customer_No"),
    ("raw_Sales_v_PO_Line", "Part_Key", "raw_Part_v_Part", "Part_Key"),
    ("raw_Sales_v_PO_Line", "Customer_Part_Key", "raw_Part_v_Customer_Part", "Customer_Part_Key"),
    ("raw_Part_v_Container", "Part_Key", "raw_Part_v_Part", "Part_Key"),
    ("raw_Part_v_Job", "Part_Key", "raw_Part_v_Part", "Part_Key"),
    ("raw_Part_v_Job_Op", "Workcenter_Key", "raw_Part_v_Workcenter", "Workcenter_Key"),
    ("raw_Quality_v_Problem_2", "Part_Key", "raw_Part_v_Part", "Part_Key"),
    ("raw_Part_v_Flat_BOM", "Part_Key", "raw_Part_v_Part", "Part_Key"),
    ("raw_Common_v_Customer", "Assigned_To", "raw_Plexus_Control_v_Plexus_User", "Plexus_User_No"),
]


def score(sb, ts):
    at = f"FOR SYSTEM_TIME AS OF TIMESTAMP '{ts}'" if ts else ""
    print(f"\n== {ts or 'now'}")
    for child, cc, parent, pc in RELATIONS:
        try:
            # Two queries: BigQuery refuses one query that reads the same table
            # at two instants, and child/parent can be the same table.
            keys = {r["k"] for r in sb.query(
                f"SELECT DISTINCT SAFE_CAST({pc} AS INT64) k FROM `{PROJECT}.{SOURCE}.{parent}` {at}")}
            rows = sb.query(
                f"SELECT SAFE_CAST({cc} AS INT64) k FROM `{PROJECT}.{SOURCE}.{child}` {at} "
                f"WHERE {cc} IS NOT NULL AND SAFE_CAST({cc} AS INT64) != 0")
            hit = sum(1 for r in rows if r["k"] in keys)
            print(f"  {child}.{cc} -> {parent}: {hit}/{len(rows)}")
        except Exception as e:
            print(f"  {child}.{cc} -> {parent}: ERROR {str(e).splitlines()[0][:80]}")


if __name__ == "__main__":
    sb = Sandbox()
    for ts in sys.argv[1:] or [None]:
        score(sb, None if ts == "now" else ts)
