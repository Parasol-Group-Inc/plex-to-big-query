"""Tests for label_design_service/fill.py: write a label field into a pushed
item only when the item was created without it, and only into an EMPTY cell
(2026-10-28).

    python tests/test_label_fill.py            # plain asserts, prints OK
    python -m pytest tests/test_label_fill.py  # same tests under pytest

No Monday or BigQuery needed. `FakeApi` answers the item read and records writes.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "label_design_service"))

import fill as F  # noqa: E402


def row(lcr, **f):
    return {"_lcr": lcr, "dedupe_key": f"k{lcr}", **f}


def test_plan_skips_unpushed_and_rows_with_nothing():
    rows = [row("a", label_part_no="73066-10KAYAN-0", part_label_size="2x3"),
            row("b", label_part_no="73001-X"),
            row("c")]
    out = F.plan(rows, {"a": "1", "c": "3"}, {})
    assert [(r["_lcr"], i, w) for r, i, w in out] == [
        ("a", "1", {"Label Part #": ("text", "73066-10KAYAN-0"), "Label Size": ("text", "2x3")})]


def test_plan_skips_settled_and_blank():
    rows = [row("a", label_part_no="73066-10KAYAN-0", part_allergen="  ", part_printing_material="Paper")]
    out = F.plan(rows, {"a": "1"}, {"a": {"Label Part #"}})
    assert out[0][2] == {"Printing Material": ("status", {"label": "Paper"})}


class FakeApi:
    def __init__(self, items):
        self.items, self.writes = items, []

    def __call__(self, q, v=None, **_):
        if q.lstrip().startswith("query"):
            return {"items": [self.items[i] for i in v["i"] if i in self.items]}
        self.writes.append((v["b"], v["i"], json.loads(v["v"])))
        return {"change_multiple_column_values": {"id": v["i"]}}


def cell(cid, title, ctype, text=""):
    return {"id": cid, "text": text, "type": ctype, "column": {"title": title}}


def test_fill_writes_only_empty_cells_on_the_items_board():
    api = FakeApi({"1": {"id": "1", "state": "active", "board": {"id": "DQA"},
                         "column_values": [cell("t1", "Label Part #", "text"),
                                           cell("t2", "Label Size", "text", "typed by team"),
                                           cell("s1", "Printing Material", "status")]},
                   "2": {"id": "2", "state": "archived", "board": {"id": "DQA"}, "column_values": []}})
    cands = [(row("a"), "1", {"Label Part #": ("text", "73066-10KAYAN-0"), "Label Size": ("text", "2x3"),
                              "Printing Material": ("status", {"label": "BOPP"})}),
             (row("b"), "2", {"Label Part #": ("text", "73001-X")})]
    asked = []
    res = F.fill(api, cands, lambda needed: asked.append(needed) or True, log=lambda *_: None)
    # one mutation per cell (2026-11-11), so a refused column cannot sink the rest
    assert api.writes == [("DQA", "1", {"t1": "73066-10KAYAN-0"}), ("DQA", "1", {"s1": {"label": "BOPP"}})]
    assert asked == [{"Printing Material": {"BOPP"}}]
    assert len(res) == 1 and res[0]["already_set"] == ["Label Size"]
    assert res[0]["written"] == {"Label Part #": "73066-10KAYAN-0", "Printing Material": {"label": "BOPP"}}


def test_fill_drops_status_when_colours_unsafe_and_dry_run_writes_nothing():
    item = {"id": "1", "state": "active", "board": {"id": "P"},
            "column_values": [cell("t1", "Label Part #", "text"), cell("s1", "Printing Material", "status")]}
    cands = [(row("a"), "1", {"Label Part #": ("text", "73X"), "Printing Material": ("status", {"label": "BOPP"})})]
    api = FakeApi({"1": item})
    res = F.fill(api, cands, lambda needed: False, log=lambda *_: None)
    assert api.writes == [("P", "1", {"t1": "73X"})]
    assert any("Printing Material" in e for e in res[0]["errors"])
    api = FakeApi({"1": item})
    F.fill(api, cands, lambda needed: True, apply=False, log=lambda *_: None)
    assert api.writes == []



# ── Screens + ODBC (2026-11-11) ───────────────────────────────────────────────

def test_screen_fields_only_on_items_created_from_the_screens():
    rows = [row("a", bdm="Tyler Hall", customer_email="x@y.com", data_source="odbc"),
            row("b", bdm="Tyler Hall", customer_email="x@y.com", data_source="odbc")]
    out = {r["_lcr"]: w for r, _, w in F.plan(rows, {"a": "1", "b": "2"}, {}, from_screens={"a"})}
    assert out["a"]["Sales Rep"] == ("status", {"label": "Tyler Hall"})
    assert out["a"]["Email"] == ("email", {"email": "x@y.com", "text": "x@y.com"})
    assert out["a"]["Data Source"][1] is F.CONFIRM
    assert "b" not in out   # created from ODBC: a cell the team cleared stays cleared


def test_data_source_confirmed_only_after_odbc_has_the_line():
    out = F.plan([row("a", data_source="live")], {"a": "1"}, {}, from_screens={"a"})
    assert out == []
    out = F.plan([row("a", data_source="odbc")], {"a": "1"}, {"a": {"Data Source"}}, from_screens={"a"})
    assert out == []


def test_data_source_overwritten_only_while_it_holds_the_screens_text():
    item = lambda text: {"id": "1", "state": "active", "board": {"id": "P"},
                         "column_values": [cell("d1", "Data Source", "text", text)]}
    cands = [(row("a"), "1", {"Data Source": ("text", F.CONFIRM)})]
    api = FakeApi({"1": item("Plex screens, read 11-11 09:20 MT")})
    res = F.fill(api, cands, lambda n: True, log=lambda *_: None, now_label="11-11 11:05 MT")
    assert api.writes == [("P", "1", {"d1": "Plex screens, read 11-11 09:20 MT; confirmed by ODBC 11-11 11:05 MT"})]
    for text in ("typed by the team", "Plex screens, read 11-11 09:20 MT; confirmed by ODBC 11-11 10:00 MT"):
        api = FakeApi({"1": item(text)})
        res = F.fill(api, cands, lambda n: True, log=lambda *_: None, now_label="x")
        assert api.writes == [] and res[0]["already_set"] == ["Data Source"]


def test_a_refused_column_is_denied_and_the_rest_still_written():
    class Refuses(FakeApi):
        def __call__(self, q, v=None, **_):
            if not q.lstrip().startswith("query") and "p1" in v["v"]:
                raise RuntimeError("UserUnauthorizedException: 403")
            return super().__call__(q, v)
    api = Refuses({"1": {"id": "1", "state": "active", "board": {"id": "DQA"},
                         "column_values": [cell("p1", "Priority", "status"), cell("e1", "Phone Number", "text")]}})
    cands = [(row("a"), "1", {"Priority": ("status", {"label": "High"}), "Phone Number": ("text", "555")})]
    res = F.fill(api, cands, lambda n: True, log=lambda *_: None)
    assert res[0]["denied"] == ["Priority"] and res[0]["written"] == {"Phone Number": "555"} and not res[0]["errors"]

if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
