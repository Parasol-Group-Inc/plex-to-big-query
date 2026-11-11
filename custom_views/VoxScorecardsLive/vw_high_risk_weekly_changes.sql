-- VoxScorecardsLive.vw_high_risk_weekly_changes (view), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-06-22 14:46 UTC by jennilyn.tockstein@parasolgroupinc.com

WITH pivoted AS (
  SELECT
    part_number,
    product_name,
    date_of_expiration,
    expiration_bucket,
    MAX(CASE WHEN snapshot_date = (
      SELECT MIN(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.high_risk_snapshots`
    ) THEN lot_inventory END)                                     AS week1_inventory,
    MAX(CASE WHEN snapshot_date = (
      SELECT MIN(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.high_risk_snapshots`
    ) THEN lot_value END)                                         AS week1_value,
    MAX(CASE WHEN snapshot_date = (
      SELECT DATE_ADD(MIN(snapshot_date), INTERVAL 7 DAY)
      FROM `voxdatalake.VoxScorecardsLive.high_risk_snapshots`
    ) THEN lot_inventory END)                                     AS week2_inventory,
    MAX(CASE WHEN snapshot_date = (
      SELECT DATE_ADD(MIN(snapshot_date), INTERVAL 7 DAY)
      FROM `voxdatalake.VoxScorecardsLive.high_risk_snapshots`
    ) THEN lot_value END)                                         AS week2_value,
    MAX(CASE WHEN snapshot_date = (
      SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.high_risk_snapshots`
    ) THEN lot_inventory END)                                     AS week3_inventory,
    MAX(CASE WHEN snapshot_date = (
      SELECT MAX(snapshot_date) FROM `voxdatalake.VoxScorecardsLive.high_risk_snapshots`
    ) THEN lot_value END)                                         AS week3_value
  FROM `voxdatalake.VoxScorecardsLive.high_risk_snapshots`
  GROUP BY part_number, product_name, date_of_expiration, expiration_bucket
)

SELECT
  part_number,
  product_name,
  date_of_expiration,
  expiration_bucket,
  week1_inventory,
  week2_inventory,
  week3_inventory,
  week3_inventory - week1_inventory                               AS total_change,
  week3_value                                                     AS current_value,
  ROUND(SAFE_DIVIDE(week3_inventory - week1_inventory, week1_inventory), 4) AS pct_change
FROM pivoted
ORDER BY current_value DESC
