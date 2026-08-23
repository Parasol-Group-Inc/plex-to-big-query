# Labeling Daily Report

> **Status:** ✅ Deployed to production 2026-08-22, currently returning 0 rows (benign — no real jobs have run through Labeling yet) · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per Labeling line per production day — how much was actually produced, how much was scrapped, which parts ran, and who worked it. This is the Plex-native replacement for the "Actual" side of the manually maintained "Labeling Daily Report" Google Sheet, which tracks Front/End counters, a start-up time, three shift-checkpoint times, and planned-vs-actual output per line.

## Where it fits

Fulfills the **Labeling Daily Report** Google Sheet tracked in [`spreadsheets/labeling_daily_report.md`](../../spreadsheets/labeling_daily_report.md) — one of four "Daily Reports" (alongside Encap, Blending, and Packaging) built the same way from the same underlying production log. Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Pulls from the same production-log data already extracted for Work Orders, then rolls it up by day and by line: total quantity produced, quantity scrapped, which parts ran, how many jobs and employees were involved, and which shifts worked. Unlike its Packaging sibling, Labeling maps cleanly here — Plex has a real workcenter group called "Labeling" (Labeling Line 1 through 6, plus a line called "First 48"), and that lines up directly with the sheet's own "Line 1-6" numbering, so no substitute grouping was needed.

- **Pipeline:** `reports/work_orders.yaml` -> `labeling_daily_report`
- **SQL:** `reports/sql/labeling_daily_report_view.sql`

## Flags and open questions

- **Fixed 2026-08-23 — scrap was silently always zero.** The scrap check compared Plex's `Rejected` flag to `1`, but Plex represents boolean true as `-1`, not `1` (an already-confirmed convention elsewhere in this pipeline) — so no row could ever match, and rejected quantity vanished from both the actual and scrap totals instead of being counted as scrap. Fixed by comparing to `-1`. Caught by code review before any real production data existed to be affected by it.
- **Currently 0 rows — expected, not broken.** No real production has been logged against this tenant's Labeling lines yet, so there's nothing to roll up. This should start populating once real jobs move past the scheduling stage.
- **Not built: the sheet's three shift-checkpoint times (6:30 AM / 8:45 AM / 12:15 PM) and "# Of Orders Complete."** No confirmed Plex data answers either one. The shift value this report does show is a shift *label* (e.g. "1st," "2nd"), not a checkpoint time, so it doesn't fill that gap. "# Of Orders Complete" is conceptually close to the open-job count already built for `labeling_open_work_orders_report`, but that counts *open* jobs — a genuinely different question from *completed* jobs, so it isn't approximated here.
- **Not built: Planned output and Start-Up Time.** These looked like manual scheduling inputs with no matching data in Plex, the same category of gap found on MFG Job Schedule's manual-only columns.
- **Employee count reflects who logged production, not who was scheduled or absent** — it isn't a substitute for an attendance/roster view.
- **Employee attribution is an inferred link, not a confirmed one.** The employee tied to each production record is matched using the same assumption already relied on elsewhere in this pipeline (for MFG Job Schedule and the other Daily Reports).
- **Rebuilt once already, same day as the initial build.** A live "Job Production" screenshot from Plex confirmed the report should read from `Part_v_Production` (which has Employee/Shift/Rejected columns) rather than the table it was first built on, which didn't. That correction is why this report can also show employee names, shift labels, and a scrap quantity.

## More detail

[`spreadsheets/labeling_daily_report.md`](../../spreadsheets/labeling_daily_report.md) has the full column-by-column mapping and research history.
