"""Tests for the ETL dispatcher's planning (deploy/etl_dispatcher/main.py).

Pure functions only: which schedule slots are due, which failed runs get their
one follow-up, and what a Cloud Run execution's status means. No BigQuery or
Cloud Run needed.

    python tests/test_dispatcher.py
"""
import datetime as dt
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "etl_dispatcher", Path(__file__).resolve().parent.parent / "deploy" / "etl_dispatcher" / "main.py")
d = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d)

UTC = dt.timezone.utc


def mt(y, mo, day, h, mi):
    """A Mountain wall-clock time, as UTC."""
    return dt.datetime(y, mo, day, h, mi, tzinfo=d.TZ).astimezone(UTC)


ROW = {"job_name": "plex-etl-sales-orders", "run_time": "13:00", "mode": "probe", "enabled": True}


def test_slot_respects_daylight_saving():
    # 13:00 Mountain is 19:00 UTC in October (MDT) and 20:00 UTC in December (MST).
    assert d.slot_for("13:00", dt.date(2026, 10, 19)) == dt.datetime(2026, 10, 19, 19, 0, tzinfo=UTC)
    assert d.slot_for("13:00", dt.date(2026, 12, 1)) == dt.datetime(2026, 12, 1, 20, 0, tzinfo=UTC)


def test_due_only_inside_window():
    slot = mt(2026, 10, 19, 13, 0)
    assert d.due_slots([ROW], slot - dt.timedelta(minutes=1), set(), set()) == []
    due = d.due_slots([ROW], slot + dt.timedelta(minutes=3), set(), set())
    assert len(due) == 1 and due[0]["action"] == "dispatch" and due[0]["scheduled_for"] == slot
    assert d.due_slots([ROW], slot + dt.timedelta(minutes=31), set(), set()) == []


def test_slot_is_dispatched_once():
    slot = mt(2026, 10, 19, 13, 0)
    now = slot + dt.timedelta(minutes=5)
    assert d.due_slots([ROW], now, {(ROW["job_name"], slot)}, set()) == []
    # The same slot listed twice in the table still dispatches once.
    assert len(d.due_slots([ROW, dict(ROW)], now, set(), set())) == 1


def test_busy_job_is_skipped_not_doubled():
    now = mt(2026, 10, 19, 13, 2)
    due = d.due_slots([ROW], now, set(), {ROW["job_name"]})
    assert due[0]["action"] == "skipped-busy"


def test_late_evening_slot_still_due_after_midnight():
    late = dict(ROW, run_time="23:55")
    due = d.due_slots([late], mt(2026, 10, 20, 0, 10), set(), set())
    assert len(due) == 1 and due[0]["scheduled_for"] == mt(2026, 10, 19, 23, 55)


def test_disabled_and_invalid_rows():
    now = mt(2026, 10, 19, 13, 2)
    assert d.due_slots([dict(ROW, enabled=False)], now, set(), set()) == []
    bad_time = d.due_slots([dict(ROW, run_time="1pm")], now, set(), set())
    assert bad_time[0]["action"] == "invalid"
    bad_mode = d.due_slots([dict(ROW, mode="sometimes")], now, set(), set())
    assert bad_mode[0]["action"] == "invalid"


