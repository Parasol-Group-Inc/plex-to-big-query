# Turn Around Time Report

> **Status:** ✅ Built and deployed (fixed 2026-08-19 after a silent deployment gap since 2026-08-14) — awaiting real Quality data to confirm the turnaround-clock definition · **Category:** Quality · **Runs:** rides the Quality Nonconformance pipeline, 9:00 PM / 9:10 PM Mountain (prod/test)

## What this tells you

One row per quality problem (NC) record, showing when it was opened, when — if ever — it was closed, and how many days that took. This is the Plex-native parity report for NetSuite's "Turn Around Time Report." Both the "Last Month" and "Rolling" variants of that NetSuite report are just different date windows over this same list, not two separate reports here.

## Where it fits

Built for NetSuite parity against **Turn Around Time Report - Last Month** and **Turn Around Time Report - Rolling**, rows #69/#70 in [`mapping/netsuite-report-mapping.md`](../../mapping/netsuite-report-mapping.md) — the closest existing Plex analog identified there was "Average Days to Problem Resolution," rated Low-Med confidence. The choice of which date starts the turnaround clock was decided in [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md). It's a sibling view on the same pipeline as `quality_nonconformance_report` and `quality_deviation_report` — same underlying quality-problem data, cut a different way.

## How it's built (high level)

Starts from the same quality-problem records pulled for the Quality Nonconformance report, then for each one calculates the number of days between when the problem was opened and when it was closed. Problems that are still open stay in the list — so open-vs-closed counts are visible — but don't get a day count until they close. Each row is also tagged with the month it closed in, so the same list can answer both "last month's turnaround" and "the trailing rolling window" by filtering to a different date range at the dashboard/query level, with no separate report needed for each.

- **Pipeline:** `reports/quality_nonconformance.yaml` -> `quality_turnaround_time_report`
- **SQL:** `reports/sql/quality_turnaround_time_view.sql`

## Flags and open questions

- **The turnaround "clock start" is a best-criteria guess, not NetSuite-confirmed.** This report measures Closed Date minus Problem Date. The underlying Plex record also has an Entered Date and a Response Due Date, either of which could be what the real NetSuite report actually intended as the start of the clock — flagged for review once there's a real NetSuite run to compare against.
- **Whether "Turn Around Time" means the same thing here as in NetSuite is unconfirmed.** This report's scope is problem-resolution time specifically. NetSuite's "Turn Around Time Report" could instead be tracking something broader or different — a supplier-return turnaround, for example — nobody has compared this against the real NetSuite report definition yet.
- **Not yet checked against real data.** The underlying quality-problem data is still empty on the test tenant — real Quality data doesn't start loading until 2026-08-24 — so no output from this report, including the open/closed split and the day counts, has been eyeballed against an actual resolved problem yet.
- **This report was silently broken from 2026-08-14 (when it was added) until 2026-08-19** — its SQL never made it out to BigQuery because of a missing deployment step, unrelated to the report's own logic. Fixed and confirmed deploying cleanly as of 2026-08-19.

## More detail

[`mapping/netsuite-report-mapping.md`](../../mapping/netsuite-report-mapping.md) (rows #69-70) has the original NetSuite parity mapping, and [`docs/NETSUITE_PARITY_OPEN_ITEMS.md`](../NETSUITE_PARITY_OPEN_ITEMS.md) has the clock-start decision. `reports/quality_nonconformance.yaml` covers the shared problem-record data this report and its two siblings (Quality Nonconformance, Quality Deviations) all draw from.
