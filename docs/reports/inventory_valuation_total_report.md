# Vox Scorecard | Inventory Value Total

> **Status:** ✅ Deployed 2026-09-01 · 🔧 **Rewritten 2026-09-24, deployed 2026-09-25**: the earlier version summed per-unit costs (see Flags) · **Category:** Inventory · **Runs:** rides the Inventory Snapshot pipeline

## What this tells you

One number per snapshot date: the total dollar value of the stock on hand (quantity × per-unit standard cost), plus how many distinct parts that total covers. **Only the latest snapshot date has a value.** Earlier dates show a blank value (see Flags).

## Where it fits

Candidate for the "Inventory Val" phase of the Vox Nutrition Scorecard's Flow revenue funnel (`Vox_Looker_DB - Flow`), currently one of the funnel's 3 unbuilt phases. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

A sum of `inventory_valuation_summary_report`'s `inventory_value` (on-hand × unit cost), grouped by snapshot date, using the last snapshot of each day. New columns (2026-09-24): `is_current_snapshot`, `valued_part_count` (costed parts actually on hand) and `uncosted_on_hand_part_count` (parts on hand that no cost covers, so their value is missing from the total, not zero).

- **Pipeline:** `reports/inventory_snapshot.yaml` → `inventory_valuation_total_report`
- **SQL:** `reports/sql/inventory_valuation_total_view.sql`

## Flags and open questions

- **Fixed 2026-09-24, deployed 2026-09-25.** The earlier view added up per-unit standard costs with no quantity, so "total inventory value" read **about $77 for the whole building** in the scorecard sandbox. It also added every routing operation's cost for a part. It now sums on-hand quantity × the part's per-unit cost. Sandbox, 1 Sep 2026: **$76.65 → $2,760,901.76**, which matches an independent on-hand × latest-cost sum to the cent. PlexTest: 5 parts have a real cost and none of them is on hand, so the value is $0.00 with `uncosted_on_hand_part_count` = 57. See [`docs/SCORECARD_SANDBOX_FINDINGS.md`](../SCORECARD_SANDBOX_FINDINGS.md) finding 4.
- **No month-end trend yet, and this is a data gap, not a query choice.** Plex's `Part_v_Snapshot` records cost only; it has no quantity column. The only on-hand quantity extracted is today's (`Part_v_Container`). Earlier snapshot dates therefore show a blank value. Giving them a number would mean pricing today's stock at old costs, which would chart the cost roll, not the inventory. A trend needs month-end on-hand captured somewhere, either by storing a daily copy of on-hand in BigQuery or by extracting a Plex inventory-history source. Not decided.
- **The earlier "0 rows, genuinely empty" note was only partly right.** PlexTest now has one real snapshot (1 Sep 2026). The deployed view still returned 0 rows because Plex's snapshot-to-cost link table is empty, and the view joined through it. The rewrite falls back to the cost history in force on the snapshot date.
- **One total only — not split by WIP/Finished Goods/Raw Material.** `Cost_Sub_Type_Key` (the column that would distinguish those categories) has no confirmed label lookup anywhere in this repo. Fine if the Flow funnel's "Inventory Val" phase just needs one grand total; not fine if it needs to be broken into categories — that's a separate, currently-blocked question.
- **⚠ `VoxScorecardsLive.Product_Cost` looks like the answer to any missing-cost problem here. It is not.** Tested 2026-09-09 as a valuation source: 199 rows of `part` + `cost_ea`, which join to **5 of 6,221** Plex parts and **none** of the `33` parts. Its `part` values are bare stems (`12335`) against Plex's full part numbers (`12335-01VOXNU-1`), it contains duplicate rows, and even stem-matching fails almost everywhere. **Before anyone builds on it, ask what its `part` column keys to** — it may be a NetSuite-era list for a different catalogue. Recorded here because it is the obvious thing to reach for the moment a report needs a cost and Plex's own cost tables are empty.

## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md) and [`docs/reports/inventory_valuation_summary_report.md`](inventory_valuation_summary_report.md).
