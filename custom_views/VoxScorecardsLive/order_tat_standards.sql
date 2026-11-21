-- VoxScorecardsLive.order_tat_standards (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-19 18:40 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE `voxdatalake.VoxScorecardsLive.order_tat_standards` (
  product_type STRING NOT NULL OPTIONS(description='Plex Product Type of the part sold on the order line (matches vw_job_turnaround.fg_product_type)'),
  stock_type_label STRING OPTIONS(description='Name used on the TAT goals sheet'),
  effective_month DATE NOT NULL OPTIONS(description='First month this goal applies. To change a goal, add a new row with a later month; the newest row on or before the order month is used'),
  bonus_standard_days INT64 OPTIONS(description='Bonus standard, work days (Pending Fulfillment to last ship)'),
  performance_standard_days INT64 OPTIONS(description='Performance standard, work days (Pending Fulfillment to last ship)'),
  note STRING,
  updated_at TIMESTAMP
)
OPTIONS(description='Order-line TAT goals (work days) by Plex Product Type, read by vw_job_turnaround. Hand-maintained.')
