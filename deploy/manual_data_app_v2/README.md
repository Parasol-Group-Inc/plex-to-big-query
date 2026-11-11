# Manual-data app v2 ("Vox Goals", database-direct): what is LIVE

Copied from the live Apps Script project on 2026-11-10 (Emilio, editor). This, not
`deploy/manual_data_app/` (superseded), is what runs. Files: `Code.gs`, `Index.html` (the HTML file is
named `Index` in the project).

## How it works

- **Saves write straight to BigQuery** (`PlexProd`), append-only: newest row per key wins, a removal is a
  row with `is_deleted = TRUE`. **No Google Sheet, no hourly push, no trigger**: a table that has not
  changed for days just means nobody saved there.
- **Access:** `PlexProd.manual_data_access` lists who may edit each area (sales/production/revenue
  goals, safety, part usage, MSL rules) and who is an admin; admins manage it on the "User access" tab;
  every save checks it on the server. Deployed "Execute as: Me", "Anyone within Parasol Group Inc".
- **Script properties:** `GCP_PROJECT` (runs and bills the jobs), `BQ_DATA_PROJECT` = voxdatalake,
  `BQ_DATASET` = PlexProd.

## BigQuery objects it uses (checked 2026-11-10)

| Object | Use | Columns |
|---|---|---|
| `scorecard_goals_app` | goal saves | metric, period_month, scope, goal_value, note, unit, updated_by, updated_at, is_deleted |
| `safety_incidents` | incidents | incident_date, area, incident_type, recordable, days_lost, description, updated_by, updated_at, is_deleted |
| `msl_item_inputs` | part usage | ns_item_id, part_no, description, ns_avg_daily_usage, ns_reorder_point, as_of_date, mapping_status, note, updated_by, updated_at, is_deleted |
| `msl_rules` | MSL rules | rule, value, note, updated_by, updated_at, is_deleted |
| `manual_data_access` | who may edit | user_email, area, updated_by, updated_at, is_deleted |
| `scorecard_goals_resolved` | reads the goals in effect (since 2026-11-10; was the orphan `v2_scorecard_goals_resolved`) | |
| `production_monthly_by_workcenter_group_report`, `sales_reps_report`, `raw_Part_v_Part` | dropdowns, part checks | |

All five tables are BigQuery-only data and in `terraform/backup_snapshots.sql`. None is created by
Terraform or the ETL.

## Changes in this copy vs. what was live on 2026-11-10

1. `MSL_RULES.usage_min_days` default 30 → 183 and help text (Jennilyn's 6-month hold).
2. The goals grid reads `scorecard_goals_resolved` instead of `v2_scorecard_goals_resolved`. The repo
   renamed the resolver on 2026-09-22 (commit 66f781f) and dropped the `v2_*` views, but the four
   `v2_*` views were never deleted from BigQuery and the app kept reading one. On 2026-11-10 both
   resolvers had the same columns and identical rows (0 differences either way), so the switch changes
   nothing visible. After the app is redeployed, the orphan views `v2_scorecard_goals_resolved`,
   `v2_revenue_vs_goal_report`, `v2_production_vs_goal_report`, `v2_sales_vs_goal_report` can be dropped
   once no Looker data source uses them (OPEN_ITEMS D36).

## Changing it

Edit only what changed in the Apps Script editor (never paste the old `deploy/manual_data_app/` over
it), save, then **Deploy > Manage deployments > edit > New version**. Saving alone does not change the
live app. Keep `MSL_RULES` defaults in step with the `cfg` CTE in `reports/sql/approaching_msl_view.sql`.
