# Reports List — Sales

Source file: `Reports List - Sales.csv`. Columns: Report Name, Source,
Function, Users, Link, Priority.

**Almost every row here is a native NetSuite saved search** (`searchid=`
URLs) — ❌ out of scope for this Plex→BigQuery pipeline in the sense that
NetSuite itself isn't a data source this pipeline reads. A 2026-08-14 pass
went through each name individually looking for a real Plex equivalent
(same treatment already given to Supply Chain's rows) — several turned out
to be buildable. See `docs/NETSUITE_REPORT_BUILD_PLAN.md` for the full
confirmation log.

> **2026-08-23:** while generating business-facing docs in `docs/reports/`, found that **Open Quotes** and **Open RMA's** — both listed "Deployed" in this table — had no Cloud Run job, scheduler, or Terraform resource anywhere in the repo, and nothing under their names in the GCS config bucket, despite finished/schema-confirmed SQL. **Fixed same day** — both now have their own Cloud Run job + scheduler pair, deployed via `terraform apply` (18 resources added), and both test runs completed clean. See [`docs/reports/sales_quotes_open_report.md`](../docs/reports/sales_quotes_open_report.md) and [`docs/reports/sales_returns_open_report.md`](../docs/reports/sales_returns_open_report.md).

> **2026-08-22:** `reports/sales_orders.yaml` — the report config backing
> every "Built"/"Deployed" row below — was promoted from test-only to the
> production GCS path (`terraform apply`; prod config had been stale since
> 2026-08-21). All of these reports go out for real on the next scheduled
> prod run, not just PlexTest.

## Built or scaffolded

| Report | Status | Notes |
|---|---|---|
| Pending Approval Orders | ✅ Built | `sales_orders_pending_approval_report` — 2nd/3rd `bq_view` on the live `sales_orders.yaml`, filtered to the confirmed "Pending Sales Approval" status (key 2585). No business-rule guess needed. |
| Orders Pending Approval by Sales Rep | ✅ Built 2026-08-21, decided best-criteria | `sales_orders_pending_approval_by_rep_report` — thin alias view over `sales_orders_pending_approval_report`, decided to be the same underlying data under NetSuite's alternate label rather than a genuinely distinct search. See `docs/NETSUITE_PARITY_OPEN_ITEMS.md`. |
| Printing Open Work Orders | ✅ Built | `printing_open_work_orders_report` — 4th `bq_view` on `work_orders.yaml`, mirrors the already-deployed `labeling_open_work_orders_report` with workcenter `'Printing%'` instead of `'Labeling Line%'`. Confirmed live workcenter. Conceptually a Production report despite appearing on this tab. |
| Orders Pending Approval by Accounting | ✅ Deployed, decided best-criteria | `sales_orders_pending_accounting_approval_report`, filtered to "Pending Payment Review" (key 2638) — the only accounting-flavored stage in the confirmed status workflow. Kept as the decision 2026-08-21 — no better candidate exists. |
| Report for orders past 14 days old | ✅ Deployed, decided best-criteria | `sales_orders_aging_report` — open orders with `PO_Date` 14+ days ago. Kept 2026-08-21; revisit with `Sales_v_PO_Change` if this looks wrong once real orders age. |
| Orders over $10k | ✅ Deployed, decided best-criteria | `sales_orders_over_10k_report` — no dollar column exists on the order/line records at all (confirmed live); computed from the same price-join `sales_orders_report` already uses (base-tier price × quantity, summed per order). Excludes tax/freight. Kept 2026-08-21 — the only basis with real data behind it. |
| Orders over 10k bottles | ✅ Deployed, decided best-criteria | `sales_orders_over_10k_bottles_report` — sums total quantity per order regardless of unit. Kept 2026-08-21; revisit once real `Quantity_Unit` values populate and it's clear whether non-bottle units mix into these orders. |
| Open Quotes | ✅ Deployed 2026-08-23, decided 2026-08-21 | `sales_quotes_open_report` (own Cloud Run job + scheduler, 10:00/10:10 PM Mountain prod/test — added via `terraform apply` after the gap below was found). `Open_Quote` confirmed dead (0 on all 8 statuses); built with a status-exclusion proxy. **Decided: Approved now counts as closed** (moving toward becoming an order, not still awaiting a decision) — New/Estimating/Quoted are the only "open" statuses. **First real run failed view creation** (`raw_Sales_v_Quote` empty → all-`STRING`, `_Status`/`Common_v_Customer` real → `INT64`) — fixed with `SAFE_CAST` on both sides of every join/filter, re-verified by directly querying the view. |
| Open RMA's | ✅ Deployed 2026-08-23, decided best-criteria | `sales_returns_open_report` (own Cloud Run job + scheduler, 10:20/10:30 PM Mountain prod/test — added via `terraform apply` after the gap below was found) — clean status-exclusion (not Closed/Cancelled). Kept 2026-08-21 — no live-data conflict to resolve. **First real run failed view creation**, same `STRING`/`INT64` cause as Open Quotes — fixed the same way, re-verified by directly querying the view. |
| Customer List by Sales Rep | ✅ Deployed, decided best-criteria | `sales_customers_by_rep_report` — derives "which customers a rep covers" from per-order rep assignment (`Sales_v_Order_Salesperson`), since Plex has no standing customer→rep assignment field. Kept 2026-08-21. |
| Revenue per sales rep | ✅ Deployed, decided best-criteria | `sales_revenue_by_rep_report` — same price-join computed revenue as the $10k report, grouped by primary rep. Same decision applies. |
| Vox \| RUSH Open Sos / One for Rush orders | ✅ Deployed (prod+test) 2026-08-21, unblocked by screenshots | `sales_orders_rush_open_report` — the earlier `Sales_v_Priority` lead was a dead end (0 rows live); the real NetSuite search ("ATL \| RUSH Open SOs") filters on `Memo (Main) contains RUSH`, a free-text convention, confirmed by a real order (SO0117746, Memo starting "RUSH \| New label review..."). Built as `UPPER(Sales_v_PO.Note) LIKE '%RUSH%'` plus a status exclusion (Closed/Cancelled/Pending Sales Approval). **Test result:** view deploys cleanly, 0 rows on this tenant's 9 real live sales orders — none currently match `RUSH` in `Note`. Inconclusive on a sample this small, not disproven; see the SQL file header for the "Billed" status gap and the unconfirmed Note-field convention caveat. |
| Allocation reports | ✅ Deployed (prod+test) 2026-08-21, decided open-status proxy | `sales_order_allocation_report` — unblocked by a screenshot of the real search ("Vox \| Allocation Report"). Joins `Sales_v_PO → Sales_v_PO_Line → Sales_v_Release → Sales_v_Release_Job → Part_v_Job`. Of NetSuite's 4 sales-order statuses in the filter, only "Pending Fulfillment" is confirmed live — **decided: use the same "not Closed/Cancelled" open-status proxy already used for Open Quotes/RMAs** rather than build on the one narrow match or wait for a data-scientist call. Job side uses the same Completed/Cancelled/Hold-inverse pattern as the Labeling/Printing Open WO reports. **Test deploy caught a real bug:** the view initially failed to create at all — `Sales_v_Release_Job`'s first-ever extraction returned 0 rows, so BigQuery typed all 3 columns as STRING, breaking the join against the already-INT64-typed `Sales_v_Release`/`Part_v_Job`. Fixed with `SAFE_CAST` on both join conditions, redeployed, now creates cleanly. **Still 0 rows** — `raw_Sales_v_Release_Job` itself is empty on this tenant (0 rows) even though `Sales_v_Release` (8 rows) and `Part_v_Job` (16 rows) both have real data, meaning no job is currently linked to a release here. Needs a data-scientist/Vox answer: does this tenant actually populate job-to-release links in Plex? See the SQL file header for the full mapping and the fix note. |

## Still genuinely open (not a criteria question — missing data)

Everything in the table above was decided 2026-08-21 on Emilio's call not
to wait for a data-scientist review — see `docs/NETSUITE_PARITY_OPEN_ITEMS.md`
for the full reasoning per report. Nothing is currently blocked on missing
data on this tab as of 2026-08-21 (the last blocker, Rush orders, was
resolved above).

## No match found — needs the actual NetSuite report or data-scientist input

| Report | What was checked |
|---|---|
| SO's with discounts | `Discount`/`Discount_Rate` columns exist only on `Sales_v_Quote_Part`/`Sales_v_Quote_Price_Cost` (the Quote side) — confirmed live there is no discount column anywhere on `Sales_v_PO`/`Sales_v_PO_Line`, and no `Quote_Key` field links an order back to its originating quote. No reliable join path exists. |
| Inventory consumption | No view or stored procedure matching "consumption" found anywhere in the schema or the 14,350-row stored-procedure catalog. Best unconfirmed lead: aggregating `Part_v_Job_Op` quantities, same lead already used for MFG Job Schedule — not built here since it's speculative, not a real match. |
| Revenue for Vox | Same issue as mapping-doc #21/#54 — too generic to pin to one report or view. |
| Sample Orders (`Sales \| Open Sample Orders (Pending Fulfillment)`) | **Investigated 2026-08-19-21, pending — flagged, not a build blocker to keep chasing.** Screenshots confirmed the saved search filters on `Sample Order` — a **custom body field** (NetSuite's own Field Help: "This is a custom field created for your account," no source formula shown), sitting alongside sibling custom checkboxes `Employee Order`/`Blanket Order`/`Design Labeling Order`. Checked `Sales_v_PO_Type` live — only "Blanket" and "Spot Buy" configured, no "Sample" type at all — ruling out the obvious Plex proxy. Real order examples show inconsistent pricing (not always $0, not a fixed tier), so no reliable Plex-side derivation exists. The one Plex status match that *did* confirm cleanly: `Sales_v_PO_Status` key 2073 is literally named "Pending Fulfillment," live-confirmed — so the status half of this search is buildable, just not the Sample flag. Options on the table if this becomes a priority: (a) bridge via a NetSuite export into a Google Sheet, same pattern as the `spreadsheets/` series; (b) ask Vox to start tracking a real "Sample" `PO_Type` in Plex going forward (would only cover new orders, not backfill); (c) a second NetSuite-native data connector (SuiteAnalytics Connect) if NetSuite-only custom fields keep coming up across other reports, not justified for one field alone. |

## Out of scope, no further action

| Report | Notes |
|---|---|
| Pending Certificates, Orders waiting to be completed, Work Orders partial buildable (labeling), Orders in Design | Native NetSuite saved searches, not individually investigated this pass (lower priority / no screenshot available) |
| Available Inventory | NetSuite's own "real-time view of inventory... committed, on hand and in order" — same concept name as `part_on_hand_inventory_report`, already built. Not a gap. |
| One for customers who are top/strategic, reports for orders with oos skus, One for SO's with credits applied, One for international customers, One for FBA sellers, Report that lets us type in a product and see all open orders | 💡 Idea, no source yet — marked "Nice to have" with no backing system |
| Design in Monday - NEW | Google Sheet that imports data *from* NetSuite into Monday.com — still fundamentally NetSuite-sourced |
