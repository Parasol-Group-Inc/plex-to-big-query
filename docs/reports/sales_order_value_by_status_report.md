# Vox Scorecard | WIP Order Value

> **Status:** ✅ Rebuilt and verified 2026-09-01 (corrected definition) — 32 real WIP lines across 15 orders, $875,475 total · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

The total dollar value of every order line that's been released or paid for but hasn't shipped yet — regardless of whether production has even started, is in progress, or is already done. This is Vox's own definition of Work In Progress (WIP), given directly by Jennilyn Tockstein (the data scientist) in a requirements meeting — see `meetings-reference/Sep-1/`.

## Where it fits

Replaces the Vox Nutrition Scorecard's "WIP" Operational Health tile. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Rebuilt the same day it was first written. The original version flagged a line as WIP if its linked job's status was "Production." Jennilyn corrected that directly: *"we don't need the production status... it's basically anything that is pending fulfillment... it doesn't matter where in the process it is... if the order line isn't a quote, isn't cancelled, and isn't shipped, then it's WIP."* The rebuilt version drops job status entirely — a line counts as WIP if its order isn't a quote, isn't cancelled, and no shipment has gone out yet for it (checked against the Shipping module added the same day). Value comes from the customer's base-tier price list, the same price join used throughout this pipeline.

- **Pipeline:** `reports/sales_orders.yaml` → `sales_order_value_by_status_report`
- **SQL:** `reports/sql/sales_order_value_by_status_view.sql`

## Flags and open questions

- **⚠ The definition is genuinely ambiguous, and both readings are now available as a filter (added 2026-09-04).** Jennilyn described WIP two different ways in the same conversation, and they do not produce the same number:
  - **Broad** — *"if it's not a quote, if it's not cancelled or whatever, and if that order line isn't shipped, then it's WIP."*
  - **Strict** — *"it's basically anything that is pending fulfillment really, any order lines that are pending fulfillment."*

  The broad reading additionally sweeps in orders still sitting in **Pending Sales Approval** and **Deposit Review**. This report implements the broad reading (every row qualifies) and adds an **`is_pending_fulfillment`** column so the strict number is one filter away — nobody has to rebuild anything once she picks, and the gap between the two figures is measurable today.
- **⚠ Some of these dollars are also counted in Total Pipeline.** The new **`also_counts_in_pipeline`** column flags rows in Pending Sales Approval, which [`pipeline_plex_value_report`](pipeline_plex_value_report.md) counts separately. Under the broad reading the same money appears in both tiles. Surfaced rather than quietly netted out, because which tile should own it is a business call, not a SQL decision.
- **Scope narrowed.** This view now covers WIP only. The original version's "ready to ship" concept moved to the new [`shipping_pending_revenue_report`](shipping_pending_revenue_report.md) — Jennilyn described that as a distinct, Shipping-module-sourced metric, not the same thing as WIP.
- **Live-verified with real data**: 32 real WIP lines, 15 distinct orders, $875,475 total — a much richer, more real result than the Job_Status-based version ever produced. 2 of the 32 lines have no price match (customer/part combination not found in the price list) and are excluded from the total.
- **`Sales_v_PO_Status.Is_Quote`/`Cancelled_Status` use `1 = true`**, not the `-1 = true` convention used elsewhere in this pipeline — confirmed by checking the real status rows before writing this.

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
