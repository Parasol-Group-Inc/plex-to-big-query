-- VoxScorecardsLive.vw_shoutouts (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-10 18:19 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH biggest_hunter AS (
  SELECT
    person,
    COUNT(*) AS opportunity_count
  FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
  WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled')
  AND person IS NOT NULL
  GROUP BY person
  ORDER BY opportunity_count DESC
  LIMIT 1
),

biggest_win AS (
  SELECT
    person,
    SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) AS won_total
  FROM `voxdatalake.VoxScorecardsLive.stalled_won_lost_18409621334`
  WHERE status = 'Won'
  GROUP BY person
  ORDER BY won_total DESC
  LIMIT 1
),

biggest_loser AS (
  SELECT
    person,
    COUNT(*) AS lost_count
  FROM `voxdatalake.VoxScorecardsLive.stalled_won_lost_18409621334`
  WHERE status = 'Lost'
  GROUP BY person
  ORDER BY lost_count DESC
  LIMIT 1
)

SELECT
  'Biggest Hunter' AS shoutout,
  person,
  CAST(opportunity_count AS NUMERIC) AS metric_number,
  NULL AS metric_currency,
  'opportunities' AS metric_label
FROM biggest_hunter

UNION ALL

SELECT
  'Biggest Win',
  person,
  NULL,
  won_total,
  'total won'
FROM biggest_win

UNION ALL

SELECT
  'Biggest Loser',
  person,
  CAST(lost_count AS NUMERIC),
  NULL,
  'deals lost'
FROM biggest_loser
