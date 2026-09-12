#!/usr/bin/env python3
"""
Distill Plex's glossary down to the terms this repo actually uses.
=================================================================

Plex's export is ~67,000 lines / 6.4 MB. Reading it is not the problem;
carrying it around is. Almost all of it describes modules Vox does not use, and
a glossary you cannot hold in your head is the same as no glossary.

So this reads the whole export ONCE, locally, and writes out only the entries
that match vocabulary the repo genuinely references:

  * Plex view names        Sales_v_PO, Part_v_Container, ...
  * raw table names        raw_Sales_v_PO  ->  Sales_v_PO
  * column names           Include_In_MRP, Minimum_Inventory_Quantity, ...
  * business phrases       spelled out in reports and docs

Matching is deliberately loose in one direction only: `Minimum_Inventory_Quantity`
also matches the glossary's "Minimum Inventory Quantity", because Plex writes
its terms as prose and its columns with underscores. It is never loosened to
substring matching - "Part" would drag in several hundred entries and defeat
the point.

    python scripts/distill_glossary.py
    python scripts/distill_glossary.py --min-len 4 --out docs/PLEX_GLOSSARY.md

Output is one markdown file, grouped by how the term reaches us.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = ROOT / "catalog" / "Glossary-2026-09-11T185130.csv"
DEFAULT_OUT = ROOT / "docs" / "PLEX_GLOSSARY.md"

# Where repo vocabulary is harvested from.
# Only the code that actually builds a report. `catalog/` holds full schema
# dumps of every Plex table Vox can see, and scanning those pulled in ~1,000
# fields from modules nobody here touches (Applicant_Status, Advancement_
# Category and friends) - a glossary that big is the thing this script exists
# to avoid.
SCAN = [
    ("reports", ("*.yaml",)),
    ("reports/test", ("*.yaml",)),
    ("reports/sql", ("*.sql",)),
]

# Words that are real English before they are Plex terms. Matching these adds
# noise and no understanding.
STOPWORDS = {
    "name", "date", "type", "status", "note", "notes", "value", "key", "code",
    "count", "total", "amount", "line", "lines", "order", "orders", "part",
    "parts", "price", "cost", "quantity", "unit", "units", "month", "year",
    "day", "days", "time", "user", "group", "report", "reports", "view",
    "views", "table", "tables", "number", "no", "id", "active", "location",
    "description", "reason", "source", "target", "level", "list", "sum",
    "average", "percent", "rate", "job", "jobs", "item", "items", "record",
    "records", "data", "test", "prod", "sales", "quality", "inventory",
}

# Definitions that exist but say nothing.
USELESS_DEFS = {
    "title", "setup table", "description", "name", "date", "note", "notes",
    "field label", "label", "value", "number", "code", "key", "status",
    "the date", "a date", "reason for change", "reason",
}

PLEX_VIEW = re.compile(r"\b([A-Z][A-Za-z]+(?:_[A-Za-z]+)*?_v_[A-Za-z_]+)\b")
IDENTIFIER = re.compile(r"\b([A-Z][a-z]+(?:_[A-Z][a-z]+)+)\b")   # Snake_Case_Words


def norm(s: str) -> str:
    """Compare on letters and digits only, case-folded."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def harvest_vocabulary() -> tuple[set[str], set[str]]:
    """Plex view names, and other Snake_Case identifiers (mostly columns)."""
    views: set[str] = set()
    idents: set[str] = set()

    for rel, patterns in SCAN:
        base = ROOT / rel
        if not base.is_dir():
            continue
        for pattern in patterns:
            for path in base.glob(pattern):
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for m in PLEX_VIEW.finditer(text):
                    views.add(m.group(1).replace("raw_", ""))
                for m in IDENTIFIER.finditer(text):
                    idents.add(m.group(1))

    # A view name is also an identifier; keep the sets disjoint so the output
    # groups cleanly.
    idents -= views
    return views, idents


