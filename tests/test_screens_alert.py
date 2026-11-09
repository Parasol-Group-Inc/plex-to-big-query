"""Tests for the "start the live screens" alert (main.py, 2026-11-09) and the
screen task's push gate 2 (scripts/plex_live_screens.py).

    python -m pytest tests/test_screens_alert.py

No Plex or BigQuery needed: the client is replaced by a fake.
"""
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT", "voxdatalake")
os.environ.setdefault("BQ_DATASET", "PlexTest")

import email_utils  # noqa: E402
import main as m  # noqa: E402

NOW = datetime(2026, 11, 4, 23, 30, tzinfo=timezone.utc)
DOWN = "ODBC connection failed: 3 attempt(s); last: no answer from Plex within 60s"


def every(minutes, hours=6, up=False, start=NOW):
    """One event every `minutes` over the last `hours`, newest first."""
    n = int(hours * 60 // minutes)
    return [(start - timedelta(minutes=i * minutes), up) for i in range(n)]


# ── screens_alert_due ─────────────────────────────────────────────────────────

def test_due_when_every_hour_failed():
    stats = m.screens_alert_due(every(10), NOW)
    assert stats and stats["downs"] == 36 and stats["ups"] == 0


def test_not_due_after_only_five_hours():
    assert m.screens_alert_due(every(10, hours=5), NOW) is None


def test_not_due_with_a_quiet_hour():
    events = [(t, up) for t, up in every(10) if not (2 <= (NOW - t).total_seconds() / 3600 < 3)]
    assert m.screens_alert_due(events, NOW) is None


def test_flapping_outage_still_counts():
    # 11-06: a canary connected now and then, the rest failed. 4 ups in 36 is 11%.
    events = every(10)
    for i in (5, 14, 23, 32):
        events[i] = (events[i][0], True)
    assert m.screens_alert_due(events, NOW)["ups"] == 4


def test_not_due_when_a_quarter_got_through():
    events = every(10)
    for i in range(0, 36, 4):          # 9 of 36 = 25%
        events[i] = (events[i][0], True)
    assert m.screens_alert_due(events, NOW) is None


def test_events_outside_the_window_are_ignored():
    old = every(10, start=NOW - timedelta(hours=7))
    assert m.screens_alert_due(old + every(10, hours=3), NOW) is None


# ── maybe_send_screens_alert ──────────────────────────────────────────────────

class FakeBQ:
    """Answers the alert's queries in order of what they ask for."""

    def __init__(self, events, already_sent=0, screens_at=None):
        self.events, self.already_sent, self.screens_at = events, already_sent, screens_at
        self.inserts = []

    def __call__(self, project=None):
        return self

    def query(self, sql, job_config=None):
        if "INSERT" in sql:
            self.inserts.append({p.name: p.value for p in job_config.query_parameters})
            rows = []
        elif "reason = 'screens-alert'" in sql:
            rows = [SimpleNamespace(n=self.already_sent)]
        elif "live_order_releases" in sql:
            rows = [SimpleNamespace(t=self.screens_at)]
        elif "MAX(finished_at)" in sql:
            rows = [SimpleNamespace(t=NOW - timedelta(hours=9))]
        else:
            rows = [SimpleNamespace(t=t, up=up) for t, up in self.events]
        return SimpleNamespace(result=lambda: rows)


def run(monkeypatch, fake, detail=DOWN, dataset="PlexProd", table="PlexOps.etl_dispatch_log"):
    sent = []
    monkeypatch.setattr(m, "BQ_DATASET", dataset)
    monkeypatch.setattr(m, "OUTPUT_MODE", "bigquery")
    monkeypatch.setattr(m, "DISPATCH_LOG_TABLE", table)
    monkeypatch.setattr(m, "OUTAGE_BREAKER_TABLE", "")
    monkeypatch.setattr(m.bigquery, "Client", fake)
    monkeypatch.setattr(m, "send_screens_alert", lambda alert: sent.append(alert) or True)

    class FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(m, "datetime", FixedNow)
    return m.maybe_send_screens_alert(detail), sent


def test_sends_once_and_records_it(monkeypatch):
    fake = FakeBQ(every(10))
    ok, sent = run(monkeypatch, fake)
    assert ok and len(sent) == 1 and sent[0]["downs"] == 36
    assert len(fake.inserts) == 1 and fake.inserts[0]["detail"].startswith("sent: 36 failed")


def test_not_resent_within_a_day(monkeypatch):
    fake = FakeBQ(every(10), already_sent=1)
    ok, sent = run(monkeypatch, fake)
    assert not ok and not sent and not fake.inserts


def test_quiet_while_screens_are_loading(monkeypatch):
    fake = FakeBQ(every(10), screens_at=NOW - timedelta(minutes=40))
    ok, sent = run(monkeypatch, fake)
    assert not ok and not sent


def test_stale_screens_do_not_stop_it(monkeypatch):
    fake = FakeBQ(every(10), screens_at=NOW - timedelta(days=2))
    ok, sent = run(monkeypatch, fake)
    assert ok and sent[0]["screens_at"] == NOW - timedelta(days=2)


def test_only_prod_and_only_connect_failures(monkeypatch):
    assert run(monkeypatch, FakeBQ(every(10)), dataset="PlexTest")[1] == []
    assert run(monkeypatch, FakeBQ(every(10)), detail="Query failed: syntax")[1] == []
    assert run(monkeypatch, FakeBQ(every(10)), table="etl_dispatch_log")[1] == []


def test_a_bigquery_error_never_raises(monkeypatch):
    def broken(project=None):
        raise RuntimeError("no BigQuery")
    ok, sent = run(monkeypatch, broken)
    assert not ok and not sent


# ── the email ─────────────────────────────────────────────────────────────────

def test_email_says_what_to_do():
    subject, html_content, text = email_utils.render_screens_alert({
        "hours": 6, "downs": 36, "ups": 2, "first_down": NOW - timedelta(hours=6),
        "last_ok": NOW - timedelta(hours=9), "screens_at": None, "detail": DOWN,
        "job_name": "plex-etl-sales-quotes", "gcp_project": "voxdatalake", "bq_dataset": "PlexProd"})
    assert "ACTION NEEDED" in subject and "start the live screens" in subject
    assert 'Enable-ScheduledTask -TaskName "Plex live screens"' in text
    assert "Disable-ScheduledTask" in text and "never" in text
    assert "Start-ScheduledTask" in html_content and "{{" not in html_content


# ── push gate 2 of the screen task ────────────────────────────────────────────

def load_screens_module():
    for name in ("playwright", "playwright.sync_api"):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules["playwright.sync_api"].sync_playwright = None
    sys.path.insert(0, str(ROOT / "scripts"))
    import plex_live_screens
    return plex_live_screens


def test_gate_2_counts_probe_skips_but_not_breaker_holds():
    s = load_screens_module()
    assert s.etl_reached_plex("success", None)
    assert s.etl_reached_plex("partial", "1 extraction error")
    assert s.etl_reached_plex("skipped", None)
    assert not s.etl_reached_plex("skipped", "Held — Plex outage breaker open since 2026-11-05 14:00 UTC")
    assert not s.etl_reached_plex("failed", DOWN)
