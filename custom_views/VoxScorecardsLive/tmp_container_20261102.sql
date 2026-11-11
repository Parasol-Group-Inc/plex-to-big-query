-- VoxScorecardsLive.tmp_container_20261102 (base table), backed up from BigQuery by scripts/backup_custom_views.py
-- last created 2026-11-09 15:37 UTC by jennilyn.tockstein@parasolgroupinc.com
-- a TABLE: this is the statement that last built it; its data is a snapshot

CREATE OR REPLACE TABLE `voxdatalake.VoxScorecardsLive.tmp_container_20261102`
OPTIONS (expiration_timestamp = TIMESTAMP '2026-12-09', description = 'Time-travel copy of PlexProd.raw_Part_v_Container as of 2026-11-02 12:00 MT, for the inventory drop investigation.')
AS SELECT * FROM `voxdatalake.PlexProd.raw_Part_v_Container` FOR SYSTEM_TIME AS OF TIMESTAMP '2026-11-02 19:00:00+00'
