-- VoxScorecardsLive.vw_sc_scrap_mtd (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 18:12 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH printing_scrap AS (
  -- Printing only (updated 2026-11-11): since 11/3 every Printing production record arrives
  -- with Rejected = 1, so the Rejected flag can't be used for Printing. Scrap = containers
  -- moved to Scrap status THIS MONTH (by scrap date, i.e. container Update_Date), valued at
  -- their original printed qty. Upper bound: Plex zeroes the container on scrap, so the
  -- leftover qty actually scrapped isn't in BigQuery yet.
  SELECT SUM(SAFE_CAST(p.Quantity AS FLOAT64)) AS scrap_qty
  FROM `voxdatalake.PlexProd.raw_Part_v_Production` p
  JOIN `voxdatalake.PlexProd.raw_Part_v_Workcenter` w
    ON SAFE_CAST(p.Workcenter_Key AS INT64) = w.Workcenter_Key
  JOIN `voxdatalake.PlexProd.raw_Part_v_Container` c
    ON c.Serial_No = p.Serial_No
  WHERE w.Workcenter_Group = 'Printing'
    AND c.Container_Status = 'Scrap'
    AND DATE_TRUNC(COALESCE(
          DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(c.Update_Date AS STRING) AS INT64), 0), 1000))),
          DATE(SAFE_CAST(CAST(c.Update_Date AS STRING) AS TIMESTAMP))), MONTH)
        = DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH)
),
base AS (
  SELECT r.*,
    IF(r.workcenter_group = 'Printing', ps.scrap_qty, r.scrap_qty) AS scrap_qty_adj
  FROM `voxdatalake.PlexProd.production_monthly_by_workcenter_group_report` r
  CROSS JOIN printing_scrap ps
  WHERE r.production_month = DATE_TRUNC(CURRENT_DATE('America/Denver'), MONTH)
)
SELECT
  CASE workcenter_group
    WHEN 'Pre-Weigh' THEN 1 WHEN 'Blending' THEN 2 WHEN 'Encapsulating' THEN 3
    WHEN 'Bottling' THEN 4 WHEN 'Printing' THEN 5 WHEN 'Labeling' THEN 6 ELSE 9 END AS sort_order,
  CASE workcenter_group
    WHEN 'Pre-Weigh' THEN 'Materials Weighed' WHEN 'Blending' THEN 'Blending'
    WHEN 'Encapsulating' THEN 'Encapsulation' WHEN 'Printing' THEN 'Labels Printed'
    ELSE workcenter_group END AS area,
  total_qty - COALESCE(scrap_qty_adj, 0)                AS good_qty_mtd,
  NULLIF(scrap_qty_adj, 0)                              AS scrap_qty_mtd,   -- NULL = no scrap recorded, shows as "-"
  total_qty                                             AS total_qty_mtd,
  IF(COALESCE(scrap_qty_adj, 0) = 0, NULL, SAFE_DIVIDE(scrap_qty_adj, total_qty)) AS scrap_rate
FROM base
