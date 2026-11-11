-- VoxScorecardsLive.vw_approaching_msl_with_held_live (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 16:48 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH part AS (
  SELECT SAFE_CAST(Part_Key AS INT64) AS part_key, Part_No AS part_no
  FROM `voxdatalake.PlexProd.raw_Part_v_Part`
),
wrap AS (  -- same wrapper-key conversion approaching_msl_report uses
  SELECT SAFE_CAST(b.Part_Key AS INT64) AS wrapper_key, MAX(SAFE_CAST(b.Quantity AS FLOAT64)) AS factor
  FROM `voxdatalake.PlexProd.raw_Part_v_BOM` b
  JOIN part pw ON pw.part_key = SAFE_CAST(b.Part_Key AS INT64)
  JOIN part pc ON pc.part_key = SAFE_CAST(b.Component_Part_Key AS INT64)
  WHERE pw.part_no = pc.part_no AND pw.part_key != pc.part_key
    AND COALESCE(SAFE_CAST(b.Active AS INT64), 1) != 0
    AND SAFE_CAST(b.Quantity AS FLOAT64) > 0
  GROUP BY 1
),
-- Use By date per lot (Shelf_Life_Type.Use_By = 1). Plex sets container status EXPIRED
-- when EITHER best-by or use-by passes; this separates the use-by-only cases.
use_by AS (
  SELECT SAFE_CAST(sl.Lot_Key AS INT64) AS lot_key,
         MIN(DATE(SAFE_CAST(sl.Lot_Shelf_Life AS TIMESTAMP))) AS use_by_date
  FROM `voxdatalake.PlexProd.raw_Part_v_Lot_Shelf_Life` sl
  JOIN `voxdatalake.PlexProd.raw_Part_v_Shelf_Life_Type` t
    ON SAFE_CAST(t.Shelf_Life_Type_Key AS INT64) = SAFE_CAST(sl.Shelf_Life_Type_Key AS INT64)
  WHERE SAFE_CAST(t.Use_By AS INT64) = 1
  GROUP BY lot_key
),
lots AS (
  SELECT l.*,
    (UPPER(l.container_status) = 'EXPIRED'
      AND u.use_by_date < CURRENT_DATE('America/Denver')
      AND NOT COALESCE(l.best_by_date < CURRENT_DATE('America/Denver'), FALSE)) AS is_past_use_by_only
  FROM `voxdatalake.PlexProd.inventory_lot_detail_report` l
  LEFT JOIN use_by u ON u.lot_key = l.lot_key
  WHERE UPPER(l.container_status) IN ('LOT HOLD', 'QUARANTINE', 'EXPIRED')
),
held AS (
  SELECT
    l.part_no,
    SUM(IF(UPPER(l.container_status) = 'LOT HOLD',   l.quantity * COALESCE(w.factor, 1), 0)) AS lot_hold_qty,
    SUM(IF(UPPER(l.container_status) = 'QUARANTINE', l.quantity * COALESCE(w.factor, 1), 0)) AS quarantine_qty,
    SUM(IF(UPPER(l.container_status) = 'EXPIRED' AND NOT l.is_past_use_by_only,
           l.quantity * COALESCE(w.factor, 1), 0)) AS expired_qty,
    SUM(IF(l.is_past_use_by_only, l.quantity * COALESCE(w.factor, 1), 0)) AS past_use_by_qty
  FROM lots l
  LEFT JOIN wrap w ON w.wrapper_key = SAFE_CAST(l.part_key AS INT64)
  GROUP BY l.part_no
)
SELECT
  m.*,
  COALESCE(h.lot_hold_qty, 0)   AS lot_hold_qty,
  COALESCE(h.quarantine_qty, 0) AS quarantine_qty,
  COALESCE(h.expired_qty, 0)    AS expired_qty,
  COALESCE(h.lot_hold_qty, 0) + COALESCE(h.quarantine_qty, 0) + COALESCE(h.expired_qty, 0)
    + COALESCE(h.past_use_by_qty, 0) AS held_qty,
  m.on_hand_qty + COALESCE(h.lot_hold_qty, 0) + COALESCE(h.quarantine_qty, 0) + COALESCE(h.expired_qty, 0)
    + COALESCE(h.past_use_by_qty, 0) AS on_hand_incl_held_qty,
  COALESCE(h.past_use_by_qty, 0) AS past_use_by_qty
FROM `voxdatalake.PlexProd.approaching_msl_report` m
LEFT JOIN held h USING (part_no)
