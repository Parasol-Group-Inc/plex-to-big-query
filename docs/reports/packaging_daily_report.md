# Packaging Daily Report

> **Status:** ✅ Fixed and verified in both Test and Prod 2026-08-26 — manually ran `plex-etl-work-orders` (prod), confirmed `PlexProd.packaging_daily_report` exists and is queryable again (0 rows, benign — see Flags below) · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per packaging line per day — how much was actually produced, how much was scrapped, and who worked it. This is the Plex-native replacement for the "Actual" side of the manually maintained "Packaging Daily Report" Google Sheet, which tracked Front/Mid/End counts, planned vs. actual output, and a start-up time per line.

## Where it fits

Fulfills the **Packaging Daily Report** Google Sheet tracked in [`spreadsheets/packaging_daily_report.md`](../../spreadsheets/packaging_daily_report.md) — one of four "Daily Reports" (alongside Encap, Blending, and Labeling) built the same way from the same underlying production log. Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Pulls from the same production-log data already extracted for Work Orders, then rolls it up by day and by line: total quantity produced, quantity scrapped, which parts ran, how many jobs and employees were involved, and which shifts worked. "Packaging" turned out not to be a real grouping inside Plex at all — production lines there are organized under a workcenter category called "Bottling," and after comparing the sheet's own line names (Line 1-5, Bulk, Gummy Line/Line 6, Powder Line, Liquid Line) against that roster, this report was built on the Bottling group as the closest match.

- **Pipeline:** `reports/work_orders.yaml` -> `packaging_daily_report`
- **SQL:** `reports/sql/packaging_daily_report_view.sql`

## Flags and open questions

- **Fixed 2026-08-24 — real "PARTIAL PRODUCTION" view-creation failure.** Same root cause and fix as [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-24 entry — see there for the full detail. Fixed by adding `SAFE_CAST(... AS INT64)` to the `Job`->`Part` join.
- **Verified 2026-08-25 — Test fixed, Prod still broken.** Same result as [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-25 entry: `PlexTest.packaging_daily_report` exists and is queryable (0 rows, benign); `PlexProd.packaging_daily_report` still doesn't exist — needs the prod job's next run.
- **Resolved 2026-08-26** — manually ran `plex-etl-work-orders` (prod), confirmed `PlexProd.packaging_daily_report` exists and is queryable (0 rows, still benign — see [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-26 entry for the full detail).
- **Fixed 2026-08-23 — scrap was silently always zero.** The scrap check compared Plex's `Rejected` flag to `1`, but Plex represents boolean true as `-1`, not `1` (an already-confirmed convention elsewhere in this pipeline) — so no row could ever match, and rejected quantity vanished from both the actual and scrap totals instead of being counted as scrap. Fixed by comparing to `-1`. Caught by code review before any real production data existed to be affected by it.
- **The "Packaging" line mapping is a decision, not a confirmed 1:1 match.** Plex has no workcenter category called "Packaging" — it only exists there as a department code and a separate part-classification field, neither of which lines up with an actual production line. This report uses Plex's "Bottling" line group instead, because those line names (Bottling Line 1-6, Bulk Room, Powder Line, Liquid Line) closely resemble the sheet's own lines. Which sheet "Line" corresponds to which Plex line hasn't been verified against real filled-in data yet.
- **Currently 0 rows — expected, not broken.** No real production has been logged against this tenant yet, so there's nothing to roll up. This should start populating once real jobs move past the scheduling stage.
- **Not built: Planned output, Start-Up Time, Real Capacity, and the Call Outs/OFF attendance roster.** These looked like manual scheduling inputs with no matching data in Plex, the same category of gap found on MFG Job Schedule's manual-only columns.
- **Employee count reflects who logged production, not who was scheduled or absent** — it isn't a substitute for an attendance/roster view.
- **Sheet's Front/Mid/End sub-counts per line aren't split out** — this report returns one total per line per day, not the finer-grained counter breakdown the sheet tracks.

## More detail

[`spreadsheets/packaging_daily_report.md`](../../spreadsheets/packaging_daily_report.md) has the full column-by-column mapping and research history.
