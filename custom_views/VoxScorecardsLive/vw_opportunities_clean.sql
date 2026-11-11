-- VoxScorecardsLive.vw_opportunities_clean (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-09 18:43 UTC by jennilyn.tockstein@parasolgroupinc.com

SELECT
  item_name,
  person,
  status,
  SAFE_CAST(numeric_mm1ry7gm AS NUMERIC) AS amount,
  SAFE.PARSE_DATE('%Y-%m-%d', date_mm396vaj) AS status_date,
  text_mm35yakj AS notes
FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled')
