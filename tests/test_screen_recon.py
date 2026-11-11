"""Tests for the screens vs ODBC comparison (scripts/screen_recon.py, 2026-11-10).

    python -m pytest tests/test_screen_recon.py

Pure: compare() gets plain dicts; no Plex, ODBC or BigQuery.
"""
import datetime as dt
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
for name in ("playwright", "playwright.sync_api"):
    sys.modules.setdefault(name, types.ModuleType(name))
sys.modules["playwright.sync_api"].sync_playwright = None

import screen_recon as r  # noqa: E402

UTC = dt.timezone.utc
FETCH = dt.datetime(2026, 11, 10, 20, 15, tzinfo=UTC)          # 13:15 MT


def prod(no, minutes_ago, qty=10.0):
    return {"num": no, "event": FETCH - dt.timedelta(minutes=minutes_ago),
            "m": {"quantity": qty, "rejected": 0}}


def odbc(rec, updated=None, eligible=True):
    return dict(rec, updated=updated, eligible=eligible)


def test_frozen_odbc_is_behind():
    # 11-10: ODBC's newest record 12:09:57 MT, screen read 13:15 MT; and 4.5 h earlier
    scr = {str(n): prod(n, 300 - n) for n in range(1, 200)}
    od = {k: odbc(v) for k, v in scr.items() if v["event"] < FETCH - dt.timedelta(minutes=270)}
    max_num = max(o["num"] for o in od.values())
    max_ev = max(o["event"] for o in od.values())
    counts, diffs, verdict, lag, why = r.compare("production", scr, od, max_num, max_ev, {}, FETCH)
    assert verdict == "behind" and lag > 120 and counts["missing_tail"] > 0 and not counts["missing_hole"]


def test_normal_lag_is_current():
    scr = {str(n): prod(n, 120 - n) for n in range(1, 100)}
    od = {k: odbc(v) for k, v in scr.items() if v["event"] < FETCH - dt.timedelta(minutes=50)}
    counts, _, verdict, lag, _ = r.compare("production", scr, od, max(o["num"] for o in od.values()),
                                           max(o["event"] for o in od.values()), {}, FETCH)
    assert verdict == "current" and lag < 60


def test_recent_records_are_excluded():
    scr = {"1": prod(1, 5)}
    counts, _, verdict, _, _ = r.compare("production", scr, {}, None, None, {}, FETCH)
    assert counts["excluded_recent"] == 1 and verdict == "current"


def test_old_hole_is_diverged():
    scr = {"5": prod(5, 400), "9": prod(9, 30)}
    od = {"9": odbc(prod(9, 30))}
    _, _, verdict, _, why = r.compare("production", scr, od, 9, od["9"]["event"], {}, FETCH)
    assert verdict == "diverged" and "5 missing" in why[0]


def test_value_edit_odbc_has_not_seen_is_lag():
    scr = {"7": {"num": 7, "event": None, "m": {"status_key": 1, "quantity": 2500.0, "order_status": "Pending Fulfillment"}}}
    o = odbc({"num": 7, "event": None, "m": {"status_key": 1, "quantity": 4000.0, "order_status": "Pending Fulfillment"}},
             updated=FETCH - dt.timedelta(days=4))
    seen = {"7": FETCH - dt.timedelta(minutes=200)}
    counts, _, verdict, lag, _ = r.compare("releases", scr, {"7": o}, 7, None, seen, FETCH)
    assert counts["value_diff"] == 1 and verdict == "behind" and lag == 200


def test_value_odbc_changed_after_screen_is_diverged():
    scr = {"7": {"num": 7, "event": None, "m": {"status_key": 1, "quantity": 2500.0, "order_status": "Pending Fulfillment"}}}
    o = odbc({"num": 7, "event": None, "m": {"status_key": 1, "quantity": 4000.0, "order_status": "Pending Fulfillment"}},
             updated=FETCH - dt.timedelta(minutes=60))
    seen = {"7": FETCH - dt.timedelta(minutes=200)}
    _, _, verdict, _, _ = r.compare("releases", scr, {"7": o}, 7, None, seen, FETCH)
    assert verdict == "diverged"


