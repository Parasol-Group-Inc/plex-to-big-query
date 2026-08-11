# Reports List — NS Reference

Source file: `Reports List - NS Reference.csv`. Just one column: a flat
list of ~78 NetSuite report names, no Source/Function/Users/Link columns.
Reads as a raw inventory of NetSuite report names, not a set of individual
mapping targets — every single one of these is ❌ **out of scope**
individually (they're NetSuite-native), but the list is useful as a
cross-reference.

## Confirmed matches to already-built work

These exact names appear in this list AND already have a live
`docs/NETSUITE_REPORT_BUILD_PLAN.md` parity report:

| NS Reference name | Built as |
|---|---|
| Current Inventory Snapshot | `inventory_snapshot_report` (#15) |
| Inventory Activity Detail Usage Per Month (listed twice) | `inventory_activity_report` (#29) |
| Vox \| Inventory Valuation Summary | `inventory_valuation_summary_report` (#73) |
| Vox \| Inventory Valuation Summary Transaction | Same pipeline as #73/#74 |
| Vox \| Open Purchase Orders | `purchasing_open_orders_report` (#75) |
| Vox \| Open Sales Orders | `sales_orders_open_report` (#76) |
| VOX \| Products to be discontinued (listed twice, one with a trailing period) | `part_obsolescence_report` (#77) |

## Not NetSuite despite the name

`Quality | Bottling Production Search` and `Quality | Encapsulation
Production Search` both appear in this list, but per `reports-list/quality.md`
their actual links are Google Sheets (Bottling Job Schedule and MFG Job
Schedule respectively) — already built. The "NS Reference" framing is
misleading for these two specifically.

## The rest

This list overlaps heavily with `mapping/netsuite-report-mapping.md`, the
seed list this project's original NetSuite parity build plan
(`docs/NETSUITE_REPORT_BUILD_PLAN.md`) was scoped from — see that doc for
the fuller confidence-tiered analysis (High/Medium/Low match to a Plex
view) of this same universe of NetSuite report names, rather than
re-deriving it here.
