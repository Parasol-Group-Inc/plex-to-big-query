-- VoxScorecardsLive.vw_sc_inventory_split (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-10 16:21 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH cust_supplied AS (
  SELECT DISTINCT SAFE_CAST(Part_Key AS INT64) AS part_key
  FROM `voxdatalake.PlexProd.raw_Part_v_Approved_Supplier`
  WHERE SAFE_CAST(Supplier_No AS INT64) = 1291153
),
s AS (
  SELECT part_key, inventory_value, part_key IN (SELECT part_key FROM cust_supplied WHERE part_key IS NOT NULL) AS is_customer
  FROM `voxdatalake.PlexProd.inventory_valuation_summary_report`
  WHERE is_current_snapshot AND is_primary_cost_model
)
SELECT
  SUM(inventory_value)                                       AS total_inventory_value,
  SUM(IF(is_customer, inventory_value, 0))                   AS customer_inventory_value,
  SUM(IF(is_customer, 0, inventory_value))                   AS vox_inventory_value,
  SAFE_DIVIDE(SUM(IF(is_customer, inventory_value, 0)), SUM(inventory_value)) AS customer_pct
FROM s
