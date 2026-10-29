"""Tests for record_breaker_evidence() in main.py (audit A5, 2026-10-29).

    python -m pytest tests/test_breaker_evidence.py

No Plex or BigQuery needed: the client is replaced by a recorder.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GCP_PROJECT", "voxdatalake")
os.environ.setdefault("BQ_DATASET", "PlexTest")

import main as m  # noqa: E402

DOWN = "ODBC connection failed after 3 attempt(s): [08001] session refused (2404)"


def run(status, detail="", failures=0, dispatch_id="", table="PlexOps.etl_dispatch_log", mode="bigquery"):
    inserts = []

    class Client:
        def __init__(self, project=None):
            pass

        def query(self, sql, job_config=None):
            if "INSERT" in sql:
                inserts.append({p.name: p.value for p in job_config.query_parameters})
            return SimpleNamespace(result=lambda: None)

    saved = (m.bigquery.Client, m._breaker_streak, m.DISPATCH_ID, m.OUTAGE_BREAKER_TABLE, m.OUTPUT_MODE)
    m.bigquery.Client = Client
    m._breaker_streak = lambda bq: SimpleNamespace(failures=failures, since="2026-10-29")
    m.DISPATCH_ID, m.OUTAGE_BREAKER_TABLE, m.OUTPUT_MODE = dispatch_id, table, mode
    try:
        m.record_breaker_evidence(status, detail)
    finally:
        m.bigquery.Client, m._breaker_streak, m.DISPATCH_ID, m.OUTAGE_BREAKER_TABLE, m.OUTPUT_MODE = saved
    return inserts


def test_connect_failure_is_always_written():
    rows = run("failed", DOWN)
    assert len(rows) == 1 and rows[0]["status"] == "failed" and rows[0]["detail"] == DOWN


def test_good_run_closes_a_streak_but_is_quiet_otherwise():
    assert len(run("success", failures=2)) == 1
    assert len(run("partial", failures=1)) == 1
    assert run("success", failures=0) == []   # no row every 15 minutes


def test_other_failures_say_nothing_about_plex():
    assert run("failed", "BigQuery load failed", failures=3) == []


def test_dispatcher_runs_and_unconfigured_jobs_are_skipped():
    assert run("failed", DOWN, dispatch_id="abc") == []      # the dispatcher records its own
    assert run("failed", DOWN, table="") == []
    assert run("failed", DOWN, mode="local") == []