def test_odbc_newer_than_screen_is_ignored():
    scr = {"3": {"num": 3, "event": None, "m": {"revenue_cents": 100}}}
    o = odbc({"num": 3, "event": None, "m": {"revenue_cents": 90}}, updated=FETCH + dt.timedelta(minutes=5))
    counts, _, verdict, _, _ = r.compare("revenue", scr, {"3": o}, 3, None, {"3": FETCH - dt.timedelta(hours=5)}, FETCH)
    assert counts["odbc_newer"] == 1 and verdict == "current"


def test_odbc_extra_twice_is_diverged_once_is_not():
    scr = {"1": prod(1, 100)}
    od = {"1": odbc(prod(1, 100)), "2": odbc(prod(2, 90))}
    _, _, v1, _, _ = r.compare("production", scr, od, 2, od["2"]["event"], {}, FETCH)
    _, _, v2, _, _ = r.compare("production", scr, od, 2, od["2"]["event"], {}, FETCH, prev_extra=frozenset({"2"}))
    assert v1 == "current" and v2 == "diverged"


def test_ineligible_odbc_rows_are_not_extra():
    od = {"2": odbc(prod(2, 90), eligible=False)}
    counts, _, _, _, _ = r.compare("history", {}, od, 2, None, {}, FETCH)
    assert counts["odbc_extra"] == 0


def test_pipeline_behind_when_bigquery_lacks_odbc_rows():
    scr = {"1": prod(1, 200)}
    od = {"1": odbc(prod(1, 200))}
    _, _, verdict, _, _ = r.compare("production", scr, od, 1, od["1"]["event"], {}, FETCH,
                                    raw=set(), raw_modified=FETCH - dt.timedelta(minutes=10))
    assert verdict == "pipeline_behind"


def test_screen_records_revenue_sums_by_invoice_and_part():
    rows = [{"invoice_link": 5, "part_key": 9, "revenue": 10.0}, {"invoice_link": 5, "part_key": 9, "revenue": 1}]
    out = r.screen_records("revenue", rows)
    assert out == {"5|9": {"num": 5, "event": None, "m": {"revenue_cents": 1100}}}


# ── login audit (2026-11-10) ──────────────────────────────────────────────────

class FakePage:
    url = "https://vox.on.plex.com/SqlDevelopmentEnvironment"
    text = ""

    def screenshot(self, **kw):
        return b"png"

    def evaluate(self, js):
        return self.text


def test_login_audit_records_ok_relogin_and_failure(monkeypatch):
    audit = r.Audit("run1", FETCH, dry_run=False)
    calls = {"n": 0}

    def real(pg, user, password):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("login did not reach the SQL Development Environment")

    login = audit.wrap_login(real)
    login(FakePage(), "u", "p")
    login(FakePage(), "u", "p")
    try:
        login(FakePage(), "u", "p")
        raise AssertionError("should have raised")
    except RuntimeError:  # LoginFailed is a RuntimeError
        pass
    assert [x["reason"] for x in audit.logins] == ["first", "re-login", "re-login"]
    assert [x["ok"] for x in audit.logins] == [True, True, False]
    assert "password" not in str(audit.logins).replace("password_change", "")
    assert audit.logins[2]["error"].startswith("unknown: login did not") and not audit.logins[2]["retryable"]


class LoginBQ:
    def __init__(self, mailed=0):
        self.mailed, self.inserts = mailed, []

    def query(self, sql, job_config=None):
        from types import SimpleNamespace
        if sql.lstrip().startswith("INSERT"):
            self.inserts.append(sql)
            rows = []
        else:
            rows = [SimpleNamespace(last_ok=FETCH - dt.timedelta(hours=9), streak=2, mailed=self.mailed)]
        return SimpleNamespace(result=lambda: rows)


def failed_rec(cause="wrong_credentials", text="The password you entered is incorrect."):
    return {"ok": False, "error": f"{cause}: x | page: {text}", "cause": cause, "retryable": False,
            "page_text": text, "attempted_at": FETCH, "reason": "first", "seconds": 9.0,
            "final_url": "https://accounts.plex.com/", "screenshot": "gs://b/x.png", "execution": "e", "job": "j"}


