-- VoxScorecardsLive.vw_sc_monthly_wide (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-10-30 17:50 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  month_start,
  SUM(IF(metric='sales', value, NULL))                                        AS sales,
  SUM(IF(metric='revenue', value, NULL))                                      AS revenue,
  SUM(IF(metric='wip_value', value, NULL))                                    AS wip,
  SUM(IF(metric='inventory_value', value, NULL))                              AS inventory_value,
  SUM(IF(metric='oos_count', value, NULL))                                    AS oos_count,
  SUM(IF(metric='production_units' AND workcenter='Encapsulation', value, NULL)) AS encapsulation,
  SUM(IF(metric='production_units' AND workcenter='Packaging', value, NULL))     AS packaging,
  SUM(IF(metric='production_units' AND workcenter='Labeling', value, NULL))      AS labeling,
  SUM(IF(metric='production_goal' AND workcenter='Encapsulation', value, NULL))  AS encapsulation_goal,
  SUM(IF(metric='production_goal' AND workcenter='Packaging', value, NULL))      AS packaging_goal,
  SUM(IF(metric='production_goal' AND workcenter='Labeling', value, NULL))       AS labeling_goal
FROM `voxdatalake.VoxScorecardsLive.vw_sc_base`
GROUP BY month_start
