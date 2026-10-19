# Audit - Part Info and Routing

> **Status:** 🔬 Built 2026-10-19, checked on PlexTest data (66,768 rows, 15,676 parts), not yet deployed · **Category:** Production · **Runs:** nightly, 11:00 PM Mountain (moves to the 1 PM / 6 PM / 11 PM / 4 AM probe schedule in phase 2 of the probe rollout)

## What this tells you

How every part is routed: its operation steps, which workcenters are approved to
run each step, and at what rate and crew size. It also shows approved suppliers
and their lead times, the part's status and group, its main building, and who
created the part and who last changed its routing. It is an audit view, used
to find parts whose routing is missing, inactive or inconsistent before that
causes a scheduling problem.

## Where it fits

It replaces the Plex stored procedure **Audit - Part_Info_and_Routing**, by
Shannon Hadley, in Plex's SQL Development Environment. It is the first of three
stored-procedure reports being rebuilt. The other two are the
`wContainerType` variant with approved containers, and the Vox Nutrition Item
List with Shelf Life Details.

## How it's built (high level)

The stored procedure joins 14 Plex tables in one query, which is what makes it
slow and heavy in Plex. This report pulls each of those 14 tables into BigQuery
on its own, and does the same join there, with the same tables, the same
filter (every part except `MATL`) and the same columns in the same order. The
largest table, approved workcenters at about 65,000 rows, is pulled in pages of
25,000 so no single Plex call is large.

## What a row is

There is **one row per part operation × approved workcenter × approved
supplier**, exactly as in Plex. Here is a part with one Bottling step approved
on eight workcenters:

| part_no | operation_code | workcenter_code | standard_production_rate | crew_size |
|---|---|---|---|---|
| 53001-01VOXNU-0 | Bottling | Bottling 1 | 2210.4 | 3 |
| 53001-01VOXNU-0 | Bottling | … Bottling 2-6 … | 2210.4 | 3-4 |
| 53001-01VOXNU-0 | Bottling | Bulk Room Bottling | 1458.6 | 3 |
| 53001-01VOXNU-0 | Bottling | SCHED - Bottling | 2210.4 | 3 |

To count operations rather than rows, count distinct part number + revision +
operation number.

## Things to know before trusting it

- **The fan-out is the procedure's own.** A step with three approved
  workcenters and two approved suppliers shows six rows. Totals summed across
  rows double-count.
- **Some parts are left out, as in Plex.** The procedure uses inner joins
  that drop:
  - parts with no part group;
  - parts with no routing at all;
  - parts whose creator's user record no longer exists.

  This report keeps the same joins, so its part count matches Plex's, not the
  part master's.
- **No PCN or building pickers.**
  - The procedure's company (PCN) picker isn't needed: this Plex connection
    sees one company, Vox Nutrition.
  - Its building picker is replaced by the `main_building` column; filter on
    it in Looker.
- **Routing update date is usually empty.** It is blank for most rows (66,058
  of 66,768 on PlexTest), because most routings have never been edited since
  they were created.
- **Freshness.** It runs nightly for now. Under the probe schedule, edits to
  run rates, crew sizes and lead times are detected through the probe's sums.
  Other edits on the two approval tables, which have no change date, are
  caught by the 4 AM full run at the latest.

## Columns

`plexus_customer_no`, `plexus_customer_code`, `part_no`, `revision`,
`old_part_no`, `part_status`, `part_active`, `created_date`, `update_date`
(routing), `routing_updated_by`, `part_type`, `part_group`, `main_building`,
`created_by_last_name`, `operation_no`, `interplant_transfer_allow`,
`net_weight`, `process_routing_location`, `workcenter_code`,
`standard_production_rate`, `ideal_rate`, `target_rate`, `crew_size`,
`supplier_code`, `lead_time`, `operation_code`, `inventory_type`, `op_active`,
`routing_operation_description`, `multiple`, `part_op_type`.

## Technical pointers

- Config: `reports/part_routing.yaml` (and `reports/test/part_routing.yaml`).
- SQL: `reports/sql/part_info_routing_view.sql`, which mirrors the procedure
  join by join.
- Jobs: `plex-etl-part-routing` / `-test`.
- Paging and the `sum:` probe columns: `docs/TECHNICAL_REFERENCE.md` and
  `docs/PROBE_BUILD_PLAN.md`.
