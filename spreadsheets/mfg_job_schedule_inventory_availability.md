# MFG Job Schedule — "Inventory Availability" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** 🚧 Partially built 2026-08-26 — the 3 columns with a
  confirmed Plex source (Description, Quantity On Hand, On Order) are
  deployed as `mfg_job_schedule_inventory_availability_report`. Real data
  analyzed (~90 SKU rows). A completely different grain from every other
  tab (one row per SKU, not per job) — this is the reorder-point/inventory
  dashboard that the "Available Inventory"/"Days Left" columns on the
  Open/FG Testing Pending/Done tabs were always pointing back to. Confirms
  several exact formulas; checked live for the 2 remaining gaps and ruled
  out the obvious leads — see "Built 2026-08-26" below for what's still
  not built and why.

## What it is

One row per SKU (not per job), including both capsule finished goods
(`13001`, `13056`, etc.) and bulk/blend powders (`13157 - Blend`,
`13188 - Blend`, etc. — confirms the `" - Blend"` SKU suffix pattern
noticed in `mfg_job_schedule_done_ytd.md`/`done_2025.md` is specifically
for bulk/powder products, not a random formatting artifact). Columns:
Description, Reorder Point, Current QTY Available, At Reorder Point?,
Days to Reorder Point, Avg Daily, On Order, In MFG/Bottling/Ordered?,
(Reorder Point again), ROUT, % Left, Days on Hand, Quantity On Hand,
Reorder Point Days on Hand.

## Confirmed exact formulas

Spot-checked against real values, including a literal `#DIV/0!` error in
the raw data that pins one formula exactly:

- **% Left = Current QTY Available ÷ ROUT.** Confirmed by the
  `Garcinia Cambogia Pure` row: `ROUT = 0` produces the literal text
  `#DIV/0!` in the `% Left` column — the sheet's own division-by-zero
  error, not a data quality issue to "fix."
- **Days on Hand = Current QTY Available ÷ Avg Daily.** Exact match:
  `B-12 Bulk Liquid` → `332 ÷ 2 = 166`, matches the shown value exactly.
- **Reorder Point Days on Hand = Reorder Point ÷ Avg Daily.** Exact
  match: `Vitamin C Serum` → `563 ÷ 7 = 80.42857143`, matches to the
  decimal.
- **Days to Reorder Point ≈ (Current QTY Available − Reorder Point) ÷
  Avg Daily**, sign convention confirmed (negative = already at/past the
  reorder point, matching `At Reorder Point? = Yes`) — the exact
  coefficient doesn't reproduce to the decimal because `Avg Daily` is
  displayed rounded to a whole number; the underlying precision is
  higher than what's visible in the export.

## The long-standing "Days Left" gap chain — resolved to one final input

Every prior tab (`mfg_job_schedule.md`'s Open tab, `fg_testing_pending.md`,
`done_ytd.md`, `done_2025.md`) flagged "Days Left"/"Days on hand when
completed" as a derived days-of-supply metric with an unconfirmed
usage-rate component. **This tab is that metric's actual source** — it's
literally `Current QTY Available ÷ Avg Daily`, computed here and almost
certainly just referenced/copied into the job-level tabs. This closes the
formula question. What's left is exactly one missing input:

**`Avg Daily` (average daily usage rate) — checked live, no Plex source
found.** Checked `Part_v_Part_Planning_Parameters` (real view, has rows,
but its columns are MRP/scheduling flags — `Finished_Part_Buffer`,
`Level_Scheduled`, `Process_Days`, etc. — not a usage rate). Speculative
view names `Material_v_Planning_Parameter`, `Material_v_Safety_Stock`,
`Material_v_Reorder_Point`, `Part_v_Reorder_Point` all **don't exist**
(confirmed via live query errors, not just absent from a name list). No
confirmed Plex source for either `Avg Daily` or `Reorder Point` — most
likely computed in the sheet from historical shipment/production data,
or sourced from NetSuite/a demand-planning tool outside this pipeline's
scope. Genuinely open, not guessed at.

## New lead, checked and mostly ruled out: Current QTY Available vs. Quantity On Hand

These are two *different* numbers per row (e.g. `B-12 Bulk Liquid`:
`Current QTY Available = 332`, `Quantity On Hand = 370`) — the natural
hypothesis is `Current QTY Available = Quantity On Hand (raw
`Part_v_Container`) − allocated/committed quantity`. Checked
`Part_v_Inventory_Allocation` live: it's a real view with rows, but only
4 columns (`PCN`, `Allocation_Key`, `Container_Serial_No`, `PO_Line_Key`)
— **no `Quantity` or `Part_Key` column**, so it can't be summed per part
directly. Would need a join through `Part_v_Container` by a serial-number
column to backtrack to `Part_Key`, and `Part_v_Container` doesn't have an
obviously-matching column either (checked, not found). **Quantity On
Hand** itself is buildable now (`Part_v_Container`, same source as
`part_on_hand_inventory_report`) — **Current QTY Available's netting
logic is not**, flagged as a gap rather than assumed solved.

## Update 2026-08-23 — two new candidates found, both empty live (inconclusive, not ruled out)

Re-swept the full 14,350-row schema catalog for "allocat"/"committed"/
"reserved"/"available"/"reorder" beyond the views already checked above.
Two real, previously-unchecked tables turned up — neither could be
confirmed against real data because both returned **0 rows live** against
`vox.test.odbc.plex.com`:

