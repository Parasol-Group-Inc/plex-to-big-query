"""Audit repros (fakes only, no network)."""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path("/Users/parasol/ptbq-picking")
sys.path.insert(0, str(ROOT / "deploy" / "picking_app"))
sys.path.insert(0, str(ROOT / "tests"))
import test_picking_app as T  # noqa: E402


def _rows(p):
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


def test_undo_sends_whole_lp_even_when_a_member_failed_its_check(monkeypatch, tmp_path):
    a = T._app(monkeypatch)
    monkeypatch.setattr(a, "LOG", tmp_path / "log.jsonl")
    at = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=3)).isoformat()
    after = lambda q: {"location": "PW - B9", "quantity": q, "containerStatus": "OK", "masterUnitNo": "LP-1"}
    rows = [T._mv("A", at, batch="bx", moved_as="LP-1", after=after(5)),
            T._mv("B", at, batch="bx", moved_as="LP-1", after=after(5))]
    monkeypatch.setattr(a, "load_log_rows", lambda limit=2000: rows)
    # B was partly consumed on the floor (qty 5 -> 2) but is still on LP-1 at the target
    state = {"A": {**after(5), "serialNo": "A"}, "B": {**after(2), "serialNo": "B"}}
    moves = []
    monkeypatch.setattr(a.api, "container", lambda s: dict(state[s]))
    monkeypatch.setattr(a.web, "sql", lambda q: [])
    def move_detail(item, to):
        moves.append((item, to))
        for s, c in state.items():
            if c.get("masterUnitNo") == item or s == item:
                c["location"] = to
        return {"ok": True, "message": "moved", "request": {}, "status": 200, "body": "{}", "ms": 5}
    monkeypatch.setattr(a.web, "move_detail", move_detail)
    c = a.app.test_client()
    rv = c.post("/log/undo/review", data={"batch_id": "bx"}).get_json()
    assert {x["serial"]: x["ok"] for x in rv["checks"]} == {"A": True, "B": False}
    c.post("/log/undo", data={"plan_id": rv["plan_id"]})
    print("moves:", moves, "B now at:", state["B"]["location"])
    restore_rows = [e["serial"] for e in _rows(tmp_path / "log.jsonl") if e["event"] == "restore"]
    print("restore rows logged:", restore_rows)
    assert moves == [("LP-1", "103")] and state["B"]["location"] == "103"   # BUG: B went back too, unlogged


def test_approve_moves_lp_that_gained_a_container_after_review(monkeypatch, tmp_path):
    a = T._app(monkeypatch)
    monkeypatch.setattr(a, "LOG", tmp_path / "log.jsonl")
    state = {"A": "103", "B": "103"}
    lp = {"A": "LP-1", "B": "LP-1"}
    _, moves = T._fake_plex(a, monkeypatch, state, lp=lp)
    c = a.app.test_client()
    pv = c.post("/move/preview", data={"part_id": "P", "target": "Pre-Weigh Staging", "serial": ["A", "B"]}).get_json()
    assert pv["items"][0]["send"] == "LP-1" and pv["containers_moving"] == 2
    state["Z"], lp["Z"] = "103", "LP-1"          # someone adds Z (same part) to LP-1 before Approve
    c.post("/move", data={"plan_id": pv["plan_id"]})
    print("moves:", moves, "Z now at:", state["Z"])
    assert moves == ["LP-1"] and state["Z"] == "Pre-Weigh Staging"   # BUG: Z moved, never reviewed
    assert "Z" not in {r["serial"] for r in _rows(tmp_path / "log.jsonl") if r["event"] == "move"}


def test_split_pallet_after_a_member_fails_has_no_left_pallet_warning(monkeypatch, tmp_path):
    a = T._app(monkeypatch)
    monkeypatch.setattr(a, "LOG", tmp_path / "log.jsonl")
    state = {"A": "103", "B": "103"}
    _, moves = T._fake_plex(a, monkeypatch, state, lp={"A": "LP-1", "B": "LP-1"}, status={"B": "Hold"})
    c = a.app.test_client()
    pv = c.post("/move/preview", data={"part_id": "P", "target": "Pre-Weigh Staging", "serial": ["A", "B"]}).get_json()
    items = [(i["send"], i["left_pallet"]) for i in pv["items"]]
    print("items:", items)
    assert items == [("A", None), (None, None)]      # BUG: A leaves LP-1 but left_pallet is None (no warning)


def test_exception_after_plex_moves_leaves_no_log(monkeypatch, tmp_path):
    a = T._app(monkeypatch)
    monkeypatch.setattr(a, "LOG", tmp_path / "log.jsonl")
    state = {"A": "103"}
    reads, moves = T._fake_plex(a, monkeypatch, state)
    c = a.app.test_client()
    pv = c.post("/move/preview", data={"part_id": "P", "target": "Pre-Weigh Staging", "serial": ["A"]}).get_json()
    orig = a.api.containers_for_part
    def flaky(pid):
        if moves:                                      # the verify read fails (Plex API 5xx after retries)
            raise RuntimeError("HTTP 503 from Plex API")
        return orig(pid)
    monkeypatch.setattr(a.api, "containers_for_part", flaky)
    a.app.config["PROPAGATE_EXCEPTIONS"] = False
    r = c.post("/move", data={"plan_id": pv["plan_id"]})
    events = [e["event"] for e in _rows(tmp_path / "log.jsonl")]
    print("status:", r.status_code, "moves:", moves, "events:", events)
    assert moves == ["A"] and "move" not in events     # BUG: moved in Plex, nothing logged


def test_reflected_xss_in_line_404(monkeypatch):
    a = T._app(monkeypatch)
    monkeypatch.setattr(a, "_find_set", lambda set_no, days: (None, None))
    r = a.app.test_client().get("/set/%3Cimg%20src=x%20onerror=alert(1)%3E/line/x")
    body = r.get_data(as_text=True)
    print(r.status_code, r.content_type, body)
    assert "<img src=x onerror=alert(1)>" in body and r.content_type.startswith("text/html")
