#!/usr/bin/env python3
"""Pick each extraction's probe columns from the schema catalog, and write them
into the report YAMLs as `probe: [...]` lines.

The change probe (main.py, `probe_mode: auto`) runs one aggregate per extraction:

    SELECT COUNT(*), MAX(<col>), ... FROM <view> <filter>

COUNT(*) catches rows added or removed. The MAX columns are what make an EDIT
visible, so they are chosen per view from catalog/full_schema_catalog.csv:

  1. a change date, first match in CHANGE_DATE_COLUMNS (Update_Date, ...), and
  2. the view's own key, `<Entity>_Key` where the view is `<Module>_v_<Entity>`
     (Sales_v_PO_Line -> PO_Line_Key), so a new row shows even where the count
     happens to stay level (one added, one removed).

A view with neither still gets COUNT(*) only, and is listed in the report this
script prints; the daily 4 AM full run is the backstop for those.

    python scripts/generate_probe_columns.py            # dry run: print the plan
    python scripts/generate_probe_columns.py --write    # edit reports/*.yaml and reports/test/*.yaml

Idempotent: an extraction that already has a `probe:` line is left alone, so a
hand correction survives a re-run. Edits are line-based, never a YAML
round-trip, so every comment in the files is kept, and files are read and
written as UTF-8 with their line endings untouched (on Windows the default
codec would corrupt the YAML's em dashes and emoji, and GCS would then refuse
to decode the config). label_design (explicit, hourly probe) is skipped.
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "full_schema_catalog.csv"
SKIP_REPORTS = {"label_design"}

CHANGE_DATE_COLUMNS = [
    "Update_Date", "Updated_Date", "Last_Update_Date", "Last_Updated_Date",
    "Last_Modified_Date", "Modified_Date", "Change_Date", "Record_Date",
    "Add_Date", "Created_Date", "Production_Date", "Snapshot_Date",
]


def load_catalog():
    cols = defaultdict(list)
    with CATALOG.open(newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) >= 2:
                cols[row[0]].append(row[1])
    return cols


def choose(view, catalog):
    have = catalog.get(view, [])
    picked = []
    for c in CHANGE_DATE_COLUMNS:
        if c in have:
            picked.append(c)
            break
    entity = view.split("_v_", 1)[1] if "_v_" in view else ""
    key = f"{entity}_Key"
    if entity and key in have:
        picked.append(key)
    return picked, bool(have)


EXTRACTION_RE = re.compile(r"^(\s*)- plex_view:\s*([A-Za-z0-9_]+)\s*(#.*)?$")
LIST_ITEM_RE  = re.compile(r"^\s*-\s+\S")
SECTION_RE    = re.compile(r"^extractions:\s*(#.*)?$")


def plan_file(path, catalog):
    """Return (new_lines, rows) where rows describe each extraction."""
    with path.open(encoding="utf-8", newline="") as f:
        lines = f.read().splitlines(keepends=True)
    out, rows, warnings = [], [], []
    i = 0
    in_extractions = False
    has_top_probe = any(re.match(r"^probe_mode:", l) for l in lines)
    if not any(SECTION_RE.match(l) for l in lines):
        return lines, rows, [f"no top-level 'extractions:' line found — file left alone"]
    while i < len(lines):
        line = lines[i]
        if SECTION_RE.match(line):
            in_extractions = True
        elif re.match(r"^\S", line) and not line.startswith("#"):
            in_extractions = False
        m = EXTRACTION_RE.match(line) if in_extractions else None
        if not m:
            if in_extractions and LIST_ITEM_RE.match(line):
                warnings.append(f"extraction not handled (plex_view must be its first key): {line.strip()}")
            out.append(line)
            i += 1
            continue
        indent, view = m.group(1), m.group(2)
        block = [line]
        j = i + 1
        while j < len(lines) and lines[j].startswith(indent + "  ") and not EXTRACTION_RE.match(lines[j]):
            block.append(lines[j])
            j += 1
        already = any(re.match(rf"^{indent}  probe:", b) for b in block)
        cols, known = choose(view, catalog)
        rows.append((view, cols, known, already))
        if not already and cols:
            # Insert after the last key line of the block (before trailing blanks).
            k = len(block)
            while k > 1 and not block[k - 1].strip():
                k -= 1
                eol = "\r\n" if block[0].endswith("\r\n") else "\n"
            block.insert(k, f"{indent}  probe: [{', '.join(cols)}]{eol}")
        out.extend(block)
        i = j
    if not has_top_probe:
        # `probe_mode: auto` goes right above `extractions:` so it reads as a
        # property of the whole extraction list. (Not `probe: auto` — see
        # probe_kind() in main.py for why the older image needs a new key.)
        idx = next(n for n, l in enumerate(out) if SECTION_RE.match(l))
        eol = "\r\n" if out[idx].endswith("\r\n") else "\n"
        out.insert(idx, f"# Change probe — see main.py and docs/PROBE_BUILD_PLAN.md. Columns per{eol}"
                        f"# extraction were picked by scripts/generate_probe_columns.py.{eol}"
                        f"probe_mode: auto{eol}{eol}")
    return out, rows, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="edit the YAML files in place")
    args = ap.parse_args()
    catalog = load_catalog()
    files = sorted((ROOT / "reports").glob("*.yaml")) + sorted((ROOT / "reports" / "test").glob("*.yaml"))
    count_only, unknown, warned = [], [], []
    for path in files:
        text = path.read_text(encoding="utf-8")
        name = re.search(r"^report_name:\s*(\S+)", text, re.M)
        report = (name.group(1) if name else path.stem).removesuffix("_test")
        if report in SKIP_REPORTS:
            continue
        new_lines, rows, warnings = plan_file(path, catalog)
        rel = path.relative_to(ROOT)
        print(f"\n{rel}")
        for w in warnings:
            print(f"  WARNING: {w}")
            warned.append(f"{rel}: {w}")
        for view, cols, known, already in rows:
            tag = "kept (already set)" if already else (", ".join(cols) if cols else "COUNT(*) only")
            if not known:
                tag += "  [view not in catalog]"
                unknown.append(f"{rel}: {view}")
            elif not cols and not already:
                count_only.append(f"{rel}: {view}")
            print(f"  {view:<50} {tag}")
        if args.write:
            with path.open("w", encoding="utf-8", newline="") as f:
                f.write("".join(new_lines))
    print(f"\n{len(count_only)} extraction(s) probe by COUNT(*) only; {len(unknown)} view(s) missing "
          f"from the catalog; {len(warned)} warning(s). Counts cover every file listed (prod + test).")
    if not args.write:
        print("Dry run. Re-run with --write to edit the files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
