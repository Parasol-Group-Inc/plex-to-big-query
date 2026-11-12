"""Tests for the watchdog's ODBC checks (watchdog.py, 2026-11-11). Pure helpers only."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import watchdog as w  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 11, 16, 0, tzinfo=UTC)          # 09:00 MT


def t(h, m=0, d=11):
    return dt.datetime(2026, 11, d, h, m, tzinfo=UTC)


def test_frozen_odbc_with_morning_plex_work_is_hours_behind():
    # 11-11: ODBC newest 11-10 16:10 MT (23:10 UTC); Plex changed orders from 06:xx MT
    changes = [t(23, 5, 10), t(13, 20), t(13, 40), t(14, 10), t(15, 30)]
    lag, n, oldest = w.odbc_plex_lag(changes, t(23, 10, 10), NOW)
    assert n == 4 and oldest == t(13, 20) and lag == 160.0


def test_quiet_night_is_not_lag():
    lag, n, _ = w.odbc_plex_lag([t(23, 5, 10)], t(23, 10, 10), t(12, 0))
    assert lag == 0.0 and n == 0


def test_change_within_slack_is_not_unseen():
    lag, n, _ = w.odbc_plex_lag([t(15, 3)], t(15, 0), NOW)
    assert n == 0


def test_no_odbc_reference_is_no_verdict():
    assert w.odbc_plex_lag([t(15)], None, NOW) == (None, 0, None)


def test_connect_failures_three_of_four():
    err = "ODBC connection failed: 3 attempt(s); last: Session refused by service"
    rows = [("failed", err, t(15, 46)), ("failed", err, t(15, 31)), ("success", "", t(15, 16)),
            ("failed", err, t(15, 1))]
    assert w.connect_failures(rows) == (3, 4, t(15, 1), err)
    rows[0] = ("failed", "BigQuery 503", t(15, 46))
    assert w.connect_failures(rows)[0] == 2


def test_weekend_window_saturday_sunday_and_early_monday():
    den = w.DEN
    assert w.weekend_window(dt.datetime(2026, 11, 14, 10, 0, tzinfo=den))      # Saturday
    assert w.weekend_window(dt.datetime(2026, 11, 15, 23, 0, tzinfo=den))      # Sunday
    assert w.weekend_window(dt.datetime(2026, 11, 16, 5, 30, tzinfo=den))      # Monday before 06:00
    assert not w.weekend_window(dt.datetime(2026, 11, 16, 6, 0, tzinfo=den))   # Monday 06:00
    assert not w.weekend_window(dt.datetime(2026, 11, 13, 22, 0, tzinfo=den))  # Friday night


def test_test_cascade_not_checked_sunday_or_monday_morning():
    den = w.DEN
    assert w.check_test_cascade(None, dt.datetime(2026, 11, 15, 9, 0, tzinfo=den)) == []
    assert w.check_test_cascade(None, dt.datetime(2026, 11, 16, 9, 0, tzinfo=den)) == []
