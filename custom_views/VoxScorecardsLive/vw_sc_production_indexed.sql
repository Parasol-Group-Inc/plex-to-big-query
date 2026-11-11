-- VoxScorecardsLive.vw_sc_production_indexed (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-10-30 17:50 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  month_start, encapsulation, packaging, labeling,
  ROUND(100 * SAFE_DIVIDE(encapsulation, FIRST_VALUE(encapsulation) OVER y), 2) AS encapsulation_idx,
  ROUND(100 * SAFE_DIVIDE(packaging,     FIRST_VALUE(packaging)     OVER y), 2) AS packaging_idx,
  ROUND(100 * SAFE_DIVIDE(labeling,      FIRST_VALUE(labeling)      OVER y), 2) AS labeling_idx
FROM `voxdatalake.VoxScorecardsLive.vw_sc_monthly_wide`
WINDOW y AS (PARTITION BY EXTRACT(YEAR FROM month_start) ORDER BY month_start)
