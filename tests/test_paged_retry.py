"""Tests for guarded paged reads (main.py run_query / guarded_read /
query_plex_paged with a PlexSession), added 2026-11-05 for the Plex prod ODBC
incident (OPEN_ITEMS D28).

    python tests/test_paged_retry.py            # plain asserts, prints OK
    python -m pytest tests/test_paged_retry.py  # same tests under pytest

No Plex, BigQuery or SendGrid needed: a fake Plex answers the paging SQL and
can be told to hang, reset (08S01) or time out (HYT00) on chosen queries.
"""
import os
import re
import sys
import threading
import time
from pathlib import Path

import pyodbc
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("GCP_PROJECT", "voxdatalake")
os.environ.setdefault("BQ_DATASET", "PlexTest")

import main as m  # noqa: E402

KEY = "Part_Operation_Key"
RELEASE = threading.Event()   # set at the end so hung fake reads can finish


class FakePlex:
    """One table on a fake Plex. Every connection to it shares `sql` (the log
    of what was sent) and `faults`: a list of (predicate(sql, n), action) where
    action is "hang", "reset", "hyt" or "bad"; each fault fires once."""

    def __init__(self, rows):
        self.rows, self.sql, self.faults, self.connects = rows, [], [], 0
        self.timeouts_seen = []

    def connect(self):
        self.connects += 1
        return FakeConn(self)


class FakeConn:
    def __init__(self, plex):
        self.plex, self.timeout, self.closed = plex, 0, False

    def close(self):
        self.closed = True

    def cursor(self):
        assert not self.closed, "a dropped connection was used again"
        plex = self.plex
        plex.timeouts_seen.append(self.timeout)

        class C:
            description = [(KEY, int), ("Workcenter_Key", int), ("Ideal_Rate", float)]

            def execute(self, sql):
                n = len(plex.sql)
                plex.sql.append(sql)
                for fault in list(plex.faults):
                    pred, action = fault
                    if pred(sql, n):
                        plex.faults.remove(fault)
                        if action == "hang":
                            RELEASE.wait()
                            raise pyodbc.OperationalError("08S01", "released")
                        if action == "reset":
                            raise pyodbc.OperationalError(
                                "08S01", "[08S01] [DataDirect][ODBC OpenAccess SDK driver]"
                                         "connection reset by peer (2310) (SQLExecDirectW)")
                        if action == "hyt":
                            raise pyodbc.OperationalError("HYT00", "[HYT00] Query timeout expired")
                        if action == "bad":
                            raise pyodbc.ProgrammingError("42S02", "[42S02] Base table not found")
                rows = plex.rows
                if sql.startswith("SELECT COUNT(*)"):
                    self.out = [(len(rows),)]
                elif mt := re.match(rf"SELECT TOP (\d+) \* FROM \w+ WHERE {KEY} (> (\d+)|IS NOT NULL) ORDER BY {KEY}$", sql):
                    n_, last = int(mt.group(1)), mt.group(3)
                    pool = sorted((r for r in rows if r[0] is not None and (last is None or r[0] > int(last))),
                                  key=lambda r: r[0])
                    self.out = pool[:n_]
                elif re.match(rf"SELECT \* FROM \w+ WHERE {KEY} IS NULL$", sql):
                    self.out = [r for r in rows if r[0] is None]
                elif mt := re.match(rf"SELECT \* FROM \w+ WHERE {KEY} = (\d+)$", sql):
                    self.out = [r for r in rows if r[0] == int(mt.group(1))]
                elif re.match(r"SELECT \* FROM \w+$", sql):
                    self.out = list(rows)
                else:
                    raise AssertionError(sql)

            def fetchall(self):
                return self.out

            def cancel(self):
                pass

            def close(self):
                pass

        return C()


def _rows():
    # Clustered, repeating keys, like Part_v_Approved_Workcenter.
    return [(op, wc, op * 0.5 + wc) for op in range(1000, 1060) for wc in range(1, 5)]


def _setup(**overrides):
    """Short, test-sized limits; returns a restore function."""
    values = dict(PLEX_QUERY_TIMEOUT_SECONDS=0.2, PLEX_QUERY_GRACE_SECONDS=0.1, PLEX_PAGE_ATTEMPTS=3,
                  PLEX_PAGE_BACKOFF_SECONDS=0, PLEX_MAX_HUNG_QUERIES=4)
    values.update(overrides)
    saved = {k: getattr(m, k) for k in values}
    for k, v in values.items():
        setattr(m, k, v)
    saved_sleep, m.sleep = m.sleep, lambda s: None

    def restore():
        for k, v in saved.items():
            setattr(m, k, v)
        m.sleep = saved_sleep
    return restore


