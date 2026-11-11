-- VoxScorecardsLive.sales_rep_roster (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 16:57 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE OR REPLACE TABLE `voxdatalake.VoxScorecardsLive.sales_rep_roster` (
  sales_rep STRING NOT NULL,
  sort_order INT64,
  active BOOL
)
