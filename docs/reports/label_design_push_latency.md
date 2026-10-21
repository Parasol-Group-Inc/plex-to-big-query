# Label Design Push Latency

> **Status:** 🛠 Built 2026-10-20, not deployed yet · **Category:** Sales · **Runs:** with the Label Design queue (hourly, 5 AM - 5 PM Mountain, Monday to Friday)

## What this tells you

How long each Label Design line took to reach the Monday board ("Plex Import"),
and where that time went:

- **Sales side:** from the line being entered in Plex to the order being
  approved (moved to Pending Fulfillment).
- **Our side:** from approval to the item appearing on the board.

## Where it fits

A companion to the [Label Design Queue](label_design_report.md). The queue
says *what* is waiting; this says *how long* it waited. It needs no change on
the Monday board: the push service already records when it created each item.

## How it's built (high level)

Every item the push creates is logged in `label_design_push_log` with the time
and the Monday item ID. This view matches each one back to its order line in
Plex and reads the Plex timestamps for when the order, line and release were
entered, and when the order was last edited.

## What a row is

One item the push service tried to create on the board (normally
`outcome = created`).

## Things to know before trusting it

- **Plex keeps no status history.** We can't see the exact moment an order
  was approved. The order's *last edit* time stands in for it. If someone edits
  the order after the item is pushed, that time moves past the push and
  `order_updated_after_push` is true: ignore the split for that row (the total
  is still right). An edit *after* approval but before the push makes "our
  side" look shorter than it was.
- **Plex's clock is Mountain time** (checked 2026-10-20 in SQL Developer).
- **Our copy of Plex runs about 50 minutes behind it.** The prod ODBC source
  lags Plex, so a change made at noon is first visible to the hourly check
  around 1 PM. "Our side" includes that delay, so about 1.5 h is normal
  there.
- **The first 38 items** (pushed 2026-10-19 at 9:22 AM) were the cutover
  backlog, from orders entered before go-live. Filter on
  `before_go_live_floor = false` to measure normal operation.
- **The hourly check watches release status, not order status** (as of
  2026-10-20). An order approved while its release status stays the same can
  wait until something else changes. Order 373 waited 5.3 h this way on
  2026-10-20.

## Columns

| Column | Meaning |
|---|---|
| `order_number`, `customer_part_no`, `po_line_key` | Which order line |
| `monday_item_id` | The item on the board |
| `outcome`, `run_id` | Push result and push run |
| `order_date` | Order date in Plex |
| `before_go_live_floor` | True for the 2026-10-19 cutover backlog |
| `line_added_at`, `release_added_at`, `order_added_at` | When each was entered in Plex (UTC) |
| `order_updated_at` | The order's last edit (UTC), the stand-in for approval |
| `order_updated_after_push` | True when that edit came after the push |
| `pushed_at` | When the item was created on the board (UTC) |
| `*_mt` | The same times in Mountain time |
| `hours_plex_to_board` | Total: line entered → on the board |
| `hours_plex_to_update` | Sales side: line entered → last order edit |
| `hours_update_to_board` | Our side: last order edit → on the board |

## Technical pointers

- SQL: `reports/sql/label_design_push_latency_view.sql`
- Config: the `bq_view` list in `reports/label_design.yaml` and `reports/test/label_design.yaml`
- Push log: `label_design_service/push.py` (`AUDIT_TABLE`)
