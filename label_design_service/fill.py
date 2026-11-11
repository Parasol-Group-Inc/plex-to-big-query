"""Fill the label fields a pushed item was created without (2026-10-28).

The push creates each item once and never rewrites it. Sales should enter a
label part's attributes when the SO is made, so the designer knows what the
label needs (Kelli Gooch, 2026-10-28), but they often reach Plex AFTER the
order is already on Monday. So
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
# attributes, as in push.COLUMNS. Filled on every pushed item.
FIELDS = [
    ("Label Part #", "text", "label_part_no"),
    ("Label Size", "text", "part_label_size"),
    ("Printing Material", "status", "part_printing_material"),
    ("Allergen", "text", "part_allergen"),
]

# SCREENS + ODBC (2026-11-11). A line first seen on Plex's screens is pushed before
# ODBC has it, so the fields that come only from ODBC tables can be blank on the item:
# reps, the customer's email and phone, bottle material, priority, the part line.
# When the line reaches the view from ODBC, these are filled the same way (empty cells
# only, once per item and field). Only on items created from the screens: an item
# created from ODBC had them at creation, and a cell the team cleared stays cleared.
SCREEN_FIELDS = [
    ("Customer Name", "text", "customer_name"),
    ("Description", "text", "line_description"),
    ("Customer PO", "text", "customer_po"),
    ("Email", "email", "customer_email"),
    ("Phone Number", "text", "customer_phone"),
    ("Sales Rep", "status", "bdm"),
    ("Inside Sales Rep", "status", "am"),
    ("Priority", "status", "priority"),
    ("Bottle Material", "status", "bottle_material"),
]

# The Data Source cell of an item created from the screens says "Plex screens, read
# ...". Once ODBC has the line, it becomes "...; confirmed by ODBC <time> MT". This is
# the one cell that is overwritten, and only while it still holds the push's own
# "Plex screens" text (a value the team typed is left alone).
DATA_SOURCE = "Data Source"
SCREENS_PREFIX = "Plex screens"
CONFIRM = object()     # plan's placeholder: fill() builds the text from the cell


def value(ctype, raw):
    """The Monday value push.COLUMNS would send for this field, or None."""
    s = str(raw).strip() if raw is not None else ""
    if not s:
        return None
    if ctype == "status":
        return {"label": s}
    if ctype == "email":
        return {"email": s, "text": s}
    return s


def plan(rows, pushed, settled, from_screens=frozenset()):
    """rows: view rows, each with `_lcr`. pushed: {lcr: item_id}. settled:
    {lcr: {titles}} already filled or found set. from_screens: lcrs whose item was
    created from a Plex screens row. Returns [(row, item_id, {title: (ctype, value)})]."""
    out = []
    for r in rows:
        if r["_lcr"] not in pushed:
            continue
        item_id = pushed[r["_lcr"]]
        done = settled.get(r["_lcr"], ())
        screens_item = r["_lcr"] in from_screens
        want = {}
        for title, ctype, field in FIELDS + (SCREEN_FIELDS if screens_item else []):
            v = value(ctype, r.get(field))
            if v is None or title in done:
                continue
            want[title] = (ctype, v)
        if screens_item and r.get("data_source") == "odbc" and DATA_SOURCE not in done:
            want[DATA_SOURCE] = ("text", CONFIRM)
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


def _denied(msg):
    m = msg.lower()
    return "unauthorized" in m or "403" in m or "permission" in m or "not allowed" in m


def fill(api, candidates, align_status, apply=True, log=print, now_label=""):
    """Write each candidate's fields into the item's EMPTY cells (Data Source: see
    above). align_status ({column title: {labels}}) -> True when those status labels
    are safe to write (push.labels.align). One mutation per cell, so a column Monday
    refuses (Priority / Reason Code on Design & QA for our token) does not sink the
    others; a refused cell is reported as `denied` and settled, so it is not retried
    on every run. Returns [{row, item_id, written, already_set, denied, errors}]."""
    items = _items(api, [str(c[1]) for c in candidates])
    status_ok = None
    results = []
    for r, item_id, want in candidates:
        it = items.get(str(item_id))
        if not it or it["state"] != "active":
            continue   # deleted or archived: nothing to fill
        res = {"row": r, "item_id": item_id, "written": {}, "already_set": [], "denied": [], "errors": []}
        values = {}
        for title, (ctype, v) in want.items():
            cell = next((cv for cv in it["column_values"]
                         if cv["column"]["title"] == title and cv["type"] == ctype), None)
            text = ((cell or {}).get("text") or "").strip()
            if cell is None:
                res["errors"].append(f"{title}: no {ctype} column on board {it['board']['id']}")
            elif v is CONFIRM:
                if text.startswith(SCREENS_PREFIX) and "confirmed by ODBC" not in text:
                    values[title] = (cell["id"], f"{text}; confirmed by ODBC {now_label}".strip())
                else:
                    res["already_set"].append(title)   # the team changed it, or already confirmed
            elif text:
                res["already_set"].append(title)
            else:
                values[title] = (cell["id"], v)
        if any(isinstance(v, dict) and "label" in v for _, v in values.values()):
            if status_ok is None:
                needed = {}
                for c in candidates:
                    for t, (ct, v) in c[2].items():
                        if ct == "status":
                            needed.setdefault(t, set()).add(v["label"])
                status_ok = align_status(needed)
            if not status_ok:
                for t in [t for t, (_, v) in values.items() if isinstance(v, dict) and "label" in v]:
                    res["errors"].append(f"{t}: label colours not safe, left for the next run")
                    del values[t]
        if values:
            log(f"  fill item {item_id} ({r.get('dedupe_key')}): "
                + ", ".join(f"{t}={v['label'] if isinstance(v, dict) and 'label' in v else v}"
                            for t, (_, v) in values.items())
                + ("" if apply else " (dry run)"))
            if apply:
                for t, (cid, v) in values.items():
                    try:
                        api("""mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(
                                   board_id: $b, item_id: $i, column_values: $v, create_labels_if_missing: false) { id } }""",
                            {"b": it["board"]["id"], "i": item_id, "v": json.dumps({cid: v})})
                        res["written"][t] = v
                    except Exception as e:   # one cell; the rest still go
                        msg = str(e)[:200]
                        if _denied(msg):
                            res["denied"].append(t)
                        else:
                            res["errors"].append(f"{t}: write failed: {msg}")
        results.append(res)
    return results
