"""Tests for label_design_service/labels.py: keep pushed status labels intact
through a Monday board move, which matches labels by COLOUR (2026-10-27).

    python tests/test_label_colours.py            # plain asserts, prints OK
    python -m pytest tests/test_label_colours.py  # same tests under pytest

No Monday or BigQuery needed. `moved()` imitates the move as observed: the
destination label with the source label's colour, else the column default.
"""
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "label_design_service"))

import labels as L  # noqa: E402


def lab(i, name, colour, deactivated=False):
    return {"id": i, "label": name, "color": colour, "index": i, "is_done": False, "is_deactivated": deactivated}


def moved(name, push, dest):
    """What a value shows after a board move, by colour."""
    colour = next(l["color"] for l in push if l["label"] == name)
    hit = [l["label"] for l in dest if l["color"] == colour]
    return hit[0] if hit else None   # None = the column's default (blank)


# Shaped on 2026-10-27's Bottle Material: same names and ids, PET/HDPE coloured
# differently, Opt In/Opt Out deactivated on Design & QA.
PUSH_BOTTLE = [lab(0, "PET", 0), lab(1, "HDPE", 1), lab(2, "Glass", 2), lab(4, "Opt Out", 4), lab(6, "Opt In", 6)]
DEST_BOTTLE = [lab(0, "PET", 101), lab(1, "HDPE", 14), lab(2, "Glass", 2),
               lab(4, "Opt Out", 4, True), lab(6, "Opt In", 6, True), lab(10, "Amber Glass", 10)]


def test_mismatched_colours_are_aligned():
    assert moved("PET", PUSH_BOTTLE, DEST_BOTTLE) is None          # the bug: blank
    push, dest, notes = L.plan(PUSH_BOTTLE, DEST_BOTTLE, {"PET", "HDPE", "Glass"})
    assert dest is None                                             # Design & QA untouched
    for name in ("PET", "HDPE", "Glass", "Opt In", "Opt Out"):
        assert moved(name, push, DEST_BOTTLE) == name, name
    assert len({l["color"] for l in push}) == len(push)             # Monday rejects duplicates


def test_swapped_colours_are_untangled():
    # Reason Code: each push label wore the colour of a DIFFERENT Design & QA label.
    push = [lab(0, "Label review", 0), lab(1, "Label edit", 1), lab(2, "New design", 2)]
    dest = [lab(0, "Label review", 1), lab(1, "Label edit", 2), lab(2, "New design", 0)]
    assert moved("Label review", push, dest) == "New design"       # silently wrong
    after, _, _ = L.plan(push, dest, {"Label review"})
    for l in push:
        assert moved(l["label"], after, dest) == l["label"]


def test_label_missing_on_dest_is_added_to_both_with_one_free_colour():
    push = [lab(0, "Kami Butcher", 7), lab(19, "Julianni Pacheco", 19)]
    dest = [lab(0, "Kami Butcher", 7), lab(19, "N/A", 19)]          # 19 = N/A there
    assert moved("Julianni Pacheco", push, dest) == "N/A"
    p, d, notes = L.plan(push, dest, {"Julianni Pacheco", "Kami Butcher"})
    assert any("add 'Julianni Pacheco' to Design & QA" in n for n in notes)
    assert moved("Julianni Pacheco", p, d) == "Julianni Pacheco"
    assert moved("Kami Butcher", p, d) == "Kami Butcher"
    assert [l["label"] for l in d][:2] == ["Kami Butcher", "N/A"]   # existing labels kept, in order


def test_label_missing_on_both_boards():
    push, dest = [lab(0, "PET", 0)], [lab(0, "PET", 0)]
    p, d, _ = L.plan(push, dest, {"Bamboo"})
    assert moved("Bamboo", p, d) == "Bamboo"


def test_unneeded_push_label_on_a_dest_colour_is_moved():
    # "RUSH ⚠️️" exists only on the push board; RUSH must take its colour.
    push = [lab(0, "RUSH", 0), lab(10, "RUSH ⚠️️", 10), lab(2, "Medium", 2)]
    dest = [lab(10, "RUSH", 10), lab(2, "Medium", 2)]
    p, _, _ = L.plan(push, dest, {"RUSH", "Medium"})
    assert moved("RUSH", p, dest) == "RUSH"
    assert moved("RUSH ⚠️️", p, dest) is None                      # blank, never a wrong label
    assert len({l["color"] for l in p}) == len(p)


def test_already_aligned_changes_nothing():
    push = [lab(0, "PET", 101), lab(1, "HDPE", 14)]
    assert L.plan(push, copy.deepcopy(push), {"PET", "HDPE"}) == (None, None, [])


def test_grey_is_never_handed_out():
    push, dest = [], [lab(i, f"L{i}", c) for i, c in enumerate(L.COLOURS[:5])]
    p, d, _ = L.plan(push, dest, {"New"})
    assert next(l for l in d if l["label"] == "New")["color"] not in (L.GREY, *L.COLOURS[:5])


def test_to_input_maps_colour_ints_to_enum_names():
    out = L.to_input([lab(0, "a", 0), lab(1, "b", 19), lab(2, "c", 101), lab(3, "d", 160),
                      {"label": "new", "color": 155, "is_done": False, "is_deactivated": False}])
    assert [o["color"] for o in out] == ["working_orange", "dark_orange", "sunset", "teal", "orchid"]
    assert out[-1]["index"] == 4 and "id" not in out[-1]


