# Scorecard: Looker Studio setup, tile by tile

What to set in Looker Studio for each tile of the Vox MTD scorecard, built
against `voxdatalake.ScorecardSandbox`. Which views work, and what is still
open for each, is in
[`SCORECARD_SANDBOX_FINDINGS.md`](SCORECARD_SANDBOX_FINDINGS.md). This page
covers only how to wire each tile.

The same setups, with copy buttons for every name and formula, are in the
**Lineage Navigator** artifact (Sandbox mode, click a tile):
https://claude.ai/artifact/1kiCCV2BhBD4aDEQPfCUKZ

## Before you start

- **Data source** = a BigQuery data source on
  `voxdatalake.ScorecardSandbox.<view>`. Add one per view and reuse it across tiles.
  At go-live, change the dataset to `PlexProd` (see the sandbox README).
- **Percentages are calculated fields, never a summed rate column.** Add metric
  → *Create field*, paste the formula, set the type to **Percent**. A
  `SUM(a) / SUM(b)` stays right over any date range. Summing a
  `pct_to_goal` or `fpy` column does not.
- **"none" under Date range** means clear the tile's date range dimension. These
  tiles are snapshots of right now, and a page-level date control would
  otherwise filter them.
- **Sandbox figures are September 2026** (latest full month). To compare a
  tile with the figures in the findings doc or the artifact, use a custom
  range of Sep 1 – Sep 30, 2026. For the Y-DAY tiles, use Oct 5, 2026 (the
  latest production day in the sandbox).
- **Filter values are exact text, checked against the sandbox data on
  2026-10-16.** The work-centre group is `Encapsulating`, not "Encapsulation".
- **Sales goals:** each rep also has a goal row in `sales_vs_goal_report`, so
  the company goal must be filtered to `sales_rep = (company-wide)`. Summing
  `goal_value` across the rows adds every rep's goal on top.
- **Revenue goal tiles can come out empty outside the sandbox.**
  `revenue_vs_goal_report` drops a month that has a goal but no revenue
  (open item S13), so `$4.7M Goal` and `88% to Goal` read blank there until that is decided.
- **Not yet checked in Looker itself.** Every field listed exists in its view
  (checked against the BigQuery schemas on 2026-10-16), but no tile has been
  built from this page yet. The Safe Days formula is the one most likely to
  need adjusting.

## Revenue

| Tile | Chart | Data source | Metric | Date range | Filter | Note |
|---|---|---|---|---|---|---|
| MTD Revenue | Scorecard | `sales_revenue_summary_report` | `shipping_revenue` · SUM | `revenue_month` · This month to date | — | Type Currency (USD). |
| 94% into month | Scorecard | `sales_revenue_run_rate_report` | `pct_into_month` · MAX | `revenue_month` · This month to date | — | One row per month. Set the field type to Percent. |
| $4.7M Goal | Scorecard | `revenue_vs_goal_report` | `goal_value` · SUM | `revenue_month` · This month to date | — | — |
| 88% to Goal | Scorecard | `revenue_vs_goal_report` | calculated field **% to rev goal** = `SUM(actual_revenue) / SUM(goal_value)` | `revenue_month` · This month to date | — | Set the field type to Percent. |

## Operational Health

| Tile | Chart | Data source | Metric | Date range | Filter | Note |
|---|---|---|---|---|---|---|
| Safe Days | Scorecard | `safety_incidents` | calculated field **Safe Days** = `DATE_DIFF(TODAY(), MAX(incident_date))` | none | Include `recordable` Equal to `true`<br>Include `is_deleted` Equal to `false` | recordable is text, so the filter value is the word true. |
| Total in Shipping | Scorecard | `shipping_pending_revenue_report` | `ready_value` · SUM | none | — | A snapshot of what is ready right now; there is no date column. |
| OOS | Scorecard | `inventory_out_of_stock_report` | Record Count | none | — | Every row is already a short part, so a plain count is right. Optional table: break down by no_inventory_on_hand. |
| WIP | Scorecard | `sales_order_value_by_status_report` | `wip_value` · SUM | none | — | Open orders right now; there is no date column. |

## Sales

| Tile | Chart | Data source | Metric | Date range | Filter | Note |
|---|---|---|---|---|---|---|
| Sales MTD | Scorecard | `sales_mtd_summary_report` | `sales_value` · SUM | `sales_month` · This month to date | — | — |
| 103% to Goal | Scorecard | `sales_vs_goal_report` | calculated field **% to sales goal** = `SUM(actual_sales) / SUM(CASE WHEN sales_rep = "(company-wide)" THEN goal_value ELSE 0 END)` | `sales_month` · This month to date | — | Reps have their own goals as well, so only the (company-wide) row may count as the goal. Set the field type to Percent. |
| $4.8M Goal | Scorecard | `sales_vs_goal_report` | `goal_value` · SUM | `sales_month` · This month to date | Include `sales_rep` Equal to `(company-wide)` | Without the filter, every rep’s goal is added on top. |
| $28.7M YTD | Scorecard | `sales_mtd_summary_report` | `sales_value` · SUM | `sales_month` · This year to date | — | — |

## Pipeline

