-- VoxScorecardsLive.vw_raw_materials_expiring_90 (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-18 15:42 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  dn.part_number,
  dn.name                                           AS product_name,
  dn.part_type,
  dn.inventory,
  dn.stocking_unit,
  dn.location,
  dn.warehouse,
  dn.shelf_life_remaining,
  dn.date_of_expiration,

  CASE
    WHEN CONTAINS_SUBSTR(dn.shelf_life_remaining, 'EXPIRED')
    THEN -1 * CAST(REGEXP_EXTRACT(dn.shelf_life_remaining, r'(\d+)') AS INT64)
    ELSE CAST(REGEXP_EXTRACT(dn.shelf_life_remaining, r'(\d+)') AS INT64)
  END                                               AS days_remaining,

  c.cost_ea,
  c.cost_source,
  CASE
    WHEN c.cost_ea IS NOT NULL AND dn.inventory IS NOT NULL
    THEN ROUND(dn.inventory * c.cost_ea, 2)
    ELSE NULL
  END                                               AS lot_value

FROM `voxdatalake.VoxScorecardsLive.DN_15_MO_Expiring` dn
LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_cost_lookup` c
  ON dn.part_number = c.part
WHERE
  REGEXP_CONTAINS(dn.part_number, r'^1[12]\d{3}$')
  AND (
    CONTAINS_SUBSTR(dn.shelf_life_remaining, 'EXPIRED')
    OR CAST(REGEXP_EXTRACT(dn.shelf_life_remaining, r'(\d+)') AS INT64) <= 90
  )
ORDER BY
  dn.date_of_expiration ASC
