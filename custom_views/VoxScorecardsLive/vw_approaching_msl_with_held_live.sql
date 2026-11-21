-- VoxScorecardsLive.vw_approaching_msl_with_held_live (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-16 22:03 UTC by jennilyn.tockstein@parasolgroupinc.com

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
-- On-hand straight from the raw containers (2026-11-16, Jennilyn). The PlexProd
-- on-hand views are redeployed from source and exclude ALLOCATED and RELEASED;
-- computing it here keeps the rule in this view and cannot double count if the
-- source is later fixed.
raw_on_hand AS (
  SELECT
    pt.part_no,
    SUM(IF(s.status IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER', 'ALLOCATED', 'RELEASED'),
           s.qty * COALESCE(w.factor, 1), 0)) AS on_hand_qty,
    SUM(IF(s.status = 'ALLOCATED', s.qty * COALESCE(w.factor, 1), 0)) AS allocated_qty,
    SUM(IF(s.status = 'RELEASED',  s.qty * COALESCE(w.factor, 1), 0)) AS released_qty
  FROM (
    SELECT SAFE_CAST(c.Part_Key AS INT64) AS part_key,
           UPPER(TRIM(CAST(c.Container_Status AS STRING))) AS status,
           SAFE_CAST(c.Quantity AS FLOAT64) AS qty
    FROM `voxdatalake.PlexProd.raw_Part_v_Container` c
    WHERE SAFE_CAST(c.Active AS INT64) = 1
  ) s
  JOIN part pt ON pt.part_key = s.part_key
  LEFT JOIN wrap w ON w.wrapper_key = s.part_key
  GROUP BY pt.part_no
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
),
adj AS (
  SELECT
    m.*,
    COALESCE(r.on_hand_qty, 0)                                   AS new_on_hand_qty,
    m.quantity_available - m.on_hand_qty + COALESCE(r.on_hand_qty, 0) AS new_quantity_available,
    COALESCE(r.allocated_qty, 0)                                 AS allocated_qty,
    COALESCE(r.released_qty, 0)                                  AS released_qty
  FROM `voxdatalake.PlexProd.approaching_msl_report` m
  LEFT JOIN raw_on_hand r USING (part_no)
)
SELECT
  a.part_no,
  a.description,
  a.reorder_point,
  a.new_on_hand_qty                                              AS on_hand_qty,
  a.new_quantity_available                                       AS quantity_available,
  (a.new_quantity_available < 0
   OR (a.reorder_point > 0 AND a.new_quantity_available <= a.reorder_point)) AS at_reorder_point,
  a.avg_daily_usage,
  a.usage_days,
  SAFE_DIVIDE(a.new_on_hand_qty, a.avg_daily_usage)              AS days_on_hand,
  SAFE_DIVIDE(a.new_quantity_available - a.reorder_point, a.avg_daily_usage) AS days_to_reorder,
  a.on_order_qty,
  a.open_job_qty,
  a.in_mfg_or_ordered,
  a.usage_source,
  a.plex_avg_daily_usage,
  a.ns_avg_daily_usage,
  a.plex_reorder_point,
  a.ns_reorder_point,
  a.ns_as_of,
  a.data_flag,
  a.unit,
  a.product_type,
  a.part_type,
  a.part_group_key,
  a.part_group,
  a.part_source_key,
  a.demand_qty,
  a.gross_demand_qty,
  COALESCE(h.lot_hold_qty, 0)   AS lot_hold_qty,
  COALESCE(h.quarantine_qty, 0) AS quarantine_qty,
  COALESCE(h.expired_qty, 0)    AS expired_qty,
  COALESCE(h.lot_hold_qty, 0) + COALESCE(h.quarantine_qty, 0) + COALESCE(h.expired_qty, 0)
    + COALESCE(h.past_use_by_qty, 0) AS held_qty,
  a.new_on_hand_qty + COALESCE(h.lot_hold_qty, 0) + COALESCE(h.quarantine_qty, 0) + COALESCE(h.expired_qty, 0)
    + COALESCE(h.past_use_by_qty, 0) AS on_hand_incl_held_qty,
  COALESCE(h.past_use_by_qty, 0) AS past_use_by_qty,
  a.allocated_qty,
  a.released_qty
FROM adj a
LEFT JOIN held h USING (part_no)
