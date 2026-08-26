-- mfg_job_schedule_fg_testing_pending_report — MFG Job Schedule "FG Testing
-- Pending" tab
--
-- Thin alias over mfg_job_schedule_success_metrics_report, same pattern as
-- sales_orders_pending_approval_by_rep_view.sql — the tab is that same
-- job-grain data, filtered to jobs whose FG testing hasn't been released
-- yet. Requires mfg_job_schedule_success_metrics_report to already exist;
-- both are bq_view entries in the same reports/work_orders.yaml run, so
-- main()'s retry-once pass (see main.py) self-heals if this ever runs
-- before its sibling in a given execution.
--
-- See spreadsheets/mfg_job_schedule_fg_testing_pending.md and
-- reports/sql/mfg_job_schedule_success_metrics_view.sql's header for every
-- caveat that applies here too (Date Entered/FG Testing Released proxies,
-- Yield generalization, Stock/Custom proxy, etc.) — this view inherits all
-- of them, it adds no new logic of its own beyond the filter.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.

SELECT *
FROM `{gcp_project}.{dataset}.mfg_job_schedule_success_metrics_report`
WHERE fg_testing_released_date IS NULL
