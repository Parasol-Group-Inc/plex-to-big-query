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

## Built or scaffolded

| Report | Status | Notes |
|---|---|---|
| Pending Approval Orders | ✅ Built | `sales_orders_pending_approval_report` — 2nd/3rd `bq_view` on the live `sales_orders.yaml`, filtered to the confirmed "Pending Sales Approval" status (key 2585). No business-rule guess needed. |
| Printing Open Work Orders | ✅ Built | `printing_open_work_orders_report` — 4th `bq_view` on `work_orders.yaml`, mirrors the already-deployed `labeling_open_work_orders_report` with workcenter `'Printing%'` instead of `'Labeling Line%'`. Confirmed live workcenter. Conceptually a Production report despite appearing on this tab. |
| Orders Pending Approval by Accounting | ✅ Deployed, best-criteria — needs data-scientist input | `sales_orders_pending_accounting_approval_report`, filtered to "Pending Payment Review" (key 2638) — the only accounting-flavored stage in the confirmed status workflow. This is a label-text inference, not NetSuite-confirmed. See "Needs discussion" below. |
| Report for orders past 14 days old | ✅ Deployed, best-criteria — needs data-scientist input | `sales_orders_aging_report` — open orders with `PO_Date` 14+ days ago. "Past 14 days old" could instead mean days since last status change; see "Needs discussion" below. |
| Orders over $10k | ✅ Deployed, best-criteria — needs data-scientist input | `sales_orders_over_10k_report` — no dollar column exists on the order/line records at all (confirmed live); computed from the same price-join `sales_orders_report` already uses (base-tier price × quantity, summed per order). Excludes tax/freight. See "Needs discussion" below. |
| Orders over 10k bottles | ✅ Deployed, best-criteria — needs data-scientist input | `sales_orders_over_10k_bottles_report` — sums total quantity per order regardless of unit; which `Quantity_Unit` value(s) actually mean "bottles" was never confirmed against live data. See "Needs discussion" below. |
| Open Quotes | 🛠 Scaffolded, needs data-scientist input | `sales_quotes_open_report` (new pipeline, `Sales_v_Quote` + `_Status`). The schema has a literal `Open_Quote` flag — looked exact — but confirmed live it's 0 on all 8 configured quote statuses. Built with a status-exclusion proxy instead. See "Needs discussion" below. |
| Open RMA's | 🛠 Scaffolded, needs data-scientist input | `sales_returns_open_report` (new pipeline, `Sales_v_Return` + `_Status`) — clean status-exclusion (not Closed/Cancelled), but was never screenshotted to confirm this is the intended definition. |
| Customer List by Sales Rep | ✅ Deployed, best-criteria — needs data-scientist input | `sales_customers_by_rep_report` — derives "which customers a rep covers" from per-order rep assignment (`Sales_v_Order_Salesperson`), since Plex has no standing customer→rep assignment field. See "Needs discussion" below. |
| Revenue per sales rep | ✅ Deployed, best-criteria — needs data-scientist input | `sales_revenue_by_rep_report` — same price-join computed revenue as the $10k report, grouped by primary rep. Same caveats apply. |

## Needs discussion with the data scientist

| Report | What's unresolved |
|---|---|
| Orders Pending Approval by Sales Rep | Only ever seen as a bare name — may be the exact same report as "Pending Approval Orders" (key 2585) listed twice under a different name, or a genuinely different NetSuite view (e.g. filtered to the current user's own orders). Not built as a separate report to avoid shipping a silent duplicate — needs either a screenshot of its actual saved-search criteria, or the data scientist confirming whether it's a duplicate. |
| Orders Pending Approval by Accounting | Confirm "Pending Payment Review" (key 2638) is really what "by Accounting" means — it's a label-text inference, not a NetSuite screenshot. |
| Report for orders past 14 days old | Confirm the 14-day clock should run from `PO_Date` (order placed) rather than last status change. |
| Orders over $10k | Confirm the $10k basis: the computed price-join total this report uses (excludes tax/freight), vs. `Sales_v_PO.Master_Price` where it's actually populated, vs. something else entirely. |
| Orders over 10k bottles | Confirm which `Sales_v_Release.Quantity_Unit` value(s) mean "bottles" — the built report currently sums ALL units together, which may overcount orders that mix bottles with other unit types. |
| Open Quotes | Confirm what "open" should mean now that `Open_Quote` is confirmed unused — is New/Estimating/Quoted/Approved the right set, or should Approved count as no-longer-open? |
| Open RMA's | Confirm the status-exclusion definition (not Closed/Cancelled) matches the real NetSuite saved search — never screenshotted. |
| Customer List by Sales Rep | Confirm whether per-order rep assignment (this report's source) is an acceptable proxy for "a customer's assigned rep," or whether a standing assignment exists elsewhere (e.g. `Common_v_Region_Customer_Type.Salesperson`, unconfirmed live). |
| Vox \| RUSH Open Sos / One for Rush orders | `Sales_v_Priority` (the lookup `Sales_v_Release.Priority_Key` joins to) exists in schema but returned **0 rows live** — cannot confirm a "Rush" priority label even exists on this tenant. Get the actual NetSuite report definition, or ask the data scientist whether Rush orders are tracked some other way in Plex. |

## No match found — needs the actual NetSuite report or data-scientist input

| Report | What was checked |
|---|---|
| SO's with discounts | `Discount`/`Discount_Rate` columns exist only on `Sales_v_Quote_Part`/`Sales_v_Quote_Price_Cost` (the Quote side) — confirmed live there is no discount column anywhere on `Sales_v_PO`/`Sales_v_PO_Line`, and no `Quote_Key` field links an order back to its originating quote. No reliable join path exists. |
| Inventory consumption | No view or stored procedure matching "consumption" found anywhere in the schema or the 14,350-row stored-procedure catalog. Best unconfirmed lead: aggregating `Part_v_Job_Op` quantities, same lead already used for MFG Job Schedule — not built here since it's speculative, not a real match. |
| Allocation reports | Never received more than a bare name — too generic to search against a schema of 2,828 views. Needs a screenshot or a fuller description. |
| Revenue for Vox | Same issue as mapping-doc #21/#54 — too generic to pin to one report or view. |

## Out of scope, no further action

| Report | Notes |
|---|---|
| Sample Orders, Pending Certificates, Orders waiting to be completed, Work Orders partial buildable (labeling), Orders in Design | Native NetSuite saved searches, not individually investigated this pass (lower priority / no screenshot available) |
| Available Inventory | NetSuite's own "real-time view of inventory... committed, on hand and in order" — same concept name as `part_on_hand_inventory_report`, already built. Not a gap. |
| One for customers who are top/strategic, reports for orders with oos skus, One for SO's with credits applied, One for international customers, One for FBA sellers, Report that lets us type in a product and see all open orders | 💡 Idea, no source yet — marked "Nice to have" with no backing system |
| Design in Monday - NEW | Google Sheet that imports data *from* NetSuite into Monday.com — still fundamentally NetSuite-sourced |
