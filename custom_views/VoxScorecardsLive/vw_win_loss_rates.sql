-- VoxScorecardsLive.vw_win_loss_rates (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-10 18:19 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH won_lost AS (
  SELECT
    SUM(CASE WHEN status = 'Won' THEN SAFE_CAST(numeric_mm1ry7gm AS NUMERIC) ELSE 0 END) AS won_total,
    SUM(CASE WHEN status = 'Lost' THEN SAFE_CAST(numeric_mm1ry7gm AS NUMERIC) ELSE 0 END) AS lost_total,
    COUNT(CASE WHEN status = 'Won' THEN 1 END) AS won_count,
    COUNT(CASE WHEN status = 'Lost' THEN 1 END) AS lost_count
  FROM `voxdatalake.VoxScorecardsLive.stalled_won_lost_18409621334`
  WHERE status IN ('Won', 'Lost')
),

active AS (
  SELECT
    SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) AS active_total,
    COUNT(*) AS active_count
  FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
  WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled')
)

SELECT
  'Dollar' AS metric_type,
  won_total,
  lost_total,
  active_total,
  NULL AS won_count,
  NULL AS lost_count,
  NULL AS active_count,
  ROUND(won_total / NULLIF(won_total + lost_total, 0), 4)                      AS win_rate,
  ROUND(lost_total / NULLIF(won_total + lost_total, 0), 4)                     AS loss_rate,
  ROUND(won_total / NULLIF(won_total + lost_total + active_total, 0), 4)       AS conversion_rate
FROM won_lost, active

UNION ALL

SELECT
  'Count' AS metric_type,
  NULL,
  NULL,
  NULL,
  won_count,
  lost_count,
  active_count,
  ROUND(won_count / NULLIF(won_count + lost_count, 0), 4)                      AS win_rate,
  ROUND(lost_count / NULLIF(won_count + lost_count, 0), 4)                     AS loss_rate,
  ROUND(won_count / NULLIF(won_count + lost_count + active_count, 0), 4)       AS conversion_rate
FROM won_lost, active
