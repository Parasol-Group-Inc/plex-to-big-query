-- VoxScorecardsLive.scorecard_monthly_history (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-10-30 17:38 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE `voxdatalake.VoxScorecardsLive.scorecard_monthly_history` (
  month_start DATE NOT NULL, metric STRING NOT NULL, workcenter STRING, value NUMERIC NOT NULL,
  agg_type STRING NOT NULL, source_system STRING NOT NULL)
