"""Job Note -> (Reason Code, Memo) split.

Rule (Emilio, 2026-09-15): the FIRST CHARACTER of a Plex Job Note is the
reason code, 1-6; everything after it is the Memo text written to Monday's
`Memo` column (id `text_mkzkysh6`). The digit itself is never surfaced —
it's translated to the real Monday Reason Code option index below.

REASON_CODE_MAP was resolved against the live "Design & QA" board
(see ../label-design/monday_board_catalog.md for the full option list —
several of the 40+ real options are near-duplicates of each other, which is
why each of these was confirmed by hand rather than text-matched):

    1  Customer Initiated: Label Edit        -> [105] Customer Initiated: Label Edit
    2  Customer Initiated: Label Review      -> [0]   Customer initiated: Label review
    3  New label design (Vox design)         -> [1]   New label design (Vox design)
    4  New label review (Customer design)    -> [2]   New label review (Customer design)
    5  Vox Initiated: Label edit/review      -> [106] Vox Initiated: Label Edit/Review
    6  3D Rendering                          -> [4]   3D Rendering

If the note is empty, or its first character isn't one of these six digits,
NOTHING is consumed as a code: the whole note goes to Memo unchanged and no
Reason Code is set. This matters in practice — most real Job Notes seen so
far don't start with a digit at all (e.g. "Label Design - White Bopp" from
the 2026-09-15 test pull), and those must stay free text, not get
misinterpreted as an out-of-range code.
"""
import re

REASON_CODE_MAP = {
    "1": 105,
    "2": 0,
    "3": 1,
    "4": 2,
    "5": 106,
    "6": 4,
}

# The same six options by LABEL TEXT, exactly as spelled on the board. The
# push service writes these ({"label": ...}), not the indices above: index
# numbers are per-board (a board built from scratch numbers from 0), label
# text is what a person actually sees. Spelling is not uniform on purpose —
# "Customer initiated: Label review" really is lower-case on Monday.
REASON_CODE_LABELS = {
    105: "Customer Initiated: Label Edit",
    0: "Customer initiated: Label review",
    1: "New label design (Vox design)",
    2: "New label review (Customer design)",
    106: "Vox Initiated: Label Edit/Review",
    4: "3D Rendering",
}

# One optional separator right after the digit, plus whatever whitespace
# follows it — so "1 - text", "1: text", "1.text" and "1text" all produce
# the same clean Memo, rather than leaking " - " or ": " into it.
_LEADING_SEPARATOR = re.compile(r"^[\s\-:.]+")


def parse_job_note(job_note):
    """Returns (reason_code_index: int | None, memo: str).

    reason_code_index is a Monday Reason Code option index (ready to send as
    ``{"index": reason_code_index}`` in a column_values payload), or None if
    no code was recognized — in which case `memo` is the ENTIRE original note,
    not a truncated remainder.
    """
    if not job_note:
        return None, ""

    text = job_note.strip()
    if not text:
        return None, ""

    first = text[0]
    if first not in REASON_CODE_MAP:
        return None, text

    rest = _LEADING_SEPARATOR.sub("", text[1:])
    return REASON_CODE_MAP[first], rest
