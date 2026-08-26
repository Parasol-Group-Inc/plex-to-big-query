-- mfg_job_schedule_gate_stats_report — MFG Job Schedule "YTD Gate Stats" tab
--
-- Monthly rollup over mfg_job_schedule_success_metrics_report (one row per
-- job) — no new extraction, just a GROUP BY month on top of the
-- already-deployed job-grain view. Every caveat on that view applies here
-- too (see its header): Yield/FG-Testing-Released/Stock-vs-Custom are all
-- best-available proxies, not confirmed against real production data,
-- which is still 0 rows on every environment as of 2026-08-26.
--
-- "Successful" (binary) = Success Rating = 100% (all 3 gates pass) — a
-- deliberate choice, not the only reading of the sheet's own headers
-- (Emilio's call 2026-08-26; a >=2-of-3 partial-credit reading was the
-- alternative considered). See spreadsheets/mfg_job_schedule_ytd_gate_stats.md
-- for the reverse-engineered formula this rolls up.
--
-- Rework rows are NOT excluded here (Emilio's call 2026-08-26) — every job
-- with a non-NULL month counts toward every total below, including ones
-- flagged is_rework on the row-level view. If a rework-excluded view of
-- these same stats is ever wanted, filter on is_rework at query time rather
-- than rebuilding this view.
--
-- Rows with month IS NULL (no FG Testing Released date yet — i.e. the FG
-- Testing Pending tab's own jobs) are excluded, same as the source sheet's
-- month-keyed table only having a row once a job has a real completion
-- month to group into.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.

SELECT

  month,

  -- ── Table 1: Success Frequency ──────────────────────────────────────────
  COUNT(*)                                                       AS total_jobs,
  COUNTIF(is_successful)                                         AS jobs_successful,
  COUNTIF(NOT is_successful)                                     AS jobs_not_successful,
  SAFE_DIVIDE(COUNTIF(is_successful), COUNT(*))                  AS pct_successful,

  COUNTIF(stock_or_custom = 'Stock')                             AS stock_total_jobs,
  COUNTIF(stock_or_custom = 'Stock' AND is_successful)           AS stock_jobs_successful,
  COUNTIF(stock_or_custom = 'Stock' AND NOT is_successful)       AS stock_jobs_not_successful,
  SAFE_DIVIDE(
    COUNTIF(stock_or_custom = 'Stock' AND is_successful),
    COUNTIF(stock_or_custom = 'Stock')
  )                                                               AS stock_pct_successful,

  COUNTIF(stock_or_custom = 'Custom')                            AS custom_total_jobs,
  COUNTIF(stock_or_custom = 'Custom' AND is_successful)          AS custom_jobs_successful,
  COUNTIF(stock_or_custom = 'Custom' AND NOT is_successful)      AS custom_jobs_not_successful,
  SAFE_DIVIDE(
    COUNTIF(stock_or_custom = 'Custom' AND is_successful),
    COUNTIF(stock_or_custom = 'Custom')
  )                                                               AS custom_pct_successful,

  -- ── Table 2: Yield / Deviations / TAT by product type ──────────────────
  AVG(IF(stock_or_custom = 'Stock', yield_pct, NULL))            AS stock_avg_yield,
  AVG(IF(stock_or_custom = 'Custom', yield_pct, NULL))           AS custom_avg_yield,

  COUNTIF(stock_or_custom = 'Stock' AND has_deviation)           AS stock_jobs_with_deviation,
  COUNTIF(stock_or_custom = 'Custom' AND has_deviation)          AS custom_jobs_with_deviation,

  AVG(IF(stock_or_custom = 'Stock', total_days, NULL))           AS stock_avg_tat,
  AVG(IF(stock_or_custom = 'Custom', total_days, NULL))          AS custom_avg_tat,

  COUNTIF(stock_or_custom = 'Stock' AND tat_meets_goal)          AS stock_jobs_within_tat_goal,
  COUNTIF(stock_or_custom = 'Custom' AND tat_meets_goal)         AS custom_jobs_within_tat_goal

FROM `{gcp_project}.{dataset}.mfg_job_schedule_success_metrics_report`
WHERE month IS NOT NULL
GROUP BY month
ORDER BY month
