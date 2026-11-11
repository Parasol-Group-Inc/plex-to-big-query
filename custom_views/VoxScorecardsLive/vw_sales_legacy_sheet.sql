-- VoxScorecardsLive.vw_sales_legacy_sheet (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 15:49 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH ns_sos AS (
  SELECT DISTINCT UPPER(TRIM(document_number)) AS so_num
  FROM `voxdatalake.VoxScorecardsLive.SalesDB_YTD`
  WHERE STARTS_WITH(document_number, 'SO')
)
SELECT
  PARSE_DATE('%m/%d/%Y', SPLIT(s.date_approved, ' ')[OFFSET(0)]) AS date_approved,
  s.name, s.sales_rep, s.sales_rep_2, s.amount
FROM `voxdatalake.VoxScorecardsLive.SalesDB_YTD` s
WHERE s.date_approved IS NOT NULL AND s.date_approved != ''
  AND NOT (
    STARTS_WITH(s.document_number, 'Plex-')
    AND EXISTS (
      SELECT 1 FROM UNNEST(REGEXP_EXTRACT_ALL(UPPER(s.po), r'SO\d+')) AS x
      JOIN ns_sos ON x = ns_sos.so_num
    )
  )