| Tile | Chart | Data source | Metric | Date range | Filter | Note |
|---|---|---|---|---|---|---|
| Funnel chart | Funnel chart (or Bar chart) by `pipeline_stage` | `pipeline_plex_value_report` | `pipeline_value` · SUM | none | — | Plex supplies only the Quote and Pending Sales Approval stages. Opportunities and Forecast still come from Monday. |
| Total Pipeline | Scorecard | `pipeline_plex_value_report` | `pipeline_value` · SUM | none | — | Plex part of the total only. |

## Production

| Tile | Chart | Data source | Metric | Date range | Filter | Note |
|---|---|---|---|---|---|---|
| Encapsulation bar chart | Bar chart by `workcenter_group` | `production_vs_goal_report` | `actual_qty` · SUM<br>`goal_value` · SUM | `production_month` · This month to date | Include `workcenter_group` Equal to `Encapsulating` | Bar 1 is made, bar 2 is goal. Swap actual_qty for total_qty if the old "Total" counted scrap. |
| Encapsulation Y-DAY | Scorecard | `encap_daily_report` | `actual_qty` · SUM | `production_date` · Yesterday | — | This view holds one work-centre group only, so no filter. |
| Encapsulation % TO GOAL | Scorecard | `production_vs_goal_report` | calculated field **encapsulating % to goal** = `SUM(actual_qty) / SUM(goal_value)` | `production_month` · This month to date | Include `workcenter_group` Equal to `Encapsulating` | Set the calculated field type to Percent. |
| Bottling bar chart | Bar chart by `workcenter_group` | `production_vs_goal_report` | `actual_qty` · SUM<br>`goal_value` · SUM | `production_month` · This month to date | Include `workcenter_group` Equal to `Bottling` | Bar 1 is made, bar 2 is goal. Swap actual_qty for total_qty if the old "Total" counted scrap. |
| Bottling Y-DAY | Scorecard | `packaging_daily_report` | `actual_qty` · SUM | `production_date` · Yesterday | — | This view holds one work-centre group only, so no filter. |
| Bottling % TO GOAL | Scorecard | `production_vs_goal_report` | calculated field **bottling % to goal** = `SUM(actual_qty) / SUM(goal_value)` | `production_month` · This month to date | Include `workcenter_group` Equal to `Bottling` | Set the calculated field type to Percent. |
| Labeling bar chart | Bar chart by `workcenter_group` | `production_vs_goal_report` | `actual_qty` · SUM<br>`goal_value` · SUM | `production_month` · This month to date | Include `workcenter_group` Equal to `Labeling` | Bar 1 is made, bar 2 is goal. Swap actual_qty for total_qty if the old "Total" counted scrap. |
| Labeling Y-DAY | Scorecard | `labeling_daily_report` | `actual_qty` · SUM | `production_date` · Yesterday | — | This view holds one work-centre group only, so no filter. |
| Labeling % TO GOAL | Scorecard | `production_vs_goal_report` | calculated field **labeling % to goal** = `SUM(actual_qty) / SUM(goal_value)` | `production_month` · This month to date | Include `workcenter_group` Equal to `Labeling` | Set the calculated field type to Percent. |

## Quality Metrics

| Tile | Chart | Data source | Metric | Date range | Filter | Note |
|---|---|---|---|---|---|---|
| Reworks | Scorecard | `quality_nonconformance_report` | Record Count | `problem_date` · This month to date | Include `final_disposition` Equal to `Rework` | — |
| Deviations | Scorecard | `quality_deviation_report` | Record Count | `deviation_month` · This month to date | — | — |
| Destruction $ | Scorecard | `quality_disposition_cost_report` | `total_cost` · SUM | `problem_month` · This month to date | Include `disposition_class` Equal to `Destruction` | Type Currency (USD). For the count of NCs, use nc_count with SUM. |
| FPY - Encap | Scorecard | `quality_fpy_by_area_month_report` | calculated field **FPY Encapsulating** = `SUM(good_qty) / SUM(total_qty)` | `fpy_month` · This month to date | Include `area` Equal to `Encapsulating` | Do not use the fpy column with SUM: it is already a rate. Set the field type to Percent. |
| FPY - Bottling | Scorecard | `quality_fpy_by_area_month_report` | calculated field **FPY Bottling** = `SUM(good_qty) / SUM(total_qty)` | `fpy_month` · This month to date | Include `area` Equal to `Bottling` | Do not use the fpy column with SUM: it is already a rate. Set the field type to Percent. |
| FPY - Labeling | Scorecard | `quality_fpy_by_area_month_report` | calculated field **FPY Labeling** = `SUM(good_qty) / SUM(total_qty)` | `fpy_month` · This month to date | Include `area` Equal to `Labeling` | Do not use the fpy column with SUM: it is already a rate. Set the field type to Percent. |

## Operations

| Tile | Chart | Data source | Metric | Date range | Filter | Note |
|---|---|---|---|---|---|---|
| 30 Day Rolling TAT chart | Combo chart (bars + line) by `stock_type` | `quality_turnaround_time_report` | `turnaround_work_days` · AVG<br>`performance_standard_days` · AVG | `closed_date` · Last 30 days | Exclude `closed_date` Is null | Bars are the average work days, the line is the standard. Sort by turnaround_work_days (AVG), descending. The sandbox figure above covers all closed NCs, not 30 days. |
| Open Caps | Scorecard | `mfg_job_open_caps_report` | `caps_pending` · SUM | none | — | The view already holds open jobs only. |
| Open Bottles | Scorecard | `bottling_job_open_report` | `qty_pending` · SUM | none | — | The view already holds open jobs only. |
