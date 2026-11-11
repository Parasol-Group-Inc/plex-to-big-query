-- VoxScorecardsLive.vw_avg_days_to_close (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-10 18:27 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH base AS (
  SELECT
    person,
    COALESCE(
      NULLIF(date_mm3zms4q, ''),
      NULLIF(date_mm1qdtds, '')
    ) AS date_won,
    NULLIF(date_mm1zhv48, '') AS date_entered
  FROM `voxdatalake.VoxScorecardsLive.stalled_won_lost_18409621334`
  WHERE status = 'Won'
  AND NULLIF(date_mm1zhv48, '') IS NOT NULL
),

calculated AS (
  SELECT
    person,
    DATE_DIFF(
      PARSE_DATE('%Y-%m-%d', date_won),
      PARSE_DATE('%Y-%m-%d', date_entered),
      DAY
    ) AS days_to_close
  FROM base
  WHERE date_won IS NOT NULL
)

SELECT
  'All Reps' AS sales_rep,
  ROUND(AVG(days_to_close), 1) AS avg_days_to_close
FROM calculated

UNION ALL

SELECT
  person AS sales_rep,
  ROUND(AVG(days_to_close), 1) AS avg_days_to_close
FROM calculated
GROUP BY person
ORDER BY avg_days_to_close
