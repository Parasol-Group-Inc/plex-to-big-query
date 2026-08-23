# Encap Daily Report

> **Status:** ✅ Deployed to production 2026-08-22, but returning 0 rows on the test tenant while we wait for real production activity to confirm it · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

One row per Encapsulation line per production day — how many capsules were actually produced, how many were scrapped, which parts ran, and who worked the line. This is the Plex-native replacement for the "Actual" side of the manually maintained "Encap Daily Report" Google Sheet.

## Where it fits

Fulfills the **Encap Daily Report** Google Sheet tracked in [`spreadsheets/encap_daily_report.md`](../../spreadsheets/encap_daily_report.md) — one of the "4 Daily Reports" alongside Blending, Labeling, and Packaging. Also listed in [`reports-list/production.md`](../../reports-list/production.md).

## How it's built (high level)

Pulls Plex's own production-log records for the Encapsulation lines (Encapsulation 1 through 10) and rolls them up by date and by line: total good quantity produced, total scrap, which parts ran that day, and which employees logged the activity. It does not touch scheduling or planning data — it only reports what actually happened on the floor, which is the half of the sheet Plex can currently answer.

- **Pipeline:** `reports/work_orders.yaml` -> `encap_daily_report`
- **SQL:** `reports/sql/encap_daily_report_view.sql`

## Flags and open questions

- **Fixed 2026-08-23 — scrap was silently always zero.** The scrap check compared Plex's `Rejected` flag to `1`, but Plex represents boolean true as `-1`, not `1` (an already-confirmed convention elsewhere in this pipeline) — so no row could ever match, and rejected quantity vanished from both the actual and scrap totals instead of being counted as scrap. Fixed by comparing to `-1`. Caught by code review before any real production data existed to be affected by it.
- **Not yet confirmed against real activity.** As of this build, every job on the test tenant had just been created that morning with nothing actually run against it yet, so this report currently returns 0 rows for a benign reason (nothing to report), not a broken join. It needs a re-check once real Encapsulation production has actually happened.
- **Not built: Daily Production Goal, Start-Up/Stop times, and a true attendance roster.** The sheet's template asks for a planned target, per-station start/stop times, and who was scheduled vs. who actually showed up — none of these have a confirmed source in Plex, so they're left out rather than guessed at. The employee names this report does show are a byproduct of who logged the production record, not a formal attendance count.
- **Stations 3 and 6 are not filtered out, but may show no data.** The sheet's template only lists Encap stations 1, 2, 4, 5, 7, 8, 9, 10, skipping 3 and 6. This report doesn't hardcode that skip — if those two stations are genuinely decommissioned or renamed in Plex, they should simply show zero activity once real data exists, but that hasn't been confirmed yet.
- **Employee attribution is an inferred link, not a confirmed one.** The employee tied to each production record is matched using the same assumption already relied on elsewhere in this pipeline (for MFG Job Schedule) — reasonable, but not something Plex or the business has explicitly confirmed.

## More detail

[`spreadsheets/encap_daily_report.md`](../../spreadsheets/encap_daily_report.md) has the full column-by-column mapping and research history, including why this report was rebuilt once mid-build after an initial attempt used the wrong underlying Plex table.
