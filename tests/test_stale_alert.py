"""Tests for the stale ODBC data check and alert (main.py, 2026-11-10).

    python -m pytest tests/test_stale_alert.py

No Plex or BigQuery needed: the cursor and the client are fakes.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT", "voxdatalake")
os.environ.setdefault("BQ_DATASET", "PlexTest")

import email_utils  # noqa: E402
import main as m  # noqa: E402

# Tuesday 2026-11-10, 12:46 MT: the probe that still saw 08:10 data.
TUE_1246 = datetime(2026, 11, 10, 12, 46)
FROZEN = {"order update": datetime(2026, 11, 10, 8, 8, 54), "production record": datetime(2026, 11, 10, 8, 9),
          "shipper": datetime(2026, 11, 10, 7, 55)}


# ── odbc_data_lag / stale_alert_due ───────────────────────────────────────────

def test_lag_uses_the_newest_value():
    assert m.odbc_data_lag(FROZEN, TUE_1246) == 277.0


def test_future_dates_are_ignored():
    newest = dict(FROZEN, shipper=datetime(2026, 11, 12, 9, 0))
    assert m.odbc_data_lag(newest, TUE_1246) == 277.0


def test_no_values_is_none():
    assert m.odbc_data_lag({"order update": None}, TUE_1246) is None


def test_due_on_11_10():
    assert m.stale_alert_due(277.0, TUE_1246)


def test_due_from_two_hours():
    assert m.stale_alert_due(120, TUE_1246) and not m.stale_alert_due(119, TUE_1246)


def test_not_due_outside_working_hours_or_at_weekends():
    assert not m.stale_alert_due(600, datetime(2026, 11, 10, 8, 59))
    assert not m.stale_alert_due(600, datetime(2026, 11, 10, 17, 0))
    assert not m.stale_alert_due(600, datetime(2026, 11, 14, 12, 0))   # Saturday


def test_nothing_in_four_days_counts_as_stale():
    assert m.stale_alert_due(None, TUE_1246)


# ── check_odbc_freshness ──────────────────────────────────────────────────────

class FakeConn:
    def __init__(self, values, fail=False):
        self.values, self.fail, self.sql = list(values), fail, []

    def cursor(self):
        conn = self

        class Cur:
            def execute(self, sql):
                if conn.fail:
                    raise RuntimeError("driver error")
                conn.sql.append(sql)

            def fetchone(self):
                return (conn.values.pop(0),)

            def close(self):
                pass
        return Cur()


def test_check_alerts_on_frozen_data(monkeypatch):
    monkeypatch.setattr(m, "OUTPUT_MODE", "bigquery")
    monkeypatch.setattr(m, "BQ_DATASET", "PlexProd")
    calls = []
    monkeypatch.setattr(m, "maybe_send_stale_alert", lambda lag, newest: calls.append(lag))
    conn = FakeConn(FROZEN.values())
    assert m.check_odbc_freshness(conn, TUE_1246) == 277.0
    assert calls == [277.0]
    assert all("'2026-11-06'" in s for s in conn.sql) and len(conn.sql) == 3


def test_check_quiet_when_current(monkeypatch):
    monkeypatch.setattr(m, "OUTPUT_MODE", "bigquery")
    monkeypatch.setattr(m, "BQ_DATASET", "PlexProd")
    calls = []
    monkeypatch.setattr(m, "maybe_send_stale_alert", lambda lag, newest: calls.append(lag))
    fresh = [datetime(2026, 11, 10, 12, 30), None, datetime(2026, 11, 10, 11, 55)]
    assert m.check_odbc_freshness(FakeConn(fresh), TUE_1246) == 16.0 and calls == []


def test_check_is_prod_only_and_never_raises(monkeypatch):
    monkeypatch.setattr(m, "OUTPUT_MODE", "bigquery")
    monkeypatch.setattr(m, "BQ_DATASET", "PlexTest")
    assert m.check_odbc_freshness(FakeConn(FROZEN.values())) is None
    monkeypatch.setattr(m, "BQ_DATASET", "PlexProd")
    assert m.check_odbc_freshness(FakeConn([], fail=True)) is None


# ── maybe_send_stale_alert ────────────────────────────────────────────────────

class FakeBQ:
    def __init__(self, already_sent=0, screens_at=None):
        self.already_sent, self.screens_at, self.inserts = already_sent, screens_at, []

    def __call__(self, project=None):
        return self

    def query(self, sql, job_config=None):
        if "INSERT" in sql:
            assert "'stale-alert'" in sql and "'alert'" in sql
            self.inserts.append({p.name: p.value for p in job_config.query_parameters})
            rows = []
        elif "reason = 'stale-alert'" in sql:
            rows = [SimpleNamespace(n=self.already_sent)]
        else:
            rows = [SimpleNamespace(t=self.screens_at)]
        return SimpleNamespace(result=lambda: rows)


def send(monkeypatch, fake):
    sent = []
    monkeypatch.setattr(m, "DISPATCH_LOG_TABLE", "PlexOps.etl_dispatch_log")
    monkeypatch.setattr(m, "OUTAGE_BREAKER_TABLE", "")
    monkeypatch.setattr(m.bigquery, "Client", fake)
    monkeypatch.setattr(m, "send_stale_alert", lambda alert: sent.append(alert) or True)
    return m.maybe_send_stale_alert(277.0, FROZEN), sent


def test_sends_once_and_records_it(monkeypatch):
    fake = FakeBQ()
    ok, sent = send(monkeypatch, fake)
    assert ok and sent[0]["lag_minutes"] == 277.0
    assert fake.inserts[0]["detail"] == "sent: newest change 277.0 min old"


def test_not_resent_within_a_day(monkeypatch):
    fake = FakeBQ(already_sent=1)
    ok, sent = send(monkeypatch, fake)
    assert not ok and not sent and not fake.inserts


def test_quiet_while_screens_are_loading(monkeypatch):
    fake = FakeBQ(screens_at=datetime.now(timezone.utc) - timedelta(minutes=30))
    ok, sent = send(monkeypatch, fake)
    assert not ok and not sent


# ── the email ─────────────────────────────────────────────────────────────────

def test_email_says_what_to_do():
    subject, html_content, text = email_utils.render_stale_alert({
        "lag_minutes": 277.0, "newest": FROZEN, "threshold": 120, "screens_at": None,
        "job_name": "plex-etl-label-design", "gcp_project": "voxdatalake", "bq_dataset": "PlexProd"})
    assert "ACTION NEEDED" in subject and "4.6 h old" in subject
    assert "Newest order update: Tue 11-10 08:08 MT" in text
    assert 'Enable-ScheduledTask -TaskName "Plex live screens"' in text and "holiday" in text
    assert "{{" not in html_content and "Tue 11-10 08:08" in html_content
