# Inventory Risk Analysis

> **Status:** ✅ Built and deployed, aging threshold decided 2026-08-21 — runs cleanly but not yet checked against a real slow-moving part · **Category:** Supply Chain · **Runs:** rides the Part On-Hand Inventory pipeline, 9:20 PM / 9:30 PM Mountain (prod/test)

## What this tells you

One row per part, showing how much is on hand right now, how many days it's been since any of that part's storage containers were last touched, and a yes/no flag for whether that gap has crossed a "this part may be going stale" threshold. It also carries two different ways to categorize each part (a generic type and a more detailed product-type classification) so the same list can be sliced either way. This is the Plex-native parity report for NetSuite's "Inventory Risk Analysis" — Custom Formula and Item Stock Type are the same underlying data, split only by which of the two category columns you group by.

## Where it fits

Built for NetSuite parity against **Inventory Risk Analysis - Custom Formula** and **Inventory Risk Analysis - Item Stock Type**, both tracked in [`reports-list/supply-chain.md`](../../reports-list/supply-chain.md) and decided 2026-08-21 — see [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) for the threshold decision. It's a sibling view on the same pipeline as [`part_on_hand_inventory_report`](part_on_hand_inventory_report.md) — it reuses that report's on-hand-quantity logic and builds the aging/risk layer on top of it.

## How it's built (high level)

Starts from the same "how much of this part is sitting in active, good-status containers" calculation as Part On-Hand Inventory, then adds how many days it's been since any of that part's containers were last updated. A part with 90 or more days since its last container activity — or with no activity on record at all — is flagged as at-risk. The day count itself is always shown too, so the 90-day line can be moved without re-running anything if it turns out to be the wrong number for this business. Each part also carries its generic type (e.g. Raw Materials) and, where populated, a much more specific product-type classification (Vitamin, Mineral, Botanical Extract, Stock vs. Custom Formula Blend/Capsules, Blank/Custom/Labeled Bottle, etc.) — either one can be used to group or filter the list, which is what lets one view stand in for both NetSuite report variants.

- **Pipeline:** `reports/part_on_hand_inventory.yaml` -> `inventory_risk_analysis_report`
- **SQL:** `reports/sql/inventory_risk_analysis_view.sql`

## Flags and open questions

- **The 90-day "at risk" cutoff is a best-criteria guess, not a Vox-confirmed policy.** Plex has no built-in concept of "risk," "slow-moving," or "aged" inventory anywhere in its schema (checked directly against the full stored-procedure catalog too). 90 days is a common general-purpose slow-moving-inventory convention, picked because nothing more specific to Vox exists yet — not because it was confirmed against how this business actually thinks about aging risk.
- **"Last container activity" is a proxy for "last transaction," and that proxy is unconfirmed.** Plex has no dedicated "last time this part moved" field, so this report uses the container record's own last-edited date instead. Whether an edit to the container row reliably reflects real inventory movement (versus, say, an unrelated data correction) hasn't been checked against real activity yet.
- **The detailed product-type classification isn't fully populated.** It was live for 64 of 80 parts on the test tenant when this was built — parts without it fall back to only the generic type, which is a weak category (it reads "Raw Materials" for nearly everything and won't usefully separate stock items from custom formulas).
- **Not yet validated against a real aging part.** The report queries and flags correctly, but nobody has checked its output against a part everyone agrees is genuinely slow-moving — that needs real, aged container activity to exist first.

## More detail

[`reports-list/supply-chain.md`](../../reports-list/supply-chain.md) and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) have the parity decision and threshold reasoning. [`part_on_hand_inventory_report.md`](part_on_hand_inventory_report.md) covers the shared on-hand-quantity logic this report builds on.
