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
    assert all(l["target"] == "" for l in s["lines"])        # chosen per line from Plex history (app.line_options)
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


def _app(monkeypatch, env="test"):
    import importlib
    monkeypatch.setenv("PLEX_ENV", env)
    import app as picking_app
    return importlib.reload(picking_app)


def test_cache_reuses_until_ttl(monkeypatch):
    a = _app(monkeypatch)
    calls = []
    f = lambda: calls.append(1) or len(calls)
    assert a.cached("k", 60, f)[0] == 1 and a.cached("k", 60, f)[0] == 1 and len(calls) == 1
    assert a.cached("k", 60, f, refresh=True)[0] == 2
    assert a.cached("k2", 0, f)[0] == 3 and a.cached("k2", 0, f)[0] == 4


def _fake_plex(a, monkeypatch, state, lp=None, status=None):
    lp, status = lp or {}, status or {}
    reads, moves = [], []

    def containers_for_part(pid):
        reads.append(pid)
        return [{"serialNo": s, "location": loc, "quantity": 5, "containerStatus": status.get(s, "OK"),
                 "masterUnitNo": lp.get(s), "lotNo": "L"} for s, loc in state.items()]

    def move_detail(item, target):
        moves.append(item)
        for s in ([k for k, v in lp.items() if v == item] or [item]):
            state[s] = target
        return {"ok": True, "message": f"{item} moved", "request": {"SerialNo": item, "Location": target},
                "status": 200, "body": '{"Success":true}', "ms": 12}

    monkeypatch.setattr(a.api, "containers_for_part", containers_for_part)
    monkeypatch.setattr(a.api, "container", lambda s: None)
    monkeypatch.setattr(a.web, "move_detail", move_detail)
    monkeypatch.setattr(a, "destinations", lambda: [])
    monkeypatch.setattr(a, "location_groups", lambda: {})
    monkeypatch.setattr(a, "_line_for", lambda *x: None)        # no line: the Staging locations are the allowed targets
    return reads, moves


def _rows(path):
    return [__import__("json").loads(l) for l in path.read_text().splitlines()]


def test_review_then_approve_moves_full_pallet_as_lp_and_logs_everything(monkeypatch, tmp_path):
    a = _app(monkeypatch)
    monkeypatch.setattr(a, "LOG", tmp_path / "log.jsonl")
    state = {"A": "103", "B": "103", "C": "104", "H": "105"}
    reads, moves = _fake_plex(a, monkeypatch, state, lp={"A": "LP-1", "B": "LP-1"}, status={"H": "Hold"})
    c = a.app.test_client()
    form = {"set_no": "", "job_no": "1", "part_id": "P", "target": "Pre-Weigh Staging", "serial": ["A", "B", "C", "H"]}
    pv = c.post("/move/preview", data=form).get_json()
    assert pv["ok"] and moves == []                                    # the review sends nothing to Plex
    assert [(i["send"], i["pallet"]) for i in pv["items"]] == [("LP-1", "LP-1"), ("C", None), (None, None)]
    assert pv["items"][2]["why"] and pv["containers_moving"] == 3
    assert {r["event"] for r in _rows(tmp_path / "log.jsonl")} == {"preview"}
    r = c.post("/move", data={"plan_id": pv["plan_id"], "set_no": ""})
    assert r.status_code == 302 and moves == ["LP-1", "C"]            # pallet as one call, Hold never sent
    assert reads == ["P", "P", "P"]                                    # review read, approve read, verify read
    rows = [x for x in _rows(tmp_path / "log.jsonl") if x["event"] in ("move", "refused")]
    assert {x["serial"]: x["ok"] for x in rows} == {"A": True, "B": True, "C": True, "H": False}
    a_row = next(x for x in rows if x["serial"] == "A")
    assert a_row["moved_as"] == "LP-1" and a_row["batch_id"] == pv["plan_id"] and a_row["lp_before"] == "LP-1"
    assert '"location":"103"' in a_row["before_json"] and "Pre-Weigh Staging" in a_row["after_json"]
    assert a_row["plex_status"] == 200 and "SerialNo" in a_row["plex_request"] and a_row["plex_response"]
    assert c.post("/move", data={"plan_id": pv["plan_id"]}).status_code == 302 and moves == ["LP-1", "C"]   # a review is used once


