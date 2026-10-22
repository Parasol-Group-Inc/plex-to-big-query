# Audit - Part Info and Routing (Container Types)

> **Status:** ✅ Live in prod (PlexProd) since 2026-10-19; 55,733 rows on 2026-10-20, from 48,398 approved containers (the PlexTest check on 10-19 saw 32,482 rows from 24,937) · **Category:** Production · **Runs:** with Audit - Part Info and Routing (same pipeline, `part_routing`), prod 1 PM / 6 PM / 11 PM probe + 4 AM full (`PlexOps.etl_schedule`), test nightly

## What this tells you

For every **shippable** part operation, which container types it is approved
to ship in, which one is the **primary**, how many container types it has in
all, and how many units go in each container. It is an audit view, used to find
shippable parts with no approved container, no primary container, or more than
one.

## Where it fits

It replaces the Plex stored procedure
**Audit - Part_Info_and_Routing_wContainerType** (Shannon Hadley, SQL
Development Environment). It is the second of three stored-procedure reports.
It shares a pipeline with
[Audit - Part Info and Routing](part_info_routing_report.md), because it reads
almost the same Plex tables.

## How it's built (high level)

It takes the same part, routing, operation and user tables as the first report,
plus the approved-container table and the container-type names, and joins them
in BigQuery exactly as the procedure joins them in Plex. Only **shippable**
operations are kept (the procedure's own rule, "added 2023.07.17 per team
discussion"), and `MATL` is excluded. Approved containers (24,937 rows today) are
set to be pulled in pages once they pass 25,000 rows. Until then they come in
one call.

## What a row is

There is **one row per shippable part operation × approved container type**.
An operation with no approved container still appears once, with the
container columns empty. Here is one part with four approved boxes:

| part_no | operation_code | container_type | primary | tot_number_container_types | is_primary | standard_pack_quantity |
|---|---|---|---|---|---|---|
| 53001-00VOXNU-0 | Bottling | 10x10x10 box | false | 4 | 0 | 50 |
| 53001-00VOXNU-0 | Bottling | 12x12x12 box | false | 4 | 0 | 90 |
| 53001-00VOXNU-0 | Bottling | 12x12x20 box | **true** | 4 | **1** | 150 |
| 53001-00VOXNU-0 | Bottling | 16x16x8 box | false | 4 | 0 | 100 |

## Things to know before trusting it

- **Two columns are added** beyond the procedure:
  - **`standard_pack_quantity`** (units per container);
  - **`containers_per_master`**.

  They were asked for ("quantities per container") and the procedure selects
  no quantity. Everything before them matches the procedure column for column.
- **True/false where Plex shows 1/0.** The view returns `primary`,
  `shippable`, `part_active` and `op_active` as true/false. The procedure
  shows `[Primary]` and `Shippable` as 1/0. The values are the same; only the
  display differs when comparing exports.
- **`tot_number_container_types`** counts every approved container type on
  the operation, so it is the same on each of that operation's rows.
- **`is_primary`** is 1 on the primary container's row and 0 otherwise.
  - It is 0 when the operation has no container.
  - It agrees with `primary` on every row checked (8,131 primaries on
    PlexTest, the same count Plex returns).
- **The same inner joins as Plex.** A part with no part group, no routing, or
  a missing creator user is left out, as in the procedure.
- **Freshness.** It refreshes when its pipeline runs. A change to a
  container's *primary* flag on its own isn't seen by the change probe, which
  can't add up Plex true/false columns. It is picked up by the daily 4 AM full
  run once the probe schedule is live. Changes to pack quantities, and added
  or removed containers, are seen at the next probe.

## Columns

`plexus_customer_no`, `plexus_customer_code`, `part_no`, `revision`,
`part_status`, `part_active`, `created_date`, `part_type`, `part_group`,
`created_by_last_name`, `operation_no`, `operation_code`, `shippable`,
`op_active`, `inventory_type`, `container_type`, `primary`,
`tot_number_container_types`, `is_primary`, then the two added columns,
`standard_pack_quantity` and `containers_per_master`.

## Technical pointers

- SQL: `reports/sql/part_info_routing_container_view.sql`. The procedure's
  `CROSS APPLY` / `OUTER APPLY` counts become two pre-aggregated CTEs.
- Config: the second `bq_view` in `reports/part_routing.yaml` (and
  `reports/test/part_routing.yaml`).
