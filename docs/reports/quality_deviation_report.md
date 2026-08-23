# Quality Deviations

> **Status:** ✅ Built and deployed 2026-08-19, awaiting real production data (loads begin 2026-08-24) to confirm coverage · **Category:** Quality · **Runs:** rides the Quality Nonconformance pipeline

## What this tells you

One row per Quality Deviation record — what kind of deviation it was, its approval status, how many pieces were affected, the reason/note behind it, and which Job(s), Problem/NC(s), Part(s), and Workcenter(s) it applies to. This is the first report in the pipeline that can connect a quality issue directly to the job it happened on, using a real relational link rather than guesswork.

## Where it fits

Built as the fix for a gap flagged in the **Quality Nonconformance** report (`reports/quality_nonconformance.yaml`) and in the **MFG Job Schedule** Google Sheet tracked in [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md): the raw Nonconformance (NC) record in Plex has no link to a specific job, so there was no reliable way to answer "did this job have a deviation?" — which matters because MFG Job Schedule's Success Rating formula needs exactly that (its "Deviation = NO/YES" input). Also referenced in [`reports-list/quality.md`](../../reports-list/quality.md) as a likely match for the manually tracked **Deviation Open Closed Trending Area** Google Sheet.

## How it's built (high level)

Starts from Plex's Deviation records and follows Plex's own linking tables out to the Job(s), Problem/NC(s), Part(s), and Workcenter(s) each deviation touches, combining them into one row per deviation (a deviation that touches more than one of something lists them together rather than repeating the row). Adds the deviation's type and approval status from their respective lookup tables, plus the reason, note, pieces-affected count, and the approval/effective/expiration dates.

- **Pipeline:** `reports/quality_nonconformance.yaml` -> `quality_deviation_report`
- **SQL:** `reports/sql/quality_deviation_view.sql`

## Flags and open questions

- **Not yet confirmed: does every Nonconformance get a Deviation, or only some of them?** In standard quality terminology, a "Deviation" is usually a formally approved, planned exception to a spec or process — not automatically the same thing as "any quality issue occurred." Plex's data shows it *can* link a Deviation to an NC, but not that it *always* does. Until real data lands, we don't know what share of NCs this report actually covers — so it should not yet be treated as the complete, final answer to "did this job have a deviation."
- **This report is not yet wired into MFG Job Schedule's Success Rating.** The Job/Problem link this report provides is exactly what that sheet's "Deviation = NO/YES" gate needs, but merging it in is waiting on the coverage question above being validated against real data first.
- **No real data yet.** The underlying Plex tables were empty as of the last build check (test-tenant data load begins 2026-08-24), so nothing in this report — including the open question above — has been checked against an actual deviation record yet.

## More detail

[`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md) has the background on the NC-to-job gap this report was built to solve, and [`reports-list/quality.md`](../../reports-list/quality.md) has the wider Quality department report inventory this fits into.
