# Vox Scorecard | FPY by Area & Month

> **Status:** ✅ Deployed and verified 2026-09-01 — real 100% FPY for Bottling and Pre-Weigh, August 2026 (see below) · **Category:** Quality · **Runs:** rides the Work Orders pipeline

## What this tells you

First Pass Yield (the % of units produced that didn't get rejected) by production area and month, plus a provisional DPMO (defects per million opportunities) figure.

## Where it fits

Replaces `Quality_Looker_DB - YTD FPYs`, the Google Sheet behind the scorecard's 3 FPY tiles (Encap/Bottling/Labeling) — the 2nd-highest-usage source in the whole scorecard (9 charts). See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

FPY comes straight from actual production logs: for each workcenter group and month, the share of produced quantity that wasn't marked rejected. This needs no assumption at all — same underlying data (`Part_v_Production`) already powers the 4 Daily Reports and the MFG Job Schedule Yield calculation.

DPMO is a provisional placeholder, decided 2026-09-01: the real formula needs an "opportunities per unit" number that's a quality-engineering process definition, not something Plex stores anywhere. This view assumes 1 opportunity per unit (each rejected unit = 1 defect) so the column isn't just blank — swap in a real number once Quality defines one. **Sigma is not computed at all** — converting DPMO to a Sigma level needs a proper statistical lookup or approximation, and given this is cGMP-adjacent reporting, a hand-rolled formula risked looking right while being wrong. Left out rather than guessed.

- **Pipeline:** `reports/work_orders.yaml` → `quality_fpy_by_area_month_report`
- **SQL:** `reports/sql/quality_fpy_by_area_month_view.sql`

## Flags and open questions

- **DPMO is provisional** (Opportunities_Per_Unit = 1, a named constant in the SQL) — treat it as a placeholder, not a final number, until Quality Engineering gives a real per-process opportunity count.
- **No Sigma column at all**, on purpose — see above.
- **Fixed 2026-09-01, same day it was written.** The first version copied the Daily Reports' `Part_v_Production → Part_v_Job_Op → Part_v_Workcenter` join, but this view already reached `Workcenter_Group` via `Part_v_Production.Workcenter_Key` directly — the `Job_Op` join was unused and, as an `INNER JOIN`, silently dropped every row (this tenant's real `Job_Op_Key` values in `Part_v_Production` have since aged out of the current `Part_v_Job_Op` extract). Removed the join entirely; reverified with real output: Bottling and Pre-Weigh both show 100% FPY for August 2026 (3,000/3,000 and 429.185/429.185 good/total), DPMO 0.
- **Doesn't correlate to individual NC records.** This computes FPY purely from produced-vs-rejected quantities; it doesn't try to link back to `quality_nonconformance_report`'s NC log the way the original sheet's "Total NCs+ Reworks" column implied, because `Quality_v_Problem` has no reliable workcenter/area link (only `Quality_v_Deviation` does, via junction tables, and coverage of Problem-by-Deviation isn't confirmed complete).
## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).
