-- VoxScorecardsLive.vw_sc_safe_days (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-05 19:09 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH live AS (
  SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (
      PARTITION BY incident_date, LOWER(TRIM(area)), LOWER(TRIM(incident_type))
      ORDER BY updated_at DESC) AS rn
    FROM `voxdatalake.PlexProd.safety_incidents`)
  WHERE rn = 1 AND NOT IFNULL(is_deleted, FALSE)
),
last_rec AS (
  SELECT MAX(SAFE_CAST(incident_date AS DATE)) AS d
  FROM live WHERE LOWER(CAST(recordable AS STRING)) = 'true'
)
SELECT
  GREATEST(IFNULL(d, DATE '2026-07-23'), DATE '2026-07-23') AS last_recordable_incident,
  DATE_DIFF(CURRENT_DATE('America/Denver'),
            GREATEST(IFNULL(d, DATE '2026-07-23'), DATE '2026-07-23'), DAY) AS safe_days,
  (SELECT COUNT(*) FROM live) AS live_incidents_logged
FROM last_rec
