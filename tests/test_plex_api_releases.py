"""plex_api_releases: the API as Label Design's third source (2026-11-20).

Cases from 11-20: order 806 (new Open releases, not Label Design), orders 811/815 (new Label
Design releases on Quote orders: not Label Design lines), and an order approved to Pending
Fulfillment that neither ODBC nor the screens have yet."""
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plex_api_releases as a  # noqa: E402

DEN = ZoneInfo("America/Denver")
UTC = dt.timezone.utc


def mt(h, mi=0, day=20):
    return dt.datetime(2026, 11, day, h, mi, tzinfo=DEN)


def iso(t):
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def order(oid, no, status, modified):
    return {"id": oid, "orderNumber": no, "status": status, "modifiedDate": iso(modified)}


def rel(rid, line, status, part, modified, created=None):
    return {"id": rid, "orderLineId": line, "status": status, "partNumber": part,
            "modifiedDate": iso(modified), "createdDate": iso(created or modified)}


ODBC = {"release": {"r-old": (101, "Label Design")}, "line": {"l-old": "o-old"},
        "po": {"o-old": "Pending Fulfillment"}}
SCREEN = {"keys": {101}, "order_parts": {("700", "93000-OLD-0")}, "read_started_at": mt(9, 20)}


def lines_for(orders, releases, odbc=ODBC, screen=SCREEN, api_lines=None):
    return a.label_design_lines(orders, releases, odbc, screen,
                                get_lines=lambda oid: (api_lines or {}).get(oid, []))


def test_known_line_in_odbc_and_screen_is_covered():
    out = lines_for([order("o-old", "700", "Pending Fulfillment", mt(8))],
                    [rel("r-old", "l-old", "Label Design", "93000-OLD-0", mt(8))])
    assert len(out) == 1 and out[0]["in_odbc"] and out[0]["in_screen"]
    assert a.missing(out) == []


def test_quote_order_is_not_a_label_design_line():
    # 11-20: orders 811 and 815, Label Design releases on Quote orders. Label Design keeps only
    # Pending Fulfillment, so these must not count as missing.
    out = lines_for([order("o-811", "811", "Quote", mt(12, 37))],
                    [rel("r-811", "l-811", "Label Design", "93102-05DRNU1-0", mt(12, 37))],
                    api_lines={"o-811": [{"id": "l-811"}]})
    assert out == []


def test_open_release_is_not_a_label_design_line():
    out = lines_for([order("o-806", "806", "Pending Fulfillment", mt(8, 20))],
                    [rel("r-806", "l-806", "Open", "93102-SBVOXNU-1", mt(8, 20))],
                    api_lines={"o-806": [{"id": "l-806"}]})
    assert out == []


def test_new_line_found_through_order_lines_and_missing():
    out = lines_for([order("o-900", "900", "Pending Fulfillment", mt(10, 5))],
                    [rel("r-900", "l-900", "Label Design", "93999-NEW-0", mt(10, 5))],
                    api_lines={"o-900": [{"id": "l-900"}]})
    assert [(x["order_no"], x["in_odbc"], x["in_screen"]) for x in out] == [("900", False, False)]
    assert len(a.missing(out)) == 1


def test_new_line_on_the_screen_matches_by_order_and_part():
    screen = dict(SCREEN, order_parts=SCREEN["order_parts"] | {("900", "93999-NEW-0")})
    out = lines_for([order("o-900", "900", "Pending Fulfillment", mt(10, 5))],
                    [rel("r-900", "l-900", "Label Design", "93999-NEW-0", mt(10, 5))],
                    screen=screen, api_lines={"o-900": [{"id": "l-900"}]})
    assert out[0]["in_screen"] and a.missing(out) == []


def test_order_approved_since_odbc_counts_from_the_order_change():
    # Known line, ODBC still has the order as Quote; Plex approved it at 10:40.
    odbc = dict(ODBC, po={"o-old": "Quote"})
    out = lines_for([order("o-old", "700", "Pending Fulfillment", mt(10, 40))],
                    [rel("r-old", "l-old", "Label Design", "93000-OLD-0", mt(8))],
                    odbc=odbc, screen=dict(SCREEN, keys=set(), order_parts=set()))
    assert not out[0]["in_odbc"] and out[0]["changed_at"] == mt(10, 40).astimezone(UTC)


# ── the trigger decision ────────────────────────────────────────────────────────

NEW = [{"order_no": "900", "part_no": "P", "in_odbc": False, "in_screen": False,
        "changed_at": mt(10, 5).astimezone(UTC)}]


def test_triggers_when_a_line_changed_after_the_last_read():
    go, why = a.decide(NEW, mt(9, 20), mt(10, 30), last_login=mt(9, 20), last_trigger=None)
    assert go and "order 900" in why


def test_no_trigger_when_the_last_read_started_after_the_change():
    # The read after the change did not show it: retrying would loop. The watchdog reports it.
    go, why = a.decide(NEW, mt(10, 20), mt(10, 45), last_login=mt(10, 20), last_trigger=None)
    assert not go and why == "nothing new"


def test_waits_for_the_hourly_read_at_20():
    go, why = a.decide(NEW, mt(9, 20), mt(10, 15), last_login=mt(9, 20), last_trigger=None)
    assert not go and "hourly" in why


def test_no_second_login_while_a_read_runs():
    go, why = a.decide(NEW, mt(9, 20), mt(10, 30), last_login=mt(10, 25), last_trigger=None)
    assert not go and "screens read started" in why


def test_at_most_one_trigger_per_20_min():
    go, why = a.decide(NEW, mt(9, 20), mt(10, 45), last_login=mt(10, 0), last_trigger=mt(10, 30))
    assert not go and "triggered" in why


def test_not_on_weekends_or_after_the_push_window():
    assert not a.decide(NEW, mt(9, 20), mt(18, 0), None, None)[0]
    sat = [dict(NEW[0], changed_at=mt(10, 5, day=21).astimezone(UTC))]
    assert not a.decide(sat, mt(9, 20, day=21), mt(10, 30, day=21), None, None)[0]
