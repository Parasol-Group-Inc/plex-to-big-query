# Blending Daily Report

> **Status:** ✅ Fixed and verified in both Test and Prod 2026-08-26 — manually ran `plex-etl-work-orders` (prod), confirmed `PlexProd.blending_daily_report` exists and is queryable again (0 rows, benign — see Flags below) · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per Blending or Pre-Weigh workstation per production day — how much product moved through that station, how much was scrapped, and who worked it. This is the Plex-native replacement for the "Actual" half of the manually maintained "Blending Daily Report" Google Sheet.

## Where it fits

Fulfills the **Blending Daily Report** Google Sheet tracked in [`spreadsheets/blending_daily_report.md`](../../spreadsheets/blending_daily_report.md) — one of the "4 Daily Reports" (alongside Encap, Labeling, and Packaging Daily Reports) built the same way. Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Takes Plex's raw production log, keeps only the entries logged against a Blending or Pre-Weigh workstation, and rolls them up into one summary line per day per station: total quantity produced, quantity scrapped, which jobs and parts ran, which employees logged time, and which shifts worked. Both "Blending" and "Pre-Weigh" stations are pulled into the same report because the sheet's own daily grid tracks both weigh-out and blending goals side by side.

- **Pipeline:** `reports/work_orders.yaml` -> `blending_daily_report`
- **SQL:** `reports/sql/blending_daily_report_view.sql`

## Flags and open questions

- **Fixed 2026-08-24 — real "PARTIAL PRODUCTION" view-creation failure.** Same root cause and fix as [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-24 entry — see there for the full detail. Fixed by adding `SAFE_CAST(... AS INT64)` to the `Job`->`Part` join.
- **Verified 2026-08-25 — Test fixed, Prod still broken.** Same result as [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-25 entry: `PlexTest.blending_daily_report` exists and is queryable (0 rows, benign); `PlexProd.blending_daily_report` still doesn't exist — needs the prod job's next run.
- **Resolved 2026-08-26** — manually ran `plex-etl-work-orders` (prod), confirmed `PlexProd.blending_daily_report` exists and is queryable (0 rows, still benign — see [`encap_daily_report.md`](encap_daily_report.md)'s 2026-08-26 entry for the full detail).
- **Fixed 2026-08-23 — scrap was silently always zero.** The scrap check compared Plex's `Rejected` flag to `1`, but Plex represents boolean true as `-1`, not `1` (an already-confirmed convention elsewhere in this pipeline) — so no row could ever match, and rejected quantity vanished from both the actual and scrap totals instead of being counted as scrap. Fixed by comparing to `-1`. Caught by code review before any real production data existed to be affected by it.
- **Weigh-out and blending quantities aren't split apart.** The sheet's template treats "Daily Weigh-Out Goal/Total" and "Daily Blending Goal/Total" as separate numbers, but this report combines both station types' output into one `actual_qty` column per row (distinguishable only by which station the row belongs to). Splitting them further would need to know whether the sheet actually wants them tracked differently — not yet confirmed.
- **Planned quantities, Start-Up Time, and Call Outs/attendance are not built.** Only the "Actual" side of the sheet (what was actually produced/scrapped, by whom) is covered — no Plex analog has been confirmed yet for the sheet's Planned/projected targets or its attendance tracking.
- **Not yet confirmed against real production data.** The underlying join between production records and employees is our best-guess mapping, not verified — as of the last test deploy, none of this tenant's real jobs had progressed far enough to produce actual output, so the report came back empty (0 rows), which is expected and not a sign of a problem. It still needs to be checked against a real day's numbers once production activity exists on this tenant.

## More detail

[`spreadsheets/blending_daily_report.md`](../../spreadsheets/blending_daily_report.md) has the full column-by-column mapping and research history.