def _page(n):
    """Predicate: the n-th TOP page query (1-based) sent so far."""
    def pred(sql, _):
        if not sql.startswith("SELECT TOP"):
            return False
        pred.count += 1
        return pred.count == n
    pred.count = 0
    return pred


def _pull(plex, session=None):
    s = session or m.PlexSession(plex.connect(), plex.connect)
    return s, m.query_plex_paged(s, "Part_v_Approved_Workcenter", "", KEY, 40)


def _same(df, rows):
    return sorted(map(tuple, df.itertuples(index=False, name=None))) == sorted(rows)


# ── run_query ──────────────────────────────────────────────────────────────────
def test_a_hung_read_is_abandoned_on_the_wall_clock():
    restore = _setup()
    try:
        plex = FakePlex(_rows())
        plex.faults.append((lambda sql, n: True, "hang"))
        started = time.monotonic()
        try:
            m.run_query(plex.connect(), "SELECT * FROM V", 0.2, 0.1)
        except m.QueryTimeout:
            assert time.monotonic() - started < 2
        else:
            raise AssertionError("a hung read must raise QueryTimeout")
    finally:
        restore()


def test_the_driver_is_asked_for_a_query_timeout_on_that_cursor_only():
    plex = FakePlex(_rows())
    conn = plex.connect()
    conn.timeout = 0
    desc, rows = m.run_query(conn, "SELECT * FROM V", 7, 1)
    assert plex.timeouts_seen == [7], "SQL_ATTR_QUERY_TIMEOUT is set when the cursor is made"
    assert conn.timeout == 0, "the connection's own timeout is restored for unpaged reads"
    assert len(rows) == len(_rows()) and desc[0][0] == KEY


def test_timeout_zero_runs_inline_like_before():
    plex = FakePlex(_rows())
    _, rows = m.run_query(plex.connect(), "SELECT * FROM V", 0, 0)
    assert len(rows) == len(_rows())


# ── classification ─────────────────────────────────────────────────────────────
def test_what_is_retried():
    assert m.page_retryable(m.QueryTimeout("x"))
    assert m.page_retryable(pyodbc.OperationalError("08S01", "connection reset by peer (2310)"))
    assert m.page_retryable(pyodbc.OperationalError("08001", "unable to connect"))
    assert m.page_retryable(pyodbc.OperationalError("HYT00", "timeout expired"))
    assert m.query_hung(pyodbc.OperationalError("HYT00", "timeout expired"))
    assert not m.query_hung(pyodbc.OperationalError("08S01", "reset"))
    assert not m.page_retryable(pyodbc.ProgrammingError("42S02", "not found"))
    assert not m.page_retryable(pyodbc.InterfaceError("28000", "login failed"))
    assert not m.page_retryable(RuntimeError("page_key is not an integer"))


# ── retry and resume ───────────────────────────────────────────────────────────
def test_a_hung_page_is_resent_on_a_new_session_and_the_pull_resumes():
    restore = _setup()
    try:
        plex = FakePlex(_rows())
        plex.faults.append((_page(3), "hang"))
        s, df = _pull(plex)
        assert _same(df, _rows()) and "page_note" not in df.attrs
        assert s.hung == 1 and s.retries == 1 and plex.connects == 2
        # Resumed, not restarted: page 1 (IS NOT NULL) was sent once, and
        # page 3's SQL exactly twice (the hung send and the retry).
        assert sum("IS NOT NULL ORDER BY" in q for q in plex.sql) == 1
        third = [q for q in plex.sql if q.startswith("SELECT TOP")][2]
        assert plex.sql.count(third) == 2
    finally:
        restore()


def test_a_reset_page_is_resent_without_counting_as_a_hang():
    restore = _setup()
    try:
        plex = FakePlex(_rows())
        plex.faults.append((_page(2), "reset"))
        s, df = _pull(plex)
        assert _same(df, _rows())
        assert s.hung == 0 and s.retries == 1 and plex.connects == 2
    finally:
        restore()


def test_a_driver_timeout_is_a_hang_and_is_retried():
    restore = _setup()
    try:
        plex = FakePlex(_rows())
        plex.faults.append((lambda sql, n: sql.startswith("SELECT COUNT"), "hyt"))
        s, df = _pull(plex)
        assert _same(df, _rows()) and s.hung == 1 and s.retries == 1
    finally:
        restore()


