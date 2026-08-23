# Part Obsolescence

> **Status:** ✅ Built and deployed, confirmed live against real production infrastructure 2026-08-10/11 · **Category:** Supply Chain · **Runs:** own daily job, 8:00 PM / 8:10 PM Mountain (prod/test)

## What this tells you

One row per part that's either already **Obsolete** or has been flagged **Phase Out** in Plex — i.e. the "products to be discontinued" list: what's on its way out or already gone, and when its status was last changed. This is the Plex-native replacement for the NetSuite **Part Obsolescence** report.

## Where it fits

Fulfills NetSuite parity item **#77 — "Products to be discontinued"** tracked in [`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) and [`mapping/netsuite-report-mapping.md`](../../mapping/netsuite-report-mapping.md). Also listed in [`reports-list/ns-reference.md`](../../reports-list/ns-reference.md).

It also looks like a strong (likely full) overlap with a separate, unbuilt Quality request called **"Discontinued Materials"** — see [`reports-list/quality.md`](../../reports-list/quality.md), which flags this report as the thing to check first before treating that request as new work.

## How it's built (high level)

Pulls the part master (the same part data other reports like Sales Orders use), but keeps only the parts whose status is `Obsolete` or `Phase Out`, and reports each part's number, name, type, status, and the date that status was last updated.

- **Pipeline:** `reports/part_obsolescence.yaml` → `part_obsolescence_report`
- **SQL:** `reports/sql/part_obsolescence_view.sql`

## Flags and open questions

- **"Phase Out" is included alongside "Obsolete" by design, not by accident.** NetSuite's report is called "products **to be** discontinued" (future tense), so both Plex statuses were included on purpose — parts already fully retired (`Obsolete`) and parts on their way out (`Phase Out`). This was confirmed as the right read of the requester's intent, not left as a guess.
- **Nothing to verify yet.** The test tenant currently has zero parts in either status, so the report runs cleanly but hasn't been checked against a real Obsolete or Phase Out part. Worth a spot-check once one exists in Plex.

## More detail

[`docs/NETSUITE_REPORT_BUILD_PLAN.md`](../NETSUITE_REPORT_BUILD_PLAN.md) (§ #77 — VOX | Products to be discontinued) has the full confirmation log, including how the original plan (a status lookup-table join) turned out to be unnecessary once the real Plex schema was checked.
