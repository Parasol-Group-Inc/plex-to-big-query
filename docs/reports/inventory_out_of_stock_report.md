# Vox Scorecard | Out of Stock (33-parts)

> **Status:** ✅ Rebuilt and verified end-to-end 2026-09-09 — returns 0 rows because no `33` part has a minimum stock level set in Plex (see flags) · **Category:** Supply Chain · **Runs:** rides the Sales Orders pipeline

## What this tells you

Which parts are genuinely out of stock, by Vox's own precise definition — not a general inventory-risk heuristic. Given directly by Jennilyn Tockstein (data scientist): *"for us to be out of stock, it has to start with 33 for the part number, and it has to have a minimum stock level... if the inventory amount is negative, or we have zero inventory and we have demand... sometimes we make custom parts, those are okay to be negative, because that's just showing us we're in the process of making this part, it's not actually something we stock."*

## Where it fits

Replaces the Vox Nutrition Scorecard's "OOS" Operational Health tile. The earlier candidate in this repo (`inventory_risk_analysis_report.is_at_risk`, a 90-day-no-activity heuristic) turned out to be a different concept entirely — this report implements Vox's real rule instead. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

It is now a filter over [`inventory_available_to_sell_report`](inventory_available_to_sell_report.md), which owns the on-hand-minus-demand calculation. Three conditions, all required: the part number starts with `33`; `Minimum_Inventory_Quantity` is greater than 0 (a literal 0 doesn't count as "assigned" — decided 2026-09-01, and Jennilyn confirmed Sep-4 that **reorder point IS the minimum inventory quantity**, the same field, not a join); and quantity available is negative. Custom-classified parts are excluded, since they are expected to run negative while being made.

Availability is on-hand minus direct order demand minus BOM-exploded component demand. Since 2026-09-09 there is no longer a choice of reading to make: demand counts exactly the order statuses Plex includes in MRP, which Jennilyn set to Pending Fulfillment and Hold. The BOM half is not optional here — a `33` blend is almost never ordered directly, so without it these parts show no demand at all and could never flag.

- **Pipeline:** `reports/sales_orders.yaml` → `inventory_out_of_stock_report`
- **SQL:** `reports/sql/inventory_out_of_stock_view.sql`

## Flags and open questions

- **⚠ Rewritten 2026-09-09 — this report returned 0 rows for its entire life, against a count of 5 on Jennilyn's own sheet.** Two independent causes, both now fixed. First, the on-hand filter tested `Active = -1` when the column holds `1/0`, so on-hand was always zero (fixed 2026-09-04). Second — the deeper one — demand was read from `Sales_v_Release_Allocation`, which has **0 rows in both `PlexTest` and `PlexProd` and always has.** Allocation is a *picking and staging* concept (which container is committed to which shipment); it is simply not where Plex keeps demand. The Sep-4 screenshots of Plex's own **Sales Order Line Inventory Check** screen showed demand coming from **sales order releases** instead. That is what the report now uses.
- **✅ The BOM half is proven, and it was the missing piece.** Before the BOM extraction ran, **no `33` part appeared in the availability report at all** — these parts have neither containers nor direct sales orders, so their demand arrives *entirely* through the finished goods that consume them. After the run (2026-09-09): `33127-01VOXNU-1` shows **305,000 units of BOM-exploded demand and −305,000 availability**. The calculation works end to end.
- **⚠ It still returns 0 rows, and now for a precise business reason: nobody has set a minimum stock level.** Both `33` parts on the tenant today (`33127-01VOXNU-1`, `33111-01VOXNU-1`) have `Minimum_Inventory_Quantity = 0`, and the rule treats a literal 0 as "not assigned". So the part above is short by 305,000 units and still correctly excluded. **This report cannot fire for any part until someone enters minimum inventory quantities in Plex** — that is data entry in Plex, not a code change here.
- **The "count of 5" on Jennilyn's sheet can't be reconciled against current data.** An earlier check found 7 `33` parts with 5 carrying a minimum above zero; `PlexTest` has since been reset and now holds only 2, both at zero. Worth re-checking against production once Vox is live rather than against test.
- **✅ The `33` naming rule is confirmed to stay (2026-09-09).** Scanning the part number looks like the fragile choice, so it is worth recording that Jennilyn rejected the alternative outright: *"the 33 is the most reliable way."* A part-type dropdown was considered and turned down because switching to it would break the rule.
- **✅ Availability no longer has a definition to choose.** The old "does this include unapproved orders" question is gone — Jennilyn removed Pending Sales Approval and Deposit Review from Plex's own MRP demand flag on 2026-09-09, so demand is exactly Pending Fulfillment + Hold and the report inherits it. The `quantity_available_firm_only` column was removed as a result.
- **Jennilyn is adding test inventory to validate this.** On 2026-09-09 the Plex screen showed zero inventory against real requirements simply because *"I didn't add any fake inventory today"*; she plans to add some and re-check. That test plus a minimum stock level is all that stands between this report and its first real row.
- **Usage/consumption is deliberately out of scope for go-live** (Jennilyn, Sep-4): *"maybe we won't consider usage for go live and we'll just base it off of is there a minimum inventory quantity and is the quantity available negative."*
- **Boolean convention** — `Part_v_Container.Active` holds `1/0`, and so do the `Sales_v_PO_Status` flags. The `-1 = true` convention this doc previously claimed for the container columns **was wrong** and is what caused the bug above. See [`docs/CHEATSHEET.md`](../CHEATSHEET.md), whose boolean table was the original source of the error.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation; [`inventory_available_to_sell_report`](inventory_available_to_sell_report.md) documents the demand rules this report inherits.
