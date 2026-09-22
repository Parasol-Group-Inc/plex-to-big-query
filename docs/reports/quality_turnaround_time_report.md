# Turn Around Time Report

> **Status:** ✅ Built and deployed · **repointed 2026-09-22 to the table Vox actually writes to — returning 22 real records for the first time, and now shipping BOTH turnaround clocks instead of picking one** · **Category:** Quality · **Runs:** rides the Quality Nonconformance pipeline, 9:00 PM / 9:10 PM Mountain (prod/test)

## What this tells you

One row per quality problem (NC) record, showing when it was opened, when — if ever — it was closed, and how many days that took. This is the Plex-native parity report for NetSuite's "Turn Around Time Report." Both the "Last Month" and "Rolling" variants of that NetSuite report are just different date windows over this same list, not two separate reports here.

## Where it fits

Built for NetSuite parity against **Turn Around Time Report - Last Month** and **Turn Around Time Report - Rolling**, rows #69/#70 in [`mapping/netsuite-report-mapping.md`](../../mapping/netsuite-report-mapping.md) — the closest existing Plex analog identified there was "Average Days to Problem Resolution," rated Low-Med confidence. The choice of which date starts the turnaround clock was decided in [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md). It's a sibling view on the same pipeline as `quality_nonconformance_report` and `quality_deviation_report` — same underlying quality-problem data, cut a different way.

## How it's built (high level)

Starts from the same quality-problem records pulled for the Quality Nonconformance report, then for each one calculates the number of days to close it — **measured two ways, side by side**: from the date the problem happened, and from the date it was written up. The gap between those two is reporting lag, and it now has its own column too. Each row also says whether it closed by its own due date. Problems that are still open stay in the list — so open-vs-closed counts are visible — but don't get a day count until they close. Each row is also tagged with the month it closed in, so the same list can answer both "last month's turnaround" and "the trailing rolling window" by filtering to a different date range at the dashboard/query level, with no separate report needed for each.

- **Pipeline:** `reports/quality_nonconformance.yaml` -> `quality_turnaround_time_report`
- **SQL:** `reports/sql/quality_turnaround_time_view.sql`

## Flags and open questions

- **The clock-start question is no longer a guess you have to make in advance — both are published.** This report used to measure only Closed Date minus the date the problem happened, and the open question was whether Vox's existing Performance and Bonus standards were set against the date it was *written up* instead. Both dates are populated on the real records and they genuinely differ, so the report now carries both day counts plus the lag between them. Whichever the standards used, the comparable number is there — **but somebody still has to say which one the standards mean**, because that decides which column the scorecard reads.
- **Whether "Turn Around Time" means the same thing here as in NetSuite is unconfirmed.** This report's scope is problem-resolution time specifically. NetSuite's "Turn Around Time Report" could instead be tracking something broader or different — a supplier-return turnaround, for example — nobody has compared this against the real NetSuite report definition yet.
- **Closed dates are being entered in the future.** Of the two records that have one, one is dated a day ahead and the other six days ahead while still sitting in "Submitted for Closure". So an odd-looking turnaround is a data-entry question for Quality, not a calculation error. Those rows are flagged rather than dropped.
- **Only 2 of 22 records are closed at all**, so there is no meaningful average yet — the list is real, the trend isn't.
- **This report was silently broken from 2026-08-14 (when it was added) until 2026-08-19** — its SQL never made it out to BigQuery because of a missing deployment step, unrelated to the report's own logic. Fixed and confirmed deploying cleanly as of 2026-08-19.

## More detail

[`mapping/netsuite-report-mapping.md`](../../mapping/netsuite-report-mapping.md) (rows #69-70) has the original NetSuite parity mapping, and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) has the clock-start decision. `reports/quality_nonconformance.yaml` covers the shared problem-record data this report and its two siblings (Quality Nonconformance, Quality Deviations) all draw from.
