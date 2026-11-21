"""Picking & staging app: pick lines, container suggestions, move answers (no Plex calls)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy" / "picking_app"))
import picking  # noqa: E402
from plex_web import parse_move  # noqa: E402


def row(job, part, pid, group, qty, comp, cid, ctype, bom, status="Scheduled"):
    return {"Job_Set_No": "832", "Set_Due": "2026-11-24", "Job_No": job, "Job_Id": "j" + job, "Job_Status": status,
            "Job_Due": "2026-11-18", "Job_Qty": str(qty), "Part_No": part, "Part_Id": pid, "Workcenter_Code": "WC",
            "Workcenter_Group": group, "Op_No": "10", "Component_Part_No": comp, "Component_Part_Id": cid,
            "Component_Type": ctype, "Bom_Qty": str(bom)}


# Set 832 on 2026-11-20 (cut down): one blend job using two weighed WIP parts, two Pre-Weigh jobs.
SET_832 = [
    row("4553", "23325-00REDRO-0", "blend", "Blending", 904, "12160-01VOXNU-1", "p12160", "WIP", 0.0078),
    row("4553", "23325-00REDRO-0", "blend", "Blending", 904, "12761-01VOXNU-1", "p12761", "WIP", 0.0973),
    row("4554", "12761-01VOXNU-1", "p12761", "Pre-Weigh", 87.959, "12761-01VOXNU-1", "p12761", "Raw Materials", 1.0),
    row("4560", "12160-01VOXNU-1", "p12160", "Pre-Weigh", 7.051, "12160-01VOXNU-1", "p12160", "Raw Materials", 1.0),
]


def test_pick_lines_are_the_pre_weigh_raw_materials_not_the_blend_wip():
    s = picking.build_sets(SET_832)["832"]
    assert [(l["job_no"], l["part_no"], l["required"]) for l in s["lines"]] == [
        ("4554", "12761-01VOXNU-1", 87.959), ("4560", "12160-01VOXNU-1", 7.051)]
    assert all(l["target"] == "Pre-Weigh Staging" for l in s["lines"])
    assert s["main"]["job_no"] == "4553" and s["open_jobs"] == 3


def test_closed_jobs_have_no_pick_lines():
    rows = [dict(r, Job_Status="Completed") if r["Job_No"] == "4554" else r for r in SET_832]
    assert [l["job_no"] for l in picking.build_sets(rows)["832"]["lines"]] == ["4560"]


def c(serial, loc, qty, status="OK", lot="L1", added="2026-11-01T00:00:00Z", lp=None):
    return {"serialNo": serial, "location": loc, "quantity": qty, "containerStatus": status, "lotId": lot,
            "lotNo": lot, "addDateTime": added, "masterUnitNo": lp}


def test_suggest_first_expiring_lot_first_and_counts_staged():
    lots = [{"id": "OLD", "bestByDateTime": "2027-01-01T00:00:00Z"}, {"id": "NEW", "bestByDateTime": "2028-01-01T00:00:00Z"}]
    cs = [c("A", "103-01", 50, lot="NEW"), c("B", "103-02", 50, lot="OLD"), c("C", "Pre-Weigh Staging", 30, lot="NEW"),
          c("D", "103-03", 99, status="Hold", lot="OLD"), c("E", "Labeling Staging", 40, lot="OLD"), c("F", "103-04", 0)]
    out = picking.suggest(cs, lots, 70, "Pre-Weigh Staging")
    roles = {r["serial"]: r["role"] for r in out["rows"]}
    assert roles == {"C": "staged", "B": "pick", "A": "spare", "D": "blocked", "E": "elsewhere-staged"}
    assert out["staged_qty"] == 30 and out["picked_qty"] == 50 and out["short_qty"] == 0


def test_suggest_reports_shortage():
    out = picking.suggest([c("A", "103-01", 10)], [], 25, "Pre-Weigh Staging")
    assert out["picked_qty"] == 10 and out["short_qty"] == 15


def test_check_movable():
    assert picking.check_movable(None, "X")
    assert "Hold" in picking.check_movable(c("A", "103", 5, status="Hold"), "X")
    assert "already" in picking.check_movable(c("A", "X", 5), "X")
    assert picking.check_movable(c("A", "103", 5), "X") is None


def test_parse_move_answers_seen_in_test():
    ok = {"ValidationResult": {"ValidationErrors": [], "CollectionValidationResults": [], "Success": True,
                               "Message": "Container 84F47G-0003 was successfully moved."}}
    bad = {"ValidationResult": {"ValidationErrors": [], "CollectionValidationResults": [], "Success": False,
                                "Message": "The selected location was not found."}}
    lp = {"ValidationResult": {"ValidationErrors": [], "Success": True, "Message": None, "CollectionValidationResults": [
        {"ValidationErrors": [], "CollectionValidationResults": [], "Success": True,
         "Message": "4 Containers of LP-087265 were moved to Pre-Weigh Staging."}]}}
    assert parse_move(ok) == (True, "Container 84F47G-0003 was successfully moved.")
    assert parse_move(bad) == (False, "The selected location was not found.")
    assert parse_move(lp) == (True, "4 Containers of LP-087265 were moved to Pre-Weigh Staging.")


def test_sql_window_is_an_integer():
    q = picking.job_sets_sql("3", "14")
    assert "DATEADD(day, 3, GETDATE())" in q and "DATEADD(day, -14," in q


def test_suggest_skips_retains_and_do_not_use_locations():
    groups = {"103-01": "Warehouse", "R5-3": "Retains", "z**DO NOT USE**": "Warehouse"}
    cs = [c("S", "R5-3", 0.05, lot="OLD"), c("Z", "z**DO NOT USE**", 0.3, lot="OLD"), c("W", "103-01", 5, lot="NEW")]
    lots = [{"id": "OLD", "bestByDateTime": "2027-01-01"}, {"id": "NEW", "bestByDateTime": "2028-01-01"}]
    roles = {r["serial"]: (r["role"], r.get("why")) for r in picking.suggest(cs, lots, 1, "Pre-Weigh Staging", loc_group=groups)["rows"]}
    assert roles["W"][0] == "pick"
    assert roles["S"] == ("not-here", "location group Retains")
    assert roles["Z"] == ("not-here", "location marked DO NOT USE")
    assert picking.pickable_from("R and D", {"R and D": "Warehouse"}) == "excluded location (samples)"


def test_prod_moves_are_off_unless_allowed(monkeypatch):
    import importlib
    monkeypatch.setenv("PLEX_ENV", "prod")
    monkeypatch.delenv("PICKING_ALLOW_PROD_MOVES", raising=False)
    import app as picking_app
    picking_app = importlib.reload(picking_app)
    calls = []
    monkeypatch.setattr(picking_app.web, "move", lambda *a: calls.append(a) or (True, "moved"))
    monkeypatch.setattr(picking_app.api, "container", lambda s: calls.append(s) or None)
    r = picking_app.app.test_client().post("/move", data={"set_no": "1", "target": "Pre-Weigh Staging", "serial": ["A"]})
    assert r.status_code == 302 and calls == []      # refused before any Plex call
    monkeypatch.setenv("PLEX_ENV", "test")
    importlib.reload(picking_app)


def test_whole_pallet_moves_as_lp_partial_pallet_moves_alone():
    cs = [c("A", "103", 25, lp="LP-1"), c("B", "103", 25, lp="LP-1"), c("C", "104", 25, lp="LP-2"),
          c("D", "104", 25, lp="LP-2"), c("E", "105", 25)]
    assert picking.plan_moves(["A", "B", "C", "E"], cs) == [("LP-1", ["A", "B"]), ("C", ["C"]), ("E", ["E"])]
    assert picking.breaks_pallet("C", ["A", "B", "C", "E"], cs) == "LP-2"
    assert picking.breaks_pallet("A", ["A", "B"], cs) is None
    assert picking.breaks_pallet("E", ["E"], cs) is None
