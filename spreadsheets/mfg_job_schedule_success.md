# MFG Job Schedule — "Success" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** ✅ Fully resolved — this is the literal config table for the
  formula reverse-engineered across `mfg_job_schedule_ytd_list.md`,
  `mfg_job_schedule_done_ytd.md`, and `mfg_job_schedule_done_2025.md`.
  Not row-level data, and nothing left to guess at.

## What it is

A tiny 4×4 config table — the actual goals/weights driving `Success
Rating`/`Success Grade` everywhere else in this spreadsheet:

| Product Type | stock | custom | success weight |
|---|---|---|---|
| Yield % | 0.95 | 0.92 | 0.33333 |
| Total Days | 84 | 84 | 0.33333 |
| Deviation | NO | NO | 0.33333 |

This is a direct, literal confirmation of everything reverse-engineered
from real data across 3 other tabs — not new inference, ground truth:

- **Yield goal**: 95% stock / 92% custom — exact match to the value
  guessed from Gate Stats' own headers back in
  `mfg_job_schedule_ytd_gate_stats.md`.
- **Total Days goal**: **84 for both stock and custom** — exact match to
  the boundary painstakingly pinned down across ~330 real rows in
  `mfg_job_schedule_ytd_list.md`/`done_ytd.md`/`done_2025.md`. Confirms
  the goal doesn't differ by product type (both are 84), which wasn't
  previously known for certain.
- **Deviation goal**: `NO` — matches.
- **Weighting**: all 3 gates weighted equally at 1/3 (`0.33333`) — matches
  the `Success Rating = (gates passed)/3` formula exactly, since 3 equally
  weighted binary pass/fail gates summed is mathematically the same thing.

A small side-table (columns J/K) logs the automation's last run —
`Date: 8/11/2026`, `19:13:58` — and a `Successful run` label, consistent
with the READ ME tab's description of a daily script. Not data to build
from, just confirms the automation actually ran recently.

## What this resolves

Confirms — from the source config itself, not inference — that the
formula and thresholds documented across the other tabs are correct.
**No longer "high confidence," now literally verified.** The one thing
this table does *not* state explicitly: the exact threshold for the
binary "Successful" flag in Gate Stats' Table 1 (100% required, or a
lower bar) — that's a UI/reporting decision downstream of this config,
not part of it. Open Question #4 in `mfg_job_schedule.md` stays open.

Also confirms the README's "you may change the success table at any
time — just note it doesn't apply retroactively" is describing exactly
this tab. If this ever needs replicating in BigQuery, this table itself
is small enough to hardcode as a versioned lookup (with an effective-date
range, per the non-retroactive note) rather than needing a live Plex
source — it's Emilio's own business config, not an ERP field.

## Verdict

Nothing to build here directly — this is config, not row-level data.
Its value was fully realized already: it validates every formula found
elsewhere in this spreadsheet.
