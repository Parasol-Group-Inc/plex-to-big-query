-- VoxScorecardsLive.vw_overstock_by_bucket (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-05-28 22:45 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  el.part_number,
  el.product_name,
  el.product_class,
  el.expiration_bucket,
  el.days_remaining,
  el.date_of_expiration,

  -- Quantity in this lot (for stacking)
  SUM(el.inventory)                                 AS bucket_inventory,
  SUM(el.lot_value)                                 AS bucket_value,
  COUNT(*)                                          AS lot_count,

  -- Carry months_on_hand from inventory base for sorting
  ib.months_on_hand,
  ib.inventory_value,
  ib.on_hand

FROM `voxdatalake.VoxScorecardsLive.vw_expiring_lots` el
INNER JOIN `voxdatalake.VoxScorecardsLive.vw_inventory_base` ib
  ON el.part_number = ib.part_number
WHERE
  ib.months_on_hand > 12
  AND ib.inventory_value > 5000
  AND el.days_remaining > 0
GROUP BY
  el.part_number,
  el.product_name,
  el.product_class,
  el.expiration_bucket,
  el.days_remaining,
  el.date_of_expiration,
  ib.months_on_hand,
  ib.inventory_value,
  ib.on_hand
ORDER BY
  ib.months_on_hand DESC
