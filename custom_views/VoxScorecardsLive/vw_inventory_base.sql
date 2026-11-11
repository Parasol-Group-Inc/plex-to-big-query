-- VoxScorecardsLive.vw_inventory_base (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-05-28 19:17 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  ns.name                                           AS part_number,
  ns.display_name,
  ns.item_stock_type,
  CASE
    WHEN STARTS_WITH(ns.name, '13') THEN 'Bulk'
    WHEN STARTS_WITH(ns.name, '14') THEN 'Bottled'
  END                                               AS product_class,
  ns.on_hand,
  ns.average_monthly_usage,
  ns.average_daily_usage,

  -- Months on hand (null-safe)
  CASE
    WHEN ns.average_monthly_usage > 0
    THEN ROUND(ns.on_hand / ns.average_monthly_usage, 1)
    ELSE NULL
  END                                               AS months_on_hand,

  -- Cost and value
  c.cost_ea,
  c.cost_source,
  CASE
    WHEN c.cost_ea IS NOT NULL AND ns.on_hand IS NOT NULL
    THEN ROUND(ns.on_hand * c.cost_ea, 2)
    ELSE NULL
  END                                               AS inventory_value,

  -- Overstock flag (>15 months)
  CASE
    WHEN ns.average_monthly_usage > 0
      AND (ns.on_hand / ns.average_monthly_usage) > 15
    THEN TRUE
    ELSE FALSE
  END                                               AS is_overstock

FROM `voxdatalake.VoxScorecardsLive.Overstock_NS` ns
LEFT JOIN `voxdatalake.VoxScorecardsLive.vw_cost_lookup` c
  ON ns.name = c.part
WHERE
  REGEXP_CONTAINS(ns.name, r'^1[34]\d{3}$')
