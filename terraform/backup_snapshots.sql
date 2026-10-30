-- Weekly snapshots of the tables that exist only in BigQuery (no Plex source, no copy in git).
-- Run by the `backup_snapshots_weekly` scheduled query (terraform/main.tf).
-- Snapshots land in voxdatalake.Backups as <Dataset>__<table>_<YYYYMMDD> and expire after 90 days.
-- To cover a new table, add it to the list below and deploy.
DECLARE src_tables ARRAY<STRING> DEFAULT [
  'PlexProd.label_design_push_log', 'PlexProd.safety_incidents', 'PlexProd.scorecard_goals',
  'PlexProd.scorecard_goals_app', 'PlexProd.msl_item_inputs', 'PlexProd.msl_rules',
  'PlexProd.turnaround_standards', 'PlexProd.job_run_log', 'PlexProd.msl_demand_daily',
  'PlexOps.etl_schedule', 'PlexOps.etl_dispatch_log',
  'PlexTest.plex_api_audit', 'PlexTest.plex_api_payloads', 'PlexTest.plex_api_push_log',
  'VoxScorecardsLive.DN_15_MO_Expiring', 'VoxScorecardsLive.Overstock_NS', 'VoxScorecardsLive.Product_Cost',
  'VoxScorecardsLive.SalesDB_YTD', 'VoxScorecardsLive.SalesQuotesLanding', 'VoxScorecardsLive.daily_sales_activity',
  'VoxScorecardsLive.high_risk_snapshots', 'VoxScorecardsLive.new_activities_18405028203',
  'VoxScorecardsLive.new_forecast_18415088271', 'VoxScorecardsLive.new_opportunities_18405027980',
  'VoxScorecardsLive.pipeline_snapshot', 'VoxScorecardsLive.sales_goals', 'VoxScorecardsLive.shipping_daily_ops',
  'VoxScorecardsLive.shipping_revenue_blanket_daily', 'VoxScorecardsLive.shipping_revenue_daily',
  'VoxScorecardsLive.shipping_revenue_shipped_daily', 'VoxScorecardsLive.stalled_win_lost_18409621334',
  'VoxScorecardsLive.stalled_won_lost_18409621334'
];

FOR t IN (SELECT x FROM UNNEST(src_tables) AS x) DO
  EXECUTE IMMEDIATE FORMAT("""
    CREATE SNAPSHOT TABLE IF NOT EXISTS `voxdatalake.Backups.%s_%s`
    CLONE `voxdatalake.%s`
    OPTIONS (expiration_timestamp = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 90 DAY))""",
    REPLACE(t.x, '.', '__'), FORMAT_DATE('%Y%m%d', CURRENT_DATE()), t.x);
END FOR;
