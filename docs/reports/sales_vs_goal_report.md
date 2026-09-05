# Vox Scorecard | Sales vs Goal by Rep

> **Status:** ✅ Deployed and verified 2026-09-04 in both datasets — PlexTest: $0 actual vs $150,000 placeholder goal, 0 unmatched rep names · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

Sales month-to-date per rep against that rep's goal, with percent-to-goal and variance.

## Where it fits

The scorecard's **"$4.8M Goal"** and **"103% to Goal"** tiles, and any per-rep breakdown under them.

## How it's built (high level)

Joins [`sales_mtd_summary_report`](sales_mtd_summary_report.md) to [`scorecard_goals`](scorecard_goals.md) on month and rep name.

**Sales is not Revenue.** The actual here counts order lines entering Pending Fulfillment that month, not shipped revenue. Those are two different numbers by design, and each has its own goal row.

A company-wide sales goal is supported too — leave `scope` blank in the sheet and it appears as `(company-wide)` alongside the per-rep rows.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_vs_goal_report`
- **SQL:** `reports/sql/sales_vs_goal_view.sql`

## Flags and open questions

- **Rep names must match exactly.** The sheet has to spell the rep as `sales_mtd_summary_report` emits it, including the literal `(no rep assigned)` bucket. A typo gives a NULL goal, not an error — hence the `goal_without_sales` and `sales_without_goal` flags.
- **Full outer join, on purpose.** A rep with a target and no sales yet still shows, at 0% — which is the case somebody is actually checking at the start of a month. An inner or left join would hide it.
- **Sales currently reads $0** across 7 real orders because those order lines have no price match. That's a separate open question, not a fault in this view — see [`sales_mtd_by_status_change_report`](sales_mtd_by_status_change_report.md).
- **Verified 2026-09-04** against a placeholder goal: the join lands correctly on `(no rep assigned)`.
