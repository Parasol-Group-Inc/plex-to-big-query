# Quality Deviations

> **Status:** ✅ Built and deployed 2026-08-19 · 🔧 **linked-NC fix and `deviation_month` added 2026-09-24, deployed 2026-09-25** · **Category:** Quality · **Runs:** rides the Quality Nonconformance pipeline

## What this tells you

One row per Quality Deviation record — what kind of deviation it was, its approval status, how many pieces were affected, the reason/note behind it, and which Job(s), Problem/NC(s), Part(s), and Workcenter(s) it applies to. This is the first report in the pipeline that can connect a quality issue directly to the job it happened on, using a real relational link rather than guesswork.

## Where it fits

Built as the fix for a gap flagged in the **Quality Nonconformance** report (`reports/quality_nonconformance.yaml`) and in the **MFG Job Schedule** Google Sheet tracked in [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md): the raw Nonconformance (NC) record in Plex has no link to a specific job, so there was no reliable way to answer "did this job have a deviation?" — which matters because MFG Job Schedule's Success Rating formula needs exactly that (its "Deviation = NO/YES" input). Also referenced in [`reports-list/quality.md`](../../reports-list/quality.md) as a likely match for the manually tracked **Deviation Open Closed Trending Area** Google Sheet.

## How it's built (high level)

Starts from Plex's Deviation records and follows Plex's own linking tables out to the Job(s), Problem/NC(s), Part(s), and Workcenter(s) each deviation touches, combining them into one row per deviation (a deviation that touches more than one of something lists them together rather than repeating the row). Adds the deviation's type and approval status from their respective lookup tables, plus the reason, note, pieces-affected count, and the approval/effective/expiration/add dates.

**Which month a deviation counts in:** `deviation_month` — the month of the **add date**, when the deviation was raised in Plex. Plex stamps it on every record and it can't be moved later, so it is what a "deviations this month" or open/closed trend should count. The effective date (when the approved exception starts to apply, typed by a person and sometimes set ahead) is still in the report for anyone asking "what is in effect", but a tile should use `deviation_month` rather than choosing for itself.

- **Pipeline:** `reports/quality_nonconformance.yaml` -> `quality_deviation_report`
- **SQL:** `reports/sql/quality_deviation_view.sql`

## Flags and open questions

- **Fixed 2026-09-24, deployed 2026-09-25: the linked NC never showed.** The Problem/NC link read Plex's classic problem table, which is permanently empty on Vox's tenant — Vox's nonconformances live in the Problem Control screen's table (`Quality_v_Problem_2`). The other Quality reports were moved to it on 2026-09-22; this one was missed, so `problem_nos` was blank on every deviation. It now reads the right table. Checked against the real link: the deviation-to-problem row points at problem key 117294, which is real NC #21. In the scorecard sandbox, deviations showing an NC went from **0 of 151 to 49** (the 50th link belongs to a deviation that no longer exists — see below). The same fix added `deviation_month` (see above).
- **The one real deviation-to-NC link in PlexTest is orphaned.** It belongs to deviation key 14453, which is no longer in Plex's deviation list — today's only deviation, `0001`, is key 14461 and has no NC or part linked. The link table was last refreshed before that change, which fits the ETL keeping yesterday's rows when a table goes to 0 (see [the sandbox findings](../SCORECARD_SANDBOX_FINDINGS.md), "ETL and data findings"). So on real data `problem_nos` is still blank today — correctly — until someone links an NC to a live deviation.
- **Not yet confirmed: does every Nonconformance get a Deviation, or only some of them?** In standard quality terminology, a "Deviation" is usually a formally approved, planned exception to a spec or process — not automatically the same thing as "any quality issue occurred." Plex's data shows it *can* link a Deviation to an NC, but not that it *always* does. Until real data lands, we don't know what share of NCs this report actually covers — so it should not yet be treated as the complete, final answer to "did this job have a deviation."
- **This report is not yet wired into MFG Job Schedule's Success Rating.** The Job/Problem link this report provides is exactly what that sheet's "Deviation = NO/YES" gate needs, but merging it in is waiting on the coverage question above being validated against real data first.
- **Barely any real data yet.** PlexTest holds one real deviation (`0001`, added 2026-09-24, linked to work centre Blend 1 only) and PlexProd none, so the coverage question above still can't be answered from real records.

## More detail

[`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md) has the background on the NC-to-job gap this report was built to solve, and [`reports-list/quality.md`](../../reports-list/quality.md) has the wider Quality department report inventory this fits into.
