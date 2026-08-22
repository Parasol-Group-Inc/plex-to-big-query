"""Build the NetSuite saved-searches catalog (JSON + Markdown) from the raw export.

Reads mapping/SavedSearches555.csv (semicolon-delimited, cp1252-encoded --
confirmed via byte-level inspection, not a guess) and writes:
    mapping/netsuite-saved-searches.json  -- one object per saved search
    mapping/netsuite-saved-searches.md    -- grouped by Type, with a summary
                                              table and a table of contents

Run locally (no ODBC/container needed, pure CSV -> JSON/MD):
    python mapping/build_netsuite_saved_searches_catalog.py
"""
import csv
import json
import os
from collections import defaultdict, Counter

MAPPING_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_CSV = os.path.join(MAPPING_DIR, "SavedSearches555.csv")
OUT_JSON = os.path.join(MAPPING_DIR, "netsuite-saved-searches.json")
OUT_MD = os.path.join(MAPPING_DIR, "netsuite-saved-searches.md")

FIELDS = [
    "Title", "From Bundle", "ID", "Type", "Owner", "Access",
    "Export Results", "Persist Results", "Scheduled", "Last Run By", "Last Run On",
]
JSON_KEYS = [
    "Title", "FromBundle", "ID", "Type", "Owner", "Access",
    "ExportResults", "PersistResults", "Scheduled", "LastRunBy", "LastRunOn",
]


def load_rows():
    with open(SRC_CSV, encoding="cp1252", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        rows = list(reader)
    header, data = rows[0], rows[1:]
    assert [h.strip() for h in header] == FIELDS, f"unexpected header: {header}"
    records = []
    for r in data:
        rec = {k: v.strip() for k, v in zip(JSON_KEYS, r)}
        records.append(rec)
    return records


def write_json(records):
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
        f.write("\n")


def slugify(text):
    return "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")


def write_md(records):
    by_type = defaultdict(list)
    for rec in records:
        by_type[rec["Type"] or "(blank)"].append(rec)

    total = len(records)
    scheduled = sum(1 for r in records if r["Scheduled"] == "Yes")
    owners = Counter(r["Owner"] for r in records if r["Owner"])
    bundled = sum(1 for r in records if r["FromBundle"])

    types_sorted = sorted(by_type.items(), key=lambda kv: -len(kv[1]))

    lines = []
    lines.append("# NetSuite Saved Searches Catalog\n")
    lines.append(
        "Generated from `SavedSearches555.csv` (raw NetSuite saved-search "
        "export, all types -- not just the reports-list business reports; "
        "see [netsuite-report-mapping.md](netsuite-report-mapping.md) for the "
        "curated ~80-report business list this is NOT a replacement for) via "
        "`build_netsuite_saved_searches_catalog.py`.\n"
    )
    lines.append(f"**Total saved searches:** {total}  ")
    lines.append(f"**Distinct types:** {len(by_type)}  ")
    lines.append(f"**Scheduled:** {scheduled}  ")
    lines.append(f"**From a bundle (not native to this account):** {bundled}  ")
    lines.append(f"**Distinct owners:** {len(owners)}\n")

    lines.append("## Table of Contents\n")
    for type_name, recs in types_sorted:
        anchor = slugify(type_name)
        lines.append(f"- [{type_name}](#{anchor}) ({len(recs)})")
    lines.append("")

    lines.append("## Top owners\n")
    lines.append("| Owner | Saved Searches |")
    lines.append("|---|---|")
    for owner, count in owners.most_common(15):
        lines.append(f"| {owner} | {count} |")
    lines.append("")

    lines.append("---\n")

    for type_name, recs in types_sorted:
        lines.append(f"## {type_name}\n")
        lines.append("| Title | ID | Owner | Bundle | Scheduled | Last Run By | Last Run On |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in sorted(recs, key=lambda x: x["Title"].lower()):
            title = r["Title"].replace("|", "\\|").replace("*", "\\*")
            bundle = r["FromBundle"] or "--"
            last_run_by = r["LastRunBy"].replace("|", "\\|") or "--"
            last_run_on = r["LastRunOn"] or "--"
            lines.append(
                f"| {title} | {r['ID']} | {r['Owner']} | {bundle} | "
                f"{r['Scheduled']} | {last_run_by} | {last_run_on} |"
            )
        lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    records = load_rows()
    write_json(records)
    write_md(records)
    print(f"Wrote {len(records)} records to {OUT_JSON} and {OUT_MD}")


if __name__ == "__main__":
    main()
