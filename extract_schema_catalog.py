"""Extract column-level schema for every view already catalogued in catalog/*.md.

Plex's SQL Dev tree already gave us view *names* for 13 databases (see
catalog/plex_catalog_index.md). This script queries each one live via ODBC
for its column list only (SELECT TOP 0 -- zero rows, schema metadata only,
no row data pulled) and writes one row per (view, column) to a CSV.

Run inside the ETL container (has the Plex ODBC driver installed):
    docker compose run --rm etl python extract_schema_catalog.py
Output lands in ./output/full_schema_catalog.csv (bind-mounted from the container).
"""
import csv
import os
import re
import sys

import main as etl

CATALOG_DIR = "catalog"

# catalog file -> ODBC database prefix (see catalog/plex_catalog_index.md)
DB_PREFIX = {
    "plex_sales_views_catalog.md": "Sales",
    "plex_common_views_catalog.md": "Common",
    "plex_part_views_catalog.md": "Part",
    "plex_accounting_views_catalog.md": "Accounting",
    "plex_purchasing_views_catalog.md": "Purchasing",
    "plex_plexus_control_views_catalog.md": "Plexus_Control",
    "plex_warehouse_views_catalog.md": "Warehouse",
    "plex_quality_views_catalog.md": "Quality",
    "plex_personnel_views_catalog.md": "Personnel",
    "plex_distribution_views_catalog.md": "Distribution",
    "plex_accelerated_views_catalog.md": "Accelerated",
    "plex_material_views_catalog.md": "Material",
    "plex_maintenance_views_catalog.md": "Maintenance",
}

NAME_RE = re.compile(r"`([A-Za-z0-9_]+)`")


def collect_view_names():
    """Parse catalog/*.md for backtick-delimited view short names, return full ODBC query names."""
    seen = set()
    out = []
    for fname, prefix in DB_PREFIX.items():
        path = os.path.join(CATALOG_DIR, fname)
        if not os.path.exists(path):
            etl.log.warning(f"Catalog file not found, skipping: {path}")
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for name in NAME_RE.findall(text):
            full = f"{prefix}_v_{name}"
            if full not in seen:
                seen.add(full)
                out.append(full)
    return out


def describe_type(type_code):
    return type_code.__name__ if hasattr(type_code, "__name__") else str(type_code)


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(etl.OUTPUT_DIR, "full_schema_catalog.csv")
    views = collect_view_names()
    etl.log.info(f"Collected {len(views)} candidate view names from catalog/*.md")

    user = os.environ["PLEX_ODBC_USER"]
    token = os.environ["PLEX_ACCESS_TOKEN"]
    conn = etl.get_odbc_connection(user=user, password="", company_code="", access_token=token)

    ok = 0
    errored = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["view_name", "column_name", "ordinal_position", "data_type"])
        for i, view in enumerate(views, 1):
            try:
                cur = conn.cursor()
                cur.execute(f"SELECT TOP 0 * FROM {view}")
                for pos, col in enumerate(cur.description, 1):
                    writer.writerow([view, col[0], pos, describe_type(col[1])])
                ok += 1
            except Exception as e:
                errored += 1
                writer.writerow([view, f"__ERROR__: {e}", "", ""])
            f.flush()
            if i % 100 == 0:
                etl.log.info(f"{i}/{len(views)} views processed ({ok} ok, {errored} errored)")

    etl.log.info(f"Done. {ok} views succeeded, {errored} errored. Wrote {out_path}")


if __name__ == "__main__":
    main()
