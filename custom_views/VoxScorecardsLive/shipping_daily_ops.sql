-- VoxScorecardsLive.shipping_daily_ops (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-18 14:54 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE `voxdatalake.VoxScorecardsLive.shipping_daily_ops` (
  snapshot_date DATE,
  sales_orders_shipped INT64,
  packages_shipped INT64,
  new_sales_orders_received INT64,
  sales_orders_in_shipping_dept INT64
);
