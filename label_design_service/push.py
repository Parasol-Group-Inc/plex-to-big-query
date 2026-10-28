#!/usr/bin/env python3
"""Label Design push — `label_design_report` (BigQuery) -> Monday board.

Replaces the Google Sheet + Apps Script hop (deploy/archive/label_design_sync/). Runs
as its own Cloud Run job. The Label Design ETL starts it after every run that
refreshed the view (POST_RUN_JOB, since 2026-10-22); its own scheduler is a
6:05 PM sweep:

    python -m label_design_service.push            # in the container
    DRY_RUN=1 python -m label_design_service.push  # show what would be created

ONE ROW, ONE ITEM, ONCE. A row is "already on Monday" when the board holds an
item whose LCR column equals the row's hash — SHA-256 of `dedupe_key`
("<order>|L<PO_Line_Key>", one per order LINE since 2026-09-30), first 12 lowercase hex chars. No existing
hand-typed LCR is lowercase hex, so a hash can never collide with an old
value. The hash is written INSIDE create_item, so a run that dies straight
after creating an item still leaves the mark that stops the next run
re-creating it. The audit table is checked too, so an LCR someone clears by
hand does not trigger a re-push either. It is checked for EVERY board, not
just MONDAY_BOARD_ID: a row pushed to an earlier board stays pushed when the
push moves to a new one ("Plex Import" -> "Plex Import Test", 2026-10-27,
when all 34 rows then in the view had already gone to the old board).

AUDIT. Every attempt, success or failure, is a row in
`<dataset>.label_design_push_log` (created on first run), written with DML
rather than streaming so test rows can be deleted immediately.

ALARM. More than MAX_NEW_ITEMS new rows in one run means the keys broke, not
that the business had a big day (a real day is single digits to low tens).
Nothing is pushed and the job exits non-zero.

Columns are found by TITLE (and type) at runtime, never by id, so the same
code works on any board shaped like Design & QA. A title the board doesn't
have is skipped and logged, not fatal.

LABEL COLOURS. The team moves pushed items to Design & QA, and a board move
carries a status value across by the label's COLOUR, not its name (2026-10-27).
Before creating anything, labels.align() gives every status label this run
writes the colour it has on MOVE_TO_BOARD_ID, adding a label that board lacks
to both boards with one free colour. Items are created with
create_labels_if_missing OFF, so Monday never invents a label (and a colour).
If a label could end up showing as a DIFFERENT label after a move, nothing is
created and the run exits non-zero; the next run tries again. If it could only
arrive blank (Design & QA refused a new label), items are created, the run
still exits non-zero.

LATE LABEL FIELDS. QA often fills a label part's attributes in Plex after the
order is on Monday. Every run also writes Label Part #, Label Size, Printing
Material and Allergen into the EMPTY cells of items it created that are still
in the view, once per (item, field), never over a value already there. Logged
as `outcome = 'filled'`. See fill.py.

EMAIL. A run that ends badly (label check failed, Design & QA refused a label,
items failed or partial, the alarm, a crash) or that ADDED labels to Design &
QA emails the report recipients (email_utils.send_push_alert): what happened,
what to do, the items. At most once a day per problem: each one emailed is an
`outcome = 'alert'` row in the audit table, and a run whose problems were all
emailed today sends nothing.

Environment:
    GCP_PROJECT            voxdatalake
    BQ_DATASET             PlexTest | PlexProd
    MONDAY_BOARD_ID        target board
    MOVE_TO_BOARD_ID       the board items are moved to; its status label
                           colours are the reference          [18395121955, Design & QA]
    MONDAY_GROUP_TITLE     group new items land in (created if missing)   [New from Plex]
    MONDAY_API_KEY         token, direct (local runs) ...
    SECRET_MONDAY_API_KEY  ... or its Secret Manager name                 [monday-api-key]
    MAX_NEW_ITEMS          alarm threshold                                 [60]
    SENDGRID_ENABLED, REPORT_TO_EMAILS, REPORT_FROM_EMAIL, SECRET_SENDGRID_KEY
                           the ETL's email settings (email_utils)
    DRY_RUN                1 = read everything, write nothing
"""
import datetime as dt
import hashlib
import json
import logging
import os
import sys
import uuid
from zoneinfo import ZoneInfo