def test_failed_login_mails_only_the_login_address_with_the_cause(monkeypatch):
    import email_utils
    sent = []
    monkeypatch.setattr(email_utils, "send_ops_alert", lambda alert, to=None: sent.append((alert, to)) or True)
    monkeypatch.setattr(r, "LOGIN_ALERT_EMAILS", "ops@example.com")
    audit = r.Audit("run1", FETCH, dry_run=False)
    audit.logins = [failed_rec()]
    bq = LoginBQ()
    audit.mail_failed_logins(bq)
    alert, to = sent[0]
    assert to == ["ops@example.com"] and "rejected the username or password" in alert["headline"]
    assert "did not retry" in alert["summary"] and "24 h" in alert["summary"] and "2 run(s) in a row" in alert["summary"]
    assert any("gcloud secrets versions add plex-portal-password" in st for st in alert["steps"])
    assert bq.inserts and "login-alert" in bq.inserts[0]


def test_failed_login_not_mailed_twice_a_day_or_after_a_good_retry(monkeypatch):
    import email_utils
    sent = []
    monkeypatch.setattr(email_utils, "send_ops_alert", lambda alert, to=None: sent.append(alert) or True)
    audit = r.Audit("run1", FETCH, dry_run=False)
    audit.logins = [failed_rec()]
    audit.mail_failed_logins(LoginBQ(mailed=1))
    audit.logins = [failed_rec("timeout", ""), dict(failed_rec(), ok=True)]
    audit.mail_failed_logins(LoginBQ())
    assert sent == []


def cause(err, text="", url="https://vox.on.plex.com/x"):
    c = r.classify_login(err, text, url)
    return c[0], c[3]


def test_login_causes():
    assert cause("x", "The password you entered is incorrect") == ("wrong_credentials", False)
    assert cause("x", "Invalid login or password") == ("wrong_credentials", False)
    assert cause("x", "Authentication failed") == ("wrong_credentials", False)
    assert cause("x", "Unable to sign in. Try again.") == ("wrong_credentials", False)
    assert cause("x", "Your account has been deactivated") == ("locked", False)
    assert cause("x", "Too many login attempts") == ("locked", False)
    assert cause("x", "Enter the verification code from your authenticator") == ("verification", False)
    assert cause("x", "Your password has expired") == ("password_change", False)
    assert cause("Timeout 118615ms exceeded.") == ("timeout", True)
    assert cause("x", "503 Service Unavailable") == ("plex_down", True)
    assert cause("net::ERR_NAME_NOT_RESOLVED") == ("network", True)


def test_login_causes_do_not_overreach():
    # the "Reset password" link on every sign-in page is not a password change
    assert cause("wait_for_url: Timeout 120000ms exceeded", "Forgot your password? Reset password") == ("timeout", True)
    # a timeout that stopped on Plex's sign-in page is a rejected login: never retried
    assert cause("wait_for_url: Timeout 120000ms exceeded", "Sign in",
                 "https://accounts.plex.com/u/login")[1] is False
    # words we don't know: not retried
    assert cause("login did not reach the SQL Development Environment", "Welcome") == ("unknown", False)
    # "Cookies are disabled" is not a locked account; a URL with 503 in it is not Plex down
    assert cause("x", "Cookies are disabled in this browser")[0] == "unknown"
    assert cause("x", "", "https://vox.on.plex.com/503abc")[0] == "unknown"


def test_password_never_logged():
    audit = r.Audit("run1", FETCH, dry_run=False)

    class P(FakePage):
        text = "Hello s3cret-pw"

    def real(pg, user, password):
        raise RuntimeError(f"fill('#pwd', '{password}') timed out")

    try:
        audit.wrap_login(real)(P(), "u", "s3cret-pw")
    except Exception as e:
        assert "s3cret-pw" not in str(e)
    assert "s3cret-pw" not in str(audit.logins)


