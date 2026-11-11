-- VoxScorecardsLive.vw_sc_base (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-10-30 17:50 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT month_start, metric, workcenter, value, agg_type, source_system
FROM `voxdatalake.VoxScorecardsLive.scorecard_monthly_history`
