# What the scorecard sandbox found

Built 2026-09-24. The sandbox (`voxdatalake.ScorecardSandbox`, see
[`scripts/scorecard_sandbox/README.md`](../scripts/scorecard_sandbox/README.md))
puts a full year of realistic data under every scorecard tile. That shows,
for each tile, whether it works, and whether a gap is ours or a decision
someone else owns.

This is the build list for the Looker Studio report. Every issue below was
seen in the sandbox and then **checked against the real Plex record** before
it was written down.

**Status key**

| Symbol | Meaning |
|---|---|
| ✅ | Works on the deployed SQL. |
| 🔧 | Works only with a fix from `scripts/scorecard_sandbox/proposed_sql/`, which is **not deployed**. |
| 🏗 | The view needs rebuilding. |
| ❓ | Needs a decision or data from someone outside this team. |
| ⛔ | No Plex source, by design. |

## Tile by tile

| Section | Tile | View | Status | What to know |
|---|---|---|---|---|
| Revenue | MTD / YTD Revenue | `sales_revenue_summary_report` | ✅ | YTD only covers months Plex has; earlier history needs a one-off top-up. |
| Revenue | Revenue by part group | `sales_revenue_summary_report` | 🏗 | **Always one bar, "(no group)".** Parts carry `Part_Group_Key` (14,149 of 14,150), but the lookup it joins, `Part_v_Part_Product_Group`, is empty in test *and* prod. The group names live in a different Plex view, not yet identified. |
| Revenue | Revenue detail | `shipping_revenue_report` | ✅ | Has both ship date and invoice date; the month is by ship date. |
| Revenue | % into month and run rate | `sales_revenue_run_rate_report` | ✅ | Calendar days, not working days. |
| Revenue | Revenue goal and % to goal | `revenue_vs_goal_report` | ❓ | The goal is the company *sales* goal reused. Is there a separate revenue target? |
| Revenue | Shipping daily | `shipping_daily_report` | ✅ | |
| Revenue | Total in Shipping | `shipping_pending_revenue_report` | ✅ | |
| Sales | Sales MTD / YTD | `sales_mtd_summary_report` | ✅ | Totals are right. The rep breakdown is not; see the next row. |
| Sales | Sales by rep | `sales_mtd_summary_report` | 🔧 | **Every sale reads "(no rep assigned)"** on the deployed SQL. See finding 1. |
| Sales | Sales goal and % to goal | `sales_vs_goal_report` | 🔧 ❓ | Needs finding 1. The company-wide goal is **its own row with actual 0**, so summing `goal_value` across rows double-counts. Company % = total actual ÷ that row's goal. One goal is scoped "Sales Representative", which is not a person. |
| Sales | Sales detail | `sales_mtd_by_status_change_report` | 🔧 | Lines are right; the rep column needs finding 1. |
| Sales | Orders pending accounting approval | `sales_orders_pending_accounting_approval_report` | 🔧 | **Always empty** on the deployed SQL. See finding 3. |
| Sales | WIP | `sales_order_value_by_status_report` | ✅ | |
| Sales | Total pipeline | `pipeline_plex_value_report` | 🔧 ❓ | The Plex half works but its rep needs finding 1. It stays a blend with Monday for pre-quote stages, which has no probabilities on the Plex side. |
| Sales | Opportunities and forecast | — | ⛔ | Monday only, by design. |
| Production | Actual vs goal, all areas | `production_vs_goal_report` | ✅ ❓ | Actual is right. The goals are the live board's July figures in the sandbox; the real ones have to be entered (see Manual inputs). |
| Production | Encap / Bottling / Labeling daily | `encap_` / `packaging_` / `labeling_daily_report` | 🔧 | Output is right; **scrap is 0** (finding 2). The employee column is blank because Plex's `Common_Name` is empty for all 132 employees. |
| Quality | FPY by area | `quality_fpy_by_area_month_report` | 🔧 ❓ | FPY is right (good ÷ total). Rejected quantity and DPMO are 0 (finding 2). DPMO uses 1 opportunity per unit as a placeholder. |
| Quality | Reworks (NCs) | `quality_nonconformance_report` | ✅ | |
| Quality | Deviations | `quality_deviation_report` | 🏗 | The linked NC never shows (finding 5). No month column, so the tile must pick add date or effective date. |
| Quality | Destruction $ / Rework $ | `quality_disposition_cost_report` | ❓ | Works in the sandbox only because costs are modelled there. On real records Cost is 0.00 and the money is typed into the description. The "missing cost" flag counts NULLs, so it never fires on those 0.00s. |
| Quality | 30-day rolling TAT | `quality_turnaround_time_report` | 🏗 ❓ | Counts **calendar** days against **work-day** standards, so met/missed is skewed. The standards themselves are placeholders. |
| Inventory | Quantity available | `inventory_available_to_sell_report` | ✅ | |
| Inventory | Out of stock | `inventory_out_of_stock_report` | ✅ | One part number can appear twice (two Part_Keys). |
| Inventory | Top quantity | `inventory_top_quantity_report` | ✅ | Quantity only. |
| Inventory | Average daily usage | `inventory_avg_daily_usage_report` | 🏗 | The current month is divided by all its days, so it reads low. It also adds capsules and bottles together. |
| Inventory | Inventory value | `inventory_valuation_total_report` | 🏗 ❓ | **Reads about $77.** See finding 4. The interim source is NetSuite anyway. |
| Inventory | Cycle count accuracy | `part_cycle_count_report` | ✅ | Averages per count, not per location. No location names, because no location master is extracted. |
| Operations | Open caps | `mfg_job_open_caps_report` | ✅ | Filters by name (`Encapsulation%`), which misses "Schedule Encapsulation". Open bottles filters by group instead. |
| Operations | Open bottles | `bottling_job_open_report` | ✅ | |
| Operations | Safe days | `safety_incidents` (table) | 🏗 ❓ | No view computes Safe Days; Looker has to (today − latest incident date). An empty log reads as a clean record. |

