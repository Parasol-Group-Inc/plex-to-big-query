#!/usr/bin/env python3
"""Label Design repair — refill what a Monday board-to-board move dropped.

Ashley moves items from "Plex Import" (where the push creates them) to
"Design & QA". Monday matches columns only on the first move between two
boards and reuses that answer silently, so a column it left unmatched comes
across blank on every move after (Bottle Material, found 2026-10-22). This job
puts the pushed value back:

    python -m label_design_service.repair            # in the container
    DRY_RUN=1 python -m label_design_service.repair  # show what would be filled

ONCE PER ITEM. Every item the push created is in `label_design_push_log` with
the exact values it was sent. Each run asks Monday where those items are now
(a move keeps the item id). An item still on the push board is left alone and
checked again next run. The first run that finds it on the repair board fills
every pushed column that is blank THERE, never one that holds a value, and
logs an `outcome = 'repaired'` row. That item is never checked again, so a
field the team clears on purpose afterwards stays cleared.

NEVER CREATES ITEMS, so it can run on its own schedule without racing the push
(two pushes at once would both create the same item; this cannot).

Items pushed more than REPAIR_DAYS ago are no longer checked: one deleted or
moved to some other board would otherwise be looked up forever.

Environment (same as push.py, plus):
    MONDAY_BOARD_ID        the board the push creates items on
    REPAIR_BOARD_ID        the board items are moved to (Design & QA)
    REPAIR_DAYS            how far back to look                           [30]
"""
import datetime as dt
import json
import logging
import os
import sys
import uuid

from google.cloud import bigquery

try:  # `python -m label_design_service.repair` (container) or run from this folder
    from . import push
    from .monday import Monday
except ImportError:
    import push
    from monday import Monday

log = logging.getLogger("label_design_repair")

REPAIR_BOARD_ID = os.environ["REPAIR_BOARD_ID"]
REPAIR_DAYS = int(os.environ.get("REPAIR_DAYS", "30"))
REPAIRED = "repaired"
AUDIT = f"`{push.GCP_PROJECT}.{push.BQ_DATASET}.{push.AUDIT_TABLE}`"


def unrepaired(bq):
    """Every item the push created in the window that has no 'repaired' row yet."""
    q = f"""
        SELECT a.monday_item_id, a.dedupe_key, a.lcr, a.order_number, a.customer_part_no, a.column_values
        FROM {AUDIT} AS a
        WHERE a.board_id = @src AND a.outcome IN ('created', 'partial')
          AND a.monday_item_id IS NOT NULL
          AND a.pushed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
          AND a.monday_item_id NOT IN (
            SELECT r.monday_item_id FROM {AUDIT} AS r
            WHERE r.outcome = '{REPAIRED}' AND r.monday_item_id IS NOT NULL)
        QUALIFY ROW_NUMBER() OVER (PARTITION BY a.monday_item_id ORDER BY a.pushed_at DESC) = 1
    """
    job = bq.query(q, job_config=bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("src", "STRING", push.BOARD_ID),
        bigquery.ScalarQueryParameter("days", "INT64", REPAIR_DAYS)]))
    return {r.monday_item_id: dict(r) for r in job.result()}


def column_keys(api, board_id):
    """{column id: (title, type)} for one board."""
    b = api("query ($b: [ID!]) { boards(ids: $b) { columns { id title type } } }", {"b": [board_id]})["boards"]
    if not b:
        raise SystemExit(f"Board {board_id} not found or not visible to this token")
    return {c["id"]: (c["title"], c["type"]) for c in b[0]["columns"]}


def where_now(api, item_ids):
    """{item id: (board id, {column id: text})} for ACTIVE items only.

    Monday still returns a deleted or archived item by id (with its last
    board), so `state` is what tells a gone item from one waiting to move.
    """
    found = {}
    for i in range(0, len(item_ids), 100):
        items = api("""query ($i: [ID!]) { items(ids: $i, limit: 100) {
                           id state board { id } column_values { id text } } }""",
                    {"i": item_ids[i:i + 100]})["items"]
        for it in items:
            if it["state"] != "active":
                continue
            found[it["id"]] = (str(it["board"]["id"]),
                               {cv["id"]: (cv["text"] or "").strip() for cv in it["column_values"]})
    return found


