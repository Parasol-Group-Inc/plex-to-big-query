# Blending Daily Report

- **Link:** https://docs.google.com/spreadsheets/d/1NyJOe2PUyNElJkHz1kYknGGQC8fKaFd9l32nPFJJjNQ/edit
- **Type:** Google Sheet
- **Category:** Daily Numbers Report / Scheduling
- **Departments:** Production, Planning
- **Status:** ⏳ Pending — awaiting sheet content
- **Plex reference:** [Production Yield](plex_production_yield_reference.md) (Inventory Tracking, ActionKey 7346) — a lead, not a confirmed source

## What's needed to start

A CSV export or full column list of the actual sheet (same as was done for
[MFG Job Schedule](mfg_job_schedule.md)) — a name and category aren't
enough to map columns to Plex views. Once available, follow the working
pattern in [SPREADSHEET_CATALOG.md](SPREADSHEET_CATALOG.md#working-pattern-established-on-mfg-job-schedule).

Note: this sheet's category includes "Scheduling" (unlike the other two
Daily Reports) — it may also overlap with `mfg_job_schedule_report`'s
blending workcenter/operation data once real workcenter naming is
confirmed (see [mfg_job_schedule.md](mfg_job_schedule.md)'s
Blending-vs-Encapsulation gap note). Worth checking for overlap before
building a separate pipeline.
