# Quality Nonconformance

> **Status:** ✅ Built 2026-08-11 · **repointed 2026-09-22 to the table Vox actually writes to, and returning 22 real records for the first time** · **Category:** Quality · **Runs:** `plex-etl-quality-nonconformance(-test)`, 9:00 PM / 9:10 PM Mountain (prod/test)

## What this tells you

One row per Non-Conformance (NC) record — **which form it was raised on** (Material Destruction, Non-Conformance Form, 8D, Risk Assessment, Complaint Form, 5P, Initial Problem Report, System Audit CAR), what part it was raised against, what kind of problem it was (type, category, status, defect type, severity), the written description of what went wrong, how many pieces were affected/rejected/returned/scrapped, root cause, the final disposition, cost, who owns it, and the dates it happened, was recorded, is due and was closed. This is the Plex-native source for NC data that today lives partly on a manually maintained tracking sheet and partly, it appears, in a separate internal Google Doc.

## It was reading the wrong table until 2026-09-22

Plex has **two** problem tables, and Vox uses the newer one. Every record the Quality team enters on the Problem Control screen goes to the "UX" table; this report was built against the classic one, which is empty and always has been on this tenant. Nothing announced it: the nightly job reported success every time, because the extraction genuinely succeeded — there was simply nothing in the table it was asking for.

Checked live on 2026-09-22: **19 records visible in the Problem Control screen, 22 in the UX table, 0 in the classic one.** The report now reads the UX table and returns all 22. The three sibling reports that read this one — Turn Around Time, NC Cost by Category, NC Cost by Disposition — were all empty for the same reason, and all three now return rows.

## Where it fits

Built to cover the **"NC #"** column of the manually maintained **MFG Job Schedule** Google Sheet — see [`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md) and [`docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md`](../MFG_JOB_SCHEDULE_BUILD_PLAN.md) for that history. [`reports-list/quality.md`](../../reports-list/quality.md) also flags a separate, human-maintained **"Internally Generated Nonconformance Tracking"** Google Doc as a strong likely overlap with this report — that comparison hasn't been done yet, so it's listed there as something to validate, not something this report has confirmed it replaces.

It ships alongside two sibling reports built off the same underlying Quality data: [Turnaround Time](quality_turnaround_time_report.md) and [Quality Deviations](quality_deviation_report.md).

## How it's built (high level)

Pulls every NC record Plex has on file, attaches the part it was raised against (part number and name), and looks up the **name of the form** it was raised on. Everything else — problem type/category/status, defect type, severity, the free-text description, root cause, the affected/rejected/returned/scrapped quantities, cost, the champion and department, and the happened/recorded/due/closed dates — comes straight off the record itself.

Descriptions typed on the UX form arrive as web markup (`<p>…&nbsp;…</p>`). The report strips that so the text reads as text on a tile or in an email, and keeps the original beside it for anyone who needs it.

- **Pipeline:** `reports/quality_nonconformance.yaml` -> `quality_nonconformance_report`
- **SQL:** `reports/sql/quality_nonconformance_view.sql`

## Flags and open questions

- **Cost is zero on every record, and the money is being typed into the description instead.** All 22 records carry a cost of 0. Three Material Destruction records have nothing in their description *but* a number — "$2305.57", "600" and "1.5". So any dollar figure built on this report reads $0 today. That is shown rather than patched: a made-up cost would be worse than a visible zero. **Question for Quality: should the destruction value go in Plex's Cost field?**
- **Final Disposition is blank on all 22, including the one closed record.** Destruction is being identified by the *form* (Material Destruction), not by dispositioning the material as Scrap. This matters for the Destruction $ tile, which is built on disposition — see [NC Cost by Disposition](quality_disposition_cost_report.md).
- **An NC record *can* be linked to a job after all.** The UX record carries a job and job-operation link directly, which retires the long-standing caveat that an NC could only be matched to a job by part number and date proximity. Nobody is filling it in yet — it is empty on all 22 records — but the capability is there, and it means the Deviation workaround isn't the only route.
- **No corrective-action field any more.** The UX record has no single corrective-action box; corrective and preventive actions live as their own records, one per action, which is what lets the CAPA/8D workflow track several at once. Those aren't pulled in yet — worth adding when someone needs action-level reporting.
- **Two spellings of the same status.** The data contains both "In Process" and "Open / In-Process", and both "Pending Verification" and "Verification Pending". Charts group on the status text, so these split into separate buckets. Worth confirming with Quality whether they're genuinely different states.
- **Problem Category is sparse and mixed.** Seven of 22 records have none, and the ones that do mix a source (Internal, Supplier, Customer Complaint, Audit Finding) with a defect ("Burnt Capsules", "Foreign Material"). [NC Cost by Category](quality_cost_by_category_report.md) groups on exactly this field.
- **Possible duplicate of a separate manual tracker.** A human-maintained "Internally Generated Nonconformance Tracking" document may cover the same ground as this report — worth a side-by-side comparison once that document's content is available, per `reports-list/quality.md`.

## More detail

[`spreadsheets/mfg_job_schedule.md`](../../spreadsheets/mfg_job_schedule.md) and [`docs/MFG_JOB_SCHEDULE_BUILD_PLAN.md`](../MFG_JOB_SCHEDULE_BUILD_PLAN.md) have the fuller history of how the NC # requirement was discovered and built out. [`reports-list/quality.md`](../../reports-list/quality.md) has the department-wide list of Quality tracking documents, including the possible manual-tracker overlap noted above.
