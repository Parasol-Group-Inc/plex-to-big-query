# Vox Scorecard | Production vs Goal

> **Status:** ✅ Deployed and verified 2026-09-04 in both datasets — PlexTest: 3,429 of 6,000 units, 0 unmatched group names · **Category:** Production · **Runs:** rides the Work Orders pipeline

## What this tells you

Actual production against target, per work centre group per month, with percent-to-goal, variance and scrap.

## Where it fits

The scorecard's **Encapsulation / Bottling / Labeling "Actual vs. Goal"** bars and their **"% TO GOAL"** tiles — all of them, from one view.

## How it's built (high level)

Joins [`production_monthly_by_workcenter_group_report`](production_monthly_by_workcenter_group_report.md) to [`scorecard_goals`](scorecard_goals.md) on month and work centre group.

This is the only one of the three goal views on the Work Orders pipeline; the other two are on Sales Orders. Split that way deliberately, so neither pipeline depends on a view the other creates.

- **Pipeline:** `reports/work_orders.yaml` → `production_vs_goal_report`
- **SQL:** `reports/sql/production_vs_goal_view.sql`

## Flags and open questions

- **⚠ The Plex group name is not the tile name.** Plex uses **`Encapsulating`**, the scorecard tile says "Encapsulation". The sheet must use the Plex spelling or the goal silently won't match. `goal_without_production` flags exactly this.
- **Confirmed live 2026-09-04:** only `Bottling` and `Pre-Weigh` have logged production so far, so the full list of group names isn't visible from the data yet.
- **Full outer join** — a group with a target and no output yet shows at 0%, which is the point of the tile early in a month.
- **Verified 2026-09-04** against placeholder goals: Bottling 3,000 of 5,000 (60%), Pre-Weigh 429 of 1,000 (43%). The join and the percentage both work.
- **Goal rows should carry `unit = 'units'`** for this metric. Nothing enforces it — it's a label for readers.
