# Plex API → Monday push: ARCHIVED (2026-10-20)

`push.py` and the `plex_api_label_design_report` view in `views.sql` were
merged to `main` in PR #42 (2026-10-20). They were **never deployed**: no
`plex-api-push-test` function exists. They are parked rather than deleted so
the work is not lost.

The **extractor** in this folder (`main.py`, deployed as `plex-api-extract-test`,
writing the `plex_api_*` tables) is **not** archived and keeps running.

The ODBC push (`label_design_service/push.py`, job `plex-etl-label-design-push`)
is still the only path from Plex to Monday.

## Fix these before deploying

A review on 2026-10-20 found these problems in the code as merged:

1. **No business filters.** The view filters only on release status
   `Label Design`. It has no order-status filter (`Pending Fulfillment`), so it
   would push Quote, Deposit Review and Pending Sales Approval orders. It also
   lacks the 2026-10-18 go-live floor. Mirror
   `reports/sql/label_design_view.sql`.
2. **Duplicate items within a single run.** `label_parts` and `bottle_parts`
   are LEFT JOINed per finished-good part, and BOM rows are not filtered on
   `active`, so one line can yield N×M rows. Several Label Design releases on
   one line also repeat it. All copies share one `dedupe_key`, and `push.py`
   never dedupes `fresh` against itself, so each copy becomes its own Monday
   item. Collapse to one row per `dedupe_key` in the view, and in `push.py`.
3. **It targets the team's live board.** It writes to board 18432111755 with a
   different dedupe key (`order|L<uuid>`) from the ODBC push
   (`order|L<PO_Line_Key>`), so the same line lands twice. It also auto-creates
   the group `API_Test` on that board if the group is missing. Point it at a
   sandbox board.
4. **Create retries are not safe to repeat.** `create_item` is retried on
   timeouts and 5xx errors, and the LCR-only fallback can create a second copy
   of an item the first call already made.
5. **The audit log is written only at the end of a run.** A crash or the 540 s
   timeout loses the record of items already created.
6. **A NULL `dedupe_key` crashes the run.** `CONCAT` returns NULL when the order
   number is NULL, and `lcr_hash` then fails before anything is pushed.
7. **It needs resources the extractor doesn't fetch by default.** The view reads
   `plex_api_parts_latest` and `plex_api_customers_latest`, but the extractor
   defaults to `orders,order_lines,releases,boms`. PlexProd has no `plex_api_*`
   tables at all.
8. **The BOM fetch is N+1.** It makes one request per unique part across every
   fetched line, with no throttle or cache. A partial failure leaves
   label and bottle parts silently NULL.

Open item: L13 in `docs/OPEN_ITEMS.md`.