## View bugs

Proposed fixes for 1–3 are in `scripts/scorecard_sandbox/proposed_sql/`. The
sandbox uses them; production does not. Editing `reports/sql/` deploys to prod
on the next `terraform apply`, so that is Emilio's decision.

**1. The sales rep comes from a table Vox doesn't use.**
- **Affects:** `sales_mtd_by_status_change_view.sql` (rep1/rep2),
  `pipeline_plex_value_view.sql`,
  `sales_orders_pending_accounting_approval_view.sql`.
- **What's wrong:** they read `Sales_v_Order_Salesperson` where
  `Sort_Order = 1`. It has one row in all of test and none in prod, and that
  row has `Sort_Order = 0`.
- **Where Vox actually records the rep:** on the order
  (`Sales_v_PO.Inside_Sales`) and on the customer (`Common_v_Customer.Assigned_To`,
  on 150 of 182 customers).
- **Fix:** `label_design_view.sql` switched to those fields on 2026-09-24. The
  proposed SQL does the same (order, then customer, then the old table) and
  adds `sales_rep_source`.
- **Impact:** Sales by rep, % to goal by rep, and the pipeline and approval
  rep columns.

**2. Scrap is counted at `Rejected = -1`; real Plex writes `1`.**
- **Affects:** `production_monthly_by_workcenter_group_view.sql:76,84`,
  `quality_fpy_by_area_month_view.sql:67`, `encap_daily_report_view.sql:98`,
  `packaging_daily_report_view.sql:65`, `labeling_daily_report_view.sql:64`,
  and — not a scorecard tile — `blending_daily_report_view.sql:57`.
- **Where it came from:** the `-1` was introduced 2026-08-23 on an *assumed*
  convention.
- **Evidence:** PlexTest's only real rejected record (Bottling Line 1, 500
  units, 2026-09-24) has `Rejected = 1`.
- **Fix:** `Rejected != 0`, which holds under either convention.
- **Impact:** scrap quantity, scrap rate, rejected quantity and DPMO all read 0.
  FPY survives because it is good ÷ total.

**3. Deposit Review is matched by an exact name that no longer exists.**
- **Affects:** `sales_orders_pending_accounting_approval_view.sql:131` matches
  `= 'DEPOSIT REVIEW'`.
