# MFG Job Schedule - FG Testing Pending

> **Status:** ✅ Built and deployed 2026-08-26, verified live against `PlexTest` (25 of 25 jobs currently pending) · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

Which manufacturing jobs are still in flight — created, but not yet through finished-goods QC release. Same detail as [MFG Job Schedule - Success Metrics](mfg_job_schedule_success_metrics_report.md), filtered down to just the jobs still waiting.

## Where it fits

Covers the **FG Testing Pending** sub-tab tracked in [`spreadsheets/mfg_job_schedule_fg_testing_pending.md`](../../spreadsheets/mfg_job_schedule_fg_testing_pending.md).

## How it's built (high level)

A filtered view of [MFG Job Schedule - Success Metrics](mfg_job_schedule_success_metrics_report.md) — every job that doesn't have an FG Testing Released date yet.

- **Pipeline:** `reports/work_orders.yaml` → `mfg_job_schedule_fg_testing_pending_report`
- **SQL:** `reports/sql/mfg_job_schedule_fg_testing_pending_view.sql`

## Flags and open questions

Inherits every caveat from [MFG Job Schedule - Success Metrics](mfg_job_schedule_success_metrics_report.md) — this view adds no logic of its own beyond the filter. Not built here (unchanged from the original mapping): Blender batch size, MG Per Cap, and the "POs Received" column's exact semantics (2 unlabeled columns in the source CSV export).

## More detail

[`spreadsheets/mfg_job_schedule_fg_testing_pending.md`](../../spreadsheets/mfg_job_schedule_fg_testing_pending.md) has the full column-by-column mapping.