def main():
    run_id = uuid.uuid4().hex[:12]
    log.info(f"Label Design repair {run_id}: items pushed to {push.BOARD_ID} -> blanks on {REPAIR_BOARD_ID}"
             f"{' (DRY RUN)' if push.DRY_RUN else ''}")
    bq = bigquery.Client(project=push.GCP_PROJECT)

    todo = unrepaired(bq)
    if not todo:
        log.info("Every pushed item is already repaired (or older than the window) — nothing to check.")
        return

    api = Monday(push.get_api_key())
    located = where_now(api, list(todo))
    arrived = {i: v for i, v in located.items() if v[0] == REPAIR_BOARD_ID}
    log.info(f"{len(todo)} item(s) to check: {len(arrived)} now on {REPAIR_BOARD_ID}, "
             f"{sum(v[0] == push.BOARD_ID for v in located.values())} still on {push.BOARD_ID}, "
             f"{len(todo) - len(located)} deleted, archived or not found")
    if not arrived:
        return

    # The audit row holds push-board column ids; the same column on the repair
    # board is found by title and type, as the push finds its own. A title can
    # repeat: Design & QA has two status columns called "Sales Rep" (2026-10-22),
    # one holding the rep and one empty. The field counts as filled if ANY of
    # them has a value; a blank one is filled in the first (board order).
    src = column_keys(api, push.BOARD_ID)
    dst_by_key = {}
    for cid, key in column_keys(api, REPAIR_BOARD_ID).items():
        dst_by_key.setdefault(key, []).append(cid)

    change = """mutation ($b: ID!, $i: ID!, $v: JSON!) { change_multiple_column_values(
        board_id: $b, item_id: $i, column_values: $v) { id } }"""
    audit, failures = [], 0
    for item_id, (_, current) in arrived.items():
        row = todo[item_id]
        fill = {}
        for src_col, value in json.loads(row["column_values"] or "{}").items():
            dst_cols = dst_by_key.get(src.get(src_col), [])
            if dst_cols and not any(current.get(c) for c in dst_cols):
                fill[dst_cols[0]] = value
        filled, lost = [], []
        if fill and not push.DRY_RUN:
            try:
                api(change, {"b": REPAIR_BOARD_ID, "i": item_id, "v": json.dumps(fill)})
                filled = list(fill)
            except RuntimeError:
                # One rejected value (a label the board lacks) fails the whole
                # mutation; retry column by column so only that one is lost.
                for col, v in fill.items():
                    try:
                        api(change, {"b": REPAIR_BOARD_ID, "i": item_id, "v": json.dumps({col: v})})
                        filled.append(col)
                    except RuntimeError as e:
                        lost.append(f"{col}={json.dumps(v)[:80]}: {str(e)[:200]}")
        names = {cid: key[0] for key, cids in dst_by_key.items() for cid in cids}
        if push.DRY_RUN:
            log.info(f"  would fill item {item_id} ({row['customer_part_no']}): "
                     f"{', '.join(names[c] for c in fill) or 'nothing missing'}")
            continue
        if lost:
            failures += 1
            log.warning(f"  item {item_id}: could not fill {'; '.join(lost)}")
        log.info(f"  item {item_id} ({row['customer_part_no']}): "
                 f"filled {', '.join(names[c] for c in filled) or 'nothing missing'}")
        audit.append({"run_id": run_id, "pushed_at": dt.datetime.now(dt.timezone.utc),
                      "board_id": REPAIR_BOARD_ID, "dedupe_key": row["dedupe_key"], "lcr": row["lcr"],
                      "order_number": row["order_number"], "customer_part_no": row["customer_part_no"],
                      "monday_item_id": item_id, "outcome": REPAIRED,
                      "detail": (("filled: " + ", ".join(names[c] for c in filled) if filled else "nothing missing")
                                + (f"; lost: {'; '.join(lost)}" if lost else ""))[:1000],
                      "column_values": json.dumps({c: fill[c] for c in filled})})

    push.write_audit(bq, audit)
    log.info(f"Done: {len(audit)} item(s) repaired, {failures} with a value that would not write.")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
