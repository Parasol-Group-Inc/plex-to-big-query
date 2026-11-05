"""Tests for the "no new data" flag (main.no_new_data_info and the email/digest
wording in email_utils), added 2026-11-05 after a run during the Plex outage
emailed a plain SUCCESS while Plex was serving a frozen copy.

    python -m pytest tests/test_no_new_data.py

No Plex or BigQuery needed: the client is a fake that answers by query text.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GCP_PROJECT", "voxdatalake")
os.environ.setdefault("BQ_DATASET", "PlexTest")

import main as m  # noqa: E402
import email_utils  # noqa: E402

CFG = m._CONFIG_SNAPSHOT_KEY
NOW = {"raw_A": "1|x", "raw_B": "6|y", CFG: "cfg2"}


def probe_row(hours_ago, data, cfg="cfg1"):
    at = datetime(2026, 11, 5, 21, 0, tzinfo=timezone.utc).replace(hour=21 - hours_ago)
    snap = dict(data, **{CFG: cfg})
    return SimpleNamespace(probed_at=at, snapshot=json.dumps(snap))


class FakeBQ:
    def __init__(self, history, failures=0, broken=False):
        self.history, self.failures, self.broken = history, failures, broken

    def query(self, sql, job_config=None):
        if self.broken:
            raise RuntimeError("BigQuery down")
        if "probe_log" in sql:
            rows = self.history
        else:
            rows = [SimpleNamespace(n=self.failures)]
        return SimpleNamespace(result=lambda: iter(rows))


def info(history, failures=0, table="PlexOps.etl_dispatch_log", broken=False):
    saved = (m.OUTAGE_BREAKER_TABLE, m.DISPATCH_LOG_TABLE)
    m.OUTAGE_BREAKER_TABLE, m.DISPATCH_LOG_TABLE = "", table
    try:
        return m.no_new_data_info(FakeBQ(history, failures, broken), "quality_supplier_returns", NOW)
    finally:
        m.OUTAGE_BREAKER_TABLE, m.DISPATCH_LOG_TABLE = saved


SAME = {"raw_A": "1|x", "raw_B": "6|y"}
OTHER = {"raw_A": "0|x", "raw_B": "6|y"}


def test_since_is_the_oldest_probe_in_the_unbroken_same_data_run():
    # newest first, as the query orders them; config differences don't count
    got = info([probe_row(1, SAME), probe_row(3, SAME, cfg="old"), probe_row(5, OTHER), probe_row(7, SAME)])
    assert got["unchanged_since"].startswith("2026-11-05T18:00")
    assert got["unchanged_since_local"] == "2026-11-05 11:00 MST"


def test_new_data_says_nothing():
    assert info([probe_row(1, OTHER), probe_row(2, SAME)]) == {}
    assert info([]) == {}


def test_flagged_only_while_plex_is_failing_to_connect():
    quiet = info([probe_row(1, SAME)], failures=1)
    assert quiet["no_new_data"] is False and quiet["no_new_data_note"] == ""
    down = info([probe_row(1, SAME)], failures=14)
    assert down["no_new_data"] is True
    assert down["no_new_data_note"].startswith(m.NO_NEW_DATA_PREFIX)
    assert "14 failed connect(s)" in down["no_new_data_note"]
    assert "does not show Plex is current" in down["no_new_data_note"]


def test_test_jobs_without_the_dispatch_log_are_never_flagged():
    assert info([probe_row(1, SAME)], failures=14, table="etl_dispatch_log")["no_new_data"] is False


def test_bigquery_trouble_is_never_fatal():
    assert info([probe_row(1, SAME)], broken=True) == {}


def test_prefix_is_shared():
    assert m.NO_NEW_DATA_PREFIX == email_utils.NO_NEW_DATA_PREFIX


def report(status="success", **probe):
    base = {"may_skip": False, "sources_checked": 3, "changed": []}
    return {"status": status, "run_mode": "probe", "probe": dict(base, **probe)}


def test_email_wording():
    flagged = report(unchanged_since_local="2026-11-04 15:17 MST", no_new_data=True,
                     connect_failures=14, connect_hours=6)
    text = email_utils._why_it_ran(flagged)
    assert "same data as at 2026-11-04 15:17 MST" in text and "frozen copy" in text
    assert email_utils.no_new_data(flagged)

    plain = report(unchanged_since_local="2026-11-04 15:17 MST", no_new_data=False)
    assert email_utils._why_it_ran(plain).endswith("Plex's data in these tables is the same as at 2026-11-04 15:17 MST.")
    assert not email_utils.no_new_data(plain)

    assert "same data" not in email_utils._why_it_ran(report())
    assert not email_utils.no_new_data(report("failed", no_new_data=True))


def test_digest_row_and_headline():
    zone = email_utils.ZoneInfo("America/Denver")
    note = m.NO_NEW_DATA_PREFIX + ": Plex returned the same data as at 2026-11-04 15:17 MST"
    rows_html, rows_text = email_utils._digest_rows(
        [{"job_name": "plex-etl-sales-returns", "status": "success", "detail": note, "rows_written": 9},
         {"job_name": "plex-etl-sales-quotes", "status": "success", "rows_written": 3}], [], zone)
    assert "NO NEW DATA" in rows_text[0] and "OK" in rows_text[1] and "NO NEW DATA" not in rows_text[1]
