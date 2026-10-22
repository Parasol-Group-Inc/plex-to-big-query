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

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"OK: {len(tests)} tests")