def test_non_retryable_failure_raises_login_failed():
    audit = r.Audit("run1", FETCH, dry_run=False)

    class P(FakePage):
        text = "The password you entered is incorrect"

    def real(pg, user, password):
        raise RuntimeError("login did not reach the SQL Development Environment")
    try:
        audit.wrap_login(real)(P(), "u", "p")
        raise AssertionError("should raise")
    except r.LoginFailed:
        pass


class SuspendBQ:
    def __init__(self, rows):
        self.rows = rows

    def query(self, sql, job_config=None):
        from types import SimpleNamespace
        return SimpleNamespace(result=lambda: [SimpleNamespace(**x) for x in self.rows])


def test_login_suspended_after_credential_failure_only():
    t = FETCH - dt.timedelta(hours=3)
    assert r.login_suspended(SuspendBQ([{"ok": False, "error": "wrong_credentials: x", "attempted_at": t}]))
    assert r.login_suspended(SuspendBQ([{"ok": False, "error": "timeout: x", "attempted_at": t}])) is None
    assert r.login_suspended(SuspendBQ([{"ok": True, "error": None, "attempted_at": t}])) is None
    assert r.login_suspended(SuspendBQ([])) is None


def test_screenshot_paths_are_dated_in_mountain_time():
    audit = r.Audit("abc", FETCH, dry_run=True)
    assert audit.prefix == "plex-screens/2026/11/10/1315-MT_abc"


def test_screens_digest_renders(monkeypatch):
    import email_utils
    got = []
    monkeypatch.setattr(email_utils, "send_ops_alert", lambda alert, to=None: got.append(alert) or True)
    ok = email_utils.send_screens_digest({
        "run_id": "r1", "took": 300, "problems": 0,
        "groups": [{"name": "Label Design", "label": "ODBC, data to 11-10 13:02 MT", "lag": 12.0}],
        "screens": [{"screen": "releases", "verdict": "current", "rows": 461, "seconds": 170.2,
                     "compared": 455, "missing": 0, "differ": 0, "error": None}],
        "logins_ok": 1, "logins_failed": 0, "screenshots": "gs://b/plex-screens/2026/11/10/1320-MT_r1/"})
    assert ok and got[0]["headline"] == "Screens Digest: all current" and got[0]["severity"] == "info"
    subject, html_content, text = email_utils.render_ops_alert(got[0])
    assert subject.startswith("[Plex ETL] - Screens Digest") and "461 rows" in text and "{{" not in html_content


def test_new_release_counts_at_once_when_odbc_is_already_stale():
    # 11-10: order 675's release first seen on the screen; ODBC's newest change 08:08 MT,
    # screen read 10:20 MT: behind now, not 4 h later.
    scr = {"9": {"num": 9, "event": None, "m": {"status_key": 1, "quantity": 500.0, "order_status": "Pending Fulfillment"}}}
    od = {"1": odbc({"num": 1, "event": None, "m": {"status_key": 1, "quantity": 1.0, "order_status": "Pending Fulfillment"}},
                    updated=FETCH - dt.timedelta(minutes=10))}
    stale = FETCH - dt.timedelta(minutes=132)
    _, _, v, lag, _ = r.compare("releases", scr, od, 1, None, {}, FETCH, odbc_newest_change=stale)
    assert v == "behind" and lag == 132
    _, _, v2, _, _ = r.compare("releases", scr, od, 1, None, {}, FETCH,
                               odbc_newest_change=FETCH - dt.timedelta(minutes=20))
    assert v2 == "current"


def test_pipeline_not_behind_during_normal_odbc_lag():
    # created 100 min ago, our load 10 min ago: ODBC may have delivered it after the load
    scr = {"1": prod(1, 100)}
    od = {"1": odbc(prod(1, 100))}
    _, _, verdict, _, _ = r.compare("production", scr, od, 1, od["1"]["event"], {}, FETCH,
                                    raw=set(), raw_modified=FETCH - dt.timedelta(minutes=10))
    assert verdict == "current"


# ── 2026-11-11: easing the alerts after the 11-10 afternoon ─────────────────────

