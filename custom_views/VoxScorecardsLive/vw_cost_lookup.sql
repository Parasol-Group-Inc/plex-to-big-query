-- VoxScorecardsLive.vw_cost_lookup (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-05-28 19:17 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  part,
  cost_ea,
  'cost_sheet' AS cost_source
FROM `voxdatalake.VoxScorecardsLive.Product_Cost`

UNION ALL

-- Fallback: NS average_cost for parts not on cost sheet
SELECT
  ns.name           AS part,
  ns.average_cost   AS cost_ea,
  'netsuite'        AS cost_source
FROM `voxdatalake.VoxScorecardsLive.Overstock_NS` ns
WHERE
  ns.average_cost IS NOT NULL
  AND ns.average_cost > 0
  AND ns.name NOT IN (SELECT part FROM `voxdatalake.VoxScorecardsLive.Product_Cost`)
  AND REGEXP_CONTAINS(ns.name, r'^1[34]\d{3}$')