def test_approve_skips_a_container_that_changed_since_the_review(monkeypatch, tmp_path):
    a = _app(monkeypatch)
    monkeypatch.setattr(a, "LOG", tmp_path / "log.jsonl")
    state = {"A": "103", "B": "104"}
    _, moves = _fake_plex(a, monkeypatch, state)
    c = a.app.test_client()
    pv = c.post("/move/preview", data={"part_id": "P", "target": "Pre-Weigh Staging", "serial": ["A", "B"]}).get_json()
    state["B"] = "106"                                                 # someone moved B on the floor meanwhile
    c.post("/move", data={"plan_id": pv["plan_id"]})
    assert moves == ["A"]
    b = next(x for x in _rows(tmp_path / "log.jsonl") if x["serial"] == "B" and x["event"] == "refused")
    assert "changed since you reviewed it" in b["message"]


def test_cancel_logs_and_bad_target_or_prod_is_refused(monkeypatch, tmp_path):
    a = _app(monkeypatch)
    monkeypatch.setattr(a, "LOG", tmp_path / "log.jsonl")
    _, moves = _fake_plex(a, monkeypatch, {"A": "103"})
    c = a.app.test_client()
    pv = c.post("/move/preview", data={"part_id": "P", "target": "Pre-Weigh Staging", "serial": ["A"]}).get_json()
    c.post("/move/cancel", data={"plan_id": pv["plan_id"]})
    assert "cancelled" in {x["event"] for x in _rows(tmp_path / "log.jsonl")}
    assert c.post("/move", data={"plan_id": pv["plan_id"]}).status_code == 302 and moves == []
    assert c.post("/move/preview", data={"part_id": "P", "target": "Ship", "serial": ["A"]}).status_code == 400


def test_destination_options_from_history():
    rows = [{"Workcenter_Code": "Pre-Weigh 1", "Workcenter_Group": "Pre-Weigh", "Location": "PW - B9", "Containers": "703"},
            {"Workcenter_Code": "Pre-Weigh 1", "Workcenter_Group": "Pre-Weigh", "Location": "PW - B10", "Containers": "313"},
            {"Workcenter_Code": "Pre-Weigh 2", "Workcenter_Group": "Pre-Weigh", "Location": "PW - B7", "Containers": "551"},
            {"Workcenter_Code": "Pre-Weigh 2", "Workcenter_Group": "Pre-Weigh", "Location": "102-04B-03", "Containers": "300"},
            {"Workcenter_Code": "Pre-Weigh 2", "Workcenter_Group": "Pre-Weigh", "Location": "PW - A9", "Containers": "1"}]
    groups = {"102-04B-03": "Warehouse"}
    by_group = picking.destination_options(rows, "SCHED - Pre-weigh", "Pre-Weigh", groups)
    assert [o["location"] for o in by_group][:3] == ["PW - B9", "PW - B7", "PW - B10"]        # group, most used first
    assert "102-04B-03" not in [o["location"] for o in by_group]                               # putaway rack dropped
    assert "PW - A9" not in [o["location"] for o in by_group]                                  # under 1%
    assert by_group[-1]["location"] == "Quality Released Staging" and by_group[-1]["uses"] == 0
    own = picking.destination_options(rows, "Pre-Weigh 1", "Pre-Weigh", groups)
    assert own[0] == {"location": "PW - B9", "uses": 703, "basis": "Pre-Weigh 1"}


