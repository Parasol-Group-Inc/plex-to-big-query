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
| 🔧 | Was broken; **fixed and deployed** (`terraform apply` from `main`, 2026-09-25 01:10 UTC). Each prod view switches to the fixed SQL on its pipeline's next scheduled run. |
| 🏗 | The view needs rebuilding. |
| ❓ | Needs a decision or data from someone outside this team. |
| ⛔ | No Plex source, by design. |

## Tile by tile

| Section | Tile | View | Status | What to know |
|---|---|---|---|---|
| Revenue | MTD / YTD Revenue | `sales_revenue_summary_report` | ✅ | YTD only covers months Plex has; earlier history needs a one-off top-up. |
| Revenue | Revenue by part group | `sales_revenue_summary_report` | 🔧 | **Always one bar, "(no group)".** Parts carry `Part_Group_Key` (14,149 of 14,150), but the lookup it joined, `Part_v_Part_Product_Group`, is empty in test *and* prod. The names live in **`Part_v_Part_Group`** (13 groups, Capsule … Supplies; every key in use resolves). See finding 7. **Needs a new extraction:** the groups appear only after the next `terraform apply` + Sales Orders ETL run; not provable in the sandbox yet. |
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
| Quality | Deviations | `quality_deviation_report` | 🔧 | The linked NC never showed (finding 5). Now has `deviation_month` (by add date), so the tile doesn't have to pick. |
| Quality | Destruction $ / Rework $ | `quality_disposition_cost_report` | 🔧 ❓ | Works in the sandbox only because costs are modelled there. On real records Cost is 0.00 and the money is typed into the description. The "missing cost" flag now counts 0.00 as missing on Scrap/Rework records (finding 6). |
| Quality | 30-day rolling TAT | `quality_turnaround_time_report` | 🔧 ❓ | Counted **calendar** days against **work-day** standards; now has work-day columns and met/missed uses them (finding 6). Mon–Fri only, no holidays. The standards themselves are placeholders. |
| Inventory | Quantity available | `inventory_available_to_sell_report` | ✅ | |
| Inventory | Out of stock | `inventory_out_of_stock_report` | ✅ | One part number can appear twice (two Part_Keys). |
| Inventory | Top quantity | `inventory_top_quantity_report` | ✅ | Quantity only. |
| Inventory | Average daily usage | `inventory_avg_daily_usage_report` | 🔧 | The current month was divided by all its days, so it read low; now by days elapsed through today (finding 6). It is per part, in each part's own unit: a tile that sums parts adds capsules to bottles. The new `unit` column lets Looker filter; the view converts nothing. |
| Inventory | Inventory value | `inventory_valuation_total_report` | 🔧 ❓ | Read about $77; now on-hand × unit cost, **$2.76M** in the sandbox (finding 4). **Only the current snapshot has a value**: Plex's snapshot holds cost, not quantity, and no month-end on-hand is extracted, so there is no trend yet. The interim source is NetSuite anyway. |
| Inventory | Cycle count accuracy | `part_cycle_count_report` | 🔧 | Averaged per count, not per location; now each location's latest count in the month (finding 6). No location names, because no location master is extracted. |
| Operations | Open caps | `mfg_job_open_caps_report` | 🔧 | Filtered by name (`Encapsulation%`), which missed "Schedule Encapsulation", where real open jobs sit. Now filters by the Encapsulating group, like Open bottles (finding 6). |
| Operations | Open bottles | `bottling_job_open_report` | ✅ | |
| Operations | Safe days | `safety_incidents` (table) | 🏗 ❓ | No view computes Safe Days; Looker has to (today − latest incident date). An empty log reads as a clean record. |

## View bugs

**Every fix below is deployed** (`terraform apply` from `main`, 2026-09-25
01:10 UTC) and was verified on real PlexTest data after the test runs. Prod
views switch over on each pipeline's next scheduled run: Work Orders at
01:20 UTC the same night, Quality and Inventory from 02:20 UTC, and Sales
Orders — which also brings the new `Part_v_Part_Group` extraction — at its
next 01:00 UTC run.

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
  three views now do the same (order, then customer, then the old table), and
  the sales view adds `sales_rep_source`.
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
- **Fix (🔧 deployed 2026-09-25):** value = on-hand
  quantity (`part_on_hand_inventory_report`) × the part's per-unit cost at
  the snapshot. That cost is the sum of the two cost sub-types at **one**
  operation: the highest-costed operation from the part's latest cost change.
  Operation costs are cumulative (the real blend is $1.25 at the op with its
  BOM and $1.354 at the next op, which has no BOM). The latest-change filter
  drops operations left behind by a re-routing. The pointer table is empty in
  real Plex, so the cost falls back to "cost history as of the snapshot date".
  Sandbox: **$76.65 → $2,760,901.76** on 1 Sep. That matches an independent
  on-hand × latest-cost sum to the cent. PlexTest: compiles, 5 costed parts,
  none on hand, so the value is $0 with 57 on-hand parts uncosted.
- **Still open:** (a) no trend. `Part_v_Snapshot` has no quantity column,
  so earlier snapshots show a NULL value, not today's stock at old costs. A
  trend needs month-end on-hand captured somewhere. (b) Operation order is a
  proxy, because `Part_v_Part_Operation` is not extracted. (c) One part
  number can have two revisions ("Rev 00" and "Weighed"), and a cost is per
  revision. In the sandbox 10 "Rev 00" powders (~2.8M units) are on hand but
  uncosted, because the generator costs only parts whose containers carry an
  operation. `uncosted_on_hand_part_count` shows this.

