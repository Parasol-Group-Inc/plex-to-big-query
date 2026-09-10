# Vox Scorecard | WIP Order Value

> **Status:** ✅ Definition settled and verified 2026-09-09 — Pending Fulfillment + Hold only; $17,950 in `PlexTest` · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

The total dollar value of every order line that's been released or paid for but hasn't shipped yet — regardless of whether production has even started, is in progress, or is already done. This is Vox's own definition of Work In Progress (WIP), given directly by Jennilyn Tockstein (the data scientist) in a requirements meeting — see `meetings-reference/Sep-1/`.

## Where it fits

Replaces the Vox Nutrition Scorecard's "WIP" Operational Health tile. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Rebuilt the same day it was first written. The original version flagged a line as WIP if its linked job's status was "Production." Jennilyn corrected that directly: *"we don't need the production status... it's basically anything that is pending fulfillment... it doesn't matter where in the process it is... if the order line isn't a quote, isn't cancelled, and isn't shipped, then it's WIP."* The rebuilt version drops job status entirely — a line counts as WIP if its order isn't a quote, isn't cancelled, and no shipment has gone out yet for it (checked against the Shipping module added the same day). Value comes from the customer's base-tier price list, the same price join used throughout this pipeline.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_order_value_by_status_report`
- **SQL:** `reports/sql/sales_order_value_by_status_view.sql`

## Flags and open questions

- **✅ The ambiguity is settled (2026-09-09), and the old number was badly wrong.** Jennilyn had described WIP two incompatible ways on Sep 1; neither was quite it. Her ruling: *"really, it should just be pending fulfillment. I guess hold as well would be WIP because it was sold but it hasn't shipped yet. So it just be those two statuses"*, and *"we don't want to count pending sales approval because that's not considered an order yet."* So WIP is **Pending Fulfillment + Hold**, unshipped balance only.

  The previous "broad" filter was *not a quote, not cancelled*, which under Vox's status set also included **Pending Sales Approval, Deposit Review and Closed**. Correcting it dropped WIP from **$43,723 to $17,950** — the old figure was inflated about 2.4x. If you have screenshots of this tile from before 9 Sep, they overstate it.
- **✅ The Total Pipeline double-count is gone, not merely flagged.** Quote and Pending Sales Approval can no longer appear here at all, so no dollar can sit in both tiles. `also_counts_in_pipeline` is kept as a hardcoded `FALSE` purely so anything selecting it by name doesn't break; **`is_on_hold`** replaces it as a real flag.
- **Partial shipments are netted off.** Per *"if partials have shipped, we only want the WIP as the value of all of the order lines that haven't shipped yet"*, a release contributes only its unshipped balance.
- **Scope narrowed.** This view now covers WIP only. The original version's "ready to ship" concept moved to the new [`shipping_pending_revenue_report`](shipping_pending_revenue_report.md) — Jennilyn described that as a distinct, Shipping-module-sourced metric, not the same thing as WIP.
- **Live-verified with real data**: 32 real WIP lines, 15 distinct orders, $875,475 total — a much richer, more real result than the Job_Status-based version ever produced. 2 of the 32 lines have no price match (customer/part combination not found in the price list) and are excluded from the total.
- **`Sales_v_PO_Status.Is_Quote`/`Cancelled_Status` use `1 = true`**, not the `-1 = true` convention used elsewhere in this pipeline — confirmed by checking the real status rows before writing this.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
