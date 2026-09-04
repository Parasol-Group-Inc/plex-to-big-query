# Vox Scorecard | Sales MTD (by status change, detail)

> **Status:** ✅ Deployed and verified 2026-09-04 — 7 real orders, 35,201 units, September 2026 · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

Every sales order line that counts as a "sale" in a given month, using Vox's own definition — **the month the order first reached "Pending Fulfillment" status**, not the month the order was placed and not the month anything shipped. One row per order line, with the sales rep, customer, part, quantity and dollar value attached.

**This is not the same number as Revenue, and must never be used as if it were.** Jennilyn Tockstein (data scientist) drew that line explicitly: Revenue means units that physically went out the door (see [`shipping_revenue_report.md`](shipping_revenue_report.md)); Sales MTD means orders that got approved into fulfillment. An order can be a September sale and an October revenue event.

Her exact words: *"Sales month to date is anything that had the status change into pending fulfillment that month to date... So it doesn't matter if it went from pending fulfillment to a different status after. As long as it entered pending fulfillment for the first time that month, it is counted as sales month to date. And it's the date of that status change, not the date of the order or anything else."*

## Where it fits

Feeds the scorecard's **Sales MTD**, **$28.7M YTD** and **103% to Goal** tiles. Roll it up with [`sales_mtd_summary_report`](sales_mtd_summary_report.md). See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Reads Plex's order status history (`Sales_v_PO_Change`) for the earliest date each order hit status key **2073 = "Pending Fulfillment"**, then attaches every line on that order with its rep, part and price.

Status key 2073 is confirmed live on this tenant, not guessed — the full Vox workflow is `2585 Pending Sales Approval → 2587 Deposit Review → 2586 Released → 2073 Pending Fulfillment → 2638 Pending Payment Review → 2639 Pending Shipment → 2074 Closed / 2076 Cancelled`.

**No new data had to be pulled from Plex for this.** It reuses the exact "Date Approved" mechanism that [`sales_orders_report`](sales_orders_report.md) has been computing in production since long before the scorecard effort started.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_mtd_by_status_change_report`
- **SQL:** `reports/sql/sales_mtd_by_status_change_view.sql`

## Flags and open questions

- **Order-level vs line-level — needs Jennilyn's confirmation.** She described this per "order line," but Plex only tracks this status on the order **header**; there is no line-level status column anywhere in the schema. So every line on an order inherits that order's approval date, meaning a 12-line order contributes 12 rows sharing one date. This is the only reading Plex's schema supports, and almost certainly what she meant — but it hasn't been confirmed.
- **Which sales rep owns the number — both readings are exposed.** Plex allows more than one salesperson per order. The view gives you `sales_rep` (Plex's primary, `Sort_Order = 1`), `sales_rep_2`, **and** the primary rep's `commission_pct` — so whole-credit-to-rep-1 *or* a commission-weighted split both work downstream without a rebuild. Jennilyn just needs to say which she wants.
- **"First time" is genuinely first time.** An order that bounces back into Pending Fulfillment a second time is not double-counted.
- **Not yet verified against real rows.** Built and syntax-checked, not deployed. Most test-tenant orders sit in Pending Sales Approval (2585) and have never reached 2073, so this may legitimately return few or zero rows until real orders move through the workflow.
- **Prices exclude tax and freight** — true of every dollar figure in this pipeline.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
