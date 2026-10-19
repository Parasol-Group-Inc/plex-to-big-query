-- Seeds PlexOps.etl_schedule with the prod probe schedule (docs/PROBE_BUILD_PLAN.md).
-- Run ONCE, after Terraform creates the table (it refuses to run twice: the
-- table must be empty). Rows go in DISABLED; stage B enables them with
--   UPDATE `voxdatalake.PlexOps.etl_schedule` SET enabled = TRUE,
--     updated_by = '<you>', updated_at = CURRENT_TIMESTAMP()
--   WHERE job_name NOT LIKE '%-test';
--
-- 13 prod jobs x 4 times. 1 PM / 6 PM / 11 PM probe, 4 AM full (the daily
-- safety net). Staggered 4 minutes apart so 13 jobs don't open 13 Plex ODBC
-- sessions at once: slot i runs at hh:00 + 4*i minutes (13:00 … 13:48). Four,
-- not five: 12 x 5 = 60 would put the last 11 PM slot at "24:00".
-- Times are America/Denver wall clock; the dispatcher handles MST/MDT.
ASSERT (SELECT COUNT(*) FROM `voxdatalake.PlexOps.etl_schedule`) = 0
  AS 'etl_schedule is not empty; seed only once';

INSERT INTO `voxdatalake.PlexOps.etl_schedule`
  (job_name, run_time, mode, enabled, note, updated_by, updated_at)
SELECT
  job_name,
  FORMAT('%02d:%02d', base_hour, i * 4),
  mode,
  FALSE,
  'seeded by deploy/etl_dispatcher/seed_schedule.sql',
  'seed',
  CURRENT_TIMESTAMP()
FROM UNNEST([
  'plex-etl-sales-orders', 'plex-etl-work-orders', 'plex-etl-purchasing-open-orders',
  'plex-etl-part-obsolescence', 'plex-etl-inventory-activity', 'plex-etl-inventory-snapshot',
  'plex-etl-quality-nonconformance', 'plex-etl-part-on-hand-inventory',
  'plex-etl-purchasing-pending-requisitions', 'plex-etl-sales-quotes', 'plex-etl-sales-returns',
  'plex-etl-quality-supplier-returns', 'plex-etl-part-routing'
]) AS job_name WITH OFFSET AS i
CROSS JOIN UNNEST([
  STRUCT(13 AS base_hour, 'probe' AS mode),
  STRUCT(18, 'probe'),
  STRUCT(23, 'probe'),
  STRUCT(4, 'full')
]);
