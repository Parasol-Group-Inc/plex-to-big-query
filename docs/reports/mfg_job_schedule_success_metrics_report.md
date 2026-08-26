# MFG Job Schedule - Success Metrics (Done/YTD List, unified)

> **Status:** ✅ Built and deployed 2026-08-26, verified live against `PlexTest` (25 real jobs) · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per manufacturing job: its Yield (actual output vs. planned), whether it had a Deviation/nonconformance, how long it took from creation to FG testing release, and a computed Success Rating combining all three against the team's own goals (95%/92% Yield for stock/custom, no Deviation, ≤84 days). This is the calculated-metrics engine behind four tabs of the manually maintained "MFG Job Schedule" spreadsheet at once.

## Where it fits

Covers 4 sub-tabs tracked in [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md)'s tab tracker — **Done YTD**, **Done 2025**, **YTD List**, and **2025 List** — collapsed into one continuous report instead of 4 separate ones. Those tabs split the same underlying calculation across a full-detail view vs. a slim extract, and a current-year view vs. a prior-year archive; a live BigQuery view doesn't need either split. Also feeds [`mfg_job_schedule_fg_testing_pending_report`](mfg_job_schedule_fg_testing_pending_report.md) and [`mfg_job_schedule_gate_stats_report`](mfg_job_schedule_gate_stats_report.md) below.

## How it's built (high level)

Starts from every job in Plex, then for each one: sums up actual production quantity logged against it, finds the most recent approved QC checksheet date as a stand-in for "FG Testing Released," and checks whether any quality Deviation record is linked to it. From those three inputs it computes Yield %, days from creation to release, and a 3-gate Success Rating (Yield, Deviation, turnaround time), plus a binary "is this job Successful" flag (all 3 gates must pass).

- **Pipeline:** `reports/work_orders.yaml` → `mfg_job_schedule_success_metrics_report`
- **SQL:** `reports/sql/mfg_job_schedule_success_metrics_view.sql`

## Flags and open questions

- **Grain is per-job, not per-blend-batch.** The source spreadsheet shows some jobs with multiple rows (different Yields for the same date/product) — evidence a job can have several blend sub-batches, each yielding independently. The real Plex table for that finer grain (`Part_v_Job_Op_Batch`) exists but has 0 rows everywhere checked so far — this report will under-count once that data exists on a multi-blend job.
- **"FG Testing Released" is a proxy, not a confirmed match.** It's the latest APPROVED QC checksheet date across a job's operations — Plex's checksheet status only has 4 generic flags (Approved/Rejected/Awaiting Approval/Expired), with no confirmed way yet to distinguish a "Raw Materials Released" checksheet from an "FG Testing Released" one specifically.
- **"Caps Made" (Yield's actual-output number) is a deliberate generalization** — it sums logged production across ALL of a job's operations, not just Encapsulation, so Blending-only jobs still get a Yield instead of a blank. Whether the Yield formula genuinely holds for Blending-only jobs is still an open question with no real data yet to test it against.
- **Deviation flag reuses the same source as [Quality Deviation](quality_deviation_report.md)** and inherits its own caveat: it's unconfirmed whether every quality Problem/nonconformance record actually gets a linked Deviation, or only ones needing a documented workaround.
- **Stock vs. Custom uses "job has a linked customer release" as the signal** (a proxy also used on [MFG Job Schedule](mfg_job_schedule_report.md)) — not confirmed against real data yet.
- **Rework rows are never dropped.** An `is_rework` flag (Job Type = Rework, or a negative day count) is exposed so a consumer can filter them out if desired, rather than this report silently excluding them — Emilio's call 2026-08-26.
- **"Successful" = 100% (all 3 gates), not partial credit** — Emilio's call 2026-08-26, feeding directly into the Gate Stats rollup.

## More detail

[`spreadsheets/mfg_job_schedule_ytd_list.md`](../../spreadsheets/mfg_job_schedule_ytd_list.md) (and its sibling docs for Done YTD/Done 2025/2025 List) has the full formula derivation and research history, including the ~330 real spreadsheet rows the formulas were reverse-engineered against.
