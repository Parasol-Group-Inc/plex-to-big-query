-- VoxScorecardsLive.vw_pipeline (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-10-30 20:08 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH opportunities AS (
  SELECT 1 AS sort_order, 'Opportunities (35%)' AS stage, 0.35 AS probability,
    SUM(SAFE_CAST(numeric_mm1ry7gm AS NUMERIC)) AS pipeline_total
  FROM `voxdatalake.VoxScorecardsLive.new_opportunities_18405027980`
  WHERE status NOT IN ('Won', 'Lost', 'NS Quote Sent', 'Stalled')
),
forecast AS (
  SELECT 2 AS sort_order, 'Forecast (70%)' AS stage, 0.70 AS probability,
    SUM(SAFE_CAST(numeric_mm3ry8p5_adjusted AS NUMERIC)) AS pipeline_total
  FROM `voxdatalake.VoxScorecardsLive.vw_forecast_decrementing`
  -- status = 'OPEN' and date_mm3rcye8 >= today are already applied inside the view
),
plex_pending AS (
  -- Plex: Pending Sales Approval + Deposit Review statuses
  SELECT 3 AS sort_order, 'Pending Approval (95%)' AS stage, 0.95 AS probability,
    CAST(SUM(pipeline_value) AS NUMERIC) AS pipeline_total
  FROM `voxdatalake.PlexProd.pipeline_plex_value_report`
  WHERE pipeline_stage = 'Pending Sales Approval'
),
plex_quotes AS (
  SELECT 4 AS sort_order, 'Quotes (80%)' AS stage, 0.80 AS probability,
    CAST(SUM(pipeline_value) AS NUMERIC) AS pipeline_total
  FROM `voxdatalake.PlexProd.pipeline_plex_value_report`
  WHERE pipeline_stage = 'Quote'
)
SELECT sort_order, stage, probability, pipeline_total FROM opportunities
UNION ALL SELECT sort_order, stage, probability, pipeline_total FROM forecast
UNION ALL SELECT sort_order, stage, probability, pipeline_total FROM plex_pending
UNION ALL SELECT sort_order, stage, probability, pipeline_total FROM plex_quotes
