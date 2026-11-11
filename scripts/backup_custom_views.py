#!/usr/bin/env python3
"""Back up and document a BigQuery dataset that people build by hand (not by the ETL).

    python scripts/backup_custom_views.py VoxScorecardsLive          # writes custom_views/VoxScorecardsLive/

Read-only against BigQuery. For every object in the dataset it writes:
  - a VIEW: its SQL, exactly as BigQuery stores it (<name>.sql);
  - a TABLE made by CREATE TABLE AS / CREATE TABLE: the newest such statement found in the
    last 180 days of job history (<name>.sql), or, when none is found (loaded from a file,
    older than 180 days), only its schema (<name>.schema.json);
and a README.md: one row per object (type, rows, last change, who last created it, the
tables it reads, columns), so the dataset can be rebuilt and understood without the console.

Why (2026-11-11, meeting with Jennilyn): VoxScorecardsLive holds her own views over PlexProd
and older NetSuite data; none were in git. Re-run after she adds or changes views; the git
diff shows what changed. The data in TABLE objects is copied separately to the Backups dataset
(see custom_views/README.md).
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

from google.cloud import bigquery

PROJECT = "voxdatalake"
ROOT = Path(__file__).resolve().parents[1] / "custom_views"
REF = re.compile(r"`?([a-z0-9-]+)\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)`?")


def main(ds):
    c = bigquery.Client(project=PROJECT)
    out = ROOT / ds
    out.mkdir(parents=True, exist_ok=True)
    objs = [dict(r) for r in c.query(f"""
        SELECT t.table_name, t.table_type, t.creation_time, v.view_definition
        FROM `{PROJECT}.{ds}.INFORMATION_SCHEMA.TABLES` t
        LEFT JOIN `{PROJECT}.{ds}.INFORMATION_SCHEMA.VIEWS` v USING (table_name)
        ORDER BY table_name""").result()]
    cols = {}
    for r in c.query(f"""SELECT table_name, column_name, data_type FROM `{PROJECT}.{ds}.INFORMATION_SCHEMA.COLUMNS`
                         ORDER BY table_name, ordinal_position""").result():
        cols.setdefault(r.table_name, []).append((r.column_name, r.data_type))
    meta = {r.table_id: r for r in c.query(f"""
        SELECT table_id, row_count, TIMESTAMP_MILLIS(last_modified_time) m FROM `{PROJECT}.{ds}.__TABLES__`""").result()}
    hist = {r.tb: r for r in c.query(f"""
        SELECT destination_table.table_id tb, query, creation_time, user_email
        FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
        WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
          AND destination_table.dataset_id = '{ds}'
          AND statement_type IN ('CREATE_TABLE_AS_SELECT', 'CREATE_VIEW', 'CREATE_TABLE')
        QUALIFY ROW_NUMBER() OVER (PARTITION BY destination_table.table_id ORDER BY creation_time DESC) = 1""").result()}
    for f in out.glob("*.sql"):
        f.unlink()
    for f in out.glob("*.schema.json"):
        f.unlink()
    rows = []
    for o in objs:
        n, typ = o["table_name"], o["table_type"]
        h, m = hist.get(n), meta.get(n)
        sql = o["view_definition"] if typ == "VIEW" else (h.query if h else None)
        if sql:
            head = (f"-- {ds}.{n} ({typ.lower()}), backed up from BigQuery by scripts/backup_custom_views.py\n"
                    + (f"-- last created {h.creation_time:%Y-%m-%d %H:%M} UTC by {h.user_email}\n" if h else "")
                    + ("-- a TABLE: this is the statement that last built it; its data is a snapshot\n" if typ != "VIEW" else ""))
            (out / f"{n}.sql").write_text(head + "\n" + sql.strip() + "\n", encoding="utf-8")
        else:
            (out / f"{n}.schema.json").write_text(json.dumps(
                [{"name": a, "type": b} for a, b in cols.get(n, [])], indent=1) + "\n", encoding="utf-8")
        refs = sorted({".".join(x[1:]) if x[0] == PROJECT else ".".join(x) for x in REF.findall(sql or "")}
                      - {f"{ds}.{n}"})
        rows.append({"name": n, "type": "view" if typ == "VIEW" else "table", "rows": m.row_count if m else None,
                     "changed": f"{m.m:%Y-%m-%d}" if m else "", "by": (h.user_email.split("@")[0] if h else ""),
                     "sql": "yes" if sql else "schema only", "reads": refs, "columns": [a for a, _ in cols.get(n, [])]})
    kinds = Counter(r["type"] for r in rows)
    lines = [f"# {ds}", "",
             f"Backed up by `scripts/backup_custom_views.py {ds}`: {kinds['view']} views and {kinds['table']} tables.",
             "These are built by hand in the BigQuery console (mostly by Jennilyn), not by the ETL, so the ETL never",
             "recreates or reverts them. A view's `.sql` is exactly what BigQuery stores. A table's `.sql` is the",
             "statement that last built it (its rows are a snapshot from then); `.schema.json` means no statement",
             "was found in 180 days of job history, so only the columns are kept.", "",
             "| Object | Type | Rows | Last changed | Last built by | SQL | Reads |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        reads = ", ".join(f"`{x}`" for x in r["reads"][:6]) + (" ..." if len(r["reads"]) > 6 else "")
        lines.append(f"| `{r['name']}` | {r['type']} | {'' if r['rows'] is None or r['type'] == 'view' else r['rows']} | "
                     f"{r['changed']} | {r['by']} | {r['sql']} | {reads} |")
    lines += ["", "## Columns", ""]
    for r in rows:
        lines.append(f"- **`{r['name']}`**: " + ", ".join(f"`{x}`" for x in r["columns"]))
    (out / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{ds}: {kinds['view']} views, {kinds['table']} tables -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "VoxScorecardsLive")
