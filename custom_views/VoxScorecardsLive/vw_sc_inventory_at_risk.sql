-- VoxScorecardsLive.vw_sc_inventory_at_risk (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 16:58 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH use_by AS (
  SELECT SAFE_CAST(sl.Lot_Key AS INT64) AS lot_key,
         MIN(DATE(SAFE_CAST(sl.Lot_Shelf_Life AS TIMESTAMP))) AS use_by_date
  FROM `voxdatalake.PlexProd.raw_Part_v_Lot_Shelf_Life` sl
  JOIN `voxdatalake.PlexProd.raw_Part_v_Shelf_Life_Type` t
    ON SAFE_CAST(t.Shelf_Life_Type_Key AS INT64) = SAFE_CAST(sl.Shelf_Life_Type_Key AS INT64)
  WHERE SAFE_CAST(t.Use_By AS INT64) = 1
  GROUP BY lot_key
),
lots AS (
  SELECT
    l.lot_key, l.container_count, l.inventory_value,
    CASE
      WHEN UPPER(l.container_status) = 'EXPIRED'
       AND u.use_by_date < CURRENT_DATE('America/Denver')
       AND NOT COALESCE(l.best_by_date < CURRENT_DATE('America/Denver'), FALSE)
        THEN 'Past Use By'
      ELSE INITCAP(l.container_status)
    END AS status
  FROM `voxdatalake.PlexProd.inventory_lot_detail_report` l
  LEFT JOIN use_by u ON u.lot_key = l.lot_key
  WHERE UPPER(l.container_status) IN ('QUARANTINE', 'EXPIRED', 'HOLD', 'LOT HOLD')
)
SELECT
  CASE status
    WHEN 'Quarantine' THEN 1 WHEN 'Expired' THEN 2 WHEN 'Past Use By' THEN 3
    WHEN 'Hold' THEN 4 WHEN 'Lot Hold' THEN 5 END AS sort_order,
  status,
  COUNT(DISTINCT lot_key)  AS lots,
  SUM(container_count)     AS containers,
  SUM(inventory_value)     AS inventory_value
FROM lots
GROUP BY 1, 2
