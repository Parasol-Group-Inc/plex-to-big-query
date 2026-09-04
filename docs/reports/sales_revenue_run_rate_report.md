# Vox Scorecard | Revenue Run Rate & % Into Month

> **Status:** ✅ Deployed and verified 2026-09-04 — September $65 MTD, $488 projected · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

For each month: shipping revenue so far, how far through the month we actually are, and the straight-line projection to month end if the current pace holds.

## Where it fits

The scorecard's **"94% into month"** sub-metric and the **MTD Run Rate** tile.

## How it's built (high level)

Pure calendar arithmetic over a number we already had — no new Plex data at all. Rolls up [`sales_revenue_summary_report`](sales_revenue_summary_report.md) to one row per month, then works out days elapsed, percent into the month, and `revenue ÷ days elapsed × days in month`.

For a month that has already ended, days-elapsed is the full month and percent-into-month is 100% — so the projection converges on the actual figure and historical rows stay honest instead of showing a stale part-month estimate.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_revenue_run_rate_report`
- **SQL:** `reports/sql/sales_revenue_run_rate_view.sql`

## Flags and open questions

- **Calendar days, not business days.** Percent-into-month counts calendar days, matching the existing scorecard's own `pct_into_month` field. If Vox actually means working days, that's a one-line change — flagged rather than assumed.
- **Revenue here means shipped units**, inherited from `sales_revenue_summary_report` and correct per the Sep 1 meeting. Deliberately a different number from [`sales_mtd_summary_report`](sales_mtd_summary_report.md), which counts orders entering Pending Fulfillment. Both are real; they answer different questions.
- **Only September 2026 has real data so far**, so the projection is currently built on a single shipment.
- **Ordering matters at deploy time** — must stay listed after `sales_revenue_summary_report` in the pipeline config.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
