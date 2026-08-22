# Bottling Job Schedule

- **Link:** https://docs.google.com/spreadsheets/d/1m6ZmBMBCQHTsc4S7W-FicIaE63AOfxvobbnEDRwmqAk/edit
- **Type:** Google Sheet
- **Category:** Scheduling bottling jobs
- **Departments:** Production, Planning, Sales
- **Status:** ✅ Built 2026-08-22 — `bottling_job_schedule_report` (9th `bq_view` on `reports/work_orders.yaml`), deployed to prod+test via `terraform apply`, verified with a clean test run
- **Related:** [MFG Job Schedule](mfg_job_schedule.md) — the bottling-specific sibling of the same production-tracking pattern; also appears as "Quality | Bottling Production Search" in `reports-list/quality.md`

## What it is

5 tabs analyzed: Open Liquids, Open Powders, Open Gummies, Open
Capsules_Softgels, and a populated "August 2026" log. Same production-board
pattern as MFG Job Schedule, specialized for the bottling/packaging step:
one row per bottling job, tracking SO/WO numbers, product spec, lot,
start/finish dates, and (in Capsules_Softgels and the August tab) actual
run metrics.

Common columns across all 5 tabs: Date Entered, Picked (blank/INITIAL/X
status), Rep, SO#, WO#, Company, Bottle/Pill Count, Product, Fill
Weight/Pill Count, Bottle Size and Color, Lid Size and Color, LOT, OZ, Sign
Off, Input Name, Start Date, Finished date, PALLET. Capsules_Softgels and
August 2026 add: # Completed, Notes, Status, Run Time (clock ranges like
`8:56-10:25`), Changeover, Total.

## Findings — column-by-column

**Buildable from Plex (same confirmed sources as MFG Job Schedule):**

| Column | Plex source |
|---|---|
| Bottle Count / Pill Count | `Part_v_Job.Quantity` |
| Start Date / Finished date | `Part_v_Job_Op.Start_Date`/`Complete_Date` |
| LOT | `Part_v_Job.Lot_Key` → `Part_v_Lot` |
| Input Name (if this is the operator, not the data-entry person — ambiguous from the sheet alone) | `Job_Op.Started_By`/`Completed_By` → `Personnel_v_Employee.Common_Name` |

**New leads specific to this sheet (unconfirmed):**

- **Run Time / Changeover / Total / # Completed** (Capsules_Softgels, August
  2026 tabs) — these look like they could be *reconstructed* rather than
  pulled as-is: `Run Time` as `Job_Op.Complete_Date - Start_Date`,
  `# Completed` as `Job_Op.Quantity`. This is the most promising new lead
  in this sheet — worth testing against real data once Job_Op populates.
- **Rep** (sales rep initials: CB, CD, SD, etc.) — if tied to a real SO
  (`SO#` non-blank), this is plausibly `Sales_v_Order_Salesperson` →
  `Plexus_Control_v_Plexus_User`, the exact join already built for
  `sales_orders_report`. Reuse candidate, not confirmed.
- **Bottle Size and Color / Lid Size and Color** — same gap as MFG Job
  Schedule's "Cap Specs": plausibly `Part_v_BOM` component parts (bottle
  and lid as BOM components of the finished good), unconfirmed.
- **Fill Weight** — same gap as MFG Job Schedule's "MG Per Cap": plausible
  `Part_v_BOM`/`Part_v_Part_Attribute` source, needs unit-conversion
  confirmation, not built speculatively.

**Genuinely NetSuite, not Plex:** SO#/WO# — same NetSuite WO-number
situation as MFG Job Schedule's "Job #". No FK to Plex `Job_No`; would need
a SKU+date correlation, not a key join.

**Manual-only — never in any ERP:** Date Entered, Picked (status
checkbox), Sign Off, PALLET (no Plex location analog identified), Notes,
Status (RUSH/On Hold/etc. — a business process gate, not an ERP field).

## What's needed next

Live schema confirmation of `Job_Op` start/complete timestamps and
`Quantity` against real production data (both were empty on the test
tenant during the MFG Job Schedule build) to validate the Run Time /
# Completed reconstruction lead, before building any report.

**Update 2026-08-11:** the bottling-relevant workcenters are now confirmed
live — `Bottling Line 1` through `Bottling Line 6` (see
`reports-list/production.md`) — so once real `Job_Op` activity exists, the
Run Time/# Completed reconstruction can be scoped to those specific
workcenters rather than all of Job_Op.

## Built 2026-08-22

Built as `bottling_job_schedule_report`, a 9th `bq_view` on the existing
`reports/work_orders.yaml`/`reports/test/work_orders.yaml` pipeline — no new
extractions or Cloud Run job needed, same extractions `mfg_job_schedule_report`
already uses. Grain: one row per job operation, filtered to
`Workcenter_Group = 'Bottling'` (same confirmed roster as
`packaging_daily_report`: Bottling Line 1-6, Bulk Room, Powder Line, Liquid
Line).

**Built:** `job_no`, `part_no`/`part_name`, `workcenter`, `planned_qty`
(Bottle/Pill Count), `lot_no`, `started_by_name`/`completed_by_name` (Input
Name candidates, both exposed — ambiguous which one the sheet means),
`job_status` + completed/cancelled flags.

**Built the Run Time / # Completed reconstruction lead too** (flagged in
the doc above as "most promising, worth testing"), exploratory and NOT
confirmed against real data: `op_qty` (Job_Op.Quantity, candidate "#
Completed"), `op_start_ts`/`op_completion_ts` (full timestamp — every other
view in this repo truncates to DATE since none of them needed time-of-day),
`run_time_minutes` (the difference, candidate "Run Time"). `op_start_date`/
`op_completion_date` (plain DATE) are also exposed to match the sheet's
Start Date/Finished date columns directly.

**Not built** (see the gaps table above — unconfirmed leads, not guessed):
Rep, Bottle/Lid Size and Color, Fill Weight. **Not attempted:** splitting
into the sheet's 4 sub-tabs (Liquids/Powders/Gummies/Capsules_Softgels) —
no confirmed Plex-side split (Part_Group/Product_Type) exists per tab, so
this view returns the whole Bottling roster undivided.

**Test deploy:** `terraform apply` (7 GCS objects added — including
backfilling terraform tracking for 6 already-live SQL files from the
2026-08-21 batch that had the same gap — 2 changed, 0 destroyed).
`plex-etl-work-orders-test` ran clean against the new config. Real-data
validation of the Run Time/# Completed lead still pending — same "no real
job has run yet on this tenant" situation as the 4 Daily Reports.
