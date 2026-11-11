-- VoxScorecardsLive.vw_sc_inventory_split_by_partno (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-10 16:21 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH vox_overrides AS (SELECT part_no FROM UNNEST(['33248-00QSMNU-0']) AS part_no),
s AS (
  SELECT part_number, inventory_value, REGEXP_EXTRACT(part_number, r'^\d{5}-[0-9A-Z]{2}([0-9A-Z]{5})') AS cust_code
  FROM `voxdatalake.PlexProd.inventory_valuation_summary_report` WHERE is_current_snapshot AND is_primary_cost_model
),
flagged AS (
  SELECT *, part_number NOT IN (SELECT part_no FROM vox_overrides)
    AND (((STARTS_WITH(part_number, '7') OR STARTS_WITH(part_number, '9')) AND NOT REGEXP_CONTAINS(part_number, r'^9\d{4}-SBVOXNU'))
      OR (cust_code IS NOT NULL AND cust_code != 'VOXNU')) AS is_customer
  FROM s
)
SELECT SUM(inventory_value) AS total_inventory_value, SUM(IF(is_customer, inventory_value, 0)) AS customer_inventory_value,
  SUM(IF(is_customer, 0, inventory_value)) AS vox_inventory_value, SAFE_DIVIDE(SUM(IF(is_customer, inventory_value, 0)), SUM(inventory_value)) AS customer_pct
FROM flagged
