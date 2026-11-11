-- VoxScorecardsLive.pipeline_snapshot (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-04 20:16 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE TABLE `voxdatalake.VoxScorecardsLive.pipeline_snapshot` (
  snapshot_date DATE,
  pipeline_total NUMERIC
);
