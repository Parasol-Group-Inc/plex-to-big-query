"""plex_api_lag.odbc_plex_lag and the screens verdict replayed on real days (11-10 to 11-12).

Must alert: 11-10 freeze. Must stay quiet: 11-11 afternoon (normal pre-refresh wait),
11-12 02:11 (our 23:00 -> 04:00 load gap), 11-12 07:21 (new lines after a quiet night),
a quiet weekend."""
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import plex_api_lag as p  # noqa: E402
import screen_recon as r  # noqa: E402

LINE = 360


def mt(d, h, mi=0):
    return p.mt_to_utc(dt.datetime(2026, 11, d, h, mi))


# ── watchdog measure: at our last load ─────────────────────────────────────────

def test_1110_freeze_alerts():
    # ODBC froze at 08:10; Plex kept working; our Label Design loads ran every 15 min.
    changes = [mt(10, 8, 30), mt(10, 9, 35), mt(10, 11, 0)]
    lag, n, oldest = p.odbc_plex_lag(changes, mt(10, 8, 10), mt(10, 14, 45))
    assert lag > LINE and n == 3 and oldest == mt(10, 8, 30)


def test_1111_afternoon_wait_before_refresh_is_quiet():
    changes = [mt(11, 12, 0), mt(11, 14, 0)]
    lag, _, _ = p.odbc_plex_lag(changes, mt(11, 11, 36), mt(11, 16, 45))
    assert lag < LINE


def test_1112_overnight_load_gap_is_quiet():
    # 11-12 02:11 fired 6.1 h when measured to "now"; at our 23:02 load it was under 3 h.
    changes = [mt(11, 20, 4), mt(11, 21, 0), mt(11, 22, 8)]
    lag, n, _ = p.odbc_plex_lag(changes, mt(11, 18, 2), mt(11, 23, 2))
    assert lag < LINE and n == 3
    # and changes after our load are not counted at all
    lag, n, _ = p.odbc_plex_lag([mt(12, 1, 0)], mt(11, 18, 2), mt(11, 23, 2))
    assert (lag, n) == (0.0, 0)


def test_quiet_weekend_is_quiet():
    lag, n, _ = p.odbc_plex_lag([mt(7, 16, 0)], mt(7, 16, 0), mt(9, 23, 0))
    assert (lag, n) == (0.0, 0)


def test_no_reference_is_no_verdict():
    assert p.odbc_plex_lag([mt(10, 9)], None, mt(10, 10)) == (None, 0, None)
    assert p.odbc_plex_lag([mt(10, 9)], mt(10, 8), None) == (None, 0, None)


def test_mt_to_utc():
    assert p.mt_to_utc(dt.datetime(2026, 11, 12, 7, 0)).hour == 14
    assert p.mt_to_utc(None) is None


# ── screens verdict: 11-12 07:21, four new lines after a quiet night ───────────

FETCH = mt(12, 7, 21)


def _scr(keys):
    return {k: {"event": None, "num": int(k), "m": {"status_key": 3016}} for k in keys}


def test_1112_0721_new_lines_after_quiet_night_are_not_behind():
    scr = _scr(["132751820", "132751849"])
    # Plex's API: the only changes ODBC lacks are this morning's (07:00)
    _, _, verdict, lag, _ = r.compare("releases", scr, {}, 1, None, {}, FETCH,
                                      odbc_newest_change=mt(11, 22, 8), plex_unseen=(mt(12, 7, 0),))
    assert verdict != "behind" and lag < r.ALERT_LAG_MIN


def test_1112_0721_without_api_keeps_old_sign():
    scr = _scr(["132751820"])
    _, _, verdict, lag, _ = r.compare("releases", scr, {}, 1, None, {}, FETCH,
                                      odbc_newest_change=mt(11, 22, 8), plex_unseen=None)
    assert verdict == "behind" and lag > 500


def test_1110_freeze_screens_still_behind():
    scr = _scr(["131000001"])
    fetch = mt(10, 12, 21)
    _, _, verdict, lag, _ = r.compare("releases", scr, {}, 1, None, {}, fetch,
                                      odbc_newest_change=mt(10, 8, 10), plex_unseen=(mt(10, 8, 30),))
    assert verdict == "behind" and lag > 200


def test_api_says_odbc_has_everything():
    scr = _scr(["132751820"])
    _, _, verdict, _, _ = r.compare("releases", scr, {}, 1, None, {}, FETCH,
                                    odbc_newest_change=mt(11, 22, 8), plex_unseen=(None,))
    assert verdict == "current"
