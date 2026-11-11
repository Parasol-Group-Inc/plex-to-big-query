-- VoxScorecardsLive.sales_history_static (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-04 15:49 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE OR REPLACE TABLE `voxdatalake.VoxScorecardsLive.sales_history_static` AS
SELECT date_approved, name, sales_rep, sales_rep_2, amount, 'legacy_sheet' AS source_system
FROM `voxdatalake.VoxScorecardsLive.vw_sales_legacy_sheet`
WHERE date_approved < DATE '2026-11-01'
