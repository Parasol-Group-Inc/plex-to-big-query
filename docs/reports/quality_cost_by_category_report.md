# Vox Scorecard | NC Cost by Category

> **Status:** ✅ Deployed and verified 2026-09-01 — 0 rows, confirmed genuinely empty (`Quality_v_Problem` has no real rows yet on this tenant), not a query bug · **Category:** Quality · **Runs:** rides the Quality Nonconformance pipeline

## What this tells you

For every category of quality issue Plex has a record of (whatever `Problem_Category` values actually exist on this tenant — not guessed here), how many records there were and how much dollar cost was logged against them, by month.

## Where it fits

Aimed at the Vox Nutrition Scorecard's `Quality_Rework` ("$ Total Cost") and `Quality_MatDestr` ("$ Value") tiles — both previously flagged as having no confirmed Plex cost source. That turned out to be wrong: `Quality_v_Problem.Cost` already exists and is already exposed by `quality_nonconformance_report`. What's still unconfirmed is which live `Problem_Category` values correspond to "Rework" and "Material Destruction" specifically. See [`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md).

## How it's built (high level)

A straight rollup of the already-deployed `quality_nonconformance_report` — group its `problem_category` and `cost` columns by category and month, no new Plex data.

- **Pipeline:** `reports/quality_nonconformance.yaml` → `quality_cost_by_category_report`
- **SQL:** `reports/sql/quality_cost_by_category_view.sql`

## Flags and open questions

- **Deliberately does not guess category strings.** Once this is queryable, look at the real `problem_category` values it returns and identify which ones map to "Rework" and "Material Destruction" — at that point a thin `WHERE problem_category IN (...)` view over this one gives the scorecard's exact two numbers.
## More detail

[`score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md`](../../score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md) and [`docs/reports/quality_nonconformance_report.md`](quality_nonconformance_report.md).
