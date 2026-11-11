-- VoxScorecardsLive.vw_high_risk (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-05-28 19:47 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  el.part_number,
  el.product_name,
  el.product_class,
  el.part_type,
  el.inventory                                      AS lot_inventory,
  el.stocking_unit,
  el.location,
  el.warehouse,
  el.lpn,
  el.vendor_lot_number,
  el.date_of_expiration,
  el.shelf_life_remaining,
  el.days_remaining,
  el.expiration_bucket,
  el.sale_by_date,
  el.cost_ea,

  -- Sale-by urgency tiers for scorecards
  CASE
    WHEN el.sale_by_date <= CURRENT_DATE()
      THEN 'Past Due'
    WHEN el.sale_by_date <= DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
      THEN 'Within 90 Days'
    WHEN el.sale_by_date <= DATE_ADD(CURRENT_DATE(), INTERVAL 180 DAY)
      THEN 'Within 6 Months'
    ELSE 'Beyond 6 Months'
  END                                               AS sale_by_tier,

  -- Combined urgent flag (past due OR within 90 days)
  CASE
    WHEN el.sale_by_date <= DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
      THEN TRUE
    ELSE FALSE
  END                                               AS sale_by_urgent,

  el.lot_value,

  -- Part-level context
  ib.on_hand                                        AS total_on_hand,
  ib.average_monthly_usage,
  ib.months_on_hand,
  ib.inventory_value                                AS total_inventory_value

FROM `voxdatalake.VoxScorecardsLive.vw_expiring_lots` el
INNER JOIN `voxdatalake.VoxScorecardsLive.vw_inventory_base` ib
  ON el.part_number = ib.part_number
WHERE
  -- High risk definition: >16 months on hand AND expiring within 15 months
  ib.months_on_hand > 16
  AND el.days_remaining <= 456   -- 15 months in days
  AND el.days_remaining > 0      -- exclude already expired
ORDER BY
  el.sale_by_date ASC,
  el.date_of_expiration ASC
