# Vox Scorecard | Production vs Goal

> **Status:** ✅ Deployed and verified 2026-09-04 in both datasets — PlexTest: 3,429 of 6,000 units, 0 unmatched group names · **Category:** Production · **Runs:** rides the Work Orders pipeline

## What this tells you

Actual production against target, per work centre group per month, with percent-to-goal, variance and scrap.

## Where it fits

The scorecard's **Encapsulation / Bottling / Labeling "Actual vs. Goal"** bars and their **"% TO GOAL"** tiles — all of them, from one view.

## How it's built (high level)

Joins [`production_monthly_by_workcenter_group_report`](production_monthly_by_workcenter_group_report.md) to [`scorecard_goals_resolved`](scorecard_goals_resolved.md) on month and work centre group (since 2026-09-22). That resolver is the single list of "one goal per month and area": a goal entered in the **Manual Data app** (Production tab) wins, and anything not entered there falls back to the older [`scorecard_goals`](scorecard_goals.md) table. No real production goals have been entered in either yet.

This is the only one of the three goal views on the Work Orders pipeline; the other two are on Sales Orders. Split that way deliberately, so neither pipeline depends on a view the other creates.

- **Pipeline:** `reports/work_orders.yaml` → `production_vs_goal_report`
- **SQL:** `reports/sql/production_vs_goal_view.sql`

## Flags and open questions

- **Bottling actuals leave out 9-parts (since 2026-10-22).** Inherited from [`production_monthly_by_workcenter_group_report`](production_monthly_by_workcenter_group_report.md): a Bottling job for a part starting with 9 is double credit for its 5 part, so it isn't counted (Jennilyn). Bottling only. Bulk cases (`9xxxx-BK…`) are exempt and still count. October 2026: 14,055 units left out (Slim Complex FG).
- **From 1 Nov 2026 Bottling actuals include 9-parts** (Jennilyn, 2026-10-30), inherited from the monthly view. Its `bottling_9part_with_5_bom_qty` shows any possible double credit.
- **From 13 Nov 2026 Bottling actuals leave out the 5/9 parts again** (Jennilyn, 2026-11-13), inherited from the monthly view: a 9-part that still has an active 5-part BOM line is double credit, at any date. 11,500 units in November to 13 Nov. Its `bottling_9part_with_5_bom_qty` shows what was left out (OPEN_ITEMS D27).
- **⚠ The Plex group name is not the tile name.** Plex uses **`Encapsulating`**, the scorecard tile says "Encapsulation". A goal must use the Plex spelling or it silently won't match — the app's area dropdown reads its names from the production report for exactly this reason. `goal_without_production` flags exactly this.
- **Confirmed live 2026-09-04:** only `Bottling` and `Pre-Weigh` have logged production so far, so the full list of group names isn't visible from the data yet.
- **Full outer join** — a group with a target and no output yet shows at 0%, which is the point of the tile early in a month.
- **Verified 2026-09-04** against placeholder goals: Bottling 3,000 of 5,000 (60%), Pre-Weigh 429 of 1,000 (43%). The join and the percentage both work.
- **Goal rows should carry `unit = 'units'`** for this metric. Nothing enforces it — it's a label for readers.

## Where the data came from

*Added 2026-11-10.* Every row carries three columns that say where its data came from and how current it was:

| Column | Meaning |
|---|---|
| `data_source` | `odbc` (Plex's database feed, the normal case) or `live` (read from Plex's own screens because the database feed was behind) |
| `data_as_of` | for `odbc`, the newest change the feed had delivered; for `live`, when the screens were read |
| `data_label` | the two in words, e.g. "ODBC, loaded 11-10 13:01, newest change 11-10 11:56 MT" or "Plex screens, read 11-10 13:20 MT" |

They come from `PlexOps.data_freshness`, group **production**. Production always reads ODBC: the screens check (every 4 h) covers Label Design, revenue and shipments only. An old `data_as_of` on a working day means the feed has stopped, even if every run succeeded (as on 2026-11-10). See [data_freshness.md](data_freshness.md).

