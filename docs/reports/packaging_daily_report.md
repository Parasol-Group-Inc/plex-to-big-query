# Packaging Daily Report

> **Status:** ✅ Fixed 2026-09-01 (join bug, see Flags below) and reverified against `PlexTest` — first real row ever returned: Bottling Line 1, 2026-08-31, 3,000 actual qty, 0 scrap · **Category:** Production · **Runs:** rides the Work Orders pipeline, prod 1 PM / 6 PM / 11 PM probe + 4 AM full (`PlexOps.etl_schedule`), test nightly

## What this tells you

One row per packaging line per day — how much was actually produced, how much was scrapped, and who worked it. This is the Plex-native replacement for the "Actual" side of the manually maintained "Packaging Daily Report" Google Sheet, which tracked Front/Mid/End counts, planned vs. actual output, and a start-up time per line.

## Where it fits

Fulfills the **Packaging Daily Report** Google Sheet tracked in [`spreadsheets/packaging_daily_report.md`](../../spreadsheets/packaging_daily_report.md) — one of four "Daily Reports" (alongside Encap, Blending, and Labeling) built the same way from the same underlying production log. Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Pulls from the same production-log data already extracted for Work Orders, then rolls it up by day and by line: total quantity produced, quantity scrapped, which parts ran, how many jobs and employees were involved, and which shifts worked. "Packaging" turned out not to be a real grouping inside Plex at all — production lines there are organized under a workcenter category called "Bottling," and after comparing the sheet's own line names (Line 1-5, Bulk, Gummy Line/Line 6, Powder Line, Liquid Line) against that roster, this report was built on the Bottling group as the closest match.

- **Pipeline:** `reports/work_orders.yaml` -> `packaging_daily_report`
- **SQL:** `reports/sql/packaging_daily_report_view.sql`

## Flags and open questions

- **Bottling 9-parts are not counted (Jennilyn, 2026-10-22).** When Bottling completes a job for a part starting with **9** (the finished-good version), the same output was already counted on the job for its **5** part, so counting both is double credit. Bottling production records for 9-parts are left out, good and scrap alike. **Bottling only:** Labeling's output is all 9-parts and still counts. **Bulk cases are exempt and still count** (Jennilyn, same day): `9xxxx-BK…` parts, all 95 "BULK CASE" parts in Plex, have no 5-part job, so nothing double-counts. October so far the rule removes **14,055** units: `93323-10REDRO-0` (Slim Complex FG, one record on 10-22), already counted on its 5 part `53323-10REDRO-0` (10-19 to 10-20). October Bottling: 126,756.
- **From 1 Nov 2026, Bottling 9-parts count (Jennilyn, 2026-10-30).** She removed the 5-part BOM from those 9-parts so the output is made once: "we want to track bottling/packaging totals for parts that start with 9 starting now." The drop above now applies only to dates before 1 Nov, so October and earlier keep their numbers. New columns `bottling_9part_qty` (good 9-part output, bulk cases excluded) and `bottling_9part_with_5_bom_qty` (the part of it whose 9-part still has a 5-part BOM line: possible double credit). If the second is not 0 from November, a BOM change is unfinished; about 14 in-use 9-parts were left to do, and finishing them is Jennilyn's.
- **⚠ Reversed 2026-09-24: scrap is `Rejected != 0`.** The 2026-08-23 change below moved the test from `1` to `-1`; the only real rejected record in PlexTest (Bottling Line 1, 500 units, 2026-09-24) has `Rejected = 1`, so scrap read **0** from 2026-08-23 until this fix. `!= 0` counts either value. Found by the scorecard sandbox — see [`docs/SCORECARD_SANDBOX_FINDINGS.md`](../SCORECARD_SANDBOX_FINDINGS.md).
- **Fixed 2026-09-01 — was silently dropping real production rows.** Same root cause and fix as [`encap_daily_report.md`](encap_daily_report.md)'s 2026-09-01 entry — see there for the full detail. The `Part_v_Job_Op` join changed from `INNER JOIN` to `LEFT JOIN`; reverified against `PlexTest` with a real row (Bottling Line 1) now flowing through — the first real number either of the 4 Daily Reports has ever returned.
- **Fixed 2026-08-24 — real "PARTIAL PRODUCTION" view-creation failure.** Same root cause and fix as [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-24 entry — see there for the full detail. Fixed by adding `SAFE_CAST(... AS INT64)` to the `Job`->`Part` join.
- **Verified 2026-08-25 — Test fixed, Prod still broken.** Same result as [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-25 entry: `PlexTest.packaging_daily_report` exists and is queryable (0 rows, benign); `PlexProd.packaging_daily_report` still doesn't exist — needs the prod job's next run.
- **Resolved 2026-08-26** — manually ran `plex-etl-work-orders` (prod), confirmed `PlexProd.packaging_daily_report` exists and is queryable (0 rows, still benign — see [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-26 entry for the full detail).
- **~~Fixed~~ Broken 2026-08-23 (reversed 2026-09-24, above) — scrap was silently always zero.** The scrap check compared Plex's `Rejected` flag to `1`, but Plex represents boolean true as `-1`, not `1` (an already-confirmed convention elsewhere in this pipeline) — so no row could ever match, and rejected quantity vanished from both the actual and scrap totals instead of being counted as scrap. Fixed by comparing to `-1`. Caught by code review before any real production data existed to be affected by it.
- **The "Packaging" line mapping is a decision, not a confirmed 1:1 match.** Plex has no workcenter category called "Packaging" — it only exists there as a department code and a separate part-classification field, neither of which lines up with an actual production line. This report uses Plex's "Bottling" line group instead, because those line names (Bottling Line 1-6, Bulk Room, Powder Line, Liquid Line) closely resemble the sheet's own lines. Which sheet "Line" corresponds to which Plex line hasn't been verified against real filled-in data yet.
- **Currently 0 rows — expected, not broken.** No real production has been logged against this tenant yet, so there's nothing to roll up. This should start populating once real jobs move past the scheduling stage.
- **Not built: Planned output, Start-Up Time, Real Capacity, and the Call Outs/OFF attendance roster.** These looked like manual scheduling inputs with no matching data in Plex, the same category of gap found on MFG Job Schedule's manual-only columns.
- **Employee count reflects who logged production, not who was scheduled or absent** — it isn't a substitute for an attendance/roster view.
- **Sheet's Front/Mid/End sub-counts per line aren't split out** — this report returns one total per line per day, not the finer-grained counter breakdown the sheet tracks.

## More detail

[`spreadsheets/packaging_daily_report.md`](../../spreadsheets/packaging_daily_report.md) has the full column-by-column mapping and research history.