class FakeMonday:
    """Two boards, one status column each; `restricted` refuses writes on Design & QA."""
    def __init__(self, push, dest, restricted=False):
        self.boards = {"P": push, "D": dest}
        self.restricted = restricted
        self.writes = []

    def __call__(self, query, variables=None, version=None):
        assert version == L.LABELS_API_VERSION
        if "update_status_column" in query:
            b = variables["b"]
            if b == "D" and self.restricted:
                raise RuntimeError("Monday API error: User unauthorized to perform action")
            back = {n: c for c, n in zip(L.COLOURS, L.ENUM)}
            self.boards[b] = [{"id": l.get("id", 900 + i), "label": l["label"], "color": back[l["color"]],
                               "index": l["index"], "is_done": l["is_done"], "is_deactivated": l["is_deactivated"]}
                              for i, l in enumerate(variables["s"]["labels"])]
            self.writes.append(b)
            return {"update_status_column": {"id": "c"}}
        b = variables["b"][0]
        return {"boards": [{"columns": [{"id": "c", "title": "Sales Rep", "type": "status", "revision": "r",
                                         "settings": {"labels": copy.deepcopy(self.boards[b])}}]}]}


def test_align_end_to_end():
    api = FakeMonday([lab(0, "Kami Butcher", 0), lab(1, "Julianni Pacheco", 1)],
                     [lab(0, "Kami Butcher", 7), lab(1, "N/A", 1)])
    assert L.align(api, "P", "D", {"Sales Rep": {"Kami Butcher", "Julianni Pacheco"}}, log=lambda m: None) == []
    for name in ("Kami Butcher", "Julianni Pacheco"):
        assert moved(name, api.boards["P"], api.boards["D"]) == name
    assert L.align(api, "P", "D", {"Sales Rep": {"Kami Butcher", "Julianni Pacheco"}}, log=lambda m: None) == []
    assert api.writes == ["D", "P"]                                 # second run: nothing to write


def test_align_restricted_dest_falls_back_to_blank_not_wrong():
    api = FakeMonday([lab(0, "Medium", 0), lab(1, "Urgent", 1)],
                     [lab(0, "Medium", 2), lab(1, "Normal", 1)], restricted=True)
    problems = L.align(api, "P", "D", {"Sales Rep": {"Medium", "Urgent"}}, log=lambda m: None)
    assert len(problems) == 1 and not problems[0][0]                # not blocking: arrives blank
    assert problems[0][1].startswith("Sales Rep: Design & QA refused new label(s) 'Urgent'; a move will leave")
    assert moved("Medium", api.boards["P"], api.boards["D"]) == "Medium"
    assert moved("Urgent", api.boards["P"], api.boards["D"]) is None   # blank, not "Normal"
    writes = len(api.writes)
    L.align(api, "P", "D", {"Sales Rep": {"Medium", "Urgent"}}, log=lambda m: None)
    assert len(api.writes) == writes                                # no rewrite on the next run


def test_align_push_board_refused_is_blocking():
    api = FakeMonday([lab(0, "PET", 0)], [lab(0, "PET", 101)])
    real = api.__call__
    def refuse(query, variables=None, version=None):
        if "update_status_column" in query and variables["b"] == "P":
            raise RuntimeError("Monday API error: stale revision")
        return real(query, variables, version)
    problems = L.align(refuse, "P", "D", {"Sales Rep": {"PET"}}, log=lambda m: None)
    assert problems and all(b for b, _ in problems)                 # PET would show wrong: stop


def test_network_error_reading_is_blocking_not_a_crash():
    def down(query, variables=None, version=None):
        raise TimeoutError("timed out")
    assert L.align(down, "P", "D", {"Sales Rep": {"PET"}}, log=lambda m: None)[0][0] is True


def test_deactivated_push_label_is_reactivated():
    push, dest = [lab(0, "A", 1, deactivated=True)], [lab(0, "A", 1)]
    p, d, notes = L.plan(push, dest, {"A"})
    assert p[0]["is_deactivated"] is False and d is None and any("reactivate" in n for n in notes)


def test_duplicate_push_names_only_one_takes_the_colour():
    push = [lab(0, "A", 0), lab(1, "A", 1, deactivated=True)]
    p, _, _ = L.plan(push, [lab(0, "A", 3)], {"A"})
    assert sorted(l["color"] for l in p)[0] != sorted(l["color"] for l in p)[1]   # no duplicate colours
    assert next(l for l in p if not l["is_deactivated"])["color"] == 3


def test_no_free_colour_is_reported_not_raised_as_stopiteration():
    dest = [lab(i, f"L{i}", c) for i, c in enumerate(L.COLOURS)]
    try:
        L.plan([], dest, {"New"})
        assert False, "expected NoFreeColour"
    except L.NoFreeColour:
        pass
    api = FakeMonday([], dest)
    problems = L.align(api, "P", "D", {"Sales Rep": {"New"}}, log=lambda m: None)
    assert problems[0] == (True, "Sales Rep: every one of Monday's 40 colours is already used in this column")
    assert all(b for b, _ in problems)


def test_dry_run_writes_nothing():
    api = FakeMonday([lab(0, "PET", 0)], [lab(0, "PET", 101)])
    seen = []
    assert L.align(api, "P", "D", {"Sales Rep": {"PET"}}, apply=False, log=seen.append) == []
    assert api.writes == [] and "dry run" in seen[0]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
