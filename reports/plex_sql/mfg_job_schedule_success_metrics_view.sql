-- mfg_job_schedule_success_metrics_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/mfg_job_schedule_success_metrics_view.sql
-- confidence: high
-- plex_views: Part_v_Job, Part_v_Job_Op, Part_v_Part, Part_v_Job_Type, Part_v_Job_Distribution, Part_v_Production, Quality_v_Checksheet, Quality_v_Checksheet_Status, Quality_v_Deviation_Job
-- notes: Mechanical translation; booleans are 1/0/NULL instead of TRUE/FALSE/NULL; Approved = -1 kept from the BigQuery view; month via FORMAT(date,'yyyy-MM').
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per job (Part_v_Job).

WITH

-- Good (non-rejected) quantity per job, from Plex's Job Production records. = "Caps Made".
job_production AS (
  SELECT
    jo.Job_Key AS job_key,
    SUM(CASE WHEN ISNULL(pr.Rejected, 0) = 0 THEN pr.Quantity ELSE 0 END) AS caps_made
  FROM Part_v_Production AS pr
  JOIN Part_v_Job_Op AS jo
    ON pr.Job_Op_Key = jo.Job_Op_Key
  GROUP BY jo.Job_Key
),

-- Latest APPROVED QC checksheet per job = proxy for "FG Testing Released".
job_checksheet AS (
  SELECT
    jo.Job_Key AS job_key,
    MAX(CAST(cs.Inspection_Date AS date)) AS fg_testing_released_date
  FROM Quality_v_Checksheet AS cs
  JOIN Part_v_Job_Op AS jo
    ON cs.Job_Op_Key = jo.Job_Op_Key
  JOIN Quality_v_Checksheet_Status AS cs_status
    ON cs.Checksheet_Status_Key = cs_status.Checksheet_Status_Key
  WHERE cs_status.Approved = -1
  GROUP BY jo.Job_Key
),

-- A job with a distribution row is fulfilling a customer order = Custom; none = Stock.
job_distribution_summary AS (
  SELECT
    jd.Job_Key AS job_key,
    COUNT(*)   AS distribution_count
  FROM Part_v_Job_Distribution AS jd
  GROUP BY jd.Job_Key
),

-- Jobs with at least one deviation.
deviation_jobs AS (
  SELECT DISTINCT dv.Job_Key AS job_key
  FROM Quality_v_Deviation_Job AS dv
),

base AS (
  SELECT
    j.Job_No                          AS job_no,
    p.Part_No                         AS part_no,
    p.Name                            AS part_name,
    jt.Job_Type                       AS job_type,
    jds.distribution_count            AS job_distribution_count,
    CASE WHEN ISNULL(jds.distribution_count, 0) > 0 THEN 'Custom' ELSE 'Stock' END AS stock_or_custom,
    CAST(j.Add_Date AS date)          AS job_add_date,
    jc.fg_testing_released_date       AS fg_testing_released_date,
    j.Quantity                        AS capsule_count,
    jp.caps_made                      AS caps_made,
    CASE WHEN dj.job_key IS NOT NULL THEN 1 ELSE 0 END AS has_deviation
  FROM Part_v_Job AS j
  LEFT JOIN Part_v_Part AS p
    ON j.Part_Key = p.Part_Key
  LEFT JOIN Part_v_Job_Type AS jt
    ON j.Job_Type_Key = jt.Job_Type_Key
  LEFT JOIN job_distribution_summary AS jds
    ON j.Job_Key = jds.job_key
  LEFT JOIN job_production AS jp
    ON j.Job_Key = jp.job_key
  LEFT JOIN job_checksheet AS jc
    ON j.Job_Key = jc.job_key
  LEFT JOIN deviation_jobs AS dj
    ON j.Job_Key = dj.job_key
),

metrics AS (
  SELECT
    bs.*,
    DATEDIFF(day, bs.job_add_date, bs.fg_testing_released_date) AS total_days,
    bs.caps_made / NULLIF(bs.capsule_count, 0)                  AS yield_pct,
    -- Yield goal: 92% Custom, 95% Stock. 1/0/NULL.
    CASE
      WHEN bs.caps_made / NULLIF(bs.capsule_count, 0) IS NULL THEN NULL
      WHEN bs.stock_or_custom = 'Custom' THEN CASE WHEN bs.caps_made / NULLIF(bs.capsule_count, 0) >= 0.92 THEN 1 ELSE 0 END
      ELSE CASE WHEN bs.caps_made / NULLIF(bs.capsule_count, 0) >= 0.95 THEN 1 ELSE 0 END
    END AS yield_meets_goal,
    -- TAT goal: 84 days or fewer from job creation to FG testing release.
    CASE
      WHEN DATEDIFF(day, bs.job_add_date, bs.fg_testing_released_date) IS NULL THEN NULL
      WHEN DATEDIFF(day, bs.job_add_date, bs.fg_testing_released_date) <= 84 THEN 1
      ELSE 0
    END AS tat_meets_goal,
    1 - bs.has_deviation AS deviation_gate_passed,
    -- Rework = Rework job type, or released before it was created (negative days). Keeps SQL three-valued logic.
    CASE
      WHEN bs.job_type = 'Rework' OR DATEDIFF(day, bs.job_add_date, bs.fg_testing_released_date) < 0 THEN 1
      WHEN bs.job_type IS NULL OR DATEDIFF(day, bs.job_add_date, bs.fg_testing_released_date) IS NULL THEN NULL
      ELSE 0
    END AS is_rework,
    FORMAT(bs.fg_testing_released_date, 'yyyy-MM') AS month
  FROM base AS bs
),

success_metrics AS (
  SELECT
    m.*,
    ( ISNULL(m.yield_meets_goal, 0)
    + ISNULL(m.deviation_gate_passed, 0)
    + ISNULL(m.tat_meets_goal, 0)
    ) / 3.0 AS success_rating,
    CASE WHEN ISNULL(m.yield_meets_goal, 0) = 1
          AND ISNULL(m.deviation_gate_passed, 0) = 1
          AND ISNULL(m.tat_meets_goal, 0) = 1 THEN 1 ELSE 0 END AS is_successful
  FROM metrics AS m
)

SELECT sm.*
FROM success_metrics AS sm;