- **What's wrong:** Plex now has two statuses, "Deposit Review (Initiate
  Payment Request)" (2587) and "(Bypass Payment Request)" (2656).
- **Fix:** `LIKE 'DEPOSIT REVIEW%'`.
- **Impact:** the tile has been empty since the split. It was already dead
  once before (fixed 2026-09-11).

**4. Inventory value adds up per-unit costs.**
- **Affects:** `inventory_valuation_summary_view.sql:33`.
- **What's wrong:** it sums standard cost per unit with no quantity, so
  "total inventory value" comes to about $77 for the whole building. It also
  adds every operation's cost for a part, and groups by the snapshot's
  `Cost_Model_Key`, which is NULL. The cost model is on the history rows.
- **Fix:** needs quantity × cost; not written yet.

**5. Deviations never show their linked NC.**
- **Affects:** `quality_deviation_view.sql:66-68`.
- **What's wrong:** it joins the classic `Quality_v_Problem`, which is
  permanently empty. Vox's NCs live in `Quality_v_Problem_2`, the UX screen's
  table, the same trap the Quality reports fell into before 2026-09-22.
- **Fix:** read `Quality_v_Problem_2`; not written yet.

**6. Smaller:**
- **TAT** uses `DATE_DIFF(DAY)`, which is calendar days
  (`quality_turnaround_time_view.sql:132-136`).
- **Average daily usage** divides the month in progress by the full month
  (`inventory_avg_daily_usage_view.sql:26-29`).
- **Cycle count** is weighted per count, not per location
  (`part_cycle_count_view.sql:82`).
- **Disposition cost** puts closed no-material records into
  "(not yet dispositioned)" (`quality_disposition_cost_view.sql:116-117`).

## ETL and data findings

- **A table that goes to 0 rows keeps yesterday's data**
  ([`main.py` `write_to_bigquery`](../main.py)). This is deliberate, as a guard
  against transient ODBC failures, but the ETL can't tell a failure from a
  genuinely empty result.
  - **Affected tiles:** Open jobs, Pending approval, Ready to ship. When those
    legitimately fall to 0, they keep showing yesterday's rows, and nothing
    says so. The only trace is a "No rows to write" line in the run email.
  - **Shown in test:** it left PlexTest's price table pointing at customer
    parts that no longer existed, and 0 of 2,119 prices joined.
- **The PlexTest tenant's master data changes between days.** On 2026-09-24
  it went from 182 customers and 2,120 priced customer parts to 24 customers
  and 312 unpriced ones. So test numbers from different days aren't
  comparable, and a view that "broke" overnight may just be the tenant.
- **Also missing in the tenant:** `Personnel_v_Employee.Common_Name` is blank
  for every employee; there is only one shift key; and
  `Part_v_Cycle_Inventory.Location` is an integer with no location master
  extracted.

## Manual inputs (for Jennilyn)

These numbers are typed by people and can never come from Plex.

| Input | Where it lives | State | Needed |
|---|---|---|---|
| Sales goals by rep and company-wide | Manual-data app, Sales tab | 68 legacy goals imported | Who is the "Sales Representative" goal for? |
| Revenue goal | App, Revenue tab | Currently a copy of the company sales goal | A real revenue target, or confirm the copy |
| Production goals by area | App, Production tab | **Empty** | Monthly goals for Encapsulating, Bottling and Labeling (the live board shows 100M / 1.5M / 700K); whether other areas have goals |
| Safety incidents | App, Incidents tab | Nothing since the 7/23 recordable | Someone to log them; an empty log reads as a clean record |
| TAT Performance / Bonus standards | `turnaround_standards` (BigQuery) | Placeholders | Real figures, and which grouping: the old sheet's bottle types, or Plex's stock types |
| Lab TAT target ("within goal") | — | No home | Decision |
| DPMO opportunities per unit | Hard-coded 1 | Placeholder | The real figure, from Quality |
| Pipeline stage probabilities (35/70/80/95%) | Monday view constants | No Plex-side home | Decision |
| Destruction $ / Rework $ | Typed into NC descriptions | Cost field is 0.00 | Quality to use Plex's Cost field |
