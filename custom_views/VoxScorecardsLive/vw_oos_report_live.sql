-- VoxScorecardsLive.vw_oos_report_live (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-16 21:42 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH
-- Manual stock list: newest row per part wins, tombstones remove it.
manual AS (
  SELECT part_no, is_stock, note
  FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY part_no ORDER BY updated_at DESC) AS rn
    FROM `voxdatalake.PlexProd.stock_products_manual`
  )
  WHERE rn = 1 AND NOT IFNULL(is_deleted, FALSE)
),

msl AS (
  SELECT
    m.*,
    (m.part_no LIKE '3%'
      AND COALESCE(m.plex_reorder_point, 0) > 0
      AND COALESCE(m.product_type, '') NOT LIKE 'Custom%')        AS is_stock_auto,
    mn.is_stock                                                   AS is_stock_manual,
    mn.note                                                       AS manual_note
  FROM `voxdatalake.VoxScorecardsLive.vw_approaching_msl_with_held_live` m
  LEFT JOIN manual mn USING (part_no)
),

-- Customers: open sales order lines on finished goods (part # starts with 9)
-- whose next 4 digits match this part's product code (digits 2-5).
open_fg_lines AS (
  SELECT
    SUBSTR(p.Part_No, 2, 4)                                       AS product_code,
    po.Customer_No                                                AS customer_no,
    GREATEST(SAFE_CAST(r.Quantity AS FLOAT64)
             - COALESCE(SAFE_CAST(r.Quantity_Shipped AS FLOAT64), 0), 0) AS open_qty
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release` r
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Line` l
    ON SAFE_CAST(r.PO_Line_Key AS INT64) = SAFE_CAST(l.PO_Line_Key AS INT64)
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO` po
    ON SAFE_CAST(l.PO_Key AS INT64) = SAFE_CAST(po.PO_Key AS INT64)
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Status` ps
    ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(ps.PO_Status_Key AS INT64)
  JOIN `voxdatalake.PlexProd.raw_Part_v_Part` p
    ON SAFE_CAST(p.Part_Key AS INT64) = SAFE_CAST(l.Part_Key AS INT64)
  WHERE SAFE_CAST(ps.Include_In_MRP AS INT64) = 1
    AND p.Part_No LIKE '9%'
),
customers AS (
  SELECT product_code,
         COUNT(DISTINCT customer_no) AS customer_count,
         SUM(open_qty)               AS fg_open_order_qty
  FROM open_fg_lines
  WHERE open_qty > 0
  GROUP BY product_code
)

SELECT
  m.part_no,
  m.description,
  m.product_type,
  m.part_type,
  m.unit,
  IF(m.is_stock_manual IS NOT NULL, 'Manual', 'Auto')             AS stock_source,
  m.manual_note,
  m.reorder_point                                                 AS msl,
  m.avg_daily_usage,
  m.usage_source,
  m.on_hand_qty,
  m.demand_qty,
  m.quantity_available,
  COALESCE(c.customer_count, 0)                                   AS customer_count,
  COALESCE(c.fg_open_order_qty, 0)                                AS fg_open_order_qty,
  m.open_job_qty                                                  AS job_qty,
  m.on_order_qty,
  m.in_mfg_or_ordered,
  m.held_qty,
  m.lot_hold_qty,
  m.quarantine_qty,
  m.expired_qty,
  m.past_use_by_qty,
  m.days_on_hand,
  m.data_flag,
  SUBSTR(m.part_no, 2, 4)                                         AS product_code
FROM msl m
LEFT JOIN customers c
  ON c.product_code = SUBSTR(m.part_no, 2, 4)
WHERE COALESCE(m.is_stock_manual, m.is_stock_auto)
  AND m.avg_daily_usage > 0
  AND m.reorder_point > 0
  AND m.quantity_available < 0
