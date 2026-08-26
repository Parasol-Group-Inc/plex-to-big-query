# MFG Job Schedule - YTD Gate Stats

> **Status:** ✅ Built and deployed 2026-08-26, verified live (0 rows, benign — see Flags below) · **Category:** Production · **Runs:** rides the Work Orders pipeline, 7:20 PM / 7:30 PM Mountain (prod/test)

## What this tells you

A monthly scorecard: how many jobs were "Successful" that month (all 3 goals hit — Yield, no Deviation, on-time), broken out by Stock vs. Custom, plus average Yield/turnaround time and Deviation counts per product type.

## Where it fits

Covers the **YTD Gate Stats** sub-tab tracked in [`spreadsheets/mfg_job_schedule_ytd_gate_stats.md`](../../spreadsheets/mfg_job_schedule_ytd_gate_stats.md).

## How it's built (high level)

Groups [MFG Job Schedule - Success Metrics](mfg_job_schedule_success_metrics_report.md) by month, counting how many jobs passed all 3 goals ("Successful") vs. didn't, split by Stock/Custom, plus the average Yield/turnaround-time and Deviation counts each side.

- **Pipeline:** `reports/work_orders.yaml` → `mfg_job_schedule_gate_stats_report`
- **SQL:** `reports/sql/mfg_job_schedule_gate_stats_view.sql`

## Flags and open questions

- **"Successful" = all 3 gates pass (100%), not partial credit** — a real decision made 2026-08-26, not the only reading of the source spreadsheet's headers; a ≥2-of-3 partial-credit reading was the alternative considered.
- **Rework rows are included in every total**, not excluded — same 2026-08-26 decision as the underlying Success Metrics report.
- **Currently 0 rows — expected, not broken.** A job only gets a `month` once it has an FG Testing Released date, and none of this tenant's real jobs have one yet (all added the same day this was built). Will populate once real QC checksheets get approved.
- Inherits every other caveat from [MFG Job Schedule - Success Metrics](mfg_job_schedule_success_metrics_report.md) (Yield/FG-Testing-Released/Stock-vs-Custom proxies).

## More detail

[`spreadsheets/mfg_job_schedule_ytd_gate_stats.md`](../../spreadsheets/mfg_job_schedule_ytd_gate_stats.md) has the full formula derivation, including the reverse-engineered Success Rating formula this rolls up.
