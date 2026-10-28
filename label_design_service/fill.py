"""Fill the label fields a pushed item was created without (2026-10-28).

The push creates each item once and never rewrites it. But QA often fills a
label part's attributes in Plex AFTER the order is already on Monday, and
printing needs them once the label is approved (Kelli Gooch, 2026-10-28). So
every push run also looks at the items it created that are still in the view:

  - a label field the view has a value for, that this step has not settled
    before, is a candidate;
  - it is written only if that cell is EMPTY on the item now, on whatever
    board the item sits (Plex Import Test or Design & QA). A value the push
    sent, or the team typed, is left alone;
  - each (item, field) is settled once: written, or found already set. Both
    are recorded as an `outcome = 'filled'` row in the push log, so a cell the
    team later clears is not filled again, and an item is read once per field.

What the item was created with is not compared: the push log keys it by
column id, and a label-only line's Label Part # equals its Item value, so a
match by value alone skipped exactly the lines this was for.

`plan()` is pure (tests: tests/test_label_fill.py); `fill()` reads the items
and writes.
"""
import json

# (board column title, column type, view field) — the label part and its
# attributes, as in push.COLUMNS.
FIELDS = [
    ("Label Part #", "text", "label_part_no"),
    ("Label Size", "text", "part_label_size"),
    ("Printing Material", "status", "part_printing_material"),
    ("Allergen", "text", "part_allergen"),
]


def value(ctype, raw):
    """The Monday value push.COLUMNS would send for this field, or None."""
    s = str(raw).strip() if raw is not None else ""
    if not s:
        return None
    return {"label": s} if ctype == "status" else s


def plan(rows, pushed, settled):
    """rows: view rows, each with `_lcr`. pushed: {lcr: item_id}. settled:
    {lcr: {titles}} already filled or found set. Returns
    [(row, item_id, {title: (ctype, value)})]."""
    out = []
    for r in rows:
        if r["_lcr"] not in pushed:
            continue
        item_id = pushed[r["_lcr"]]
        want = {}
        for title, ctype, field in FIELDS:
            v = value(ctype, r.get(field))
            if v is None or title in settled.get(r["_lcr"], ()):
                continue
            want[title] = (ctype, v)
        if want:
            out.append((r, item_id, want))
    return out


def _items(api, ids):
    out = {}
    for i in range(0, len(ids), 100):
        q = ("query ($i: [ID!]) { items(ids: $i, limit: 100) { id state board { id } "
             "column_values { id text type column { title } } } }")
        for it in api(q, {"i": ids[i:i + 100]})["items"]:
            out[it["id"]] = it
    return out


def fill(api, candidates, align_status, apply=True, log=print):
    """Write each candidate's fields into the item's EMPTY cells. align_status
    ({column title: {labels}}) -> True when those status labels are safe to
    write (push.labels.align). Returns [{row, item_id, written, already_set,
    errors}] for every item looked at."""
    items = _items(api, [c[1] for c in candidates])
    status_ok = None
    results = []
    for r, item_id, want in candidates:
        it = items.get(str(item_id))
        if not it or it["state"] != "active":
            continue   # deleted or archived: nothing to fill
        res = {"row": r, "item_id": item_id, "written": {}, "already_set": [], "errors": []}
        values = {}
        for title, (ctype, v) in want.items():
            cell = next((cv for cv in it["column_values"]
                         if cv["column"]["title"] == title and cv["type"] == ctype), None)
            if cell is None:
                res["errors"].append(f"{title}: no {ctype} column on board {it['board']['id']}")
            elif (cell["text"] or "").strip():
                res["already_set"].append(title)
            else:
                values[title] = (cell["id"], v)
        if any(isinstance(v, dict) for _, v in values.values()):
            if status_ok is None:
                needed = {}
                for c in candidates:
                    for t, (ct, v) in c[2].items():
                        if ct == "status":
                            needed.setdefault(t, set()).add(v["label"])
                status_ok = align_status(needed)
            if not status_ok:
                for t in [t for t, (_, v) in values.items() if isinstance(v, dict)]:
                    res["errors"].append(f"{t}: label colours not safe, left for the next run")
                    del values[t]
        if values:
            log(f"  fill item {item_id} ({r.get('dedupe_key')}): "
                + ", ".join(f"{t}={v['label'] if isinstance(v, dict) else v}" for t, (_, v) in values.items())
                + ("" if apply else " (dry run)"))
            if apply:
                try:
                    api("""mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(
                               board_id: $b, item_id: $i, column_values: $v, create_labels_if_missing: false) { id } }""",
                        {"b": it["board"]["id"], "i": item_id,
                         "v": json.dumps({cid: v for cid, v in values.values()})})
                    res["written"] = {t: v for t, (_, v) in values.items()}
                except RuntimeError as e:
                    res["errors"].append(f"write failed: {str(e)[:200]}")
        results.append(res)
    return results
