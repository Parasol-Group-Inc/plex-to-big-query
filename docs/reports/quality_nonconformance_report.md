# Quality Nonconformance

> **Status:** ✅ Built and deployed 2026-08-11, compiles and queries cleanly but not yet checked against a real NC record · **Category:** Quality · **Runs:** `plex-etl-quality-nonconformance(-test)`, 9:00 PM / 9:10 PM Mountain (prod/test)

## What this tells you

One row per Non-Conformance (NC) record — what part it was raised against, what kind of problem it was (type, category, status, defect type, severity), the written description of what went wrong, how many pieces were affected/rejected/returned, root cause and corrective action, the final disposition, cost, and when it was opened and closed. This is the Plex-native source for NC data that today lives partly on a manually maintained tracking sheet and partly, it appears, in a separate internal Google Doc.

## Where it fits

Built to cover the **"NC #"** column of the manually maintained **MFG Job Schedule** Google Sheet — see [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md) and [`docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md`](../MFG_JOB_SCHEDULE_BUILD_PLAN.md) for that history. [`reports-list/quality.md`](../../reports-list/quality.md) also flags a separate, human-maintained **"Internally Generated Nonconformance Tracking"** Google Doc as a strong likely overlap with this report — that comparison hasn't been done yet, so it's listed there as something to validate, not something this report has confirmed it replaces.

It ships alongside two sibling reports built off the same underlying Quality data: [Turnaround Time](quality_turnaround_time_report.md) and [Quality Deviations](quality_deviation_report.md).

## How it's built (high level)

Pulls every NC record Plex has on file and attaches the part it was raised against (part number and name). Everything else — problem type/category/status, defect type, severity, the free-text description and root-cause/corrective-action fields, the affected/rejected/returned quantities, cost, and the opened/closed dates — comes straight off the NC record itself; none of it needed a lookup table.

- **Pipeline:** `reports/quality_nonconformance.yaml` -> `quality_nonconformance_report`
- **SQL:** `reports/sql/quality_nonconformance_view.sql`

## Flags and open questions

- **An NC record isn't linked to a specific job or work order.** Plex ties each NC to a part (and optionally a workcenter/building), not to a specific production job. Matching an NC back to a row on the job schedule has to be done by part number + date proximity, not a real join key — there's no way to say for certain "this NC belongs to that job."
- **A real job link exists, but only for NCs that also have a Deviation, and that's unconfirmed.** A sibling report, [Quality Deviations](quality_deviation_report.md), found that Plex's Deviation records *do* carry a real link to Job — but it's not yet known whether every NC gets a linked Deviation, or only the ones that needed a documented workaround. Until that's checked against real data, this report has no confirmed job link of its own.
- **Not yet verified against a real NC record.** The test tenant had zero NC records when this was built, so the report is confirmed to compile and run correctly, but no one has checked its output against an actual finished nonconformance case yet.
- **Possible duplicate of a separate manual tracker.** A human-maintained "Internally Generated Nonconformance Tracking" document may cover the same ground as this report — worth a side-by-side comparison once that document's content is available, per `reports-list/quality.md`.

## More detail

[`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md) and [`docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md`](../MFG_JOB_SCHEDULE_BUILD_PLAN.md) have the fuller history of how the NC # requirement was discovered and built out. [`reports-list/quality.md`](../../reports-list/quality.md) has the department-wide list of Quality tracking documents, including the possible manual-tracker overlap noted above.
