-- Probe phase 2, STAGE B: hand the prod ETL to the dispatcher.
-- Run AFTER deploy.sh has removed the prod nightly + -retry schedulers (or
-- just before — overlapping for one cycle only means one extra run).
-- Also removes any temporary E2E test rows left in the schedule.
DELETE FROM `voxdatalake.PlexOps.etl_schedule` WHERE note LIKE 'E2E TEST%';

UPDATE `voxdatalake.PlexOps.etl_schedule`
SET enabled = TRUE, updated_by = 'stage-b', updated_at = CURRENT_TIMESTAMP()
WHERE job_name NOT LIKE '%-test' AND NOT enabled;

SELECT mode, COUNT(*) AS rows_, COUNTIF(enabled) AS enabled_
FROM `voxdatalake.PlexOps.etl_schedule` GROUP BY mode;
