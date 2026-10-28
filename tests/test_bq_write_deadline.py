"""Tests for the BigQuery load deadlines in main.py's write_to_bigquery.

    python tests/test_bq_write_deadline.py            # plain asserts, prints OK
    python -m pytest tests/test_bq_write_deadline.py  # same tests under pytest

No Plex, BigQuery or SendGrid needed.
"""
import concurrent.futures
import os
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GCP_PROJECT", "voxdatalake")
os.environ.setdefault("BQ_DATASET", "PlexTest")

import main as m  # noqa: E402


class FakeJob:
    def __init__(self, hang=False):
        self.hang, self.errors, self.result_timeout = hang, None, "unset"

    def result(self, timeout=None):
        self.result_timeout = timeout
        if self.hang:
            raise concurrent.futures.TimeoutError()


class FakeBQ:
    """Fails the first load with `first_error`, then succeeds."""
    def __init__(self, first_error):
        self.first_error, self.calls, self.jobs = first_error, [], []

    def load_table_from_dataframe(self, df, table_ref, job_config=None, timeout=None):
        self.calls.append(timeout)
        if len(self.calls) == 1 and isinstance(self.first_error, Exception):
            raise self.first_error
        job = FakeJob(hang=len(self.calls) == 1 and self.first_error == "hang")
        self.jobs.append(job)
        return job


def _write(bq):
    slept = []
    real_sleep, m.sleep = m.sleep, slept.append
    try:
        n = m.write_to_bigquery(bq, pd.DataFrame({"a": [1, 2]}), "raw_X")
    finally:
        m.sleep = real_sleep
    return n, slept


def test_stuck_upload_retries_once_with_deadlines():
    # 2026-10-27, 6 PM Mountain: an upload that never returned.
    bq = FakeBQ(requests.exceptions.ReadTimeout("read timed out"))
    n, slept = _write(bq)
    assert n == 2 and slept == [30]
    assert bq.calls == [(30, m.BQ_UPLOAD_TIMEOUT_SECONDS)] * 2
    assert bq.jobs[0].result_timeout == m.BQ_LOAD_JOB_TIMEOUT_SECONDS


def test_slow_load_job_retries_once():
    bq = FakeBQ("hang")
    n, slept = _write(bq)
    assert n == 2 and slept == [30] and len(bq.calls) == 2


if __name__ == "__main__":
    test_stuck_upload_retries_once_with_deadlines()
    test_slow_load_job_retries_once()
    print("OK")
