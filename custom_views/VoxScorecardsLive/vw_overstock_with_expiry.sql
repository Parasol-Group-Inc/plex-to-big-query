-- VoxScorecardsLive.vw_overstock_with_expiry (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-05-28 22:29 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH expiry_summary AS (
  SELECT
    part_number,
    MIN(date_of_expiration)                         AS earliest_exp_date,
    MIN(days_remaining)                             AS min_days_remaining,
    SUM(lot_value)                                  AS expiring_lot_value,
    SUM(inventory)                                  AS expiring_inventory,
    CASE
      WHEN MIN(days_remaining) <= 0   THEN 'Expired'
      WHEN MIN(days_remaining) <= 90  THEN '0-3 Months'
      WHEN MIN(days_remaining) <= 180 THEN '4-6 Months'
      WHEN MIN(days_remaining) <= 305 THEN '7-10 Months'
      ELSE '11-15 Months'
    END                                             AS earliest_exp_bucket,
    COUNTIF(days_remaining <= 90)                   AS lots_expiring_0_3mo,
    COUNTIF(days_remaining > 90 AND days_remaining <= 180)  AS lots_expiring_4_6mo,
    COUNTIF(days_remaining > 180 AND days_remaining <= 305) AS lots_expiring_7_10mo,
    COUNTIF(days_remaining > 305)                   AS lots_expiring_11_15mo
  FROM `voxdatalake.VoxScorecardsLive.vw_expiring_lots`
  WHERE days_remaining > 0
  GROUP BY part_number
)

SELECT
  ib.part_number,
  ib.display_name,
  ib.product_class,
  ib.item_stock_type,
  ib.on_hand,
  ib.average_monthly_usage,
  ib.months_on_hand,
  ib.inventory_value,
  ib.cost_ea,
  ib.cost_source,
  ib.is_overstock,
  es.earliest_exp_date,
  es.min_days_remaining,
  COALESCE(es.earliest_exp_bucket, 'No Expiry on Record') AS earliest_exp_bucket,
  es.expiring_lot_value,
  es.expiring_inventory,
  COALESCE(es.lots_expiring_0_3mo, 0)              AS lots_expiring_0_3mo,
  COALESCE(es.lots_expiring_4_6mo, 0)              AS lots_expiring_4_6mo,
  COALESCE(es.lots_expiring_7_10mo, 0)             AS lots_expiring_7_10mo,
  COALESCE(es.lots_expiring_11_15mo, 0)            AS lots_expiring_11_15mo,
  CASE WHEN es.part_number IS NOT NULL THEN TRUE ELSE FALSE END AS has_expiring_lots,
  CASE
    WHEN es.earliest_exp_date IS NOT NULL
    THEN DATE(TIMESTAMP_SUB(es.earliest_exp_date, INTERVAL 305 DAY))
    ELSE NULL
  END                                               AS earliest_sale_by_date

FROM `voxdatalake.VoxScorecardsLive.vw_inventory_base` ib
LEFT JOIN expiry_summary es ON ib.part_number = es.part_number
WHERE
  ib.months_on_hand > 12
  AND ib.inventory_value > 5000
ORDER BY ib.months_on_hand DESC
