#!/usr/bin/env python3
"""Copy a Monday board's columns, groups AND items (column values) onto
another board, optionally wiping the target first.

    python scripts/copy_monday_board.py --source 18395121955 --target 18432111755 --wipe-target

Built 2026-09-24 to fill the new "Plex Import" board (18432111755) with the
real Design & QA history so Ashley can review it. Where
`replicate_board_columns.py` copies structure only, this copies data too.

What is copied:
  - columns, in source order, same titles/types. Status labels keep their
    SOURCE index numbers (so colors match); any label past Monday's
    ~20-per-create_column cap is added on the fly by item writes via
    `create_labels_if_missing`.
  - formula columns, with every {column_id} reference remapped to the
    target board's new ids.
  - groups, same titles and order.
  - items, same group and order, every writable column value.

What is NOT copied (reported, not silently dropped):
  - files (file columns): no API path copies an asset by value; each would
    need a download + re-upload.
  - updates/comments, activity log, subitem structure (source had none).
  - item ids and "created" timestamps — every item is new on the target.

--wipe-target deletes EVERY item, every non-name column and every group on
the target before copying. It is irreversible (items go to Monday's trash
for 30 days, columns/groups do not).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API_VERSION = "2024-10"
# Types whose value can't (or shouldn't) be written by value.
NO_VALUE_TYPES = {"name", "file", "formula", "subtasks", "mirror", "board_relation",
                  "dependency", "creation_log", "last_updated", "auto_number",
                  "item_id", "button", "time_tracking", "vote", "doc"}
NO_CREATE_TYPES = {"name", "subtasks", "mirror", "board_relation", "dependency"}


def load_api_key(env_path, var_name):
    prefix = var_name + "="
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(prefix):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{var_name} not found in {env_path}")


class Monday:
    def __init__(self, api_key):
        self.api_key = api_key

    def __call__(self, query, variables=None, tries=5):
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        for attempt in range(tries):
            req = urllib.request.Request("https://api.monday.com/v2", data=payload, method="POST",
                                         headers={"Authorization": self.api_key,
                                                  "Content-Type": "application/json",
                                                  "API-Version": API_VERSION})
            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
                if attempt == tries - 1:
                    raise
                time.sleep(5 * (attempt + 1))
                continue
            errors = body.get("errors") or ([body] if "error_message" in body else None)
            if errors:
                text = json.dumps(errors)
                if ("Complexity" in text or "rate limit" in text.lower()) and attempt < tries - 1:
                    time.sleep(30)
                    continue
                raise RuntimeError("Monday API error: " + text)
            return body["data"]


def fetch_board(api, board_id):
    b = api("""query ($b: [ID!]) { boards(ids: $b) { name
               columns { id title type settings_str } groups { id title } } }""",
            {"b": [board_id]})["boards"]
    if not b:
        raise SystemExit(f"Board {board_id} not found or not visible to this token")
    return b[0]


def fetch_items(api, board_id):
    fields = "cursor items { id name group { id } column_values { id type text value } }"
    page = api("query ($b: [ID!]) { boards(ids: $b) { items_page(limit: 50) { %s } } }" % fields,
               {"b": [board_id]})["boards"][0]["items_page"]
    items = list(page["items"])
    while page["cursor"]:
        page = api("query ($c: String!) { next_items_page(cursor: $c, limit: 50) { %s } }" % fields,
                   {"c": page["cursor"]})["next_items_page"]
        items += page["items"]
    return items


def status_defaults(settings_str, keep_index):
    labels = (json.loads(settings_str or "{}").get("labels") or {})
    ordered = [(k, labels[k]) for k in sorted(labels, key=int) if labels[k]]
    if not ordered:
        return None
    if keep_index:
        return json.dumps({"labels": {k: v for k, v in ordered}})
    return json.dumps({"labels": {str(i): v for i, (_, v) in enumerate(ordered[:20])}})


def write_value(ctype, text, raw):
    """Source column value -> the shape change_multiple_column_values accepts."""
    if not text and not raw:
        return None
    v = json.loads(raw) if raw else None
    if ctype == "status":
        return {"label": text} if text else None
    if ctype == "dropdown":
        return {"labels": [t.strip() for t in text.split(",") if t.strip()]} if text else None
    if ctype == "text":
        return text or None
    if ctype == "numbers":
        return text or None
    if ctype == "long_text":
        return {"text": (v or {}).get("text", text)} if (text or v) else None
    if ctype == "people":
        pt = (v or {}).get("personsAndTeams")
        return {"personsAndTeams": [{"id": p["id"], "kind": p["kind"]} for p in pt]} if pt else None
    if ctype == "date":
        if not v or not v.get("date"):
            return None
        out = {"date": v["date"]}
        if v.get("time"):
            out["time"] = v["time"]
        return out
    if ctype == "timeline":
        return {"from": v["from"], "to": v["to"]} if v and v.get("from") else None
    if ctype == "email":
        return {"email": v.get("email"), "text": v.get("text") or v.get("email")} if v and v.get("email") else None
    if ctype == "link":
        return {"url": v.get("url"), "text": v.get("text") or v.get("url")} if v and v.get("url") else None
    if ctype == "phone":
        return {"phone": v.get("phone"), "countryShortName": v.get("countryShortName")} if v and v.get("phone") else None
    if ctype == "checkbox":
        return {"checked": "true"} if v and v.get("checked") else None
    # hour, week, rating, country, location, color_picker, tags, world_clock:
    # the read value is the write value.
    return v


def wipe(api, board_id, board):
    items = fetch_items(api, board_id)
    for it in items:
        api("mutation ($i: ID!) { delete_item(item_id: $i) { id } }", {"i": it["id"]})
    print(f"  deleted {len(items)} items")
    cols = [c for c in board["columns"] if c["type"] != "name"]
    for c in cols:
        api("mutation ($b: ID!, $c: String!) { delete_column(board_id: $b, column_id: $c) { id } }",
            {"b": board_id, "c": c["id"]})
    print(f"  deleted {len(cols)} columns")
    return [g["id"] for g in board["groups"]]  # deleted after new groups exist


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--env-path", default=os.path.join(os.path.dirname(__file__), "..", ".env"))
    ap.add_argument("--key-var", default="MONDAY_API_KEY")
    ap.add_argument("--wipe-target", action="store_true")
    args = ap.parse_args()

    api = Monday(load_api_key(os.path.abspath(args.env_path), args.key_var))
    src = fetch_board(api, args.source)
    tgt = fetch_board(api, args.target)
    src_items = fetch_items(api, args.source)
    print(f"Source '{src['name']}': {len(src['columns'])} columns, {len(src['groups'])} groups, {len(src_items)} items")
    print(f"Target '{tgt['name']}': {len(tgt['columns'])} columns, {len(tgt['groups'])} groups")

    old_groups = []
    if args.wipe_target:
        print("Wiping target...")
        old_groups = wipe(api, args.target, tgt)

    # -- columns --------------------------------------------------------
    col_map, skipped = {}, []
    src_name_col = next(c for c in src["columns"] if c["type"] == "name")
    tgt_name_col = next(c for c in tgt["columns"] if c["type"] == "name")
    col_map[src_name_col["id"]] = tgt_name_col["id"]
    api("mutation ($b: ID!, $c: String!, $t: String!) { change_column_title(board_id: $b, column_id: $c, title: $t) { id } }",
        {"b": args.target, "c": tgt_name_col["id"], "t": src_name_col["title"]})

    create = """mutation ($b: ID!, $t: String!, $ty: ColumnType!, $d: JSON) {
                  create_column(board_id: $b, title: $t, column_type: $ty, defaults: $d) { id } }"""
    formulas = []
    for c in src["columns"]:
        if c["type"] in NO_CREATE_TYPES:
            if c["type"] != "name":
                skipped.append(f"{c['title']} ({c['type']}) — column not creatable")
            continue
        if c["type"] == "formula":
            formulas.append(c)  # after all other columns exist, so ids can be remapped
            continue
        defaults = None
        if c["type"] in ("status", "dropdown"):
            defaults = status_defaults(c["settings_str"], keep_index=True)
        try:
            new = api(create, {"b": args.target, "t": c["title"], "ty": c["type"], "d": defaults})
        except RuntimeError as e:
            if defaults is None:
                raise
            print(f"  '{c['title']}': full label set refused ({str(e)[:120]}), retrying with first 20 renumbered")
            new = api(create, {"b": args.target, "t": c["title"], "ty": c["type"],
                               "d": status_defaults(c["settings_str"], keep_index=False)})
        col_map[c["id"]] = new["create_column"]["id"]
    for c in formulas:
        f = json.loads(c["settings_str"]).get("formula", "")
        f = re.sub(r"\{(\w+)\}", lambda m: "{%s}" % col_map.get(m.group(1), m.group(1)), f)
        try:
            new = api(create, {"b": args.target, "t": c["title"], "ty": "formula", "d": json.dumps({"formula": f})})
            col_map[c["id"]] = new["create_column"]["id"]
        except RuntimeError as e:
            skipped.append(f"{c['title']} (formula) — {str(e)[:150]}")
    print(f"Created {len(col_map) - 1} columns")

    # -- groups (create_group puts new groups on top, so go bottom-up) ---
    group_map = {}
    for g in reversed(src["groups"]):
        new = api("mutation ($b: ID!, $n: String!) { create_group(board_id: $b, group_name: $n) { id } }",
                  {"b": args.target, "n": g["title"]})
        group_map[g["id"]] = new["create_group"]["id"]
    for gid in old_groups:
        api("mutation ($b: ID!, $g: String!) { delete_group(board_id: $b, group_id: $g) { id } }",
            {"b": args.target, "g": gid})
    print(f"Created {len(group_map)} groups, removed {len(old_groups)} default groups")

    # -- items (create_item puts new items on top, so go bottom-up) -----
    create_item = """mutation ($b: ID!, $g: String!, $n: String!, $v: JSON) {
        create_item(board_id: $b, group_id: $g, item_name: $n, column_values: $v,
                    create_labels_if_missing: true) { id } }"""
    failed = []
    for n, it in enumerate(reversed(src_items), 1):
        values = {}
        for cv in it["column_values"]:
            if cv["type"] in NO_VALUE_TYPES or cv["id"] not in col_map:
                continue
            w = write_value(cv["type"], cv["text"], cv["value"])
            if w is not None:
                values[col_map[cv["id"]]] = w
        base = {"b": args.target, "g": group_map[it["group"]["id"]], "n": it["name"] or "(untitled)"}
        try:
            api(create_item, dict(base, v=json.dumps(values)))
        except RuntimeError:
            # One bad value rejects the whole item — create it bare, then set
            # columns one by one so only the offending value is lost.
            new_id = api(create_item, dict(base, v="{}"))["create_item"]["id"]
            for col, w in values.items():
                try:
                    api("""mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(
                           board_id: $b, item_id: $i, column_values: $v, create_labels_if_missing: true) { id } }""",
                        {"b": args.target, "i": new_id, "v": json.dumps({col: w})})
                except RuntimeError as e:
                    failed.append((it["id"], it["name"], col, json.dumps(w)[:80], str(e)[:200]))
        if n % 25 == 0:
            print(f"  {n}/{len(src_items)} items")
    print(f"Created {len(src_items)} items; {len(failed)} individual values failed")

    for s in skipped:
        print("SKIPPED COLUMN:", s)
    for f in failed:
        print("FAILED VALUE:", *f)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
