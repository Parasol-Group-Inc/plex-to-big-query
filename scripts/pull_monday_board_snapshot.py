#!/usr/bin/env python3
"""Pull every item on the "Design & QA" Monday board dated in the last 14
days into a CSV, for a broad look at what's actually there before designing
the hash-based dedupe.

    python scripts/pull_monday_board_snapshot.py

Read-only — a single GraphQL query (paginated), nothing written to Monday.

WHERE THE OUTPUT GOES, AND WHY NOT THE REPO: board items carry real customer
names/emails/phone numbers, so this is treated exactly like the historical
Label Design export — written to a local, gitignored path, never committed.
Default output directory is this machine's temp folder; override with
--out-dir if you want it somewhere specific (still never inside the repo).

FILTER: matched against each item's "Date" column (id date_mm07aq60) — the
closest analog to Plex's order_date in the current board schema. An item
with that column blank is NOT guessed into or out of the window; it's
counted separately and listed at the end of the run so nothing is silently
dropped. If "Date" turns out to be the wrong column for this purpose, rerun
with --date-column-id to point at a different one (see
label-design/monday_board_catalog.md for the full column list).
"""
import argparse
import csv
import datetime as dt
import json
import os
import sys
import tempfile
import urllib.request

BOARD_ID = "18395121955"
DEFAULT_DATE_COLUMN_ID = "date_mm07aq60"  # "Date"


def load_api_key(env_path):
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("MONDAY_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"MONDAY_API_KEY not found in {env_path}")


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


def fetch_columns(api_key):
    data = monday_query(api_key, """
        query ($board: [ID!]) {
          boards (ids: $board) { name columns { id title } }
        }
    """, {"board": [BOARD_ID]})
    board = data["boards"][0]
    return board["name"], board["columns"]


def fetch_all_items(api_key):
    """Pages through items_page until every item on the board is collected."""
    items = []
    cursor = None
    query = """
        query ($board: [ID!], $cursor: String) {
          boards (ids: $board) {
            items_page (limit: 100, cursor: $cursor) {
              cursor
              items {
                id
                name
                created_at
                column_values { id text }
              }
            }
          }
        }
    """
    while True:
        data = monday_query(api_key, query, {"board": [BOARD_ID], "cursor": cursor})
        page = data["boards"][0]["items_page"]
        items.extend(page["items"])
        cursor = page["cursor"]
        if not cursor:
            break
    return items


def parse_monday_date(text):
    """Monday's 'text' rendering of a date column, e.g. '2026-09-12'."""
    if not text:
        return None
    try:
        return dt.date.fromisoformat(text.strip()[:10])
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--date-column-id", default=DEFAULT_DATE_COLUMN_ID)
    ap.add_argument("--out-dir", default=None,
                     help="Defaults to the system temp dir. Never the repo.")
    ap.add_argument("--env-path", default=os.path.join(
        os.path.dirname(__file__), "..", ".env"))
    args = ap.parse_args()

    api_key = load_api_key(os.path.abspath(args.env_path))

    board_name, columns = fetch_columns(api_key)
    print(f"Board: {board_name}  ({len(columns)} columns)")

    items = fetch_all_items(api_key)
    print(f"Total items on board: {len(items)}")

    cutoff = dt.date.today() - dt.timedelta(days=args.days)
    print(f"Cutoff (last {args.days} days): items with "
          f"'{args.date_column_id}' >= {cutoff.isoformat()}")

    in_window, blank_date, out_of_window = [], [], []
    for item in items:
        cv_by_id = {cv["id"]: cv["text"] for cv in item["column_values"]}
        raw_date = cv_by_id.get(args.date_column_id)
        parsed = parse_monday_date(raw_date)
        if parsed is None:
            blank_date.append(item)
        elif parsed >= cutoff:
            in_window.append(item)
        else:
            out_of_window.append(item)

    print(f"  in window:              {len(in_window)}")
    print(f"  blank/unparseable date: {len(blank_date)}  (listed separately below, not guessed either way)")
    print(f"  older than window:      {len(out_of_window)}")

    out_dir = args.out_dir or tempfile.gettempdir()
    os.makedirs(out_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    out_path = os.path.join(out_dir, f"monday_board_snapshot_last{args.days}days_{stamp}.csv")

    header = ["item_id", "item_name", "created_at"] + [c["title"] for c in columns]
    col_id_by_title = {c["title"]: c["id"] for c in columns}

    def write_rows(writer, rows, section_label):
        if not rows:
            return
        writer.writerow([f"--- {section_label} ({len(rows)}) ---"])
        for item in rows:
            cv_by_id = {cv["id"]: cv["text"] for cv in item["column_values"]}
            row = [item["id"], item["name"], item["created_at"]]
            row += [cv_by_id.get(col_id_by_title[title], "") for title in header[3:]]
            writer.writerow(row)

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        write_rows(writer, in_window, "IN WINDOW")
        write_rows(writer, blank_date, "BLANK/UNPARSEABLE DATE")
        write_rows(writer, out_of_window, "OLDER THAN WINDOW (for context)")

    print(f"\nWrote {out_path}")
    print("NOT committed to git — contains real customer names/emails/phones, same as the historical Label Design export.")


if __name__ == "__main__":
    main()