def load_glossary(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def tidy(text: str, limit: int) -> str:
    """Collapse Plex's multi-line definitions into one readable line."""
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    # Definitions routinely open with a part-of-speech tag on its own line.
    text = re.sub(r"^(Noun|Verb|Adjective|Adverb|Acronym)\b[:.]?\s*", "", text, flags=re.I)
    if len(text) > limit:
        cut = text[:limit].rsplit(" ", 1)[0]
        text = cut + "..."
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--min-len", type=int, default=4,
                    help="ignore glossary terms shorter than this (default 4)")
    ap.add_argument("--max-def", type=int, default=320,
                    help="truncate definitions to this many characters")
    args = ap.parse_args()

    if not args.csv.exists():
        print(f"Glossary not found: {args.csv}", file=sys.stderr)
        return 1

    views, idents = harvest_vocabulary()
    print(f"repo vocabulary: {len(views)} Plex views, {len(idents)} identifiers")

    # One lookup keyed on the normalised form, so Minimum_Inventory_Quantity
    # and "Minimum Inventory Quantity" collide on purpose.
    wanted: dict[str, tuple[str, str]] = {}
    for v in views:
        wanted[norm(v)] = ("view", v)
    for i in idents:
        n = norm(i)
        if n in STOPWORDS or len(n) < args.min_len:
            continue
        wanted.setdefault(n, ("field", i))

    rows = load_glossary(args.csv)
    print(f"glossary rows: {len(rows)}")

    hits: dict[str, dict] = {}
    for row in rows:
        term = (row.get("Plex Term") or "").strip()
        if not term:
            continue
        n = norm(term)
        if n not in wanted:
            continue
        definition = tidy(row.get("Definition") or "", args.max_def)
        # A definition that just restates the field name teaches nothing.
        # Plex has a lot of "Title", "Setup Table", "Description" entries.
        if len(definition) < 12 or norm(definition) in USELESS_DEFS:
            continue
        # Keep the longest definition when Plex lists a term more than once.
        prev = hits.get(n)
        if prev and len(prev["definition"]) >= len(definition):
            continue
        kind, repo_name = wanted[n]
        hits[n] = {
            "term": term,
            "repo_name": repo_name,
            "kind": kind,
            "definition": definition,
            "customer_term": (row.get("Customer Term") or "").strip(),
            "term_type": (row.get("Term Type") or "").strip(),
        }

    grouped: dict[str, list[dict]] = defaultdict(list)
    for h in hits.values():
        grouped[h["kind"]].append(h)
    for v in grouped.values():
        v.sort(key=lambda x: x["repo_name"].lower())

    matched_views = len(grouped.get("view", []))
    matched_fields = len(grouped.get("field", []))

    lines: list[str] = []
    lines.append("# Plex glossary — the part of it we use")
    lines.append("")
    lines.append("Generated by `scripts/distill_glossary.py`. **Do not hand-edit** — re-run it.")
    lines.append("")
    lines.append(
        f"Plex's full export is **{len(rows):,} entries**. This is the "
        f"**{len(hits)}** of them that name something this repo actually reads: "
        f"{matched_views} tables and {matched_fields} fields."
    )
    lines.append("")
    lines.append(
        "Terms are matched on the name, ignoring case and underscores, so "
        "`Minimum_Inventory_Quantity` finds Plex's \"Minimum Inventory Quantity\". "
        "Substring matching is deliberately **not** used — \"Part\" alone would pull in "
        "hundreds of entries and bury the useful ones."
    )
    lines.append("")
    lines.append(
        "A term missing here means one of two things: Plex never defined it, or we "
        "invented the name ourselves. Both are worth knowing when someone asks "
        "*\"where does that come from?\"*"
    )
    lines.append("")

    titles = {
        "view": ("Tables we extract", "Each of these is pulled from Plex over ODBC into a `raw_` table."),
        "field": ("Fields we read", "Columns referenced in report SQL or config."),
    }
    for kind in ("view", "field"):
        items = grouped.get(kind, [])
        if not items:
            continue
        title, blurb = titles[kind]
        lines.append(f"## {title}")
        lines.append("")
        lines.append(blurb)
        lines.append("")
        lines.append("| Term | What Plex means by it |")
        lines.append("|---|---|")
        for h in items:
            label = f"`{h['repo_name']}`"
            if h["customer_term"] and norm(h["customer_term"]) != norm(h["term"]):
                label += f"<br>*Vox: {h['customer_term']}*"
            definition = h["definition"].replace("|", "\\|")
            lines.append(f"| {label} | {definition} |")
        lines.append("")

    # Unmatched vocabulary is the more interesting half: it is the list of names
    # nobody outside this repo can look up.
    unmatched_views = sorted(v for v in views if norm(v) not in hits)
    if unmatched_views:
        lines.append("## Tables Plex does not define")
        lines.append("")
        lines.append(
            "We extract these, and the glossary has nothing to say about them. If one "
            "of these comes up in a meeting, the answer has to come from the data or "
            "from Vox — there is no authority to appeal to."
        )
        lines.append("")
        lines.append(", ".join(f"`{v}`" for v in unmatched_views))
        lines.append("")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"matched: {len(hits)} ({matched_views} views, {matched_fields} fields)")
    print(f"unmatched views: {len(unmatched_views)}")
    print(f"written: {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