def test_a_small_view_single_pull_is_guarded_too():
    restore = _setup()
    try:
        plex = FakePlex(_rows()[:10])
        plex.faults.append((lambda sql, n: re.match(r"SELECT \* FROM \w+$", sql) is not None, "reset"))
        s, df = _pull(plex)
        assert len(df) == 10 and df.attrs["pages"] == 1 and s.retries == 1
        assert not any("TOP" in q for q in plex.sql)
    finally:
        restore()


def test_a_page_that_keeps_failing_fails_the_table_after_its_attempts():
    restore = _setup()
    try:
        plex = FakePlex(_rows())
        for _ in range(3):
            plex.faults.append((lambda sql, n: sql.startswith("SELECT TOP"), "reset"))
        try:
            _pull(plex)
        except pyodbc.OperationalError as exc:
            assert exc.args[0] == "08S01"
        else:
            raise AssertionError("three failed sends of one page must fail the table")
        assert plex.connects == 3, "first session plus two reconnects"
    finally:
        restore()


def test_a_bad_query_is_not_retried():
    restore = _setup()
    try:
        plex = FakePlex(_rows())
        plex.faults.append((lambda sql, n: True, "bad"))
        try:
            _pull(plex)
        except pyodbc.ProgrammingError:
            pass
        else:
            raise AssertionError("42S02 must propagate")
        assert plex.connects == 1 and len(plex.sql) == 1
    finally:
        restore()


def test_after_too_many_hangs_nothing_more_is_sent():
    restore = _setup(PLEX_MAX_HUNG_QUERIES=2)
    try:
        plex = FakePlex(_rows())
        plex.faults += [(_page(1), "hang"), (_page(2), "hang")]
        s = m.PlexSession(plex.connect(), plex.connect)
        try:
            _pull(plex, s)
        except m.PlexUnresponsive:
            pass
        else:
            raise AssertionError("the second hang must stop the guarded path")
        assert s.conn is None, "a hung connection is dropped, never reused or closed in the foreground"
        sent = len(plex.sql)
        try:
            _pull(plex, s)          # the next extraction in the same run
        except m.PlexUnresponsive:
            pass
        else:
            raise AssertionError("later paged extractions must fail at once")
        assert len(plex.sql) == sent, "nothing more is sent to Plex"
    finally:
        restore()


def test_a_failed_reconnect_fails_the_table_and_the_next_one_reconnects():
    restore = _setup()
    try:
        plex = FakePlex(_rows())
        plex.faults.append((_page(2), "reset"))
        calls = {"n": 0}

        def flaky_connect():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("3 attempt(s); last: no answer from Plex within 60s")
            return plex.connect()

        s = m.PlexSession(plex.connect(), flaky_connect)
        try:
            _pull(plex, s)
        except ConnectionError as exc:
            assert "reconnect" in str(exc)
        else:
            raise AssertionError("a failed reconnect must fail the table")
        assert s.conn is None
        _, df = _pull(plex, s)
        assert _same(df, _rows()) and s.conn is not None
    finally:
        restore()


def test_a_bare_connection_is_bounded_but_not_retried():
    restore = _setup()
    try:
        plex = FakePlex(_rows())
        plex.faults.append((_page(2), "reset"))
        try:
            m.query_plex_paged(plex.connect(), "Part_v_Approved_Workcenter", "", KEY, 40)
        except pyodbc.OperationalError:
            pass
        else:
            raise AssertionError("without a reconnect function a reset propagates")
        assert plex.connects == 1
    finally:
        restore()


# ── the YAML ───────────────────────────────────────────────────────────────────
PAGED_PIPELINES = ["sales_orders", "part_on_hand_inventory", "part_routing"]


def _extractions(path):
    return yaml.safe_load(path.read_text())["extractions"]


def test_scoped_pipelines_page_every_extraction_identically_in_prod_and_test():
    for p in PAGED_PIPELINES:
        prod = _extractions(ROOT / "reports" / f"{p}.yaml")
        test = _extractions(ROOT / "reports" / "test" / f"{p}.yaml")
        shape = lambda xs: [(x["plex_view"], x["bq_table"], x.get("page_key"), x.get("page_size")) for x in xs]
        assert shape(prod) == shape(test), f"{p}: prod and test extraction lists differ"
        for x in prod:
            assert x.get("page_key"), f"{p}: {x['plex_view']} has no page_key"
            assert m.validate_extraction(x) == "", (p, m.validate_extraction(x))


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print("OK")
    finally:
        RELEASE.set()


def teardown_module(module):
    RELEASE.set()
