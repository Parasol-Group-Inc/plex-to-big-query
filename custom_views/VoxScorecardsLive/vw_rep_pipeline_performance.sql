-- VoxScorecardsLive.vw_rep_pipeline_performance (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-10 18:19 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH opportunities AS (
  SELECT
    person AS sales_rep,
    SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) AS opp_total,
    COUNT(*) AS opp_count
  FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
  WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled')
  AND person IS NOT NULL
  GROUP BY 1
),

won_lost AS (
  SELECT
    person AS sales_rep,
    SUM(CASE WHEN status = 'Won' THEN SAFE_CAST(numeric_mm1ry7gm AS NUMERIC) ELSE 0 END) AS won_total,
    SUM(CASE WHEN status = 'Lost' THEN SAFE_CAST(numeric_mm1ry7gm AS NUMERIC) ELSE 0 END) AS lost_total,
    COUNT(CASE WHEN status = 'Won' THEN 1 END) AS won_count,
    COUNT(CASE WHEN status = 'Lost' THEN 1 END) AS lost_count
  FROM `voxdatalake.VoxScorecardsLive.stalled_won_lost_18409621334`
  WHERE status IN ('Won', 'Lost')
  AND person IS NOT NULL
  GROUP BY 1
)

SELECT
  COALESCE(o.sales_rep, w.sales_rep) AS sales_rep,
  COALESCE(o.opp_total, 0)           AS opp_total,
  COALESCE(o.opp_count, 0)           AS opp_count,
  COALESCE(w.won_total, 0)           AS won_total,
  COALESCE(w.lost_total, 0)          AS lost_total,
  COALESCE(w.won_count, 0)           AS won_count,
  COALESCE(w.lost_count, 0)          AS lost_count,
  ROUND(w.won_total / NULLIF(w.won_total + w.lost_total, 0), 4)                       AS win_rate,
  ROUND(w.lost_total / NULLIF(w.won_total + w.lost_total, 0), 4)                      AS loss_rate,
  ROUND(w.won_total / NULLIF(w.won_total + w.lost_total + o.opp_total, 0), 4)         AS conversion_rate,
  ROUND(w.won_count / NULLIF(w.won_count + w.lost_count, 0), 4)                       AS win_rate_by_count,
  ROUND(w.lost_count / NULLIF(w.won_count + w.lost_count, 0), 4)                      AS loss_rate_by_count,
  ROUND(w.won_count / NULLIF(w.won_count + w.lost_count + o.opp_count, 0), 4)         AS conversion_rate_by_count
FROM opportunities o
FULL OUTER JOIN won_lost w ON o.sales_rep = w.sales_rep
ORDER BY opp_total DESC
