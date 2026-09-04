# Vox Scorecard | Out of Stock (33-parts)

> **Status:** ✅ Built and verified 2026-09-01 — 0 rows, confirmed genuinely empty (see below), logic ready · **Category:** Supply Chain · **Runs:** rides the Sales Orders pipeline

## What this tells you

Which parts are genuinely out of stock, by Vox's own precise definition — not a general inventory-risk heuristic. Given directly by Jennilyn Tockstein (data scientist): *"for us to be out of stock, it has to start with 33 for the part number, and it has to have a minimum stock level... if the inventory amount is negative, or we have zero inventory and we have demand... sometimes we make custom parts, those are okay to be negative, because that's just showing us we're in the process of making this part, it's not actually something we stock."*

## Where it fits

Replaces the Vox Nutrition Scorecard's "OOS" Operational Health tile. The earlier candidate in this repo (`inventory_risk_analysis_report.is_at_risk`, a 90-day-no-activity heuristic) turned out to be a different concept entirely — this report implements Vox's real rule instead. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Three conditions, all required: the part number starts with `33`; `Part_v_Part.Minimum_Inventory_Quantity` is greater than 0 (a literal 0 doesn't count as "assigned" — decided 2026-09-01); and quantity available (on-hand minus allocated) is negative. Custom-classified parts are excluded via `Part_v_Part_Product_Type` (real values like "Custom Formula Capsules" vs. "Stock Formula Capsules" are already live on this tenant). On-hand quantity reuses `part_on_hand_inventory_report`'s already-confirmed logic; allocated quantity comes from `Sales_v_Release_Allocation`, added the same day.

- **Pipeline:** `reports/sales_orders.yaml` → `inventory_out_of_stock_report`
- **SQL:** `reports/sql/inventory_out_of_stock_view.sql`

## Flags and open questions

- **0 rows today for a real, checked reason**: `Sales_v_Release_Allocation` (needed for the "allocated" half of the calculation) has zero rows on this tenant right now — confirmed live, not assumed. The rest of the logic is checked against real data: only 7 real parts start with `33` today (all Semi-Finished Goods, none yet Custom-classified), and 410 parts on this tenant have a real `Minimum_Inventory_Quantity` set.
- **`Sales_v_Release_Allocation`'s boolean/Active convention (if it has one) has never been checked** — there are no real rows yet to check it against. No `Active` filter is applied here; revisit once rows exist.
- **Boolean convention note**: `Part_v_Container.Active`/`Container_Status.OK_Status` (used for on-hand) use `-1 = true` — the *other* convention from the one confirmed on `Sales_v_Shipper_Status`/`Sales_v_PO_Status` in this session's sibling reports. Don't mix them up.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
