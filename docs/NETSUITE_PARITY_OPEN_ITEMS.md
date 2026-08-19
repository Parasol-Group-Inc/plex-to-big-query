# NetSuite Parity — Open Items (2026-08-14)

Consolidated punch list from the 2026-08-14 reports-list-wide equivalent
sweep (`docs/NETSUITE_REPORT_BUILD_PLAN.md` § "2026-08-14 batch"). Every
report below is *not yet resolved* — either it needs a data-scientist
decision, or it needs the actual NetSuite report definition. Reports that
were built cleanly or with a defensible best-criteria guess are NOT listed
here — see `reports-list/supply-chain.md`, `production.md`, and `sales.md`
for those.

## Part 1 — Needs a data-scientist decision

These all have a real, schema-confirmed Plex path — the open question is a
business-rule choice, not a missing table. Each was built with a best-guess
default so nothing is blocked, but the guess should be confirmed (or
corrected) before trusting the numbers.

| Report | Built as | The question | Live-data finding |
|---|---|---|---|
| Approve Vendor Return Authorizations | `quality_supplier_returns_pending_report` | What does "pending approval" mean for a supplier return? | The `Approving`/`Approved` flag columns exist but are **0 on all 6 live statuses** (New/Hold/OK to Ship/Shipped/Complete/Cancelled). Built with a status-exclusion proxy (not yet Shipped/Complete/Cancelled) instead. |
| Open Quotes | `sales_quotes_open_report` | What does "open" mean for a quote? | The `Open_Quote` flag exists but is **0 on all 8 live statuses**. Built with a status-exclusion proxy (not Won/Lost/Cancelled/No Quote) instead — is "Approved" open or closed here? |
| Orders Pending Approval by Sales Rep | *not built* | Is this the same report as "Pending Approval Orders" (key 2585), or genuinely different? | No live-data conflict — this one was never distinguishable from its sibling report by name alone. Deliberately not built as a guessed duplicate. |
| Orders Pending Approval by Accounting | `sales_orders_pending_accounting_approval_report` | Is "Pending Payment Review" (2638) really the "Accounting" stage? | Confirmed live as the only accounting-flavored status in the workflow, but it's a label-text inference, not NetSuite-confirmed. |
| Report for orders past 14 days old | `sales_orders_aging_report` | Should the 14-day clock start from `PO_Date`, or from the last status change? | Built using `PO_Date`. `Sales_v_PO_Change` (status history) is already extracted and could support the alternative if needed. |
| Orders over $10k | `sales_orders_over_10k_report` | What's the $10k basis? | No dollar column exists on the order/line records at all — confirmed live. Built from the same price-join `sales_orders_report` already uses (base-tier price × quantity, excludes tax/freight). `Sales_v_PO.Master_Price` exists as an alternative but is often unpopulated. |
| Orders over 10k bottles | `sales_orders_over_10k_bottles_report` | Which `Quantity_Unit` value(s) mean "bottles" specifically? | Built by summing ALL units together per order — could overcount orders that mix bottles with other unit types. Unit values were never seen live (0 rows on test tenant). |
| Open RMA's | `sales_returns_open_report` | Does "open" (not Closed/Cancelled) match the real NetSuite search? | Clean status-exclusion, no live-data conflict — just never screenshotted to confirm. |
| Customer List by Sales Rep / Revenue per Sales Rep | `sales_customers_by_rep_report` / `sales_revenue_by_rep_report` | Is per-order rep assignment (`Sales_v_Order_Salesperson`) an acceptable proxy for "a customer's assigned rep"? | Plex has no standing customer→rep field. A different lead (`Common_v_Region_Customer_Type.Salesperson`) exists but was never confirmed live. |
| Vox \| RUSH Open Sos (aka "One for Rush orders") | *not built* | Does a "Rush" priority label actually exist on this tenant? | `Sales_v_Priority` (the lookup `Sales_v_Release.Priority_Key` points to) returned **0 rows live** — can't confirm the concept exists at all without prod data or the actual NetSuite report. |
| Rolling / Monthly TAT Report | `quality_turnaround_time_report` | Is `Problem_Date` (vs. `Entered_Date`) the right "clock start" for turnaround time? Does this even cover the GSheet layer of the original hybrid report? | Built using `Problem_Date` → `Closed_Date`. The GSheet portion of the original manual report was never investigated. |
| Inventory Risk Analysis (Custom Formula / Item Stock Type) | `inventory_risk_analysis_report` | What aging threshold defines "risk" or "slow-moving"? | No packaged risk concept anywhere in Plex (confirmed at both the view and stored-procedure layer). Built exposing on-hand qty + days-since-last-container-activity with no cutoff baked in — the cutoff itself is the open question. |

## Part 2 — No Plex match found

Nothing was built for these. Either pull the actual NetSuite report
definition (a screenshot of its saved-search criteria, same as what
unblocked the Requisitions and Labeling Open WO reports), or ask the data
scientist whether Vox tracks this concept somewhere else entirely.

| Report | What was checked | Recommendation |
|---|---|---|
| Reorder Multiple Search | The only candidate name, `Material_v_Reorder_Point`, was tree-guessed only (never confirmed) — live query 2026-08-14 confirmed it doesn't exist ("Base table not found"). No other reorder-point view anywhere in the 2,828-view catalog. | Get the NetSuite report — it may define its own reorder logic (e.g. from `Item_Supplier`/lead-time fields) that doesn't map to a single Plex view. |
| SO's with discounts | Discount columns exist only on the Quote side (`Sales_v_Quote_Part.Discount`, `Sales_v_Quote_Price_Cost.Discount_Rate`) — confirmed live there is no discount field anywhere on `Sales_v_PO`/`Sales_v_PO_Line`, and no `Quote_Key` link from an order back to its originating quote. | Ask the data scientist how Vox actually represents an order-level discount today — it may not be a Plex-native concept at all (e.g. handled via a price override at order entry with no audit trail). |
| Inventory consumption | No view or stored procedure matching "consumption" anywhere in the schema or the 14,350-row stored-procedure catalog. | Get the NetSuite report definition — "consumption" likely means something specific (material usage vs. finished-good depletion) that needs a screenshot to disambiguate before searching further. |
| Allocation reports | Never received more than a bare name. | Get a screenshot or a fuller description — too generic to search a 2,828-view schema against. |
| Revenue for Vox | Same issue as mapping-doc #21/#54 (too generic to pin to one view). | Get a screenshot, or ask the data scientist what specific revenue breakdown this refers to (it may just be a saved search that scopes an otherwise-generic NetSuite "Revenue" report to the Vox subsidiary). |
