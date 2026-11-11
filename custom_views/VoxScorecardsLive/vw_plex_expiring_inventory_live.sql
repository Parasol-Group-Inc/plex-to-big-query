-- VoxScorecardsLive.vw_plex_expiring_inventory_live (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 16:48 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH use_by AS (
  SELECT SAFE_CAST(sl.Lot_Key AS INT64) AS lot_key,
         MIN(DATE(SAFE_CAST(sl.Lot_Shelf_Life AS TIMESTAMP))) AS use_by_date
  FROM `voxdatalake.PlexProd.raw_Part_v_Lot_Shelf_Life` sl
  JOIN `voxdatalake.PlexProd.raw_Part_v_Shelf_Life_Type` t
    ON SAFE_CAST(t.Shelf_Life_Type_Key AS INT64) = SAFE_CAST(sl.Shelf_Life_Type_Key AS INT64)
  WHERE SAFE_CAST(t.Use_By AS INT64) = 1
  GROUP BY lot_key
),
base AS (
  SELECT l.part_key, l.part_no, l.part_name, l.part_product_type, l.best_by_date,
         l.days_to_best_by, l.is_expired_status, l.quantity, l.inventory_value,
         u.use_by_date,
         (u.use_by_date < CURRENT_DATE('America/Denver')
           AND NOT COALESCE(l.days_to_best_by < 0, FALSE)) AS is_past_use_by_only
  FROM `voxdatalake.PlexProd.inventory_lot_detail_report` l
  LEFT JOIN use_by u ON u.lot_key = l.lot_key
  WHERE (l.is_available OR l.is_expired_status)
    AND l.best_by_date IS NOT NULL AND NOT l.best_by_is_placeholder
),
lots AS (
  SELECT *,
    CASE WHEN days_to_best_by < 0       THEN 'Expired'
         WHEN is_past_use_by_only       THEN 'Past Use By'
         WHEN is_expired_status         THEN 'Expired'
         WHEN days_to_best_by <= 90     THEN '0-3 mo'
         WHEN days_to_best_by <= 180    THEN '4-6 mo'
         WHEN days_to_best_by <= 270    THEN '7-9 mo'
         ELSE '10-12 mo' END AS exp_bucket,
    CASE WHEN days_to_best_by < 0       THEN 1
         WHEN is_past_use_by_only       THEN 2
         WHEN is_expired_status         THEN 1
         WHEN days_to_best_by <= 90     THEN 3
         WHEN days_to_best_by <= 180    THEN 4
         WHEN days_to_best_by <= 270    THEN 5
         ELSE 6 END AS exp_bucket_sort
  FROM base
  WHERE days_to_best_by <= 365 OR is_past_use_by_only OR is_expired_status
),
by_part AS (
  SELECT part_key, exp_bucket, exp_bucket_sort,
         ANY_VALUE(part_no) AS part_no, ANY_VALUE(part_name) AS part_name,
         ANY_VALUE(part_product_type) AS product_type,
         MIN(best_by_date) AS earliest_best_by, COUNT(*) AS lot_count,
         SUM(quantity) AS expiring_qty, SUM(inventory_value) AS expiring_value,
         SAFE_DIVIDE(SUM(inventory_value), SUM(quantity)) AS unit_cost,
         MIN(use_by_date) AS earliest_use_by
  FROM lots
  GROUP BY part_key, exp_bucket, exp_bucket_sort
)
SELECT
  b.part_no, b.part_name, b.product_type,
  b.exp_bucket, b.exp_bucket_sort,
  b.earliest_best_by, b.lot_count,
  b.expiring_qty, b.expiring_value,
  COALESCE(d.net_demand_qty, 0) AS open_demand_qty,
  GREATEST(b.expiring_qty - COALESCE(d.net_demand_qty, 0), 0) AS uncovered_qty,
  GREATEST(b.expiring_qty - COALESCE(d.net_demand_qty, 0), 0) * COALESCE(b.unit_cost, 0) AS uncovered_value,
  b.part_key,
  b.earliest_use_by
FROM by_part b
LEFT JOIN `voxdatalake.PlexProd.inventory_net_demand_report` d USING (part_key)
