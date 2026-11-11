-- VoxScorecardsLive.shipping_revenue_blanket_daily (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-17 19:38 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE `voxdatalake.VoxScorecardsLive.shipping_revenue_blanket_daily` (
  snapshot_date DATE,
  total_blanket_revenue FLOAT64
);
