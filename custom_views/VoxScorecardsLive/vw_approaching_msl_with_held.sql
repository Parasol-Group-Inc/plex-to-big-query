-- VoxScorecardsLive.vw_approaching_msl_with_held (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 21:18 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE OR REPLACE TABLE `voxdatalake.VoxScorecardsLive.vw_approaching_msl_with_held`
OPTIONS (description = 'TABLE (not a view). Snapshot of vw_approaching_msl_with_held_live, refreshed every 4 hours by a scheduled query. Edit logic in the _live view.')
AS
SELECT *, CURRENT_TIMESTAMP() AS refreshed_at
FROM `voxdatalake.VoxScorecardsLive.vw_approaching_msl_with_held_live`;
