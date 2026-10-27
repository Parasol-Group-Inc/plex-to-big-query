"""Status label colours — keep what the push writes intact through a board move.

A Monday board move carries a status value across by the label's COLOUR, not
its name or id (proven 2026-10-27: 10 items moved from "Plex Import Test" to a
structure-only copy of Design & QA). The destination shows its label of that
colour; with no label of that colour, the column's default. So before the push
creates items:

  - every label it writes must exist on the push board with the colour the
    same label has on Design & QA;
  - a label Design & QA lacks is added there, with a colour neither board uses,
    and the push board's copy gets the same colour;
  - if Design & QA cannot be changed (403: Priority is a restricted column),
    the push board's label gets a colour Design & QA does not use, so a move
    leaves the field blank instead of showing some other label.

`plan()` is pure (tests: tests/test_label_colours.py); `align()` reads both
boards, applies the plan and checks the result. align() returns problems as
(blocking, message). Blocking = a move could show a WRONG label, so the push
must not create items this run; non-blocking = the field would arrive blank.
"""
try:
    from .monday import LABELS_API_VERSION
except ImportError:
    from monday import LABELS_API_VERSION

# Monday's colour ints run 0-19, 101-110, 151-160: the 40 StatusColumnColors
# values, in this order (checked against each label's hex, 2026-10-27).
ENUM = ["working_orange", "done_green", "stuck_red", "dark_blue", "purple", "explosive", "grass_green",
        "bright_blue", "saladish", "egg_yolk", "blackish", "dark_red", "sofia_pink", "lipstick", "dark_purple",
        "bright_green", "chili_blue", "american_gray", "brown", "dark_orange", "sunset", "bubble", "peach",
        "berry", "winter", "river", "navy", "aquamarine", "indigo", "dark_indigo", "pecan", "lavender",
        "royal", "steel", "orchid", "lilac", "tan", "sky", "coffee", "teal"]
COLOURS = list(range(20)) + list(range(101, 111)) + list(range(151, 161))
GREY = 5  # the empty label's colour; never handed out


class NoFreeColour(Exception):
    pass


def _by_name(labels):
    """{name: label}, an active label winning over a deactivated one of the same name."""
    out = {}
    for l in labels:
        if l["label"] and (l["label"] not in out or not l["is_deactivated"]):
            out[l["label"]] = l
    return out


def plan(push, dest, needed):
    """Label lists (dicts: id, label, color, index, is_done, is_deactivated) for
    one column on the push board and on Design & QA, and the label names this
    run will write. Returns (push_after, dest_after, notes): a full new label
    list for a board that must change, else None; notes say what changed."""
    push = [dict(l) for l in push]
    dest = [dict(l) for l in dest]
    on_dest = _by_name(dest)
    chosen = _by_name(push)   # the push label a write uses, per name
    taken = {l["color"] for l in dest} | {GREY}
    notes, dest_changed, push_changed = [], False, False

    def free(avoid=()):
        used = taken | {l["color"] for l in push} | set(avoid)
        c = next((c for c in COLOURS if c not in used), None)
        if c is None:
            raise NoFreeColour("every one of Monday's 40 colours is already used in this column")
        return c

    for name in sorted(n for n in needed if n not in on_dest):
        mine = chosen.get(name)
        colour = mine["color"] if mine and mine["color"] not in taken else free()
        new = {"label": name, "color": colour, "is_done": False, "is_deactivated": False}
        dest.append(new)
        on_dest[name] = new
        taken.add(colour)
        dest_changed = True
        notes.append(f"add {name!r} to Design & QA")

    # Push labels Design & QA has take its colour; any other push label holding
    # one of those colours moves to a free one (Monday rejects duplicates).
    # A second push label with the same name is treated as an unmatched one.
    want = {n: on_dest[n]["color"] for n in chosen if n in on_dest}
    for name in sorted(n for n in needed if n in on_dest and n not in want):
        new = {"label": name, "color": on_dest[name]["color"], "is_done": False, "is_deactivated": False}
        push.append(new)
        chosen[name] = new
        want[name] = on_dest[name]["color"]
        push_changed = True
        notes.append(f"add {name!r} to the push board")
    for name in sorted(needed):   # a deactivated label cannot be written
        l = chosen.get(name)
        if l is not None and l["is_deactivated"]:
            l["is_deactivated"] = False
            push_changed = True
            notes.append(f"reactivate {name!r} on the push board")
    claimed = set(want.values())
    for l in push:
        if l["label"] in want and l is chosen.get(l["label"]):
            if l["color"] != want[l["label"]]:
                l["color"] = want[l["label"]]
                push_changed = True
                notes.append(f"recolour {l['label']!r} to match Design & QA")
        elif l["color"] in claimed or (l["label"] and l["color"] in taken):
            l["color"] = free(claimed)
            claimed.add(l["color"])
            push_changed = True
            notes.append(f"move {l['label'] or '(empty label)'!r} off a colour Design & QA uses")
        else:
            claimed.add(l["color"])
    return (push if push_changed else None), (dest if dest_changed else None), notes


def to_input(labels):
    """UpdateStatusLabelInput list. A label with no stored position goes last."""
    nxt = max([l["index"] for l in labels if l.get("index") is not None] + [-1]) + 1
    out = []
    for l in labels:
        item = {"label": l["label"], "color": ENUM[COLOURS.index(l["color"])],
                "is_done": bool(l.get("is_done")), "is_deactivated": bool(l.get("is_deactivated"))}
        if l.get("index") is None:
            item["index"], nxt = nxt, nxt + 1
        else:
            item["index"] = l["index"]
        if l.get("id") is not None:
            item["id"] = l["id"]
        out.append(item)
    return out