**5. Deviations never show their linked NC.**
- **Affects:** `quality_deviation_view.sql:66-68`.
- **What's wrong:** it joins the classic `Quality_v_Problem`, which is
  permanently empty. Vox's NCs live in `Quality_v_Problem_2`, the UX screen's
  table, the same trap the Quality reports fell into before 2026-09-22.
- **Fix:** read `Quality_v_Problem_2`. **Fixed 2026-09-24, deployed 2026-09-25.** The link table's
  `Problem_Key` is Problem_2's own key: the one real link (problem 117294)
  resolves to NC #21. Sandbox: deviations with an NC went from 0 of 151 to 49.
  The view also gained `deviation_month` (by add date).
- **Still blank on real data, correctly:** that one real link belongs to
  deviation 14453, which is gone from Plex; today's only deviation (14461) has
  no NC linked. The stale link row fits the "0 rows keeps yesterday's data"
  finding below.

**6. Smaller:**
- **TAT** used `DATE_DIFF(DAY)`, which is calendar days
  (`quality_turnaround_time_view.sql:132-136`). **Fixed 2026-09-24,
  deployed 2026-09-25:** work-day columns for both clocks, and
  met/missed now uses them. Mon–Fri only; there is no holiday table. Sandbox
  misses fell 31 → 6 (Performance) and 95 → 73 (Bonus).
- **Average daily usage** divided the month in progress by the full month
  (`inventory_avg_daily_usage_view.sql:26-29`). **Fixed 2026-09-24,
  deployed 2026-09-25:** the current month divides by days elapsed
  through today (today included, the run-rate tile's rule); past months by
  their full length. Through today, not the last usage date, so idle days
  count as zero. Sandbox, September (25 days elapsed by UTC date): the top
  part reads 3.05M/day, not 2.54M. Adds `days_in_period`,
  `is_month_in_progress` and `unit`.
- **Cycle count** was weighted per count, not per location
  (`part_cycle_count_view.sql:82`). **Fixed 2026-09-24, deployed 2026-09-25:** each location counts once a month, on its latest count
  that month. `locations_counted` is now exactly the accuracy denominator;
  `items_counted` still counts every count; new `recounted_locations`.
  Sandbox May: 92.5% → 94.1%. (PlexTest's September "82.1%" is **not**
  evidence either way: those 56 counts were rows the retired
  `scorecard_test_data.py` injector wrote, which outlived it because the ETL
  keeps a raw table when Plex returns 0 rows. They were deleted 2026-09-24.)
- **Open caps** filtered `wc.Name LIKE 'Encapsulation%'`
  (`mfg_job_open_caps_view.sql:54`), which misses **Schedule Encapsulation**.
  That is not an empty pseudo-centre: in PlexTest it holds open job 3
  (1,342,000 caps, the same Encapsulating operation as the line job), and
  all four open bottling jobs sit on Schedule Bottling, which Open bottles'
  group filter already includes. **Fixed 2026-09-24,
  deployed 2026-09-25.** `Workcenter_Group = 'Encapsulating'` (exactly the ten lines plus
  Schedule Encapsulation). PlexTest: 200,000 → 1,542,000 open caps. The
  sandbox has no Schedule Encapsulation jobs, so it is unchanged there.
- **Disposition cost** put closed no-material records into
  "(not yet dispositioned)" (`quality_disposition_cost_view.sql:116-117`), and
  its "missing cost" flag counted only NULLs, while an unfilled Plex Cost is
  0.00. **Both fixed 2026-09-24, deployed 2026-09-25:** blanks
  split into open / closed-no-material / closed-disposition-missing (sandbox:
  91 → 32 / 58 / 1), and the flag counts NULL-or-0 on Scrap/Rework.

**7. Part group joins the wrong lookup.**
- **Affects:** `shipping_revenue_report.sql` (so `sales_revenue_summary_report`
  and "Revenue by part group"), `sales_mtd_by_status_change_view.sql`, and the
  `product_group` column of `sales_orders_view.sql` and
  `sales_orders_open_view.sql`.
- **What's wrong:** they joined `Part_v_Part.Part_Group_Key` to
  `Part_v_Part_Product_Group`, which has 0 rows in test and prod.
- **Where the names are:** `Part_v_Part_Group` (`Part_Group_Key`, `Part_Group`;
  no PCN column). Pulled live from the Plex test host on 2026-09-24: 13 groups,
  and all 10 distinct keys on `Part_v_Part` (test and prod) resolve.
- **Fix, deployed 2026-09-25:** new extraction
  `Part_v_Part_Group` → `raw_Part_v_Part_Group` in both `reports/sales_orders.yaml`
  and `reports/test/sales_orders.yaml` (26 → 27 `plex_view:` entries each), and
  the four views join it. Checked read-only against PlexTest with the 13 rows
  inlined: the sales view's 21 rows all read `Capsule`; 36 of 40 order lines
  get a group.
- **Not in the sandbox yet:** the raw table doesn't exist in PlexTest until the
  next `terraform apply` + Sales Orders ETL run, so the sandbox keeps the old
  versions of `shipping_revenue_report` and `sales_mtd_by_status_change_report`
  (their recreate fails). After that run, `build.copy_base_tables(sb,
  ['raw_Part_v_Part_Group'])` and a view rebuild will prove it.

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
