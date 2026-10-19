"""Tests for the change probe (main.py) and the run emails (email_utils.py).

No Plex, BigQuery or SendGrid needed: a fake ODBC connection answers the probe
queries, and SendGrid's client is replaced so the rendered email is captured
instead of sent.

    python tests/test_probe.py            # plain asserts, prints OK
    python -m pytest tests/test_probe.py  # same tests under pytest

Set WRITE_EMAIL_PREVIEWS=dir to also save the rendered HTML emails there.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GCP_PROJECT", "voxdatalake")
os.environ.setdefault("BQ_DATASET", "PlexTest")

import main as m  # noqa: E402
import email_utils  # noqa: E402


# ── fakes ──────────────────────────────────────────────────────────────────────
class FakeCursor:
    def __init__(self, answers, seen):
        self.answers, self.seen, self.rows = answers, seen, []

    def execute(self, sql):
        self.seen.append(sql)
        for needle, rows in self.answers.items():
            if needle in sql:
                if isinstance(rows, Exception):
                    raise rows
                self.rows = rows
                return
        raise AssertionError(f"unexpected probe SQL: {sql}")

    def fetchall(self):
        return self.rows

    def close(self):
        pass


class FakeConn:
    def __init__(self, answers):
        self.answers, self.seen = answers, []

    def cursor(self):
        return FakeCursor(self.answers, self.seen)


def auto_config(**extra):
    cfg = {
        "report_name": "sales_orders",
        "probe_mode": "auto",
        "_config_sha": "abc",
        "extractions": [
            {"plex_view": "Sales_v_PO_Line", "bq_table": "raw_Sales_v_PO_Line",
             "filter": "", "probe": ["Update_Date", "PO_Line_Key"]},
            {"plex_view": "Part_v_Flat_BOM", "bq_table": "raw_Part_v_Flat_BOM", "filter": ""},
            {"plex_view": "Part_v_Part", "bq_table": "raw_Part_v_Part_obsolete",
             "filter": "WHERE Part_Status IN ('Obsolete')", "probe": ["Updated_Date"]},
        ],
        "bq_view": [{"name": "v1", "sql": "SELECT 1"}],
    }
    cfg.update(extra)
    return cfg


ANSWERS = {
    "FROM Sales_v_PO_Line": [(591, "2026-10-19 08:08:27", 16658916)],
    "FROM Part_v_Flat_BOM": [(235550,)],
    "FROM Part_v_Part WHERE": [(12, "2026-10-16 18:31:00")],
}


# ── run modes ──────────────────────────────────────────────────────────────────
def test_may_skip_rules():
    assert m.probe_may_skip("auto", "probe")
    assert not m.probe_may_skip("auto", "scheduled"), "a plain nightly/manual run of an auto pipeline is full"
    assert not m.probe_may_skip("auto", "full")
    assert m.probe_may_skip("explicit", "scheduled"), "label_design's hourly runs keep probing"
    assert m.probe_may_skip("explicit", "probe")
    assert not m.probe_may_skip("explicit", "full")
    assert not m.probe_may_skip("auto", "retry")


def test_probe_kind():
    assert m.probe_kind({"probe_mode": "auto"}) == "auto"
    assert m.probe_kind({"probe": "auto"}) == "", "the old key must not be honoured (older images crash on it)"
    assert m.probe_kind({"probe": {"queries": [{"plex_view": "X", "columns": ["a"]}]}}) == "explicit"
    assert m.probe_kind({}) == ""
    assert m.probe_kind({"probe": {"queries": []}}) == ""


# ── auto probe ─────────────────────────────────────────────────────────────────
def test_auto_probe_sql_matches_extractions():
    conn = FakeConn(ANSWERS)
    fp, snap = m.run_probe(conn, auto_config())
    assert conn.seen == [
        "SELECT COUNT(*), MAX(Update_Date), MAX(PO_Line_Key) FROM Sales_v_PO_Line",
        "SELECT COUNT(*) FROM Part_v_Flat_BOM",
        "SELECT COUNT(*), MAX(Updated_Date) FROM Part_v_Part WHERE Part_Status IN ('Obsolete')",
    ], conn.seen
    assert snap["raw_Sales_v_PO_Line"] == "591|2026-10-19 08:08:27|16658916"
    assert snap["raw_Part_v_Flat_BOM"] == "235550"
    assert m._CONFIG_SNAPSHOT_KEY in snap
    assert len(fp) == 32


def test_fingerprint_is_stable_and_sensitive():
    fp1, _ = m.run_probe(FakeConn(ANSWERS), auto_config())
    fp2, _ = m.run_probe(FakeConn(ANSWERS), auto_config())
    assert fp1 == fp2
    changed = dict(ANSWERS, **{"FROM Part_v_Flat_BOM": [(235551,)]})
    fp3, snap3 = m.run_probe(FakeConn(changed), auto_config())
    assert fp3 != fp1
    _, snap1 = m.run_probe(FakeConn(ANSWERS), auto_config())
    assert m.changed_sources(snap1, snap3) == ["raw_Part_v_Flat_BOM"]


def test_config_or_sql_change_changes_fingerprint():
    """OPEN_ITEMS L10: a deployed YAML/SQL change must never be skipped."""
    fp1, snap1 = m.run_probe(FakeConn(ANSWERS), auto_config())
    fp2, snap2 = m.run_probe(FakeConn(ANSWERS), auto_config(_config_sha="def"))
    fp3, snap3 = m.run_probe(FakeConn(ANSWERS), auto_config(bq_view=[{"name": "v1", "sql": "SELECT 2"}]))
    assert fp1 != fp2 and fp1 != fp3
    assert m.changed_sources(snap1, snap2) == [m._CONFIG_SNAPSHOT_KEY]
    assert m.changed_sources(snap1, snap3) == [m._CONFIG_SNAPSHOT_KEY]


def test_auto_probe_fails_open():
    def inconclusive(cfg, answers=ANSWERS):
        try:
            m.run_probe(FakeConn(answers), cfg)
        except m.ProbeInconclusive:
            return True
        return False
    assert inconclusive(auto_config(), dict(ANSWERS, **{"FROM Part_v_Flat_BOM": RuntimeError("ODBC down")}))
    bad = auto_config()
    bad["extractions"][0]["probe"] = ["Update_Date; DROP"]
    assert inconclusive(bad), "a non-identifier probe column must not reach SQL"
    assert inconclusive(auto_config(extractions=[])), "nothing to probe is inconclusive, not 'unchanged'"
    assert inconclusive(auto_config(), dict(ANSWERS, **{"FROM Part_v_Flat_BOM": []})), "aggregate must return one row"


def test_changed_sources_without_history():
    assert m.changed_sources(None, {"a": "1", "b": "2"}) == ["a", "b"]
    assert m.changed_sources({"a": "1"}, {"a": "1", "b": "2"}) == ["b"]
    assert m.changed_sources({"a": "1", "gone": "x"}, {"a": "1"}) == ["gone"]


# ── explicit probe (label_design) keeps working ────────────────────────────────
def test_explicit_probe_still_binds():
    cfg = {
        "_config_sha": "x",
        "probe": {"queries": [
            {"plex_view": "Sales_v_Release_Status", "columns": ["Release_Status_Key"],
             "filter": "WHERE t.Release_Status = 'Label Design'", "bind": "status_keys"},
            {"plex_view": "Sales_v_Release", "columns": ["Release_Key", "PO_Line_Key"],
             "filter": "WHERE t.Release_Status_Key IN ({status_keys})"},
        ]},
    }
    conn = FakeConn({
        "FROM Sales_v_Release_Status": [(7,)],
        "FROM Sales_v_Release AS t WHERE t.Release_Status_Key IN (7)": [(1, 10), (2, 20)],
    })
    fp, snap = m.run_probe(conn, cfg)
    assert conn.seen[1].endswith("IN (7)")
    assert snap["2. Sales_v_Release(Release_Key,PO_Line_Key)"].startswith("2 rows:")


def test_explicit_queries_on_same_view_do_not_collide():
    q = {"plex_view": "Sales_v_Release", "columns": ["Release_Key"]}
    cfg = {"_config_sha": "x", "probe": {"queries": [dict(q, filter="WHERE t.A = 1"), dict(q, filter="WHERE t.A = 2")]}}
    _, snap = m.run_probe(FakeConn({"t.A = 1": [(1,)], "t.A = 2": [(2,)]}), cfg)
    assert len([k for k in snap if "Sales_v_Release" in k]) == 2


def test_cursor_failure_is_inconclusive_not_fatal():
    class BrokenConn:
        def cursor(self):
            raise RuntimeError("connection reset")
    try:
        m.run_probe(BrokenConn(), auto_config())
    except m.ProbeInconclusive:
        return
    raise AssertionError("a cursor error must be inconclusive")


# ── paging (query_plex_paged) ──────────────────────────────────────────────────
import re as _re


class PagingConn:
    """A tiny Plex: one table, answers COUNT(*), TOP-keyset pages and the
    boundary-key query exactly the way query_plex_paged() writes them."""

    def __init__(self, rows, key="Part_Operation_Key"):
        self.rows, self.key, self.sql = rows, key, []

    def cursor(self):
        conn = self

        class C:
            description = [("Part_Operation_Key", int), ("Workcenter_Key", int), ("Ideal_Rate", float)]

            def execute(self, sql):
                conn.sql.append(sql)
                k = conn.key
                if sql.startswith("SELECT COUNT(*)"):
                    self.out = [(len(conn.rows),)]
                elif m_ := _re.match(rf"SELECT TOP (\d+) \* FROM \w+ WHERE {k} (> (\d+)|IS NOT NULL) ORDER BY {k}$", sql):
                    n, last = int(m_.group(1)), m_.group(3)
                    pool = sorted((r for r in conn.rows if r[0] is not None and (last is None or r[0] > int(last))),
                                  key=lambda r: r[0])
                    self.out = pool[:n]
                elif _re.match(rf"SELECT \* FROM \w+ WHERE {k} IS NULL$", sql):
                    self.out = [r for r in conn.rows if r[0] is None]
                elif m_ := _re.match(rf"SELECT \* FROM \w+ WHERE {k} = (\d+)$", sql):
                    self.out = [r for r in conn.rows if r[0] == int(m_.group(1))]
                elif sql.startswith("SELECT * FROM"):
                    self.out = list(conn.rows)
                else:
                    raise AssertionError(sql)

            def fetchall(self):
                return self.out

            def close(self):
                pass

        return C()


def _rows():
    # Clustered, repeating keys: like the real Approved_Workcenter table.
    rows = []
    for op in list(range(1000, 1040)) + list(range(900000, 900003)):
        for wc in range(1, 8 if op % 3 else 3):
            rows.append((op, wc, op * 0.5 + wc))
    return rows


def test_paging_returns_every_row_once_without_splitting_keys():
    rows = _rows()
    conn = PagingConn(rows)
    df = m.query_plex_paged(conn, "Part_v_Approved_Workcenter", "", "Part_Operation_Key", 50)
    got = sorted(map(tuple, df.itertuples(index=False, name=None)))
    assert got == sorted(rows), (len(got), len(rows))
    assert df.attrs["pages"] > 1 and "page_note" not in df.attrs
    assert any(q.startswith("SELECT TOP 50 ") for q in conn.sql)
    assert not any("LIMIT" in q for q in conn.sql), "Plex rejects LIMIT"


def test_paging_keeps_rows_with_a_null_key():
    rows = _rows() + [(None, 9, 1.0), (None, 10, 2.0)]
    df = m.query_plex_paged(PagingConn(rows), "Part_v_Approved_Workcenter", "", "Part_Operation_Key", 50)
    assert len(df) == len(rows) and "page_note" not in df.attrs


def test_float_sums_are_rounded_in_the_snapshot():
    cfg = auto_config(extractions=[{"plex_view": "V", "bq_table": "raw_v", "filter": "", "probe": ["sum:Rate"]}])
    _, a = m.run_probe(FakeConn({"FROM V": [(3, 645305690.6000001)]}), cfg)
    _, b = m.run_probe(FakeConn({"FROM V": [(3, 645305690.5999999)]}), cfg)
    assert a["raw_v"] == b["raw_v"] == "3|645305690.6000"


def test_paging_small_table_is_one_plain_pull():
    conn = PagingConn(_rows()[:10])
    df = m.query_plex_paged(conn, "Part_v_Approved_Workcenter", "", "Part_Operation_Key", 50)
    assert len(df) == 10 and df.attrs["pages"] == 1
    assert not any("TOP" in q for q in conn.sql)


def test_paging_reports_a_count_mismatch_instead_of_failing():
    rows = _rows()
    conn = PagingConn(rows)
    original = conn.cursor

    def lying_cursor():
        c = original()
        real = c.execute

        def execute(sql):
            real(sql)
            if sql.startswith("SELECT COUNT(*)"):
                c.out = [(len(rows) + 5,)]
        c.execute = execute
        return c
    conn.cursor = lying_cursor
    df = m.query_plex_paged(conn, "Part_v_Approved_Workcenter", "", "Part_Operation_Key", 50)
    assert "counted" in df.attrs.get("page_note", "")


def test_paging_validation():
    base = {"plex_view": "Part_v_Approved_Workcenter", "bq_table": "raw_x", "page_key": "Part_Operation_Key"}
    assert m.validate_extraction(base) == ""
    assert "page_size" in m.validate_extraction(dict(base, page_size=5))
    assert "page_size" in m.validate_extraction(dict(base, page_size="big"))
    assert "identifier" in m.validate_extraction(dict(base, page_key="Key; DROP"))
    assert "WHERE" in m.validate_extraction(dict(base, filter="ORDER BY x"))
    assert m.validate_extraction(dict(base, filter="where\n  Active = 1")) == "", "multi-line/lower-case WHERE is fine"
    assert "ORDER BY" in m.validate_extraction(dict(base, filter="WHERE a = 1 ORDER BY b"))
    assert "date_col" in m.validate_extraction(dict(base, date_col="Update_Date"))


def test_auto_probe_sum_columns():
    cfg = auto_config(extractions=[{"plex_view": "Part_v_Approved_Workcenter", "bq_table": "raw_aw",
                                    "filter": "", "probe": ["Part_Operation_Key", "sum:Ideal_Rate", "sum:Crew_Size"]}])
    conn = FakeConn({"FROM Part_v_Approved_Workcenter": [(64942, 66391187, 1234.5, 900)]})
    _, snap = m.run_probe(conn, cfg)
    assert conn.seen == ["SELECT COUNT(*), MAX(Part_Operation_Key), SUM(Ideal_Rate), SUM(Crew_Size) "
                         "FROM Part_v_Approved_Workcenter"], conn.seen
    assert snap["raw_aw"] == "64942|66391187|1234.5000|900"
    keysum = auto_config(extractions=[{"plex_view": "X", "bq_table": "raw_x", "filter": "", "probe": ["sum:workcenter_key"]}])
    try:
        m.run_probe(FakeConn({}), keysum)
        raise AssertionError("summing a key column must be refused (32-bit overflow in Plex)")
    except m.ProbeInconclusive:
        pass
    bad = auto_config(extractions=[{"plex_view": "X", "bq_table": "raw_x", "filter": "", "probe": ["avg:Rate"]}])
    try:
        m.run_probe(FakeConn({}), bad)
    except m.ProbeInconclusive:
        return
    raise AssertionError("only MAX (plain name) and sum: are allowed")


# ── emails ─────────────────────────────────────────────────────────────────────
def render(report):
    """Run send_report with SendGrid replaced; return (subject, html, text)."""
    captured = {}

    class FakeClient:
        def __init__(self, key):
            pass

        def send(self, message):
            captured["message"] = message
            return type("R", (), {"status_code": 202})()

    env = {"SENDGRID_ENABLED": "true", "SENDGRID_API_KEY": "x",
           "REPORT_TO_EMAILS": "a@example.com", "REPORT_FROM_EMAIL": "b@example.com"}
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    original = email_utils.SendGridAPIClient
    email_utils.SendGridAPIClient = FakeClient
    try:
        assert email_utils.send_report(report)
    finally:
        email_utils.SendGridAPIClient = original
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    msg = captured["message"].get()
    html_part = next(c["value"] for c in msg["content"] if c["type"] == "text/html")
    text_part = next(c["value"] for c in msg["content"] if c["type"] == "text/plain")
    return msg["subject"], html_part, text_part


BASE_REPORT = {
    "start_time": "2026-10-20T05:00:00+00:00",   # 11 PM Mountain on the 19th
    "duration_seconds": 41, "gcp_project": "voxdatalake", "bq_dataset": "PlexProd",
    "plex_host": "vox.odbc.plex.com", "report_name": "sales_orders", "report_category": "Sales",
    "reports_detail": [{"display_name": "Open Orders", "table_name": "sales_orders_open_report"}],
    "time_zone": "America/Denver", "execution_name": "plex-etl-sales-orders-abc12",
}


def test_subject_is_identical_for_every_outcome_and_uses_local_date():
    probe = {"kind": "auto", "sources_checked": 27, "changed": ["raw_Sales_v_PO_Line"],
             "may_skip": True, "seconds": 9.4}
    full, _, _ = render({**BASE_REPORT, "status": "success", "run_mode": "probe", "probe": probe,
                         "extractions": [{"table": "raw_Sales_v_PO_Line", "rows": 591, "ok": True}]})
    none, _, _ = render({**BASE_REPORT, "status": "no_changes", "run_mode": "probe", "probe": probe})
    failed, _, _ = render({**BASE_REPORT, "status": "failed", "run_mode": "probe", "errors": ["ODBC down"]})
    assert full == none == failed == "[Plex ETL] - Sales: Orders — 2026-10-19", (full, none, failed)


def test_no_change_email():
    subject, body, text = render({**BASE_REPORT, "status": "no_changes", "run_mode": "probe",
                                  "probe": {"kind": "auto", "sources_checked": 27, "changed": [],
                                            "may_skip": True, "seconds": 9.4}})
    assert "nothing to update" in body
    assert "27" in body and "9.4s" in body
    assert "nothing was extracted" in body
    assert "{{" not in body, "every placeholder must be filled"
    assert "nothing has changed" in text
    save("probe_nochange", body)


def test_full_email_names_changed_tables_and_compacts_extractions():
    extractions = [{"table": f"raw_T{i}", "rows": i * 100, "ok": True} for i in range(1, 26)]
    extractions.append({"table": "raw_Broken", "rows": None, "ok": False})
    _, body, text = render({**BASE_REPORT, "status": "partial", "run_mode": "probe",
                            "errors": ["Part_v_X query: timeout"],
                            "events": ["Fetched 100 rows from X", "WARNING: 1 view(s) applied despite 1 error(s)"],
                            "probe": {"kind": "auto", "sources_checked": 26,
                                      "changed": ["raw_T1", "raw_T2"], "may_skip": True, "seconds": 8},
                            "extractions": extractions})
    assert "2 of 26 table(s) changed in Plex (raw_T1, raw_T2)" in body
    assert "Extractions &mdash; 25 of 26 tables, 32,500 rows" in body
    assert "Fetched 100 rows from X" not in body, "per-table events moved to the extraction table"
    assert "WARNING: 1 view(s) applied" in body, "warnings stay visible"
    assert "failed" in body and "{{" not in body
    assert "11:00 PM" not in body and "23:00:00" in body and "MDT" in body
    save("report_partial", body)


def test_failed_run_keeps_the_pipeline_subject():
    """A run that crashes AFTER the config loaded must email under the real
    category/name, so it threads with the pipeline's other runs."""
    sent = []
    originals = (m.main, m.send_report, m.log_job_run, m.record_dispatch_outcome, m.bigquery.Client)

    def crashing_main():
        m._RUN_CONTEXT.update({"report_name": "sales_orders", "report_category": "Sales"})
        raise RuntimeError("ODBC connection failed: (2404) session refused by service")

    m.main, m.send_report = crashing_main, lambda r: sent.append(r)
    m.log_job_run = lambda *a, **k: None
    m.record_dispatch_outcome = lambda *a, **k: None
    m.bigquery.Client = lambda *a, **k: None
    try:
        try:
            m.run_and_report()
        except RuntimeError:
            pass
    finally:
        m.main, m.send_report, m.log_job_run, m.record_dispatch_outcome, m.bigquery.Client = originals
        m._RUN_CONTEXT.clear()
    assert sent and sent[0]["report_category"] == "Sales" and sent[0]["status"] == "failed"
    subject, body, _ = render({**sent[0], "start_time": BASE_REPORT["start_time"]})
    assert subject == "[Plex ETL] - Sales: Orders — 2026-10-19", subject
    assert "stopped before it finished" in body and "Every table was extracted" not in body


