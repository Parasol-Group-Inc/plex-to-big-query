-- VoxScorecardsLive.high_risk_snapshots (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-05 13:22 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE IF NOT EXISTS `voxdatalake.VoxScorecardsLive.high_risk_snapshots` (
  snapshot_date DATE,
  part_number STRING,
  product_name STRING,
  lot_inventory FLOAT64,
  date_of_expiration TIMESTAMP,
  expiration_bucket STRING,
  lot_value FLOAT64,
  total_on_hand FLOAT64,
  average_monthly_usage FLOAT64
);
