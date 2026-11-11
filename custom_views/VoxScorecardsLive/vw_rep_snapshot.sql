-- VoxScorecardsLive.vw_rep_snapshot (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 15:49 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH pipeline_opps AS (
  SELECT person AS sales_rep, SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) AS pipeline_total
  FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
  WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled') AND person IS NOT NULL
  GROUP BY 1
),
pipeline_forecast AS (
  SELECT person AS sales_rep, SUM(SAFE_CAST(numeric_mm3ry8p5_adjusted AS NUMERIC)) AS pipeline_total
  FROM `voxdatalake.VoxScorecardsLive.vw_forecast_decrementing`
  WHERE person IS NOT NULL
  GROUP BY 1
),
pipeline_plex AS (  -- Plex quotes + Pending Sales Approval / Deposit Review
  SELECT sales_rep, CAST(SUM(pipeline_value) AS NUMERIC) AS pipeline_total
  FROM `voxdatalake.PlexProd.pipeline_plex_value_report`
  WHERE sales_rep IS NOT NULL
  GROUP BY 1
),
pipeline_combined AS (
  SELECT sales_rep, pipeline_total FROM pipeline_opps
  UNION ALL SELECT sales_rep, pipeline_total FROM pipeline_forecast
  UNION ALL SELECT sales_rep, pipeline_total FROM pipeline_plex
),
pipeline_by_rep AS (
  SELECT sales_rep, SUM(pipeline_total) AS total_pipeline FROM pipeline_combined GROUP BY 1
),
top_customers AS (
  SELECT sales_rep, name AS customer, SUM(amount) AS customer_total,
    ROW_NUMBER() OVER (PARTITION BY sales_rep ORDER BY SUM(amount) DESC) AS rank
  FROM `voxdatalake.VoxScorecardsLive.vw_sales`
  WHERE sales_rep IS NOT NULL AND sales_rep != ''
  GROUP BY 1, 2
),
top_opps AS (
  SELECT person AS sales_rep, item_name AS customer,
    SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) AS opp_total,
    ROW_NUMBER() OVER (PARTITION BY person ORDER BY SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) DESC) AS rank
  FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
  WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled') AND person IS NOT NULL
  GROUP BY 1, 2
)
SELECT
  p.sales_rep, p.total_pipeline,
  tc.customer AS top_customer_1, tc.customer_total AS top_customer_1_total,
  tc2.customer AS top_customer_2, tc2.customer_total AS top_customer_2_total,
  tc3.customer AS top_customer_3, tc3.customer_total AS top_customer_3_total,
  to1.customer AS top_opp_1, to1.opp_total AS top_opp_1_total,
  to2.customer AS top_opp_2, to2.opp_total AS top_opp_2_total,
  to3.customer AS top_opp_3, to3.opp_total AS top_opp_3_total
FROM pipeline_by_rep p
LEFT JOIN top_customers tc  ON p.sales_rep = tc.sales_rep  AND tc.rank = 1
LEFT JOIN top_customers tc2 ON p.sales_rep = tc2.sales_rep AND tc2.rank = 2
LEFT JOIN top_customers tc3 ON p.sales_rep = tc3.sales_rep AND tc3.rank = 3
LEFT JOIN top_opps to1 ON p.sales_rep = to1.sales_rep AND to1.rank = 1
LEFT JOIN top_opps to2 ON p.sales_rep = to2.sales_rep AND to2.rank = 2
LEFT JOIN top_opps to3 ON p.sales_rep = to3.sales_rep AND to3.rank = 3
ORDER BY p.total_pipeline DESC
