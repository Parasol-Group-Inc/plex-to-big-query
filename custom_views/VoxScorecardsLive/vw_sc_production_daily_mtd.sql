-- VoxScorecardsLive.vw_sc_production_daily_mtd (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-10-30 19:25 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT a.sort_order, a.area, a.unit_label, a.yesterday_value, a.today_value,
  g.actual_qty AS mtd_value, g.goal_value AS mtd_goal, g.pct_to_goal,
  SAFE_DIVIDE(EXTRACT(DAY FROM CURRENT_DATE('America/Denver')) - 1,
              EXTRACT(DAY FROM LAST_DAY(CURRENT_DATE('America/Denver')))) AS pct_of_month,
  -- Labeling open blanked: labeling isn't a job op on most Plex routings, so open qty isn't meaningful
  IF(a.workcenter_group = 'Labeling', NULL, a.open_value) AS open_value,
  IF(a.workcenter_group = 'Labeling', NULL, a.open_jobs)  AS open_jobs,
  a.last_record_at
FROM `voxdatalake.PlexProd.production_area_summary_report` a
LEFT JOIN `voxdatalake.PlexProd.v2_production_vs_goal_report` g
  ON g.workcenter_group = a.workcenter_group
 AND g.production_month = DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH)
