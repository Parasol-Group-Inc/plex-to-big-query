#!/usr/bin/env python3
"""Copy a Monday board's column STRUCTURE (title + type + status/dropdown
labels) onto another board. No items/data are copied — only columns.

    python scripts/replicate_board_columns.py --source 18395121955 --target 18430735110

Built once, 2026-09-16, to turn the empty "Plex Import Board" (test) into a
structural mirror of the real "Design & QA" board (prod), so the new
standalone Label Design push service can be tested against a board shaped
like the real thing before it ever touches prod.

Idempotent by title+type: columns already present on the target (by title)
are skipped and reported, not recreated, so a re-run after a partial
failure only fills in what's missing.

Columns that can't be meaningfully recreated via the API are skipped with a
warning, not attempted:
  - `name`      the item's own title column, already exists on every board.
  - `formula`   a formula string references other columns' internal ids,
                which differ per board — copying the text would silently
                point at the wrong (or nonexistent) columns on the target.
  - `subtasks`  an automatic column Monday manages itself; not creatable
                directly via `create_column`.

For `status` columns, the source's option LABELS are recreated (via the
`defaults` argument) so dropdowns are usable for testing. The option
INDEX NUMBERS are not preserved — Monday assigns its own on the new board,
which is fine for a fresh test board where nothing existing depends on the
old numbers, but means the id/index maps in
`label-design/monday_board_catalog.md` do NOT apply to the target board.
Re-run listMondayColumns() (or this script's own --report-only mode) against
the target once done to get its real ids before wiring a push at it.
"""
import argparse
import json
import os
import urllib.request

SKIP_TYPES = {"name", "formula", "subtasks"}


def load_api_key(env_path, var_name="MONDAY_API_KEY"):
    prefix = var_name + "="
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{var_name} not found in {env_path}")


def monday_query(api_key, query, variables=None):
    req = urllib.request.Request(
        "https://api.monday.com/v2",
        data=json.dumps({"query": query, "variables": variables or {}}).encode("utf-8"),
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
            "API-Version": "2023-10",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if "errors" in body:
        raise SystemExit("Monday API error: " + json.dumps(body["errors"], indent=2))
    return body["data"]


def fetch_columns(api_key, board_id):
    data = monday_query(api_key, """
        query ($board: [ID!]) {
          boards (ids: $board) { name columns { id title type settings_str } }
        }
    """, {"board": [board_id]})
    boards = data["boards"]
    if not boards:
        raise SystemExit(f"Board {board_id} not found or not visible to this token")
    return boards[0]["name"], boards[0]["columns"]


def status_defaults(settings_str):
    """Build a `defaults` JSON string carrying the option labels.

    Monday's `create_column` defaults for a status column must echo the
    same shape `settings_str` itself returns on read — a dict keyed by
    string index ("0", "1", ...) — NOT a bare array. Passing an array is
    silently accepted (create_column still returns an id) but produces a
    column with a single NULL-labeled option; the real label text is
    dropped with no error. Caught 2026-09-16 by reading settings_str back
    after creation and finding every "created" status column had null
    labels. Re-numbering from 0 (rather than reusing the source's original
    index numbers, which have gaps) is fine here — nothing on the new board
    depends on the old numbers.
    """
    settings = json.loads(settings_str or "{}")
    labels = settings.get("labels") or {}
    ordered = [labels[k] for k in sorted(labels, key=lambda x: int(x)) if labels[k]]
    if not ordered:
        return None
    return json.dumps({"labels": {str(i): text for i, text in enumerate(ordered)}})


def create_column(api_key, board_id, title, column_type, defaults_json):
    data = monday_query(api_key, """
        mutation ($board: ID!, $title: String!, $type: ColumnType!, $defaults: JSON) {
          create_column (board_id: $board, title: $title, column_type: $type, defaults: $defaults) {
            id
            title
          }
        }
    """, {"board": board_id, "title": title, "type": column_type, "defaults": defaults_json})
    return data["create_column"]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="Source board id to copy columns FROM")
    ap.add_argument("--target", required=True, help="Target board id to copy columns TO")
    ap.add_argument("--env-path", default=os.path.join(os.path.dirname(__file__), "..", ".env"))
    ap.add_argument("--source-key-var", default="MONDAY_API_KEY",
                     help="Env var name holding the token used to READ the source board")
    ap.add_argument("--target-key-var", default="MONDAY_API_KEY",
                     help="Env var name holding the token used to WRITE (create_column) on the target board")
    ap.add_argument("--dry-run", action="store_true",
                     help="Print what would be created, make no API writes")
    args = ap.parse_args()

    source_api_key = load_api_key(os.path.abspath(args.env_path), args.source_key_var)
    target_api_key = load_api_key(os.path.abspath(args.env_path), args.target_key_var)

    source_name, source_columns = fetch_columns(source_api_key, args.source)
    target_name, target_columns = fetch_columns(target_api_key, args.target)
    print(f"Source: '{source_name}' ({args.source}) — {len(source_columns)} columns")
    print(f"Target: '{target_name}' ({args.target}) — {len(target_columns)} columns already present")

    existing_titles = {c["title"] for c in target_columns}

    created, skipped_existing, skipped_type, failed = [], [], [], []

    for col in source_columns:
        title, ctype = col["title"], col["type"]

        if ctype in SKIP_TYPES:
            skipped_type.append((title, ctype))
            continue
        if title in existing_titles:
            skipped_existing.append((title, ctype))
            continue

        defaults_json = status_defaults(col["settings_str"]) if ctype == "status" else None

        if args.dry_run:
            print(f"  WOULD CREATE  {ctype:10s} {title!r}"
                  + (f"  ({defaults_json})" if defaults_json else ""))
            created.append((title, ctype, None))
            continue

        try:
            result = create_column(target_api_key, args.target, title, ctype, defaults_json)
            print(f"  created  {ctype:10s} {title!r} -> {result['id']}")
            created.append((title, ctype, result["id"]))
            existing_titles.add(title)  # guard duplicate source titles (e.g. two "Sales Rep")
        except SystemExit as e:
            print(f"  FAILED   {ctype:10s} {title!r}: {e}")
            failed.append((title, ctype, str(e)))

    print()
    print(f"Created: {len(created)}  Skipped (already present): {len(skipped_existing)}  "
          f"Skipped (unsupported type): {len(skipped_type)}  Failed: {len(failed)}")
    if skipped_type:
        print("  Unsupported type, needs manual creation in the Monday UI if needed:")
        for title, ctype in skipped_type:
            print(f"    {ctype:10s} {title!r}")
    if failed:
        print("  Failed — investigate before assuming the target board is complete:")
        for title, ctype, err in failed:
            print(f"    {ctype:10s} {title!r}: {err}")


if __name__ == "__main__":
    main()