def test_run_time_validation():
    assert d.parse_run_time("04:00") == (4, 0)
    for bad in ("24:00", "13:60", "13", "x:y"):
        try:
            d.parse_run_time(bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def log_row(**kw):
    base = {"dispatch_id": "a1", "job_name": "plex-etl-sales-orders", "reason": "schedule",
            "outcome": "failed", "finished_at": mt(2026, 10, 19, 13, 10), "followup_of": None}
    base.update(kw)
    return base


def test_one_followup_after_fifteen_minutes():
    row = log_row()
    assert d.followups_due([row], mt(2026, 10, 19, 13, 20)) == []        # only 10 min
    assert d.followups_due([row], mt(2026, 10, 19, 13, 25)) == [row]     # 15 min
    sent = log_row(dispatch_id="b2", reason="follow-up", outcome=None, followup_of="a1")
    assert d.followups_due([row, sent], mt(2026, 10, 19, 13, 40)) == []  # already sent


def test_followups_never_chain_and_skip_clean_runs():
    now = mt(2026, 10, 19, 14, 0)
    assert d.followups_due([log_row(reason="follow-up")], now) == []
    for ok in ("success", "skipped", "skipped-busy", None):
        assert d.followups_due([log_row(outcome=ok)], now) == []
    assert d.followups_due([log_row(outcome="partial")], now)
    assert d.followups_due([log_row(outcome="lost")], now)
    assert d.followups_due([log_row()], mt(2026, 10, 20, 13, 10)) == []  # beyond the 6 h horizon


def test_reconcile_from_execution_status():
    row = {"dispatched_at": mt(2026, 10, 19, 13, 0)}
    now = mt(2026, 10, 19, 13, 30)
    done = "2026-10-19T19:10:00Z"   # 13:10 Mountain
    assert d.reconcile(row, {"completionTime": done, "failedCount": 1}, now)[0] == "failed"
    assert d.reconcile(row, {"completionTime": done, "succeededCount": 1}, now)[0] == "succeeded-unrecorded"
    # Just finished: give the job's own outcome write a few minutes.
    assert d.reconcile(row, {"completionTime": done, "succeededCount": 1}, mt(2026, 10, 19, 13, 12)) is None
    assert d.reconcile(row, {"runningCount": 1}, now) is None
    # Cancelled by hand: completes with failedCount 0 — still not a success.
    assert d.reconcile(row, {"completionTime": done, "cancelledCount": 1, "taskCount": 1}, now)[0] == "failed"
    assert d.reconcile(row, None, mt(2026, 10, 19, 15, 1))[0] == "lost"


def test_run_body_carries_mode_and_dispatch_table():
    env = {e["name"]: e["value"] for e in d.run_body("full", "abc")["overrides"]["containerOverrides"][0]["env"]}
    assert env == {"RUN_MODE": "full", "DISPATCH_ID": "abc", "DISPATCH_LOG_TABLE": "PlexOps.etl_dispatch_log"}
    batch = {"role": "last", "batch_id": "full-0400-2026-10-21", "batch_kind": "full-0400"}
    env = {e["name"]: e["value"] for e in d.run_body("full", "abc", batch)["overrides"]["containerOverrides"][0]["env"]}
    assert env["EMAIL_ROLE"] == "last" and env["BATCH_ID"] == "full-0400-2026-10-21" and env["BATCH_KIND"] == "full-0400"


def schedule_rows():
    """The prod shape: three probe hours and the 4 AM full run, jobs 4 min apart."""
    jobs = ["plex-etl-sales-orders", "plex-etl-work-orders", "plex-etl-sales-quotes", "plex-etl-part-lot"]
    rows = []
    for hour, mode in ((13, "probe"), (18, "probe"), (23, "probe"), (4, "full")):
        rows += [{"job_name": j, "run_time": f"{hour:02d}:{i * 4:02d}", "mode": mode, "enabled": True}
                 for i, j in enumerate(jobs)]
    return rows


def test_batch_roles_follow_run_time_within_the_hour():
    rows = schedule_rows()
    at = lambda j, h, m: d.batch_for(rows, j, "probe", mt(2026, 10, 21, h, m))
    assert at("plex-etl-sales-orders", 13, 0)["role"] == "first"
    assert at("plex-etl-work-orders", 13, 4)["role"] == "middle"
    assert at("plex-etl-part-lot", 13, 12) == {"role": "last", "batch_id": "probe-1300-2026-10-21",
                                               "batch_kind": "probe-1300"}
    # The 11 PM batch is named by its local date, not the UTC one (05:00 next day).
    assert at("plex-etl-part-lot", 23, 12)["batch_id"] == "probe-2300-2026-10-21"
    full = d.batch_for(rows, "plex-etl-sales-orders", "full", mt(2026, 10, 21, 4, 0))
    assert full["role"] == "first" and full["batch_kind"] == "full-0400"


def test_batch_ignores_disabled_rows_and_other_modes():
    rows = schedule_rows()
    rows = [dict(r, enabled=False) if r["job_name"] == "plex-etl-part-lot" else r for r in rows]
    assert d.batch_for(rows, "plex-etl-sales-quotes", "probe", mt(2026, 10, 21, 13, 8))["role"] == "last"
    assert d.batch_for(rows, "plex-etl-part-lot", "probe", mt(2026, 10, 21, 13, 12)) is None
    solo = [dict(ROW)]
    assert d.batch_for(solo, ROW["job_name"], "probe", mt(2026, 10, 21, 13, 0))["role"] == "only"


def test_tick_sends_batch_env_and_followups_mail_as_themselves():
    rows = schedule_rows()
    failed = {"dispatch_id": "f1", "job_name": "plex-etl-work-orders", "mode": "probe", "reason": "schedule",
              "scheduled_for": mt(2026, 10, 21, 13, 4), "outcome": "failed",
              "finished_at": mt(2026, 10, 21, 13, 6), "followup_of": None}

    def run_tick(now):
        started = {}

        def fake_query(bq, sql, params=None):
            if "FROM" in sql and "run_time" in sql:
                return rows
            if "followup_of" in sql and "INSERT" not in sql:
                return [failed]
            return []

        saved = d._bq, d._session, d._query, d.start_job
        d._bq, d._session, d._query = (lambda: None), (lambda: None), fake_query
        d.start_job = lambda session, job, mode, dispatch_id, batch=None: started.update({job: batch}) or "x"
        try:
            d.tick(now_utc=now)
        finally:
            d._bq, d._session, d._query, d.start_job = saved
        return started

    # 13:13: the whole 1 PM batch is due (the failure is too fresh to follow up).
    started = run_tick(mt(2026, 10, 21, 13, 13))
    assert {j: b["role"] for j, b in started.items()} == {
        "plex-etl-sales-orders": "first", "plex-etl-work-orders": "middle",
        "plex-etl-sales-quotes": "middle", "plex-etl-part-lot": "last"}, started
    # 13:45: only the follow-up, filed under the failed run's batch.
    started = run_tick(mt(2026, 10, 21, 13, 45))
    assert started == {"plex-etl-work-orders": {"role": "followup", "batch_id": "probe-1300-2026-10-21",
                                                "batch_kind": "probe-1300"}}, started


def test_seed_sql_keeps_every_slot_inside_its_hour():
    sql = (Path(__file__).resolve().parent.parent / "deploy" / "etl_dispatcher" / "seed_schedule.sql").read_text()
    assert "i * 4" in sql and "13 AS base_hour" in sql
    jobs = sql.count("'plex-etl-")
    assert jobs == 13, jobs
    assert (jobs - 1) * 4 < 60, "the last staggered slot must stay inside the hour"



def test_a_failed_log_insert_starts_nothing_and_keeps_the_pass_going():
    """A BigQuery error on one job's dispatch row must not abort the tick, and
    must not start a run that has no row (it would be started again)."""
    rows = [ROW, dict(ROW, job_name="plex-etl-work-orders")]
    started = []

    def fake_query(bq, sql, params=None):
        if "INSERT INTO" in sql:
            job = next(p for p in params if p.name == "job").value
            if job == ROW["job_name"]:
                raise RuntimeError("streaming buffer busy")
            return []
        if "FROM" in sql and "run_time" in sql:
            return rows
        return []

    saved = d._bq, d._session, d._query, d.start_job
    d._bq, d._session, d._query = (lambda: None), (lambda: None), fake_query
    d.start_job = lambda session, job, mode, dispatch_id, batch=None: started.append(job) or "exec-1"
    try:
        summary = d.tick(now_utc=mt(2026, 10, 19, 13, 3))
    finally:
        d._bq, d._session, d._query, d.start_job = saved
    assert started == ["plex-etl-work-orders"], started
    assert any(e.startswith(f"log {ROW['job_name']}") for e in summary["errors"]), summary["errors"]
    assert [x["job_name"] for x in summary["dispatched"]] == ["plex-etl-work-orders"], summary["dispatched"]


# ── Plex outages: breaker, canary, recovery ───────────────────────────────────
ODBC_DOWN = "ODBC connection failed: 3 attempt(s); last: ('08S01', 'connection unexpectedly closed')"


def run_row(dispatch_id, job, minute, outcome="failed", detail=ODBC_DOWN, **kw):
    """A dispatch row started at 23:mm Mountain on 21 Oct; a finished run took three minutes."""
    finished = (None if outcome is None else mt(2026, 10, 21, 23, minute) if outcome == "held-outage"
                else mt(2026, 10, 21, 23, minute + 3))
    base = {"dispatch_id": dispatch_id, "job_name": job, "mode": "probe", "reason": "schedule",
            "dispatched_at": mt(2026, 10, 21, 23, minute), "finished_at": finished,
            "outcome": outcome, "detail": detail, "followup_of": None}
    base.update(kw)
    return base


def test_outage_opens_after_consecutive_connect_failures_only():
    one = [run_row("a", "plex-etl-sales-orders", 0)]
    assert d.outage_state(one) is None
    two = one + [run_row("b", "plex-etl-work-orders", 4)]
    assert d.outage_state(two) == {"since": mt(2026, 10, 21, 23, 3), "failures": 2}
    # A run that reached Plex since closes it; a non-connect failure says nothing.
    assert d.outage_state(two + [run_row("c", "plex-etl-part-lot", 8, outcome="success", detail=None)]) is None
    sql_error = run_row("c", "plex-etl-part-lot", 8, detail="view creation failed")
    assert d.outage_state(one + [sql_error]) is None
    assert d.outage_state(two + [sql_error])["failures"] == 2
    # Held slots are not evidence either way.
    assert d.outage_state(two + [run_row("h", "plex-etl-part-lot", 12, outcome="held-outage", detail=None)])


def test_canary_one_at_a_time_and_only_the_first_alerts():
    schedule = schedule_rows()
    log = [run_row("a", "plex-etl-sales-orders", 0), run_row("b", "plex-etl-work-orders", 4)]
    outage = d.outage_state(log)
    since = outage["since"]
    prefer = ["plex-etl-sales-quotes", "plex-etl-part-lot"]
    assert d.canary_due(log, since + dt.timedelta(minutes=9), outage, schedule, set(), preferred=prefer) is None
    first = d.canary_due(log, since + dt.timedelta(minutes=10), outage, schedule, set(), preferred=prefer)
    assert first == {"job_name": "plex-etl-sales-quotes", "role": "outage-alert"}
    busy = d.canary_due(log, since + dt.timedelta(minutes=10), outage, schedule,
                        {"plex-etl-sales-quotes"}, preferred=prefer)
    assert busy["job_name"] == "plex-etl-part-lot"
    # One running: wait. It failed: the next one is quiet, ten minutes later.
    canary = run_row("k1", "plex-etl-sales-quotes", 13, outcome=None, reason="canary")
    assert d.canary_due(log + [canary], since + dt.timedelta(minutes=40), outage, schedule, set(),
                        preferred=prefer) is None
    canary.update(outcome="failed", finished_at=mt(2026, 10, 21, 23, 16))
    assert d.canary_due(log + [canary], mt(2026, 10, 21, 23, 22), outage, schedule, set(),
                        preferred=prefer) is None
    assert d.canary_due(log + [canary], mt(2026, 10, 21, 23, 23), outage, schedule, set(),
                        preferred=prefer)["role"] == "canary"


def test_recovery_reruns_each_held_job_once_full_beats_probe():
    held = [run_row("h1", "plex-etl-sales-orders", 20, outcome="held-outage", detail=None),
            run_row("h2", "plex-etl-work-orders", 24, outcome="held-outage", detail=None),
            run_row("h3", "plex-etl-sales-orders", 40, outcome="held-outage", detail=None, mode="full"),
            run_row("h4", "plex-etl-part-lot", 44, outcome="held-outage", detail=None)]
    now = mt(2026, 10, 22, 0, 30)
    plan = d.recovery_plan(held, now, set(), per_tick=2)
    assert plan["batch_id"] == "recovery-h4" and plan["batch_kind"] == "recovery"
    assert plan["expected"] == ["plex-etl-part-lot", "plex-etl-sales-orders", "plex-etl-work-orders"]
    # Priority order, and only one run until a recovery run has reached Plex.
    assert plan["runs"] == [
        {"job_name": "plex-etl-sales-orders", "mode": "full", "followup_of": "h3", "role": "first"}]
    first = run_row("r0", "plex-etl-sales-orders", 50, outcome=None, reason="recovery", mode="full")
    assert d.recovery_plan(held + [first], now, set(), per_tick=2)["runs"] == [], "wait for the first"
    # It reached Plex: the rest go per_tick at a time.
    first.update(outcome="success", finished_at=mt(2026, 10, 21, 23, 53))
    nxt = d.recovery_plan(held + [first], now, set(), per_tick=2)
    assert nxt["batch_id"] == "recovery-h4"
    assert nxt["runs"] == [
        {"job_name": "plex-etl-work-orders", "mode": "probe", "followup_of": "h2", "role": "middle"},
        {"job_name": "plex-etl-part-lot", "mode": "probe", "followup_of": "h4", "role": "last"}]
    # A recovery run is the job's one try even if it fails: no loop.
    started = [first] + [run_row(f"r{i}", r["job_name"], 51, outcome="failed", reason="recovery",
                                 finished_at=mt(2026, 10, 21, 23, 55)) for i, r in enumerate(nxt["runs"], 1)]
    assert d.recovery_plan(held + started, now, set()) is None
    # Busy jobs wait; held slots older than the horizon are forgotten.
    assert [r["job_name"] for r in d.recovery_plan(held, now, {"plex-etl-sales-orders"})["runs"]] == [
        "plex-etl-work-orders"]
    assert d.recovery_plan(held, mt(2026, 10, 23, 1, 0), set()) is None


def test_a_recovery_run_cloud_run_refused_is_still_owed():
    held = [run_row("h1", "plex-etl-part-routing", 20, outcome="held-outage", detail=None)]
    refused = run_row("r1", "plex-etl-part-routing", 50, outcome="dispatch-failed", reason="recovery",
                      detail="jobs.run plex-etl-part-routing -> HTTP 503")
    plan = d.recovery_plan(held + [refused], mt(2026, 10, 22, 0, 30), set())
    assert [r["job_name"] for r in plan["runs"]] == ["plex-etl-part-routing"]


def test_a_killed_last_run_hands_the_digest_to_its_followup():
    last = {"role": "last", "batch_id": "probe-1800-2026-10-27", "batch_kind": "probe-1800"}
    killed = {"detail": "execution failed or was cancelled before the job wrote its outcome"}
    assert d.followup_role(killed, last) == "last"
    assert d.followup_role({"detail": "no outcome and no finished execution after 120 min"}, last) == "last"
    assert d.followup_role({"detail": "ODBC connection failed: 2404"}, last) == "followup"
    assert d.followup_role(killed, dict(last, role="middle")) == "followup"
    assert d.followup_role(killed, None) == "followup"


class _Resp:
    def __init__(self, code):
        self.status_code, self.text = code, "x"

    def json(self):
        return {"metadata": {"name": "projects/p/jobs/j/executions/e1"}}


class _Session:
    def __init__(self, codes):
        self.codes, self.calls = list(codes), 0

    def post(self, *a, **k):
        self.calls += 1
        return _Resp(self.codes.pop(0))


def test_start_job_retries_a_5xx_but_not_a_4xx():
    s = _Session([503, 200])
    assert d.start_job(s, "plex-etl-x", "probe", "id1", pause=0) == "projects/p/jobs/j/executions/e1"
    assert s.calls == 2
    s = _Session([503, 503, 503])
    try:
        d.start_job(s, "plex-etl-x", "probe", "id1", pause=0)
        raise AssertionError("three 503s must fail")
    except RuntimeError as exc:
        assert "HTTP 503" in str(exc) and s.calls == 3
    s = _Session([403])
    try:
        d.start_job(s, "plex-etl-x", "probe", "id1", pause=0)
        raise AssertionError("a 403 must fail")
    except RuntimeError:
        assert s.calls == 1


def test_a_later_run_covers_a_held_or_failed_slot():
    held = run_row("h1", "plex-etl-sales-orders", 20, outcome="held-outage", detail=None, mode="full")
    probe = run_row("p1", "plex-etl-sales-orders", 30, outcome="success", detail=None)
    full = dict(probe, dispatch_id="p2", mode="full")
    now = mt(2026, 10, 22, 0, 30)
    assert d.recovery_plan([held, probe], now, set())["runs"], "a probe does not cover a full run"
    assert d.recovery_plan([held, full], now, set()) is None
    failed_canary = dict(full, reason="canary", outcome="failed")
    assert d.recovery_plan([held, failed_canary], now, set())["runs"], "a canary that failed covers nothing"
    # The same rule replaces the follow-up of a failed run once the job ran again.
    failed = run_row("f1", "plex-etl-sales-orders", 0)
    assert d.followups_due([failed], mt(2026, 10, 21, 23, 30)) == [failed]
    assert d.followups_due([failed, probe], mt(2026, 10, 21, 23, 30)) == []
    for reason in ("canary", "recovery", "external"):
        assert d.followups_due([dict(failed, reason=reason)], mt(2026, 10, 21, 23, 30)) == []


def test_run_body_lists_the_recovery_batch():
    batch = {"role": "first", "batch_id": "recovery-h4", "batch_kind": "recovery",
             "expected": ["plex-etl-a", "plex-etl-b"]}
    env = {e["name"]: e["value"]
           for e in d.run_body("full", "x1", batch)["overrides"]["containerOverrides"][0]["env"]}
    assert env["BATCH_EXPECTED"] == "plex-etl-a plex-etl-b" and env["BATCH_KIND"] == "recovery"
    plain = d.run_body("probe", "x2", {"role": "first", "batch_id": "b", "batch_kind": "probe-1300"})
    assert "BATCH_EXPECTED" not in str(plain)


def test_tick_during_an_outage_holds_slots_and_starts_one_canary():
    rows = schedule_rows()
    recent = [run_row("a", "plex-etl-sales-orders", 0, dispatched_at=mt(2026, 10, 21, 12, 40),
                      finished_at=mt(2026, 10, 21, 12, 43)),
              run_row("b", "plex-etl-work-orders", 4, dispatched_at=mt(2026, 10, 21, 12, 44),
                      finished_at=mt(2026, 10, 21, 12, 47))]
    inserted, started = [], {}

    def fake_query(bq, sql, params=None):
        if "INSERT INTO" in sql:
            p = {x.name: x.value for x in params}
            inserted.append((p["job"], p["reason"], p["outcome"]))
            return []
        if "FROM" in sql and "run_time" in sql:
            return rows
        if "followup_of" in sql and "detail" in sql:
            return recent
        return []

    saved = d._bq, d._session, d._query, d.start_job
    d._bq, d._session, d._query = (lambda: None), (lambda: None), fake_query
    d.start_job = lambda session, job, mode, dispatch_id, batch=None: started.update({job: batch}) or "x"
    try:
        summary = d.tick(now_utc=mt(2026, 10, 21, 13, 13))
    finally:
        d._bq, d._session, d._query, d.start_job = saved
    assert summary["outage"]["failures"] == 2
    held = sorted(j for j, reason, outcome in inserted if outcome == "held-outage")
    assert held == sorted(r["job_name"] for r in rows if r["run_time"].startswith("13:")), inserted
    assert list(started) == ["plex-etl-sales-quotes"], started
    assert started["plex-etl-sales-quotes"]["role"] == "outage-alert"
    assert summary["followups"] == [], "no follow-ups while Plex is down"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"OK: {len(tests)} tests")
