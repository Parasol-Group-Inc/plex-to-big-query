-- VoxScorecardsLive.vw_top_overstock (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-07-17 23:17 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH inventory AS (
  SELECT
    display_name,
    on_hand,
    on_hand * average_cost AS inventory_value
  FROM `voxdatalake.VoxScorecardsLive.Overstock_NS`
  WHERE display_name IS NOT NULL  -- excludes the 'Total' summary row baked into the table
),

top_value AS (
  SELECT
    'Top Value' AS category,
    display_name AS item,
    inventory_value AS metric_value,
    ROW_NUMBER() OVER (ORDER BY inventory_value DESC) AS rank
  FROM inventory
),

top_qty AS (
  SELECT
    'Top Quantity' AS category,
    display_name AS item,
    on_hand AS metric_value,
    ROW_NUMBER() OVER (ORDER BY on_hand DESC) AS rank
  FROM inventory
)

SELECT category, rank, item, metric_value FROM top_value WHERE rank <= 3
UNION ALL
SELECT category, rank, item, metric_value FROM top_qty WHERE rank <= 3
ORDER BY category, rank