def test_plan_restore_puts_back_pallets_and_containers_and_skips_moved_again():
    import restore_moves as rm
    rows = [{"serial": "A", "moved_as": "LP-1", "from_location": "103", "to_location": "PW - B9", "ok": True},
            {"serial": "B", "moved_as": "LP-1", "from_location": "103", "to_location": "PW - B9", "ok": True},
            {"serial": "C", "moved_as": "C", "from_location": "104", "to_location": "PW - B9", "ok": True, "left_pallet": "LP-2"},
            {"serial": "D", "moved_as": "D", "from_location": "105", "to_location": "PW - B9", "ok": True},
            {"serial": "E", "moved_as": "E", "from_location": "106", "to_location": "PW - B9", "ok": True}]
    live = {"A": {"location": "PW - B9", "masterUnitNo": "LP-1"}, "B": {"location": "PW - B9", "masterUnitNo": "LP-1"},
            "C": {"location": "PW - B9"}, "D": {"location": "Pre-Weigh 1"}, "E": {"location": "106"}}
    acts = {tuple(x["serials"]): x for x in rm.plan_restore(rows, live)}
    assert acts[("A", "B")]["kind"] == "pallet" and acts[("A", "B")]["send"] == "LP-1" and acts[("A", "B")]["to"] == "103"
    assert acts[("C",)]["kind"] == "container" and "LP-2" in acts[("C",)]["note"]
    assert acts[("D",)]["kind"] == "skip" and "moved again" in acts[("D",)]["why"]
    assert acts[("E",)]["kind"] == "done"


def test_saved_session_file_round_trip(tmp_path, monkeypatch):
    import plex_web
    monkeypatch.setenv("PICKING_SESSION_GCS", "")
    w = plex_web.PlexWeb("test")
    w.store = str(tmp_path / "s.json")
    w._store_write({"host": w.host, "at": 1, "ua": "x", "cookies": []})
    assert w._store_read()["host"] == "https://vox.test.on.plex.com"
    w2 = plex_web.PlexWeb("prod")
    w2.store = w.store
    assert w2._try_saved() is False                   # a TEST session is never used for prod


def test_set_page_opens_with_loaders_and_each_line_fills_in_live(monkeypatch):
    a = _app(monkeypatch)
    s = picking.build_sets(SET_832)["832"]
    monkeypatch.setattr(a, "_find_set", lambda set_no, days: (s, 0) if set_no == "832" else (None, 0))
    monkeypatch.setattr(a, "location_groups", lambda: {"103": "Warehouse"})
    monkeypatch.setattr(a, "destinations", lambda: [])
    reads = []
    monkeypatch.setattr(a.api, "containers_for_part", lambda pid: reads.append(pid) or
                        [{"serialNo": "S1", "location": "103", "quantity": 50, "containerStatus": "OK", "lotId": "L1"}])
    monkeypatch.setattr(a.api, "lots_for_part", lambda pid: [{"id": "L1", "bestByDateTime": "2027-01-01T00:00:00Z"}])
    client = a.app.test_client()
    page = client.get("/set/832").get_data(as_text=True)
    assert reads == []                                         # opens without waiting for Plex
    assert page.count('class="card line-loading"') == len(s["lines"]) and "/set/832/line/p12761" in page
    frag = client.get("/set/832/line/p12761?days=3").get_data(as_text=True)
    assert reads == ["p12761"] and "S1" in frag and 'id="line-p12761"' in frag and "Review move" in frag
    assert client.get("/set/832/line/nope").status_code == 404
    full = client.get("/set/832?all=1").get_data(as_text=True)  # the old one-go page still works
    assert "line-loading" not in full and full.count("<td>S1</td>") == len(s["lines"])


def test_move_log_query_quotes_reserved_at_and_favicon_is_quiet(monkeypatch):
    a = _app(monkeypatch)
    assert "ORDER BY `at`" in a.LOG_SQL                 # unquoted `at` failed in BigQuery (live audit 11-23)
    assert a.app.test_client().get("/favicon.ico").status_code == 204


def test_api_calls_are_capped_however_many_pages_load(monkeypatch):
    import threading
    import plex_api
    live, peak, lock = [0], [0], threading.Lock()

    class R:
        status_code, content = 200, b"[]"
        def json(self): return []
        def raise_for_status(self): return None

    def fake_get(url, timeout):
        with lock:
            live[0] += 1; peak[0] = max(peak[0], live[0])
        __import__("time").sleep(0.02)
        with lock:
            live[0] -= 1
        return R()

    api = plex_api.PlexApi("test")
    api._key = ("k", "s")
    api._session().get = fake_get
    monkeypatch.setattr(plex_api, "_PARALLEL", threading.BoundedSemaphore(4))
    ts = [threading.Thread(target=api.containers_for_part, args=(str(i),)) for i in range(30)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert 1 <= peak[0] <= 4
