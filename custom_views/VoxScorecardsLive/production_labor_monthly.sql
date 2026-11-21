-- VoxScorecardsLive.production_labor_monthly (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-19 15:44 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE `voxdatalake.VoxScorecardsLive.production_labor_monthly` (
  month_start DATE NOT NULL OPTIONS(description='First day of the month'),
  capsules_produced INT64 OPTIONS(description='Capsules produced in the month (from finance sheet)'),
  temp_labor_cost NUMERIC,
  vox_non_production_cost NUMERIC,
  vox_production_cost NUMERIC,
  production_ot_cost NUMERIC,
  employee_benefits_cost NUMERIC,
  parasol_admin_fees_cost NUMERIC,
  total_revenue NUMERIC,
  workdays INT64 OPTIONS(description='Production workdays in the month. Seeded as Mon-Fri minus US holidays; edit if the plant calendar differs'),
  temp_headcount NUMERIC OPTIONS(description='Avg temp headcount for the month (pending)'),
  prod_headcount NUMERIC OPTIONS(description='Avg Vox production headcount for the month (pending)'),
  non_prod_headcount NUMERIC OPTIONS(description='Avg Vox non-production headcount for the month (pending)'),
  source STRING,
  updated_at TIMESTAMP
)
OPTIONS(description='Monthly Vox labor cost, capsules produced and revenue (finance sheet production_millions). Drives labor $ per million capsules on the scorecard. Total labor = all cost columns; production labor = temp + vox production + OT.')
