"""Tests for read_windows() in scripts/plex_live_screens.py (2026-11-13): a screen window that
comes back at the row cap is read again in halves, never used as is.

    python -m pytest tests/test_screen_windows.py
"""
import datetime as dt
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
for name in ("playwright", "playwright.sync_api"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["playwright.sync_api"].sync_playwright = None

import plex_live_screens as pls  # noqa: E402

D = dt.date


def fake_screen(per_day, cap=None):
    """fetch(beg, end) returning per_day[d] rows for each day in [beg, end), cut at cap."""
    calls = []

    def fetch(beg, end):
        calls.append((beg, end))
        rows, d = [], beg
        while d < end:
            rows += [(d, i) for i in range(per_day.get(d, 0))]
            d += dt.timedelta(days=1)
        return rows[:cap] if cap else rows
    return fetch, calls


def test_under_cap_reads_each_window_once():
    fetch, calls = fake_screen({D(2026, 11, 3): 10})
    out = pls.read_windows([(D(2026, 11, 1), D(2026, 11, 16))], fetch, 500, "Rev")
    assert len(calls) == 1 and sum(len(r) for _, r in out) == 10


def test_capped_window_is_split_and_nothing_is_lost():
    # Nov 1-15 with 40 rows a day = 600 > cap 500 (the 11-13 failure); the screen cuts at 520
    per_day = {D(2026, 11, d): 40 for d in range(1, 16)}
    fetch, calls = fake_screen(per_day, cap=520)
    out = pls.read_windows([(D(2026, 11, 1), D(2026, 11, 16))], fetch, 500, "Rev")
    assert sum(len(r) for _, r in out) == 600                      # every row, none from the cut answer
    assert [w for w, _ in out] == sorted(w for w, _ in out)        # date order
    assert out[0][0][0] == D(2026, 11, 1) and out[-1][0][1] == D(2026, 11, 16)
    assert all(len(r) < 500 for _, r in out)


def test_exactly_at_cap_is_treated_as_cut():
    fetch, calls = fake_screen({D(2026, 11, 1): 250, D(2026, 11, 2): 250})
    out = pls.read_windows([(D(2026, 11, 1), D(2026, 11, 3))], fetch, 500, "Rev")
    assert len(calls) == 3 and [len(r) for _, r in out] == [250, 250]


def test_one_day_at_cap_raises_clearly():
    fetch, _ = fake_screen({D(2026, 11, 5): 900}, cap=520)
    with pytest.raises(pls.ScreenCapError, match="2026-11-05: 520 rows for one day"):
        pls.read_windows([(D(2026, 11, 1), D(2026, 11, 16))], fetch, 500, "Rev")


def test_runaway_is_bounded():
    def fetch(beg, end):          # a screen that ignores the dates: always capped
        return [0] * 600
    with pytest.raises(RuntimeError):
        pls.read_windows([(D(2026, 10, 1), D(2026, 12, 1))], fetch, 500, "Rev", max_requests=10)


def test_bad_answer_and_empty_windows():
    with pytest.raises(RuntimeError, match="not a row list"):
        pls.read_windows([(D(2026, 11, 1), D(2026, 11, 2))], lambda b, e: None, 500, "Rev")
    fetch, calls = fake_screen({})
    assert pls.read_windows([(D(2026, 11, 2), D(2026, 11, 2))], fetch, 500, "Rev") == [] and not calls


def test_fetch_errors_propagate():
    def fetch(beg, end):
        raise TimeoutError("screen timed out")
    with pytest.raises(TimeoutError):
        pls.read_windows([(D(2026, 11, 1), D(2026, 11, 16))], fetch, 500, "Rev")


def test_half_months_cover_go_live_to_today_without_gaps():
    ws = list(pls.half_months(pls.START, D(2026, 11, 13)))
    assert ws[0][0] == pls.START and ws[-1][1] == D(2026, 11, 14)
    assert all(a[1] == b[0] for a, b in zip(ws, ws[1:]))
