# Vox Scorecard | Sales MTD/YTD by Rep

> **Status:** ✅ Deployed and verified 2026-09-04 — 1 rep, September 2026 · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

Sales totals rolled up by **month and sales rep** — order count, units and dollar value — ready to sit straight against the goal table Jennilyn Tockstein is building.

Same source and same definition as [`sales_mtd_by_status_change_report`](sales_mtd_by_status_change_report.md): a "sale" is an order line whose order first entered **Pending Fulfillment** in that month. Again — this is a different number from Revenue by design.

## Where it fits

The **Sales MTD**, **$28.7M YTD** and **103% to Goal** tiles. MTD and YTD are the same view with a different filter, not two reports:

- **MTD** → filter `sales_month` to the current month, then sum `sales_value`
- **YTD** → filter `sales_year` to the current year, then sum `sales_value`

Kept as one view on purpose so it also serves trend charts, not just the two headline numbers.

## How it's built (high level)

A thin rollup over `sales_mtd_by_status_change_report`, grouped by month, year and primary sales rep.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_mtd_summary_report`
- **SQL:** `reports/sql/sales_mtd_summary_view.sql`

## Flags and open questions

- **The YTD historical gap is deliberately not solved here.** Plex only has data from go-live forward, so YTD out of this view is short by everything earlier in the year. Jennilyn's plan is a static top-up number: *"We'll just pull over whatever we get in Plex and then add a static number to it on the date of transfer, and then let it just keep adding from there."* **That number belongs in her maintained goal/adjustment table as a real editable row — not hardcoded in SQL where only an engineer could change it.** Left out on purpose.
- **Rep attribution** inherits the open question from the detail report — whole credit to the primary rep today, with commission % available for a split.
- **Rows are absent, not zero.** A month/rep pair with no sales simply won't appear. Treat a missing row as $0.
- **Ordering matters at deploy time.** This view reads from its sibling, so it must stay listed *after* `sales_mtd_by_status_change_report` in the pipeline config.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
