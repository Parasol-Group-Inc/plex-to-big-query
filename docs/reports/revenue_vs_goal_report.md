# Vox Scorecard | Revenue vs Goal

> **Status:** ✅ Deployed and verified 2026-09-04 in both datasets — PlexTest: $65 actual vs $200,000 placeholder goal · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

Month-to-date shipping revenue next to the company revenue goal, with percent-to-goal and the dollar variance.

## Where it fits

The scorecard's **"$4.7M Goal"** and **"88% to Goal"** tiles.

## How it's built (high level)

Rolls up [`sales_revenue_summary_report`](sales_revenue_summary_report.md) per month, then joins the goal from [`scorecard_goals`](scorecard_goals.md) — the maintained table fed from a Google Sheet. Revenue goals are company-wide, so it matches rows where `scope` is blank.

- **Pipeline:** `reports/sales_orders.yaml` → `revenue_vs_goal_report`
- **SQL:** `reports/sql/revenue_vs_goal_view.sql`

## Flags and open questions

- **Depends on a table the ETL doesn't create.** If `scorecard_goals` is dropped, this view stops being creatable. See [`scorecard_goals`](scorecard_goals.md).
- **A month with revenue but no goal still appears**, with `goal_value` and `pct_to_goal` NULL. That's a deliberate LEFT JOIN: an inner join would make the revenue tile vanish whenever someone forgets to fill in next month's goal — exactly the failure a hand-maintained table invites. Actuals are Plex truth and shouldn't disappear because a spreadsheet is behind.
- **A goal of 0 yields NULL, not an error** — `SAFE_DIVIDE` guards the case where a row is typed as 0 before being filled in.
- **Verified 2026-09-04** against a placeholder goal: September revenue $65 against a $200,000 placeholder. The join works; the numbers are test data.