from google.cloud import bigquery

try:  # `python -m label_design_service.push` (container) or run from this folder
    from . import fill, labels
    from .monday import Monday
except ImportError:
    import fill
    import labels
    from monday import Monday

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("label_design_push")

GCP_PROJECT = os.environ.get("GCP_PROJECT", "voxdatalake")
BQ_DATASET = os.environ["BQ_DATASET"]
BOARD_ID = os.environ["MONDAY_BOARD_ID"]
MOVE_TO_BOARD_ID = os.environ.get("MOVE_TO_BOARD_ID", "18395121955")
GROUP_TITLE = os.environ.get("MONDAY_GROUP_TITLE", "New from Plex")
MAX_NEW_ITEMS = int(os.environ.get("MAX_NEW_ITEMS", "60"))
DRY_RUN = os.environ.get("DRY_RUN", "") not in ("", "0", "false", "False")

VIEW = "label_design_report"
AUDIT_TABLE = "label_design_push_log"
AUDIT_SCHEMA = [
    bigquery.SchemaField("run_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("pushed_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("board_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("dedupe_key", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("lcr", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("order_number", "STRING"),
    bigquery.SchemaField("customer_part_no", "STRING"),
    bigquery.SchemaField("monday_item_id", "STRING"),
    bigquery.SchemaField("outcome", "STRING", mode="REQUIRED"),  # created | partial | failed | alert | filled
    bigquery.SchemaField("detail", "STRING"),
    bigquery.SchemaField("column_values", "STRING"),
]


def lcr_hash(dedupe_key):
    return hashlib.sha256(dedupe_key.encode("utf-8")).hexdigest()[:12]


def get_api_key():
    direct = os.environ.get("MONDAY_API_KEY")
    if direct:
        return direct
    from google.cloud import secretmanager
    name = f"projects/{GCP_PROJECT}/secrets/{os.environ.get('SECRET_MONDAY_API_KEY', 'monday-api-key')}/versions/latest"
    return secretmanager.SecretManagerServiceClient().access_secret_version(
        request={"name": name}).payload.data.decode("utf-8").strip()


# ── Row -> Monday values ───────────────────────────────────────────────────
# (board column title, column type, builder(row) -> value or None). Everything
# not listed is left for the team to fill in on the board.

def _text(field):
    return lambda r: (str(r[field]).strip() or None) if r.get(field) not in (None, "") else None


def _sales_order(r):
    s = str(r.get("order_number") or "").strip()
    if not s:
        return None
    # The board's own convention, kept from the Apps Script flow.
    return s if s.lower().startswith("sales order") else f"Sales Order #{s}"


def _date(r):
    d = r.get("order_date")
    return {"date": str(d)[:10]} if d else None


def _email(r):
    e = (r.get("customer_email") or "").strip()
    return {"email": e, "text": e} if e else None


def _label(field):
    return lambda r: {"label": str(r[field]).strip()} if (r.get(field) or "").strip() else None


def _link(field, text):
    """A Monday link value. The URL comes from the view; `text(r)` is what shows."""
    return lambda r: {"url": r[field], "text": text(r)} if r.get(field) else None


def _part_text(r):
    # "93001-00CGNUT-2 Rev 00", or the key when the part master row is missing.
    return " ".join(str(x).strip() for x in (r.get("part_no"), r.get("part_revision")) if x) or str(r.get("part_key"))


def _item(r):
    # The "Item" column: the customer part number when the line carries one
    # (FG/label parts), else the Plex part number (2026-10-08, Emilio). Component
    # lines (POWDER/SUPPLY) have no customer part, so they used to leave Item
    # blank; `part_no` is always populated and keeps the part identifiable.
    return ((r.get("customer_part_no") or "").strip()
            or (r.get("part_no") or "").strip() or None)


COLUMNS = [
    ("Customer Name", "text", _text("customer_name")),
    ("Date", "date", _date),
    # The part line: "<part no> <rev> | <Plex part name>" (2026-09-29, Ashley).
    # The customer part description it used to read is empty in Plex.
    ("Description", "text", _text("line_description")),
    ("Sales Order", "text", _sales_order),
    # Reason Code and Memo are split out of the Job Note by the VIEW (the one
    # place that rule lives). No code -> reason_code_label is NULL -> nothing
    # is written to Reason Code, and the whole note is the Memo.
    ("Memo", "text", _text("memo")),
    ("Reason Code", "status", _label("reason_code_label")),
    ("Email", "email", _email),
    ("Phone Number", "text", _text("customer_phone")),
    # Sales Rep = the BDM / Outside Salesperson: order's Outside Sales, else the
    # customer's Assigned To 2, else Order_Salesperson secondary (2026-10-08).
    # The AM (Inside Salesperson) now has its own column below — the two used to
    # be conflated into one "Sales Rep" that was actually the AM. Both resolved
    # in label_design_view.sql.
    ("Sales Rep", "status", _label("bdm")),
    # The AM / Inside Salesperson (Account Manager): order's Inside Sales, else
    # the customer's Assigned To, else Order_Salesperson primary. Needs an
    # "Inside Sales Rep" status column on the board; a board without it logs a
    # warning and skips the field.
    ("Inside Sales Rep", "status", _label("am")),
    # The line's Priority (2026-10-07), from Sales_v_Release.Priority_Key via
    # Sales_v_Priority — the Priority dropdown (`PriorityKey`) on every
    # sales-order line. Plex's five options are RUSH / High / Medium / Low /
    # Blanket; the board's Priority column should carry those same five labels.
    # Pushed verbatim. A label the board lacks is added (with Design & QA's
    # colour) by labels.align() before the item is created.
    ("Priority", "status", _label("priority")),
    # The text "Item" column next to Design File (the product), NOT the item
    # name column, which on Design & QA holds the label code the team assigns.
    # Falls back to the Plex part number when there is no customer part
    # (component lines) — see _item.
    ("Item", "text", _item),
    # Added 2026-09-29, replacing the 2026-09-25 "Plex Part URL" / "PO URL"
    # columns (deleted from Plex Import that day). The URLs are built in the
    # view, host by dataset, so the report and the board carry the same links.
    ("Customer PO", "text", _text("customer_po")),
    # The container (HDPE / PET / Glass), from the bottle component's name in
    # the BOM. Only ever one of the board's existing labels, or nothing.
    ("Bottle Material", "status", _label("bottle_material")),
    ("Part URL", "link", _link("part_url", _part_text)),
    ("Customer PO URL", "link", _link("customer_po_url", lambda r: f"PO {r.get('customer_po') or r.get('po_key')}")),
    ("Sales Order URL", "link", _link("sales_order_url", lambda r: f"SO {r.get('order_number') or r.get('po_key')}")),
    # ── The label part and its attributes (2026-10-02) ──────────────────────
    # QA records these against the LABEL part (73001-*), which reaches the
    # order line only through the BOM -- the view resolves it now, see the
    # `labels` CTE in label_design_view.sql. Before 2026-10-02 the view looked
    # them up on the finished good and every one of these was NULL.
    #
    # Label Size and Allergen are TEXT deliberately: sizes will multiply and
    # allergens will arrive as combinations ("Tree Nuts, Soy"), either of which
    # would fill a status column with one-off labels. Printing Material is a
    # status -- a small closed vocabulary worth filtering on, same call as
    # Bottle Material above. A new label is added by labels.align() before the
    # item is created.
    #
    # A board without these columns logs a warning and skips them; it does not
    # fail. That is what let the columns be created ahead of this code.
    ("Label Part #", "text", _text("label_part_no")),
    ("Label Size", "text", _text("part_label_size")),
    ("Printing Material", "status", _label("part_printing_material")),
    ("Allergen", "text", _text("part_allergen")),
    ("LCR", "text", _text("_lcr")),
]


# ── Monday reads ───────────────────────────────────────────────────────────

def resolve_board(api):
    b = api("""query ($b: [ID!]) { boards(ids: $b) { name
               columns { id title type } groups { id title } } }""", {"b": [BOARD_ID]})["boards"]
    if not b:
        raise SystemExit(f"Board {BOARD_ID} not found or not visible to this token")
    b = b[0]
    by_title = {(c["title"], c["type"]): c["id"] for c in b["columns"]}
    col_ids, missing = {}, []
    for title, ctype, _ in COLUMNS:
        if (title, ctype) in by_title:
            col_ids[title] = by_title[(title, ctype)]
        else:
            missing.append(f"{title} ({ctype})")
    if "LCR" not in col_ids:
        raise SystemExit("Board has no text column titled 'LCR' — dedupe impossible, refusing to push")
    group = next((g["id"] for g in b["groups"] if g["title"] == GROUP_TITLE), None)
    return b["name"], col_ids, missing, group


def existing_lcrs(api, lcr_col):
    fields = "cursor items { column_values(ids: [\"%s\"]) { text } }" % lcr_col
    page = api("query ($b: [ID!]) { boards(ids: $b) { items_page(limit: 200) { %s } } }" % fields,
               {"b": [BOARD_ID]})["boards"][0]["items_page"]
    seen = set()
    while True:
        for it in page["items"]:
            for cv in it["column_values"]:
                if cv["text"]:
                    seen.add(cv["text"].strip())
        if not page["cursor"]:
            return seen
        page = api("query ($c: String!) { next_items_page(cursor: $c, limit: 200) { %s } }" % fields,
                   {"c": page["cursor"]})["next_items_page"]


# ── BigQuery ───────────────────────────────────────────────────────────────

def pending_count(bq):
    """How many view rows carry an LCR the audit table has never recorded.

    `lcr_hash()` done in SQL, so the hourly run can decide whether there is any
    work before it pages the whole Monday board. A hand-typed item has no audit
    row, so this can over-count and never under-count — the board scan below
    still has the last word on what gets created.
    """
    q = f"""
        SELECT COUNT(*) AS n
        FROM (
          SELECT SUBSTR(TO_HEX(SHA256(v.dedupe_key)), 1, 12) AS lcr
          FROM `{GCP_PROJECT}.{BQ_DATASET}.{VIEW}` AS v
        ) AS candidate
        LEFT JOIN (
          SELECT DISTINCT a.lcr
          FROM `{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}` AS a
          WHERE a.outcome IN ('created', 'partial')
        ) AS seen
          ON seen.lcr = candidate.lcr
        WHERE seen.lcr IS NULL
    """
    return list(bq.query(q).result())[0].n


def ensure_audit_table(bq):
    table = bigquery.Table(f"{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}", schema=AUDIT_SCHEMA)
    bq.create_table(table, exists_ok=True)


def audited_lcrs(bq):
    # Every board, not just BOARD_ID: see "ONE ROW, ONE ITEM, ONCE" above.
    q = (f"SELECT DISTINCT lcr FROM `{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}` "
         f"WHERE outcome IN ('created', 'partial')")
    return {r.lcr for r in bq.query(q).result()}


def view_rows(bq):
    rows = [dict(r) for r in bq.query(f"SELECT * FROM `{GCP_PROJECT}.{BQ_DATASET}.{VIEW}`").result()]
    for r in rows:
        r["_lcr"] = lcr_hash(r["dedupe_key"])
    return rows


def fill_candidates(bq, rows):
    """View rows whose pushed item may be missing a label field (fill.plan)."""
    q = (f"SELECT lcr, monday_item_id, outcome, column_values FROM `{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}` "
         f"WHERE outcome IN ('created', 'partial', 'filled') AND monday_item_id IS NOT NULL ORDER BY pushed_at")
    pushed, settled = {}, {}
    for a in bq.query(q).result():
        if a.outcome == "filled":
            settled.setdefault(a.lcr, set()).update(json.loads(a.column_values or "{}"))
        else:   # the latest creation wins
            pushed[a.lcr] = a.monday_item_id
    return fill.plan(rows, pushed, settled)


def fill_blanks(api, bq, ctx, candidates):
    """Write late label fields into empty cells (see LATE LABEL FIELDS). Never
    fails the run: a problem is logged and the next run tries again."""
    if not candidates:
        return
    log.info(f"{len(candidates)} pushed item(s) may be missing label fields")
    def align_status(needed):
        problems = labels.align(api, BOARD_ID, MOVE_TO_BOARD_ID, needed, apply=not DRY_RUN, log=log.info)
        for blocking, p in problems:
            log.warning(f"Label colours (fill){' (BLOCKING)' if blocking else ''}: {p}")
        return not any(b for b, _ in problems)
    try:
        results = fill.fill(api, candidates, align_status, apply=not DRY_RUN, log=log.info)
    except Exception as e:
        log.warning(f"Filling label fields stopped ({type(e).__name__}: {str(e)[:300]}); the next run tries again")
        return
    audit = []
    for res in results:
        for e in res["errors"]:
            log.warning(f"  fill item {res['item_id']}: {e}")
        if DRY_RUN or not (res["written"] or res["already_set"]):
            continue
        r = res["row"]
        detail = "; ".join([f"{t} = {v['label'] if isinstance(v, dict) else v}" for t, v in res["written"].items()]
                           + [f"{t} already set on the board" for t in res["already_set"]])
        audit.append({"run_id": ctx["run_id"], "pushed_at": dt.datetime.now(dt.timezone.utc), "board_id": BOARD_ID,
                      "dedupe_key": r["dedupe_key"], "lcr": r["_lcr"], "order_number": r.get("order_number"),
                      "customer_part_no": r.get("customer_part_no"), "monday_item_id": str(res["item_id"]),
                      "outcome": "filled", "detail": detail[:1000],
                      # Title -> value written, or null when the cell was already set: both are settled.
                      "column_values": json.dumps({**res["written"], **{t: None for t in res["already_set"]}})})
    write_audit(bq, audit)
    log.info(f"Label fields: {sum(1 for a in results if a['written'])} item(s) filled, "
             f"{sum(len(a['already_set']) for a in results)} field(s) already set")


def write_audit(bq, rows):
    if not rows:
        return
    cols = [f.name for f in AUDIT_SCHEMA]
    params, values = [], []
    for i, r in enumerate(rows):
        ph = []
        for c, f in zip(cols, AUDIT_SCHEMA):
            name = f"p{i}_{c}"
            params.append(bigquery.ScalarQueryParameter(name, f.field_type, r.get(c)))
            ph.append(f"@{name}")
        values.append("(" + ", ".join(ph) + ")")
    q = (f"INSERT INTO `{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}` ({', '.join(cols)}) "
         f"VALUES {', '.join(values)}")
    bq.query(q, job_config=bigquery.QueryJobConfig(query_parameters=params)).result()


# ── Alerts ─────────────────────────────────────────────────────────────────

LABEL_ACTION = {
    True: "Nothing was created; the next run tries again. If this email comes back, check that the label "
          "exists on Plex Import Test and on Design & QA with the same colour, or read the Cloud Run logs "
          "of plex-etl-label-design-push.",
    False: "Add the label(s) to that column on Design & QA by hand, in a colour the column does not use yet, "
           "and give the same label on Plex Import Test the same colour. Until then, moved items show this "
           "field blank: fill it in on Design & QA.",
}


def alert(kind, ctx, problems=(), label_changes=(), items=()):
    """Email what went wrong (or which labels were added), unless every one of
    these problems was already emailed today. Never raises."""
    if DRY_RUN:
        return
    keys = ([("p|" + p["text"].split(" (")[0], p["text"]) for p in problems]
            + [("l|" + c, c) for c in label_changes]
            + [("i|" + i["key"], f"{i['name']}: {i['outcome']}") for i in items])
    try:
        bq = ctx.get("bq") or bigquery.Client(project=GCP_PROJECT)
        q = (f"SELECT DISTINCT dedupe_key FROM `{GCP_PROJECT}.{BQ_DATASET}.{AUDIT_TABLE}` "
             f"WHERE outcome = 'alert' AND DATE(pushed_at, 'America/Denver') = CURRENT_DATE('America/Denver')")
        sent_today = {r.dedupe_key for r in bq.query(q).result()}
    except Exception as e:
        log.warning(f"Could not read today's alerts ({type(e).__name__}); emailing anyway")
        bq, sent_today = None, set()
    if keys and all(k[:300] in sent_today for k, _ in keys):
        log.info("Every problem in this run was already emailed today; no email")
        return
    try:
        import email_utils
        sent = email_utils.send_push_alert({
            "kind": kind, "date": dt.datetime.now(ZoneInfo("America/Denver")).strftime("%Y-%m-%d"),
            "problems": list(problems), "label_changes": list(label_changes),
            "items": [{k: v for k, v in i.items() if k != "key"} for i in items],
            "in_view": ctx.get("in_view", "—"), "new_rows": ctx.get("new_rows", "—"),
            "created": ctx.get("created", "—"), "not_clean": ctx.get("not_clean", "—"),
            "board_id": BOARD_ID, "board_name": ctx.get("board_name"), "run_id": ctx.get("run_id", ""),
            "gcp_project": GCP_PROJECT, "bq_dataset": BQ_DATASET,
            "execution_name": os.environ.get("CLOUD_RUN_EXECUTION", "")})
    except Exception as e:
        log.error(f"Alert email failed ({type(e).__name__}: {e})")
        return
    log.info(f"Alert email ({kind}) {'sent' if sent else 'not sent: email is off or not configured'}")
    if sent and bq is not None:
        now = dt.datetime.now(dt.timezone.utc)
        try:
            write_audit(bq, [{"run_id": ctx.get("run_id", ""), "pushed_at": now, "board_id": BOARD_ID,
                              "dedupe_key": k[:300], "lcr": lcr_hash(k), "outcome": "alert",
                              "detail": text[:1000]} for k, text in keys])
        except Exception as e:
            log.warning(f"Could not record the alert ({type(e).__name__}); it may be emailed again today")


def labels_added(notes, label_problems):
    """labels.align()'s log lines ("Label colours, <column>: add 'X' to Design &
    QA; ...") -> one line per label actually added to Design & QA. A column
    where Design & QA refused is a problem, not a change."""
    refused = {p.split(":")[0] for b, p in label_problems if not b}
    out = []
    for n in notes:
        if n.endswith("(dry run, not applied)") or ":" not in n:
            continue
        column, rest = n.split(":", 1)
        column = column.replace("Label colours, ", "")
        if column in refused:
            continue
        out += [f"{column}: {part.strip()}" for part in rest.split(";") if part.strip().endswith("to Design & QA")]
    return out


# ── Main ───────────────────────────────────────────────────────────────────

def main(ctx):
    run_id = ctx["run_id"] = uuid.uuid4().hex[:12]
    log.info(f"Label Design push {run_id}: {GCP_PROJECT}.{BQ_DATASET}.{VIEW} -> board {BOARD_ID}"
             f"{' (DRY RUN)' if DRY_RUN else ''}")
    bq = ctx["bq"] = bigquery.Client(project=GCP_PROJECT)

    # Cheap gate, ahead of the Secret Manager read and the board scan: on most
    # hourly runs the view holds nothing the audit table hasn't seen, and this
    # exits without a single Monday API call. DRY_RUN deliberately skips the
    # gate so a dry run always shows the full picture.
    if not DRY_RUN:
        ensure_audit_table(bq)
        try:
            pending = pending_count(bq)
        except Exception as e:
            log.info(f"Pending check skipped ({type(e).__name__}: {e}) — doing the full pass")
            pending = None
        if pending == 0:
            candidates = fill_candidates(bq, view_rows(bq))
            if not candidates:
                log.info("Nothing in the view that the audit table hasn't seen, and no label fields to fill.")
                return
            log.info("Nothing new to push.")
            fill_blanks(Monday(get_api_key()), bq, ctx, candidates)
            return

    api = Monday(get_api_key())
    rc = push_new(api, bq, ctx)
    fill_blanks(api, bq, ctx, fill_candidates(bq, view_rows(bq)))
    if rc:
        sys.exit(rc)


def push_new(api, bq, ctx):
    """Create an item for every view row not yet on Monday. Returns the exit
    code; the alarm and a blocking label problem exit straight away."""
    run_id = ctx["run_id"]
    board_name, col_ids, missing, group_id = resolve_board(api)
    ctx["board_name"] = board_name
    log.info(f"Board '{board_name}': {len(col_ids)}/{len(COLUMNS)} mapped columns found")
    for m in missing:
        log.warning(f"Board has no column {m} — that field will not be written")

    rows = view_rows(bq)
    on_board = existing_lcrs(api, col_ids["LCR"])
    try:
        in_audit = audited_lcrs(bq)
    except Exception as e:  # table absent on a first dry run
        log.info(f"No audit history read ({type(e).__name__}); relying on the board's LCRs")
        in_audit = set()

    fresh = []
    for r in rows:
        if r["_lcr"] in on_board or r["_lcr"] in in_audit:
            continue
        fresh.append(r)
    log.info(f"{len(rows)} row(s) in the view, {len(rows) - len(fresh)} already on the board, "
             f"{len(fresh)} new")
    ctx.update(in_view=len(rows), new_rows=len(fresh), created=0, not_clean=0)

    if len(fresh) > MAX_NEW_ITEMS:
        log.error(f"ALARM: {len(fresh)} new rows exceeds MAX_NEW_ITEMS={MAX_NEW_ITEMS}. The keys have "
                  f"probably changed shape; nothing pushed. Check dedupe_key in {VIEW}.")
        alert("alarm", ctx, problems=[{
            "text": f"{len(fresh)} new lines at once, over the limit of {MAX_NEW_ITEMS}.", "blocking": True,
            "action": f"Check dedupe_key in {VIEW} (did the key change shape?). If the volume is real, run the "
                      f"push once with a higher MAX_NEW_ITEMS."}])
        sys.exit(2)

    if not fresh:
        return 0

    # Status label colours, before anything is created (see LABEL COLOURS).
    needed = {}
    for r in fresh:
        for title, ctype, build in COLUMNS:
            if ctype == "status" and title in col_ids:
                v = build(r)
                if v:
                    needed.setdefault(title, set()).add(v["label"])
    notes = []
    def note(msg):
        log.info(msg)
        notes.append(msg)
    label_problems = labels.align(api, BOARD_ID, MOVE_TO_BOARD_ID, needed, apply=not DRY_RUN, log=note)
    for blocking, p in label_problems:
        log.warning(f"Label colours{' (BLOCKING)' if blocking else ''}: {p}")
    problems = [{"text": p, "blocking": b, "action": LABEL_ACTION[b]} for b, p in label_problems]
    if any(b for b, _ in label_problems):
        log.error("A label could show as a different label after a move to Design & QA; nothing created. "
                  "The next run tries again.")
        alert("blocked", ctx, problems=problems)
        sys.exit(1)
    label_changes = labels_added(notes, label_problems)

    if DRY_RUN:
        for r in fresh:
            log.info(f"  would create: {r.get('customer_part_no')!r}  {r['dedupe_key']}  lcr={r['_lcr']}")
        return 0

    if not group_id:
        group_id = api("mutation ($b: ID!, $n: String!) { create_group(board_id: $b, group_name: $n) { id } }",
                       {"b": BOARD_ID, "n": GROUP_TITLE})["create_group"]["id"]
        log.info(f"Created group '{GROUP_TITLE}'")

    create = """mutation ($b: ID!, $g: String!, $n: String!, $v: JSON) {
        create_item(board_id: $b, group_id: $g, item_name: $n, column_values: $v,
                    create_labels_if_missing: false) { id } }"""
    change = """mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(
        board_id: $b, item_id: $i, column_values: $v, create_labels_if_missing: false) { id } }"""

    audit, failures, bad_items = [], 0, []
    for r in fresh:
        values = {}
        for title, _, build in COLUMNS:
            if title in col_ids:
                v = build(r)
                if v is not None:
                    values[col_ids[title]] = v
        # The item name: the customer part # when the line has one (FG/label
        # parts), else the full line description — "<part no> Rev xx | <TYPE> |
        # <name>" — which is what the historical Sheet/NetSuite items were named
        # and keeps component lines (POWDER/SUPPLY, no customer part #) legible
        # instead of a bare "(no part #) 16" (2026-10-08, Emilio). The order-only
        # fallback stays as a last resort if even the description is blank.
        name = ((r.get("customer_part_no") or "").strip()
                or (r.get("line_description") or "").strip()
                or f"(no part #) {r.get('order_number')}")
        entry = {"run_id": run_id, "pushed_at": dt.datetime.now(dt.timezone.utc), "board_id": BOARD_ID,
                 "dedupe_key": r["dedupe_key"], "lcr": r["_lcr"], "order_number": r.get("order_number"),
                 "customer_part_no": r.get("customer_part_no"), "column_values": json.dumps(values)}
        try:
            item_id = api(create, {"b": BOARD_ID, "g": group_id, "n": name, "v": json.dumps(values)})["create_item"]["id"]
            entry.update(monday_item_id=item_id, outcome="created")
        except RuntimeError as whole:
            # One bad value (say, a malformed email) rejects the whole item.
            # Create it with just the LCR — the dedupe mark matters most — then
            # set the rest one column at a time so only the bad value is lost.
            try:
                lcr_only = {col_ids["LCR"]: r["_lcr"]}
                item_id = api(create, {"b": BOARD_ID, "g": group_id, "n": name,
                                       "v": json.dumps(lcr_only)})["create_item"]["id"]
            except RuntimeError as e:
                entry.update(outcome="failed", detail=str(e)[:1000])
                failures += 1
                log.error(f"FAILED {r['dedupe_key']}: {e}")
                audit.append(entry)
                bad_items.append({"key": f"{r['dedupe_key']}|failed", "order": r.get("order_number"), "name": name,
                                  "outcome": "not created (retried next run)", "url": "", "detail": str(e)[:300]})
                continue
            lost = []
            for col, v in values.items():
                if col == col_ids["LCR"]:
                    continue
                try:
                    api(change, {"b": BOARD_ID, "i": item_id, "v": json.dumps({col: v})})
                except RuntimeError as e:
                    lost.append(f"{col}={json.dumps(v)[:80]}: {str(e)[:200]}")
            entry.update(monday_item_id=item_id, outcome="partial" if lost else "created",
                         detail=("; ".join(lost) or f"retried column-by-column after: {str(whole)[:300]}")[:1000])
            if lost:
                failures += 1
                log.warning(f"PARTIAL {r['dedupe_key']} (item {item_id}): {'; '.join(lost)}")
                bad_items.append({"key": f"{r['dedupe_key']}|partial", "order": r.get("order_number"), "name": name,
                                  "outcome": "created without some values",
                                  "url": f"https://voxnutrition-company.monday.com/boards/{BOARD_ID}/pulses/{item_id}",
                                  "detail": "; ".join(lost)[:300]})
        log.info(f"  created item {entry['monday_item_id']} for {r['dedupe_key']}")
        audit.append(entry)

    write_audit(bq, audit)
    created = sum(1 for a in audit if a["outcome"] != "failed")
    log.info(f"Done: {created} item(s) created, {failures} with problems. Audit: {BQ_DATASET}.{AUDIT_TABLE}")
    ctx.update(created=created, not_clean=failures)
    if bad_items:
        problems.append({"text": f"{len(bad_items)} item(s) not created, or created without some values.",
                         "blocking": False,
                         "action": "Items not created are retried on the next run. For an item created without "
                                   "some values, fill them in on the board; the table below says which."})
    if bad_items or problems or label_changes:
        alert("failed" if bad_items else "blank" if problems else "labels", ctx,
              problems=problems, label_changes=label_changes, items=bad_items)
    return 1 if failures or label_problems else 0


if __name__ == "__main__":
    ctx = {}
    try:
        main(ctx)
    except Exception as e:  # SystemExit is not an Exception: planned exits pass through
        log.exception("Label Design push stopped")
        alert("crash", ctx, problems=[{
            "text": f"The push stopped on {type(e).__name__} ({str(e)[:300]})", "blocking": True,
            "action": "Usually Monday or BigQuery being briefly unavailable; the next run retries. If this "
                      "email comes back, read the Cloud Run logs of plex-etl-label-design-push."}])
        raise
