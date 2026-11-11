-- VoxScorecardsLive.vw_sales_line_status (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 17:09 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH price AS (
  SELECT PO_Line_Key,
    ARRAY_AGG(SAFE_CAST(Price AS FLOAT64) ORDER BY SAFE_CAST(Breakpoint_Quantity AS FLOAT64) LIMIT 1)[OFFSET(0)] AS price_ea
  FROM `voxdatalake.PlexProd.raw_Sales_v_Price`
  WHERE COALESCE(SAFE_CAST(Active AS INT64), 1) = 1
  GROUP BY 1
),
rel AS (
  SELECT po.Order_No AS order_no, p.Part_No AS part_no, rs.Release_Status AS release_status,
    COALESCE(SAFE_CAST(rs.Cancelled_Status AS INT64), 0) = 1 OR UPPER(rs.Release_Status) IN ('CANCELED', 'CANCELLED') AS is_canceled,
    COALESCE(SAFE_CAST(rs.Shipped_Status AS INT64), 0) = 1 OR COALESCE(SAFE_CAST(rs.Closed_Status AS INT64), 0) = 1
      OR UPPER(rs.Release_Status) IN ('CLOSED', 'SHIPPED') AS is_closed,
    SAFE_CAST(r.Quantity AS FLOAT64) AS qty, pr.price_ea
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release` r
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Line` pl ON r.PO_Line_Key = pl.PO_Line_Key
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO` po ON po.PO_Key = pl.PO_Key
  LEFT JOIN `voxdatalake.PlexProd.raw_Part_v_Part` p ON p.Part_Key = SAFE_CAST(pl.Part_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_Release_Status` rs ON SAFE_CAST(rs.Release_Status_Key AS INT64) = SAFE_CAST(r.Release_Status_Key AS INT64)
  LEFT JOIN price pr ON pr.PO_Line_Key = pl.PO_Line_Key
)
SELECT order_no, part_no,
  LOGICAL_AND(is_canceled OR is_closed) AS all_done,
  LOGICAL_AND(is_canceled) AS all_canceled,
  SUM(IF(is_canceled, qty * IFNULL(price_ea, 0), 0)) AS canceled_value,
  STRING_AGG(DISTINCT release_status, ', ') AS release_statuses
FROM rel GROUP BY 1, 2
