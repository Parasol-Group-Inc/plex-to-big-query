# Vox Scorecard | Open Caps (Encapsulation)

> **Status:** ✅ Deployed and verified 2026-09-01 — 2 real open jobs, 4,643,140 combined caps pending · **Category:** Production · **Runs:** rides the Work Orders pipeline

## What this tells you

The planned quantity still pending on every currently-open Encapsulation job — one row per job, with its status and the date it was entered.

## Where it fits

Replaces `Vox_Looker_DB - MFG_Job`'s "Open Caps" Operations tile. The scorecard's own audit flagged that tile as summing `Caps Pending` with **no status filter applied at all** — this report fixes that by only counting jobs that are genuinely still open (not Completed, Cancelled, or on Hold). See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Mirrors the already-deployed `labeling_open_work_orders_report` exactly — same open-job definition (a job is "open" if it's not Completed, Cancelled, or on Hold), same join shape, just pointed at the Encapsulation workcenter roster instead of Labeling.

- **Pipeline:** `reports/work_orders.yaml` → `mfg_job_open_caps_report`
- **SQL:** `reports/sql/mfg_job_open_caps_view.sql`

## Flags and open questions

- **"Open" definition decided 2026-09-01** (inverse of Completed/Cancelled/Hold status flags) — matches the pattern already used for Labeling/Printing Open WO reports, chosen specifically so it won't go stale if this tenant adds new status values later.
- **No `Customer` field** — the original sheet's Customer column has no confirmed Plex source at this report's grain (a job isn't directly linked to a customer without going through the sales-order allocation chain, which is a separate, currently-empty join — see `sales_order_value_by_status_report`).
## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md) and [`docs/reports/labeling_open_work_orders_report.md`](labeling_open_work_orders_report.md) (the report this one's pattern is copied from).
