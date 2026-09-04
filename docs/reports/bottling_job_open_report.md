# Vox Scorecard | Open Bottles (Bottling)

> **Status:** ✅ Deployed and verified 2026-09-01 — 0 rows, confirmed for a real reason (no currently-open job sits on a Bottling-group workcenter on this tenant right now) · **Category:** Production · **Runs:** rides the Work Orders pipeline

## What this tells you

The planned quantity still pending on every currently-open Bottling job — one row per job, with its status and the date it was entered.

## Where it fits

Replaces `Vox_Looker_DB - Bottling_Job`'s "Open Bottles" Operations tile — same no-status-filter gap the scorecard audit flagged, same fix, for Bottling instead of Encapsulation. See [`mfg_job_open_caps_report.md`](mfg_job_open_caps_report.md) (this report's sibling) and [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

Same pattern as `mfg_job_open_caps_report`, filtered to the confirmed-live `Bottling` workcenter group instead of the Encapsulation roster.

- **Pipeline:** `reports/work_orders.yaml` → `bottling_job_open_report`
- **SQL:** `reports/sql/bottling_job_open_view.sql`

## Flags and open questions

- Same "open" definition and `Customer`-field gap as `mfg_job_open_caps_report` — see that doc.

## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).
