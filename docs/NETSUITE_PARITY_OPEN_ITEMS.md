# NetSuite Parity — Open Items (2026-08-14, decided 2026-08-21)

Consolidated punch list from the 2026-08-14 reports-list-wide equivalent
sweep (`docs/NETSUITE_REPORT_BUILD_PLAN.md` § "2026-08-14 batch").

**Update 2026-08-21:** Emilio made the call not to wait on a data-scientist
review for Part 1 below — pick the best-criteria answer for each and adjust
later if a report's numbers come out wrong once real data lands (starts
2026-08-24). Every Part 1 item is now DECIDED on that basis; none of them
were blocked by missing data, only by an unconfirmed business rule. Part 2
is unchanged — those are genuinely missing a Plex data source, which
"pick a criteria" can't fix; they still need the actual NetSuite report
definition or a data-scientist steer on where the concept lives.

## Part 1 — Decided (best-criteria, adjust if real data disagrees)

These all have a real, schema-confirmed Plex path. Each already had a
best-guess default in place; the entries below are the ones where that
default was upgraded to a documented decision on 2026-08-21 (code updated
where the decision required a SQL change).

| Report | Built as | The question | Decision |
|---|---|---|---|
| Approve Vendor Return Authorizations | `quality_supplier_returns_pending_report` | What does "pending approval" mean for a supplier return? | Kept the existing status-exclusion proxy (not yet Shipped/Complete/Cancelled) — the `Approving`/`Approved` flags are confirmed dead (0 on all 6 statuses) so there's no better literal signal available. |
| Open Quotes | `sales_quotes_open_report` | Is "Approved" open or closed? | **Decided: closed.** Approved now excluded alongside Won/Lost/Cancelled/No Quote — reasoning: Approved marks the decision point, the quote is moving toward becoming an order, not still awaiting action. SQL updated (`sales_quotes_open_view.sql`). |
| Orders Pending Approval by Sales Rep | `sales_orders_pending_approval_by_rep_report` (new) | Is this the same report as "Pending Approval Orders" (key 2585)? | **Decided: yes, same data.** Built as a thin alias view over `sales_orders_pending_approval_report` rather than a duplicated pipeline, so the two can't silently drift apart. If it's ever confirmed to be a genuinely different scope, replace the alias with real logic. |
| Orders Pending Approval by Accounting | `sales_orders_pending_accounting_approval_report` | Is "Pending Payment Review" (2638) really the "Accounting" stage? | Kept — it's the only accounting-flavored status in the confirmed workflow, no better candidate exists. |
| Report for orders past 14 days old | `sales_orders_aging_report` | `PO_Date` or last status change? | Kept `PO_Date` — simpler and already live; revisit with `Sales_v_PO_Change` (already extracted) if the aging numbers look wrong once real orders age past 14 days. |
| Orders over $10k | `sales_orders_over_10k_report` | What's the $10k basis? | Kept the price-join total (base-tier price × quantity, excludes tax/freight) — the only basis with real data behind it; `Master_Price` stays a fallback if it turns out to be more consistently populated than expected. |
| Orders over 10k bottles | `sales_orders_over_10k_bottles_report` | Which `Quantity_Unit` value(s) mean "bottles"? | Kept summing all units — no live unit values exist yet to disambiguate. Revisit once real orders populate `Quantity_Unit` and it's clear whether non-bottle units are actually mixed into these orders in practice. |
| Open RMA's | `sales_returns_open_report` | Does "open" match the real NetSuite search? | Kept — clean status-exclusion, no live-data conflict to resolve. |
| Customer List by Sales Rep / Revenue per Sales Rep | `sales_customers_by_rep_report` / `sales_revenue_by_rep_report` | Is per-order rep assignment an acceptable proxy for "assigned rep"? | Kept the per-order proxy (`Sales_v_Order_Salesperson`) — Plex has no standing customer→rep field to use instead. |
| Rolling / Monthly TAT Report | `quality_turnaround_time_report` | `Problem_Date` or `Entered_Date` as the clock start? | Kept `Problem_Date` → `Closed_Date`. |
| Inventory Risk Analysis (Custom Formula / Item Stock Type) | `inventory_risk_analysis_report` | What aging threshold defines "risk"? | **Decided: 90+ days since last container activity (or no activity at all) = `is_at_risk`.** A general-purpose slow-moving-inventory convention, not derived from Vox policy — `days_since_activity` stays exposed so the cutoff can change with zero recomputation if 90 is wrong. SQL updated (`inventory_risk_analysis_view.sql`). |

**Still genuinely blocked, not a criteria question:** Vox | RUSH Open Sos
(aka "One for Rush orders") — `Sales_v_Priority` (the lookup
`Sales_v_Release.Priority_Key` points to) returned **0 rows live**, so
there's no data to pick a criteria *from*. This isn't an ambiguous rule
like the ones above, it's an empty table — needs either the actual
NetSuite report definition or confirmation the "Rush" concept exists on
this tenant at all before anything can be built.

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
