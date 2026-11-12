-- Weekend schedule (2026-11-12, Emilio: "only probes for saturday and sunday,
-- only one probe in the morning, one at night", to save money).
--
-- Run ONCE, after deploy.sh has added the `days` column (terraform/main.tf,
-- google_bigquery_table.etl_schedule). Weekdays stay as they are; on Saturday
-- and Sunday (America/Denver) each prod job runs only:
--   04:xx  probe  (new rows, same staggered minute as the weekday full run)
--   23:xx  probe  (the existing rows, days = 'all')
-- The 13:xx and 18:xx probes and the 04:xx full run become weekdays-only, so
-- Monday 04:xx is a full run again.
--
-- Undo: DELETE the 'weekends' rows, then UPDATE days = NULL everywhere.

ASSERT (SELECT COUNTIF(days IS NOT NULL) FROM `voxdatalake.PlexOps.etl_schedule`) = 0
  AS 'days is already set on some rows; this script runs once';

UPDATE `voxdatalake.PlexOps.etl_schedule`
SET days = 'weekdays', updated_by = 'weekend-schedule', updated_at = CURRENT_TIMESTAMP()
WHERE job_name NOT LIKE '%-test'
  AND (mode = 'full' OR SUBSTR(run_time, 1, 2) IN ('13', '18'));

UPDATE `voxdatalake.PlexOps.etl_schedule`
SET days = 'all', updated_by = 'weekend-schedule', updated_at = CURRENT_TIMESTAMP()
WHERE job_name NOT LIKE '%-test' AND days IS NULL;

INSERT INTO `voxdatalake.PlexOps.etl_schedule`
  (job_name, run_time, mode, enabled, note, updated_by, updated_at, days)
SELECT job_name, run_time, 'probe', enabled,
       'weekend morning probe (2026-11-12)', 'weekend-schedule', CURRENT_TIMESTAMP(), 'weekends'
FROM `voxdatalake.PlexOps.etl_schedule`
WHERE job_name NOT LIKE '%-test' AND mode = 'full';

SELECT days, mode, SUBSTR(run_time, 1, 2) AS hour, COUNT(*) AS rows_, COUNTIF(enabled) AS enabled_
FROM `voxdatalake.PlexOps.etl_schedule`
GROUP BY 1, 2, 3 ORDER BY 1, 3;
