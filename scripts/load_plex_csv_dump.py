#!/usr/bin/env python3
"""Load Plex SQL Developer CSV exports into PlexProd raw_* tables, when ODBC is down.

    python scripts/load_plex_csv_dump.py manual-dumps/nov-5 20261105           # stage + compare only
    python scripts/load_plex_csv_dump.py manual-dumps/nov-5 20261105 --swap    # then replace raw_*

Each file must be `<Plex view>.csv` from `SELECT * FROM <Plex view>` in Plex SQL
Developer (headers on). Every extraction in sales_orders, part_on_hand_inventory and
part_routing is unfiltered, so SELECT * gives exactly what the ETL would have loaded.

What it does, per file:
  1. Converts each CSV value to the type the existing raw_<view> table uses:
     "NULL" -> NULL, True/False -> 1/0, and dates to the ETL's integer nanoseconds.
     Plex SQL Developer prints dates in Plex local wall time; the ETL stores that
     wall time plus its UTC offset (-6 h MDT, -7 h MST), measured on 2026-11-05 on
     14,834 dates (the CSV also drops milliseconds, so dates differ by under 1 s).
  2. Loads it into Backups.stage_raw_<view>_<tag> with the raw table's exact schema.
  3. Prints, for rows whose key exists in both, how many are identical and which
     columns differ. Expect differences only in rows Plex changed since the last run.
  4. With --swap: copies the staged table over PlexProd.raw_<view>. Back the raw
     tables up first (bq cp ... Backups.PlexProd__raw_<view>_<tag>).

Writes need the operator account. Run with
CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT=claude-operator@voxdatalake.iam.gserviceaccount.com
(or your own login). The next successful ETL run overwrites the raw tables again.
"""
import argparse
import collections
import csv
import datetime as dt
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from google.cloud import bigquery

PROJECT = "voxdatalake"
DEN = ZoneInfo("America/Denver")
EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)

# Key used to match staged rows with the current table (one row per key, except
# Sales_v_Shipper_AR_Invoice, where Plex itself has a line invoiced twice).
KEYS = {
    "Sales_v_PO": "PO_Key", "Sales_v_PO_Line": "PO_Line_Key", "Sales_v_Release": "Release_Key",
    "Sales_v_Price": "Price_Key", "Sales_v_PO_Change": "Change_Key",
    "Sales_v_Order_Salesperson": "PO_Key", "Sales_v_Shipper": "Shipper_Key",
    "Sales_v_Shipper_Line": "Shipper_Line_Key", "Sales_v_Shipper_Line_Release": "Shipper_Line_Key",
    "Sales_v_Shipper_AR_Invoice": "Shipper_Line_Key", "Accounting_v_AR_Invoice": "Invoice_Link",
    "Part_v_Part": "Part_Key", "Part_v_Container": "Serial_No",
    "Sales_v_Shipper_Container": "Shipper_Container_Key",
    "Accounting_v_AR_Invoice_Dist": ("Invoice_Link", "Line_Item_No"),
}


def is_date(s):
    return "/" in s and ":" in s and s[-2:] in ("AM", "PM")


def convert(s, typ):
    if s == "NULL":
        return None
    if typ == "STRING":
        return s
    if s == "":
        return None
    if s in ("True", "False"):
        return (1 if s == "True" else 0) if typ == "INTEGER" else (1.0 if s == "True" else 0.0)
    if is_date(s):
        naive = dt.datetime.strptime(s, "%m/%d/%Y %I:%M:%S %p")
        stored = naive.replace(tzinfo=dt.timezone.utc) + naive.replace(tzinfo=DEN).utcoffset()
        if typ == "DATETIME":  # e.g. Shipper_Container.Loaded_Date: same shift, kept as naive time
            return stored.replace(tzinfo=None).isoformat()
        ns = int((stored - EPOCH).total_seconds()) * 1_000_000_000
        return ns if typ == "INTEGER" else float(ns)
    if typ == "INTEGER":
        d = Decimal(s)
        if d != d.to_integral_value():
            raise ValueError(f"non-integer {s!r}")
        return int(d)
    return float(s)


def same(a, b, typ):
    if a == b:
        return True
    if a is None or b is None:
        return False
    if typ == "FLOAT":
        return abs(a - b) < 1e-6
    if typ == "DATETIME":  # the CSV drops milliseconds
        return abs((dt.datetime.fromisoformat(a) - b).total_seconds()) < 1
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("tag", help="date tag for staging tables, e.g. 20261105")
    ap.add_argument("--swap", action="store_true", help="replace PlexProd.raw_<view> with the staged table")
    args = ap.parse_args()
    c = bigquery.Client(project=PROJECT)
    for f in sorted(Path(args.folder).glob("*.csv")):
        view = f.stem
        raw = f"{PROJECT}.PlexProd.raw_{view}"
        table = c.get_table(raw)
        schema = {x.name: x.field_type for x in table.schema}
        with open(f, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
        header = rows[0][:-1] if rows[0] and rows[0][-1] == "" else rows[0]
        missing = [x for x in schema if x not in header]
        if missing:
            print(f"{view}: SKIPPED, columns missing from the CSV: {missing}")
            continue
        out, errors = [], collections.Counter()
        for r in rows[1:]:
            d = dict(zip(header, r))
            o = {}
            for col, typ in schema.items():
                try:
                    o[col] = convert(d[col], typ)
                except ValueError:
                    errors[col] += 1
                    o[col] = None
            out.append(o)
        if errors:
            print(f"{view}: SKIPPED, conversion errors {dict(errors)}")
            continue
        stage = f"{PROJECT}.Backups.stage_raw_{view}_{args.tag}"
        c.load_table_from_json(out, stage, job_config=bigquery.LoadJobConfig(
            schema=table.schema, write_disposition="WRITE_TRUNCATE")).result()
        key = KEYS.get(view)
        cols_of_key = key if isinstance(key, tuple) else (key,)
        kf = lambda r: "|".join(str(r[k]) for k in cols_of_key)
        diff, identical, changed = collections.Counter(), 0, 0
        if key:
            old = {kf(r): dict(r.items()) for r in c.query(f"SELECT * FROM `{raw}`").result()}
            for o in out:
                b = old.get(kf(o))
                if not b:
                    continue
                cols = [col for col, typ in schema.items() if not same(o[col], b[col], typ)]
                changed += bool(cols)
                identical += not cols
                diff.update(cols)
        print(f"{view}: csv {len(out)} rows, current {table.num_rows}; matched rows identical {identical}, "
              f"changed {changed}; columns differing {diff.most_common(6)}")
        if args.swap:
            c.copy_table(stage, raw, job_config=bigquery.CopyJobConfig(write_disposition="WRITE_TRUNCATE")).result()
            print(f"{view}: raw_{view} replaced")


if __name__ == "__main__":
    main()
