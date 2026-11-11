-- VoxScorecardsLive.vw_top_opp_by_rep (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-09 18:46 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  person AS sales_rep,
  item_name,
  status,
  SAFE_CAST(numeric_mm1ry7gm AS NUMERIC) AS opp_value
FROM (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY person
      ORDER BY SAFE_CAST(numeric_mm1ry7gm AS NUMERIC) DESC
    ) AS rank
  FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
  WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled')
  AND person IS NOT NULL
)
WHERE rank = 1
ORDER BY opp_value DESC
