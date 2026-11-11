-- VoxScorecardsLive.shipping_revenue_shipped_daily (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-17 19:50 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE `voxdatalake.VoxScorecardsLive.shipping_revenue_shipped_daily` (
  snapshot_date DATE,
  total_shipped_revenue FLOAT64
);