def _status_columns(api, board_id, titles):
    """{title: column} — the FIRST status column with each title, as the push
    and a board move both use."""
    cols = api("query ($b: [ID!]) { boards(ids: $b) { columns { id title type revision settings } } }",
               {"b": [board_id]}, version=LABELS_API_VERSION)["boards"][0]["columns"]
    out = {}
    for c in cols:
        if c["type"] == "status" and c["title"] in titles and c["title"] not in out:
            out[c["title"]] = c
    return out


def _write(api, board_id, col, labels):
    api("""mutation ($b: ID!, $c: String!, $r: String!, $s: UpdateStatusColumnSettingsInput!) {
               update_status_column(board_id: $b, id: $c, revision: $r, settings: $s) { id } }""",
        {"b": board_id, "c": col["id"], "r": col["revision"], "s": {"labels": to_input(labels)}},
        version=LABELS_API_VERSION)


def align(api, push_board, dest_board, needed, apply=True, log=print):
    """Make every label in `needed` ({column title: {label names}}) safe to move
    from push_board to dest_board. Returns [(blocking, message)]; empty = safe."""
    titles = set(needed)
    try:
        push_cols = _status_columns(api, push_board, titles)
        dest_cols = _status_columns(api, dest_board, titles)
    except Exception as e:
        return [(True, f"could not read the boards' status labels ({type(e).__name__}: {str(e)[:200]})")]
    problems = []
    for title in sorted(titles):
        if title not in push_cols or title not in dest_cols:
            problems.append((title not in push_cols, f"{title}: no status column of that title on "
                             f"{'the push board' if title not in push_cols else 'Design & QA'}"))
            continue
        pcol, dcol = push_cols[title], dest_cols[title]
        plabels, dlabels = pcol["settings"]["labels"], dcol["settings"]["labels"]
        try:
            push_after, dest_after, notes = plan(plabels, dlabels, needed[title])
        except NoFreeColour as e:
            problems.append((True, f"{title}: {e}"))
            continue
        if not notes:
            continue
        log(f"Label colours, {title}: {'; '.join(notes)}{'' if apply else ' (dry run, not applied)'}")
        if not apply:
            continue
        if dest_after is not None:
            try:
                _write(api, dest_board, dcol, dest_after)
            except Exception as e:
                # Design & QA refused (restricted column). Plan again as if it may
                # not change: the new labels then get a colour it does not use.
                missing = ", ".join(repr(n) for n in sorted(needed[title]) if n not in _by_name(dlabels))
                problems.append((False, f"{title}: Design & QA refused new label(s) {missing}; a move will leave "
                                        f"the field blank ({type(e).__name__}: {str(e)[:200]})"))
                try:
                    push_after, _, _ = plan(plabels, dlabels, {n for n in needed[title] if n in _by_name(dlabels)})
                    push_after = _add_unmatched(push_after or plabels, dlabels, needed[title])
                except NoFreeColour as e2:
                    problems.append((True, f"{title}: {e2}"))
                    continue
                if _same(push_after, plabels):
                    push_after = None
        if push_after is not None:
            try:
                _write(api, push_board, pcol, push_after)
            except Exception as e:
                problems.append((True, f"{title}: could not update the push board's labels "
                                       f"({type(e).__name__}: {str(e)[:200]})"))

    if apply:  # check what Monday now holds, not what was sent
        try:
            push_cols = _status_columns(api, push_board, titles)
            dest_cols = _status_columns(api, dest_board, titles)
        except Exception as e:
            return problems + [(True, f"could not re-read the boards to check ({type(e).__name__})")]
        for title in sorted(titles & set(push_cols) & set(dest_cols)):
            p = {l["label"]: l for l in push_cols[title]["settings"]["labels"]
                 if l["label"] and not l["is_deactivated"]}
            d = _by_name(dest_cols[title]["settings"]["labels"])
            dest_colours = {l["color"] for l in dest_cols[title]["settings"]["labels"]}
            for name in sorted(needed[title]):
                if name not in p:
                    problems.append((True, f"{title}: {name!r} missing or deactivated on the push board"))
                elif name in d and p[name]["color"] != d[name]["color"]:
                    problems.append((True, f"{title}: {name!r} colour differs from Design & QA"))
                elif name not in d and p[name]["color"] in dest_colours:
                    problems.append((True, f"{title}: {name!r} shares a colour with another Design & QA label"))
    return problems


def _same(a, b):
    key = lambda ls: sorted((l["label"], l["color"], bool(l.get("is_deactivated"))) for l in ls)
    return key(a) == key(b)


def _add_unmatched(push, dest, needed):
    """Push labels for names Design & QA lacks, each on a colour it does not use."""
    push = [dict(l) for l in push]
    have = {l["label"] for l in push}
    used = {l["color"] for l in dest} | {l["color"] for l in push} | {GREY}
    def free():
        c = next((c for c in COLOURS if c not in used), None)
        if c is None:
            raise NoFreeColour("every one of Monday's 40 colours is already used in this column")
        return c
    for name in sorted(n for n in needed if n not in have and n not in _by_name(dest)):
        colour = free()
        push.append({"label": name, "color": colour, "is_done": False, "is_deactivated": False})
        used.add(colour)
    for l in push:  # an existing one on a Design & QA colour would show as that label
        if l["label"] in needed and l["label"] not in _by_name(dest) and l["color"] in {d["color"] for d in dest}:
            l["color"] = free()
            used.add(l["color"])
    return push
