-- VoxScorecardsLive.vw_sc_revenue_adjustments (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-09 16:01 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH dist AS (
  SELECT SAFE_CAST(d.Shipper_Line_Key AS INT64) AS shipper_line_key, d.Account_No AS account_no, d.Description AS description,
         SAFE_CAST(d.Invoice_Link AS INT64) AS invoice_link,
         SAFE_CAST(d.Credit AS FLOAT64) - SAFE_CAST(d.Debit AS FLOAT64) AS amount
  FROM `voxdatalake.PlexProd.raw_Accounting_v_AR_Invoice_Dist` d
  WHERE STARTS_WITH(d.Account_No, '4') AND d.Account_No != '40200-01-01'
)
SELECT
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')) AS ship_date,
  s.Shipper_No AS shipper_no, a.Invoice_No AS invoice_no, dist.account_no, dist.description, dist.amount
FROM dist
LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_Shipper_Line` sl ON SAFE_CAST(sl.Shipper_Line_Key AS INT64) = dist.shipper_line_key
LEFT JOIN `voxdatalake.PlexProd.raw_Sales_v_Shipper` s ON SAFE_CAST(s.Shipper_Key AS INT64) = SAFE_CAST(sl.Shipper_Key AS INT64)
LEFT JOIN `voxdatalake.PlexProd.raw_Accounting_v_AR_Invoice` a ON SAFE_CAST(a.Invoice_Link AS INT64) = dist.invoice_link