def test_missing_record_at_odbcs_newest_minute_is_lag_not_hole():
    # 11-10 20:21 MT: five shipment lines at 16:10, ODBC's newest also 16:10 (same minute,
    # lower key): ODBC stopped there; that is a delay, not a hole.
    t = FETCH - dt.timedelta(minutes=250)
    scr = {"5": {"num": 5, "event": t, "m": {"quantity": 1.0}}, "9": {"num": 9, "event": t, "m": {"quantity": 1.0}}}
    od = {"9": odbc(scr["9"])}
    counts, _, verdict, lag, why = r.compare("history", scr, od, 9, t, {}, FETCH)
    assert counts["missing_tail"] == 1 and not counts["missing_hole"] and verdict == "behind" and not why


def test_odbc_extras_while_odbc_is_stale_are_not_diverged():
    # 11-10: five releases ODBC still showed open, twice, while ODBC's newest change was 4 h old
    scr = {"1": prod(1, 100)}
    od = {"1": odbc(prod(1, 100)), "2": odbc(prod(2, 90))}
    _, _, stale, _, _ = r.compare("releases", scr, od, 2, None, {}, FETCH, prev_extra=frozenset({"2"}),
                                  odbc_newest_change=FETCH - dt.timedelta(minutes=250))
    _, _, fresh, _, _ = r.compare("releases", scr, od, 2, None, {}, FETCH, prev_extra=frozenset({"2"}),
                                  odbc_newest_change=FETCH - dt.timedelta(minutes=20))
    assert stale == "current" and fresh == "diverged"


def test_needs_action_only_past_the_alert_lag():
    assert not r.needs_action({"verdict": "current"})
    assert not r.needs_action({"verdict": "behind", "odbc_lag_min": 337})
    assert r.needs_action({"verdict": "behind", "odbc_lag_min": r.ALERT_LAG_MIN + 1})
    for v in ("diverged", "odbc_unreachable", "pipeline_behind", "screens_failed"):
        assert r.needs_action({"verdict": v})


def test_quiet_switch_mails_nothing_and_its_return_neither(monkeypatch):
    sent = set()
    monkeypatch.setattr(r, "alert_sent_recently", lambda c, kind, hours=24: kind in sent)
    behind = {"history": {"screen": "history", "verdict": "behind", "odbc_lag_min": 254, "detail": None},
              "revenue": {"screen": "revenue", "verdict": "behind", "odbc_lag_min": 240, "detail": None}}
    on = r.decide_alerts(None, {"revenue": {"use_live": False}}, {"revenue": {"use_live": True}}, behind)
    assert not [k for k, _ in on if k.startswith("live-")]
    clean = {n: dict(v, verdict="current", odbc_lag_min=0) for n, v in behind.items()}
    off = r.decide_alerts(None, {"revenue": {"use_live": True}}, {"revenue": {"use_live": False}}, clean)
    assert not off
    long = {n: dict(v, odbc_lag_min=r.ALERT_LAG_MIN + 30) for n, v in behind.items()}
    on2 = r.decide_alerts(None, {"revenue": {"use_live": True}}, {"revenue": {"use_live": True}}, long)
    assert [k for k, _ in on2] == ["live-on:revenue"]
    sent.add("live-on:revenue")
    off2 = r.decide_alerts(None, {"revenue": {"use_live": True}}, {"revenue": {"use_live": False}}, clean)
    assert [k for k, _ in off2] == ["live-off:revenue"]


def test_screens_digest_quiet_lag_is_info(monkeypatch):
    import email_utils
    got = []
    monkeypatch.setattr(email_utils, "send_ops_alert", lambda alert, to=None: got.append(alert) or True)
    email_utils.send_screens_digest({"run_id": "r2", "took": 180, "problems": 0, "quiet_behind": 2,
                                     "alert_lag_min": 360, "groups": [], "screens": []})
    assert got[0]["severity"] == "info" and got[0]["headline"] == "Screens Digest: ODBC catching up"
    assert "under 6 h" in got[0]["summary"] and not got[0]["steps"]
