-- VoxScorecardsLive.vw_sc_ytd_cards (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-10-30 17:50 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  EXTRACT(YEAR FROM month_start) AS year,
  MAX(month_start)               AS through_month,
  SUM(sales)          AS sales_ytd,
  SUM(revenue)        AS revenue_ytd,
  SUM(encapsulation)  AS encap_ytd,
  SUM(packaging)      AS packaging_ytd,
  SUM(labeling)       AS labeling_ytd,
  AVG(oos_count)      AS oos_avg,
  AVG(inventory_value) AS inventory_avg
FROM `voxdatalake.VoxScorecardsLive.vw_sc_monthly_wide`
GROUP BY year