def test_real_main_fills_run_context_before_a_crash():
    """The REAL main(): config loads, then the ODBC connection fails. The
    identity recorded before the crash must be the pipeline's, not the file's."""
    import tempfile
    cfg = Path(tempfile.mkdtemp()) / "sales_orders.yaml"
    cfg.write_text("report_name: sales_orders\ncategory: Sales\nprobe_mode: auto\nextractions: []\n",
                   encoding="utf-8")
    saved = {n: getattr(m, n) for n in ("REPORT_CONFIG_GCS_PATH", "get_secret", "get_credential",
                                        "ensure_metadata_table", "ensure_job_run_log_table",
                                        "get_odbc_connection")}
    saved_client = m.bigquery.Client

    def no_secret(name):
        raise RuntimeError("no Secret Manager in tests")

    def refused(*a, **k):
        raise RuntimeError("(2404) session refused by service")

    m.REPORT_CONFIG_GCS_PATH = str(cfg)
    m.get_secret, m.get_credential = no_secret, lambda *a, **k: "x"
    m.ensure_metadata_table = m.ensure_job_run_log_table = lambda bq: None
    m.bigquery.Client = lambda *a, **k: object()
    m.get_odbc_connection = refused
    m._RUN_CONTEXT.clear()
    try:
        try:
            m.main()
        except RuntimeError as exc:
            assert "ODBC connection failed" in str(exc)
        else:
            raise AssertionError("main() should have raised on the refused connection")
        assert m._RUN_CONTEXT["report_category"] == "Sales"
        assert m._RUN_CONTEXT["report_name"] == "sales_orders"
    finally:
        for n, v in saved.items():
            setattr(m, n, v)
        m.bigquery.Client = saved_client
        m._RUN_CONTEXT.clear()