- **`Part_v_Kitting_Allocation_w`** — `Kitting_Allocation_w_Key`,
  `Master_Unit_Key`, `Component_Part_Key`, `Component_Part_Operation_Key`,
  `Quantity`, `Production_Order`, `Serial_No`. Unlike
  `Part_v_Inventory_Allocation` (checked above, no `Quantity`/`Part_Key`),
  this one has both a real `Quantity` and a `Component_Part_Key` — exactly
  the shape needed to net against `Quantity On Hand` per part. The `_w`
  suffix (seen elsewhere in Plex as a "working"/scratch-table convention)
  suggests this may only be populated transiently during an active
  MRP/kitting run rather than held as persistent history, which would
  explain the 0 rows without ruling it out as the real source.
- **`Part_v_RP`** — a 42-column MRP/requirements-planning record
  (`Component_Key`, `Material_Key`, `Component_Balance`,
  `Material_Balance`, `Order_Date`, `Generated_Date`,
  `Estimated_Available_Date`, `Can_Trigger_RP`, ...). "RP" here reads as
  **Requirements Planning**, not literally "Reorder Point" — but
  `Component_Balance`/`Material_Balance` are plausible candidates for
  either `Current QTY Available` or the netting logic behind it. Also 0
  rows live, same transient-table caveat as above.

**Not resolvable by more schema searching** — both tables exist and have
the right shape, but confirming what they actually mean requires either
real data or someone who's used Plex's MRP/Kitting screens directly.

## Update 2026-08-23 (cont.) — all 5 allocation-family candidates confirmed empty, live

Live row-count check (SQL Development Environment, Emilio) against all
five allocation/kitting candidate tables identified across both research
passes:

| Table | Row_Count |
|---|---|
| `Part_v_Kitting_Allocation_w` | 0 |
| `Part_v_Kitting_Production_w` | 0 |
| `Part_v_Kitting_Production_Log` | 0 |
| `Part_v_RP` | 0 |
| `Part_v_Inventory_Allocation` | 0 |

**Discrepancy worth noting:** the "New lead, checked and mostly ruled out"
section above says `Part_v_Inventory_Allocation` "is a real view with
rows" — that was true at the time of an earlier check, but it's 0 rows as
of this 2026-08-23 count. Either the tenant's data was reset/cleared
between checks, or the earlier check ran against a different environment
(prod vs. test) — not chased down, just flagged so a future re-check
isn't confused by the contradiction.

**Verdict: this is not a missing-join problem like Q8 turned out to be —
kitting/allocation as a Plex feature appears simply unused on this
tenant.** All five tables have plausible shapes; none have a single row.
No further schema searching or query refinement will produce an answer
here. This needs one of:
1. Real data to accumulate on this tenant (same "nothing has run yet"
   situation as everything else on `vox.test.odbc.plex.com`), or
2. Direct confirmation from someone who's used Plex's Kitting/MRP screens
   — does Vox use this feature at all, on any part, ever? If the answer
   is "no, we don't use Kitting in Plex," these five tables are a dead
   end regardless of future data, and `Current QTY Available`'s netting
   logic (and `Avg Daily`/`Reorder Point`, per Q13) most likely lives
   entirely outside Plex — worth treating both as one combined
   data-architect question rather than two separate open items.

## Buildable from Plex (same confirmed sources)

| Column | Plex source |
|---|---|
| Description | `Part_v_Part.Name` |
| Quantity On Hand | `Part_v_Container` (`part_on_hand_inventory_report`) |
| On Order | `purchasing_open_orders_report` (already live) |

## Manual-only / process context, not data

A short legend at the bottom of the sheet (`Over 100 days`, `Looking at
capsules usage and inventory`, `Contacting vendors/placing POs`,
`Product in testing`, `Adding to MFG`, `It should be in MFG — if not,
talk to Purchasing`) is a human escalation workflow tied to how far a SKU
is from its reorder point — a business process guide, not a data column.

## Verdict

Meaningfully de-risked a gap that's been open since the very first MFG
Job Schedule pass: the "days of supply" formula is now known exactly, and
both remaining unknowns (`Avg Daily`'s source, and `Current QTY
Available`'s allocation/committed netting logic) have been actively
checked against every plausible Plex candidate found across two research
passes — 7 tables total, all either don't exist, don't have the right
columns, or (the 5 kitting/allocation candidates) exist with the right
shape but are completely empty live. **Closed out on the Plex-research
side as of 2026-08-23** — not resolvable by more schema searching or
querying; genuinely needs a person.

## What's needed next

Ask Emilio/the data architect directly, as one combined question (both
gaps point the same direction): where do `Avg Daily`, `Reorder Point`,
and `Current QTY Available`'s netting logic actually come from — and does
Vox use Plex's Kitting/MRP screens at all? If not, all three most likely
live entirely outside Plex (NetSuite demand planning, or a sheet-side
calculation), and no amount of waiting for more test-tenant data will
change that.

## Built 2026-08-26 — the 3 unblocked columns, not the whole tab

Rather than wait on the open questions above, built the 3 columns that
were always independently buildable: Description, Quantity On Hand, On
Order. Added as a 3rd `bq_view` (`mfg_job_schedule_inventory_availability_report`)
on the existing `part_on_hand_inventory.yaml` pipeline — no new
extraction, just a query joining the already-deployed
`part_on_hand_inventory_report` and `purchasing_open_orders_report`
views by part number. Deployed to both `PlexProd` and `PlexTest` via
`terraform apply`, verified live (view exists and is queryable, 0 rows —
same benign reason as everything else on this tenant). See
`reports/sql/mfg_job_schedule_inventory_availability_view.sql` and
`docs/reports/mfg_job_schedule_inventory_availability_report.md`.

Reorder Point, Avg Daily, Current QTY Available, % Left, Days on Hand,
Days to Reorder Point, and Reorder Point Days on Hand remain **not
built** — still genuinely blocked on the two open questions above, not
something this pass changed.
