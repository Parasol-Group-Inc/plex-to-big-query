"""Tests for the Label Design push's problem emails (2026-10-27):
email_utils.render_push_alert and push.alert / push.labels_added.

    python tests/test_push_alert.py            # plain asserts, prints OK
    python -m pytest tests/test_push_alert.py  # same tests under pytest

Needs the ETL image's libraries (sendgrid, google-cloud-bigquery); no SendGrid,
Monday or BigQuery access. Run inside the image:
    docker run --rm -v "$PWD":/src -w /src --entrypoint python <image> tests/test_push_alert.py
"""
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BQ_DATASET", "PlexProd")
os.environ.setdefault("MONDAY_BOARD_ID", "18437236736")

import email_utils  # noqa: E402
from label_design_service import push  # noqa: E402


def base(**kw):
    a = {"kind": "blank", "date": "2026-10-27", "in_view": 36, "new_rows": 2, "created": 2, "not_clean": 0,
         "board_id": "18437236736", "board_name": "Plex Import Test", "run_id": "abc123",
         "gcp_project": "voxdatalake", "bq_dataset": "PlexProd", "problems": [], "label_changes": [], "items": []}
    a.update(kw)
    return a


def test_subject_and_badge_per_kind():
    for kind, words in (("blocked", "Nothing created"), ("blank", "arrive blank"), ("failed", "not created"),
                        ("alarm", "Nothing pushed"), ("crash", "stopped"), ("labels", "New labels")):
        subject, html, text = email_utils.render_push_alert(base(kind=kind))
        assert subject == "[Plex ETL] - Sales: Label Design push — 2026-10-27", subject
        assert words in html and words in text, kind
        assert "{{" not in html, kind                          # every placeholder filled
        assert "PRODUCTION" in html


def test_problems_actions_items_and_escaping():
    subject, html, text = email_utils.render_push_alert(base(
        kind="failed",
        problems=[{"text": "Priority: Design & QA refused new label(s) 'Urgent <b>'", "blocking": False,
                   "action": "Add it by hand"}],
        label_changes=["Sales Rep: add 'Julianni Pacheco' to Design & QA"],
        items=[{"order": "454", "name": "93011-00PURE1-0", "outcome": "created without some values",
                "url": "https://voxnutrition-company.monday.com/boards/18437236736/pulses/1", "detail": "x"}]))
    assert "Urgent &lt;b&gt;" in html and "<b>'" not in html     # escaped
    assert "Add it by hand" in html and "What to do: Add it by hand" in text
    assert "Julianni Pacheco" in html and "Label changes made" in text
    assert 'href="https://voxnutrition-company.monday.com/boards/18437236736/pulses/1"' in html
    assert "boards/18437236736" in text


class FakeBQ:
    def __init__(self, sent_today=()):
        self.sent_today, self.inserted = set(sent_today), []

    def query(self, q, job_config=None):
        if q.startswith("INSERT"):
            self.inserted.append(job_config)
            return types.SimpleNamespace(result=lambda: [])
        return types.SimpleNamespace(result=lambda: [types.SimpleNamespace(dedupe_key=k) for k in self.sent_today])


def run_alert(bq, **kw):
    sent = []
    real = email_utils.send_push_alert
    email_utils.send_push_alert = lambda a: sent.append(a) or True
    try:
        push.alert(ctx={"bq": bq, "run_id": "r1"}, **kw)
    finally:
        email_utils.send_push_alert = real
    return sent


def test_alert_sends_once_a_day_per_problem():
    p = {"text": "Priority: could not update the push board's labels (RuntimeError: request 1)",
         "blocking": True, "action": "x"}
    bq = FakeBQ()
    assert len(run_alert(bq, kind="blocked", problems=[p])) == 1
    assert len(bq.inserted) == 1                                  # recorded as an alert row
    # same problem later today, different error detail in brackets: no email
    p2 = dict(p, text="Priority: could not update the push board's labels (RuntimeError: request 2)")
    assert run_alert(FakeBQ(["p|Priority: could not update the push board's labels"]),
                     kind="blocked", problems=[p2]) == []
    # a new problem alongside it: email, with both
    p3 = {"text": "Sales Rep: no status column of that title on the push board", "blocking": True, "action": "x"}
    sent = run_alert(FakeBQ(["p|Priority: could not update the push board's labels"]),
                     kind="blocked", problems=[p2, p3])
    assert len(sent) == 1 and len(sent[0]["problems"]) == 2


def test_alert_not_recorded_when_email_is_off():
    bq, real = FakeBQ(), email_utils.send_push_alert
    email_utils.send_push_alert = lambda a: False
    try:
        push.alert("blocked", {"bq": bq}, problems=[{"text": "x", "blocking": True, "action": "y"}])
    finally:
        email_utils.send_push_alert = real
    assert bq.inserted == []                                      # so it is tried again later


def test_labels_added():
    notes = ["Label colours, Sales Rep: add 'Julianni Pacheco' to Design & QA; add 'Julianni Pacheco' to the push board",
             "Label colours, Reason Code: recolour 'Customer initiated: Label review' to match Design & QA",
             "Label colours, Priority: add 'Urgent' to Design & QA",
             "Label colours, Bottle Material: add 'Bamboo' to Design & QA (dry run, not applied)"]
    refused = [(False, "Priority: Design & QA refused new label(s) 'Urgent'; a move will leave the field blank (x)")]
    assert push.labels_added(notes, refused) == ["Sales Rep: add 'Julianni Pacheco' to Design & QA"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
