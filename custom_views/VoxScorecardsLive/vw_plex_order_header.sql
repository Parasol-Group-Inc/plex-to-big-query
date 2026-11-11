-- VoxScorecardsLive.vw_plex_order_header (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-11 17:09 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH users AS (
  SELECT SAFE_CAST(Plexus_User_No AS INT64) AS user_no, CONCAT(First_Name, ' ', Last_Name) AS full_name
  FROM `voxdatalake.PlexProd.raw_Plexus_Control_v_Plexus_User`
),
rep1 AS (
  SELECT SAFE_CAST(PO_Key AS INT64) AS po_key, SAFE_CAST(Plexus_User_No AS INT64) AS user_no
  FROM `voxdatalake.PlexProd.raw_Sales_v_Order_Salesperson`
  WHERE TRUE
  QUALIFY ROW_NUMBER() OVER (PARTITION BY SAFE_CAST(PO_Key AS INT64)
                             ORDER BY SAFE_CAST(Sort_Order AS INT64), SAFE_CAST(Plexus_User_No AS INT64)) = 1
),
rel AS (
  SELECT
    SAFE_CAST(pol.PO_Key AS INT64) AS po_key,
    MIN(IF(SAFE_CAST(r.Quantity AS FLOAT64) > COALESCE(SAFE_CAST(r.Quantity_Shipped AS FLOAT64), 0)
           AND COALESCE(SAFE_CAST(rs.Cancelled_Status AS INT64), 0) = 0
           AND COALESCE(SAFE_CAST(rs.Shipped_Status AS INT64), 0) = 0
           AND COALESCE(SAFE_CAST(rs.Closed_Status AS INT64), 0) = 0
           AND UPPER(IFNULL(rs.Release_Status, '')) NOT IN ('CANCELED', 'CANCELLED', 'CLOSED', 'SHIPPED'),
      COALESCE(
        DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(r.Due_Date AS STRING) AS INT64), 0), 1000))),
        NULLIF(SAFE_CAST(CAST(r.Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
        NULLIF(DATE(SAFE_CAST(CAST(r.Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')),
      NULL)) AS next_due_date
  FROM `voxdatalake.PlexProd.raw_Sales_v_Release` r
  JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Line` pol ON SAFE_CAST(r.PO_Line_Key AS INT64) = SAFE_CAST(pol.PO_Line_Key AS INT64)
  LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_Release_Status` rs ON SAFE_CAST(rs.Release_Status_Key AS INT64) = SAFE_CAST(r.Release_Status_Key AS INT64)
  GROUP BY 1
)
SELECT
  po.Order_No AS order_no,
  po.PO_No    AS document_so,
  cust.Name   AS customer_name,
  COALESCE(ui.full_name, ua.full_name, u1.full_name) AS sales_rep,
  sts.PO_Status AS status,
  rel.next_due_date
FROM `voxdatalake.PlexProd.raw_Sales_v_PO` po
LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_PO_Status` sts ON SAFE_CAST(po.PO_Status_Key AS INT64) = SAFE_CAST(sts.PO_Status_Key AS INT64)
LEFT JOIN `voxdatalake.PlexProd.raw_Common_v_Customer` cust ON SAFE_CAST(po.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)
LEFT JOIN users ui ON SAFE_CAST(po.Inside_Sales AS INT64) = ui.user_no
LEFT JOIN users ua ON SAFE_CAST(cust.Assigned_To AS INT64) = ua.user_no
LEFT JOIN rep1 r1 ON r1.po_key = SAFE_CAST(po.PO_Key AS INT64)
LEFT JOIN users u1 ON r1.user_no = u1.user_no
LEFT JOIN rel ON rel.po_key = SAFE_CAST(po.PO_Key AS INT64)
