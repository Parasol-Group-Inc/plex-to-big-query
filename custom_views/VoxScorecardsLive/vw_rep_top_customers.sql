-- VoxScorecardsLive.vw_rep_top_customers (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 16:04 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT sales_rep, name AS customer, SUM(amount) AS customer_total, 'YTD Customer' AS category,
  ROW_NUMBER() OVER (PARTITION BY sales_rep ORDER BY SUM(amount) DESC) AS rank
FROM `voxdatalake.VoxScorecardsLive.vw_sales`
WHERE sales_rep IS NOT NULL AND sales_rep != ''
GROUP BY 1, 2
UNION ALL
-- Added 2026-11-04: rolling last 30 days (today included), for the Team Snapshot cards
SELECT sales_rep, name AS customer, SUM(amount) AS customer_total, 'Last 30 Days Customer' AS category,
  ROW_NUMBER() OVER (PARTITION BY sales_rep ORDER BY SUM(amount) DESC) AS rank
FROM `voxdatalake.VoxScorecardsLive.vw_sales`
WHERE sales_rep IS NOT NULL AND sales_rep != ''
  AND date_approved >= DATE_SUB(CURRENT_DATE('America/Denver'), INTERVAL 29 DAY)
GROUP BY 1, 2
UNION ALL
SELECT person AS sales_rep, item_name AS customer, SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) AS customer_total,
  'Active Opportunity' AS category,
  ROW_NUMBER() OVER (PARTITION BY person ORDER BY SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) DESC) AS rank
FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled') AND person IS NOT NULL
GROUP BY 1, 2