def test_dispatch_outcome_goes_to_the_dispatchers_dataset():
    """The dispatcher passes DISPATCH_LOG_TABLE=PlexOps.etl_dispatch_log; the
    job's own dataset (PlexProd/PlexTest) must not be prefixed onto it."""
    seen = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def query(self, sql, job_config=None):
            seen.append(sql)
            return type("J", (), {"result": lambda self: []})()

    saved = (m.DISPATCH_ID, m.DISPATCH_LOG_TABLE, m.OUTPUT_MODE, m.bigquery.Client)
    m.bigquery.Client = FakeClient
    try:
        m.DISPATCH_ID, m.OUTPUT_MODE = "abc", "bigquery"
        m.DISPATCH_LOG_TABLE = "PlexOps.etl_dispatch_log"
        m.record_dispatch_outcome("success")
        m.DISPATCH_LOG_TABLE = "etl_dispatch_log"
        m.record_dispatch_outcome("success")
        m.DISPATCH_ID = ""
        m.record_dispatch_outcome("success")          # no dispatch id: no query at all
    finally:
        m.DISPATCH_ID, m.DISPATCH_LOG_TABLE, m.OUTPUT_MODE, m.bigquery.Client = saved
    assert len(seen) == 2, seen
    assert f"`{m.GCP_PROJECT}.PlexOps.etl_dispatch_log`" in seen[0]
    assert f"`{m.GCP_PROJECT}.{m.BQ_DATASET}.etl_dispatch_log`" in seen[1]


def test_failed_email_shows_errors_first():
    _, body, _ = render({**BASE_REPORT, "status": "failed", "run_mode": "full",
                         "errors": ["ODBC connection failed: (2404) session refused by service"]})
    assert "FAILED" in body
    assert body.index("Errors") < body.index("Source &rarr; Destination")
    assert "daily safety net" in body
    assert "{{" not in body
    save("report_failed", body)


def save(name, body):
    out = os.environ.get("WRITE_EMAIL_PREVIEWS")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        (Path(out) / f"{name}.html").write_text(body, encoding="utf-8")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"OK: {len(tests)} tests")
