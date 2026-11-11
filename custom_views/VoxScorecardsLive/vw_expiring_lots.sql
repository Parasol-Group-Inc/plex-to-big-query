-- VoxScorecardsLive.vw_expiring_lots (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-01 14:21 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  dn.part_number,
  dn.name                                           AS product_name,
  dn.part_type,
  CASE
    WHEN STARTS_WITH(dn.part_number, '13') THEN 'Bulk'
    WHEN STARTS_WITH(dn.part_number, '14') THEN 'Bottled'
  END                                               AS product_class,
  dn.inventory,
  dn.stocking_unit,
  dn.shelf_life_remaining,
  dn.date_of_expiration,
  dn.location,
  dn.warehouse,
  dn.lpn,
  dn.vendor_lot_number,
  dn.display_identifier,

  CASE
    WHEN CONTAINS_SUBSTR(dn.shelf_life_remaining, 'EXPIRED')
    THEN -1 * CAST(REGEXP_EXTRACT(dn.shelf_life_remaining, r'(\d+)') AS INT64)
    ELSE CAST(REGEXP_EXTRACT(dn.shelf_life_remaining, r'(\d+)') AS INT64)
  END                                               AS days_remaining,

  CASE
    WHEN CONTAINS_SUBSTR(dn.shelf_life_remaining, 'EXPIRED')
      THEN 'Expired'
    WHEN CAST(REGEXP_EXTRACT(dn.shelf_life_remaining, r'(\d+)') AS INT64) <= 90
      THEN '0-3 Months'
    WHEN CAST(REGEXP_EXTRACT(dn.shelf_life_remaining, r'(\d+)') AS INT64) <= 180
      THEN '4-6 Months'
    WHEN CAST(REGEXP_EXTRACT(dn.shelf_life_remaining, r'(\d+)') AS INT64) <= 305
      THEN '7-10 Months'
    ELSE '11-15 Months'
  END                                               AS expiration_bucket,

  DATE(TIMESTAMP_SUB(dn.date_of_expiration, INTERVAL 305 DAY))
                                                    AS sale_by_date,

  CASE
    WHEN DATE(TIMESTAMP_SUB(dn.date_of_expiration, INTERVAL 305 DAY))
         <= DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
    THEN TRUE
    ELSE FALSE
  END                                               AS sale_by_urgent,

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
  REGEXP_CONTAINS(dn.part_number, r'^1[34]\d{3}$')
