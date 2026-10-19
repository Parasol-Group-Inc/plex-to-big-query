# PlexProd report views — audit, 2026-10-19 (go-live day)

Every view in `voxdatalake.PlexProd` was checked on the day Plex production went
live:
- 80 views in all, counted in PlexProd and in PlexTest;
- each empty or suspicious view traced back to its raw tables, filters and joins;
- deployed SQL compared with the repo.

Five read-only agents did the checks, one per area. The fixes were then made and
verified by hand on branch `scorecard-prod-views`.

**Result:**
- **2 real bugs, both fixed.**
  - Order values blank in 8 sales views.
  - `inventory_snapshot_report` empty everywhere.
- **About 25 views are empty for an expected reason.** Prod has no shipments,
  production records, quotes, returns, deviations or requisitions yet.
- **4 decisions** for the owner.
- **No drift.** All the SQL checked in GCS matches the repo.

## Bugs fixed

### 1. Sales order values were blank in prod

**Cause.** Eight views priced orders only from the customer price list,
`Part_v_Customer_Part_Price`:
- `sales_orders_report`
- `sales_orders_open_report`
- `sales_orders_aging_report`
- `sales_orders_pending_approval_report`
- `sales_orders_pending_accounting_approval_report`
- `sales_orders_rush_open_report`
- `sales_orders_over_10k_report`
- `sales_revenue_by_rep_report`

That list is **empty in Plex prod**. The raw table was last written on
2026-07-14, because a 0-row pull keeps the old table (see D3). In test, its
2,119 rows match no current customer part. So every order value was NULL, and
`sales_orders_over_10k_report` was empty.

**Fix.** Use the price agreed on the order line (`Sales_v_Price`) first, as
`sales_order_value_by_status_view.sql` and three other views already did
(Jennilyn, 2026-09-04: "it needs to be the line item price"). Fall back to the
list.

**Verified.** Row counts are unchanged in every view (the line price is one row
per line). Rows with a price, before → after, in prod:

| View | Before | After |
|---|---|---|
| `sales_orders_report` | 0 | 583 of 613 |
| `sales_orders_open_report` | 0 | 574 of 600 |
| `sales_orders_aging_report` | 0 | 305 of 305 |
| `sales_orders_pending_accounting_approval_report` | 0 | 40 of 40 |
| `sales_revenue_by_rep_report` | 0 | 308 of 333 |
| `sales_orders_pending_approval_report` | 0 | 2 of 11 |

`sales_orders_over_10k_report` went from 0 to **81** orders, in prod and test.
`sales_orders_rush_open_report` stays 0, because no order note says RUSH.

### 2. `inventory_snapshot_report` was empty in prod and test

**Cause.** It INNER JOINed Plex's snapshot pointer table
(`Part_v_Snapshot_Cost_Sub_Type_Breakdown`), which real Plex never fills.

**Fix.** Reuse the valuation summary's "cost rows in force" logic: pointer rows
if present, otherwise the latest history row on or before the snapshot date.

**Result.** About 1.49M rows over 35 snapshots and 14,713 parts, in both
datasets. That's large, so filter on `snapshot_date` in Looker.

## Decisions for the owner

1. **Open orders include POs in "Quote" status** (PO_Status 2653, 78 POs, 136
   lines in prod). `sales_orders_open_report` excludes only Closed/Cancelled.
   Should quotes count as open orders? If not, add 2653 to the exclusion.
2. **Old `v2_*` views:** `v2_production_vs_goal_report`, `v2_revenue_vs_goal_report`,
   `v2_sales_vs_goal_report` and `v2_scorecard_goals_resolved`, in both
   datasets. Leftovers from 2026-09-24 that nothing in the repo manages. Drop
   them by hand once no Looker dashboard uses them.
3. **`labeling_open_work_orders_report` matches `Labeling Line%` only.** Prod's
   one labeling operation sits on "Schedule Labeling", so the report is empty.
   Widen to the whole Labeling group (which would also bring in Label Design /
   Label Approval) or keep as is? The recommendation is to keep it.
4. **The customer price list is empty in Plex prod.** Will Vox load customer
   part prices into Plex? Until it does, the line price is the only source.
   Orders whose lines lack a price show no value.

## For people, not code

- **Goals (S2):** `PlexProd.scorecard_goals_app` is empty; the manual-data app
  still writes to PlexTest. Until it's switched, goal tiles use the legacy
  `scorecard_goals` table, which someone reloaded in prod on 2026-10-19 (116
  rows; backup `scorecard_goals_backup_20261019`).

## Expected empties, and what fills them

| Views | Empty until |
|---|---|
| shipping_daily, shipping_revenue, shipping_pending_revenue, sales_revenue_summary, sales_revenue_run_rate, revenue_vs_goal | the first shipment is shipped and invoiced in Plex prod |
| encap/packaging/labeling/blending daily, production_monthly_by_workcenter_group, quality_fpy_by_area_month (weekly_production_update and production_vs_goal show 0 quantities) | production is recorded against jobs |
| inventory_activity, inventory_avg_daily_usage | cell production/depletion is recorded |
| part_cycle_count | the first cycle count |
| mfg_job_schedule_gate_stats | the first job is released from FG testing |
| printing_open_work_orders | a job is routed to a Printing workcenter |
| sales_quotes_open, sales_returns_open | a quote / return is entered (Quote, Return modules) |
| quality_deviation | the first deviation is logged |
| purchasing_pending_requisitions, purchasing_po_pending_approval | a requisition is entered / a PO enters Pending Approval-NS. The requisition join on Part_Key is still unverified. |
| label_design_report | an order dated after 2026-10-18 with a Label Design release reaches Pending Fulfillment. 11 such releases exist, on orders still in Quote / Pending Sales Approval. |

Every other view returns rows in prod, within a few rows of PlexTest.
`part_info_routing_report` has 66,787 rows (test 66,768), which is ordinary
drift of three parts.
