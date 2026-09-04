# Vox Scorecard | Pipeline Value (Plex half only)

> **Status:** ✅ Deployed and verified 2026-09-04 — $900,975 across 15 orders, all Quote status · **Category:** Sales · **Runs:** rides the Sales Orders pipeline

## What this tells you

The dollar value of sales orders sitting in a **Quote** status or in **Pending Sales Approval** — the Plex-side contribution to the scorecard's Total Pipeline figure, broken out by stage, customer, rep and part.

## Where it fits

**This is deliberately only half the tile.** Per Jennilyn Tockstein: *"It's a blend of the Monday data and a little bit of the Plex data... it'll be a sum of the Monday data plus the quotes and pending sales approval sales orders."*

Total Pipeline = Monday.com opportunities/forecast **+** this report. **Do not present this figure as "Total Pipeline" on its own.**

## How it's built (high level)

Reads `Sales_v_PO` filtered to orders whose status is flagged as a quote (`Sales_v_PO_Status.Is_Quote`) or is Pending Sales Approval (key 2585), excluding anything cancelled, and prices each line off the customer price list.

**Worth knowing why this is not built on Plex's Quote module.** Jennilyn said *"the sales **orders** that have the status quote"* — that's an order status, not `Sales_v_Quote`, which is a separate object with its own New/Estimating/Quoted/Won/Lost workflow. Reading her words literally keeps this inside already-extracted tables and adds zero ETL. Going the other way would have meant extracting Plex's automotive-flavoured quote-pricing tables (with their Escalation Year / IRR / NPV / EBITDA / Die Cavity Count fields) that a supplement manufacturer almost certainly doesn't populate.

- **Pipeline:** `reports/sales_orders.yaml` → `pipeline_plex_value_report`
- **SQL:** `reports/sql/pipeline_plex_value_view.sql`

## Flags and open questions

- **⚠ The Monday.com question is unresolved and it's a real one.** Jennilyn's plan keeps Monday permanently for the Opportunities and Forecast stages. This project's working assumption has been that Plex replaces Monday outright. The Monday sync that feeds `voxdatalake.VoxScorecardsLive` is not managed by this repo's Terraform at all. Needs a decision, not a query.
- **⚠ Overlaps with WIP.** Pending Sales Approval orders counted here are *also* counted by [`sales_order_value_by_status_report`](sales_order_value_by_status_report.md) under its broad WIP reading — see that report's `also_counts_in_pipeline` flag. The same dollars can land in both tiles. Surfaced in both places rather than quietly netted out, because which tile should own them is a business call.
- **Prices exclude tax and freight.**

## More detail

[`meetings-reference/Sep-1/`](../../meetings-reference/Sep-1/) has the full requirements conversation.
