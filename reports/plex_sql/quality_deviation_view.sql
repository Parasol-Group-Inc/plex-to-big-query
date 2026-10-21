-- quality_deviation_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/quality_deviation_view.sql
-- confidence: high
-- plex_views: Quality_v_Deviation, Quality_v_Deviation_Type, Quality_v_Deviation_Status, Quality_v_Deviation_Job, Quality_v_Deviation_Problem, Quality_v_Deviation_Part, Quality_v_Deviation_Workcenter, Quality_v_Problem_2, Part_v_Job, Part_v_Part, Part_v_Workcenter
-- notes: STRING_AGG(DISTINCT) is not T-SQL, so each list de-duplicates in a subquery first (STRING_AGG needs SQL Server 2017+). Status flags cast to int.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per Deviation record (Deviation_No); linked jobs/problems/parts/workcenters are comma-separated lists.
-- RULE: problem links read Quality_v_Problem_2 (Deviation_Problem.Problem_Key is Problem_2's key), ordered numerically.
-- RULE: deviation_month is the month of Add_Date (when raised in Plex), not Effective_Date.
WITH job_links AS (
  SELECT x.Deviation_Key,
         STRING_AGG(x.Job_No, ', ') WITHIN GROUP (ORDER BY x.Job_No) AS job_nos
  FROM (
    SELECT DISTINCT dj.Deviation_Key, j.Job_No
    FROM Quality_v_Deviation_Job AS dj
    LEFT JOIN Part_v_Job AS j
      ON dj.Job_Key = j.Job_Key
  ) AS x
  GROUP BY x.Deviation_Key
),

problem_links AS (
  SELECT x.Deviation_Key,
         STRING_AGG(CAST(x.problem_no AS varchar(30)), ', ') WITHIN GROUP (ORDER BY x.problem_no) AS problem_nos
  FROM (
    SELECT DISTINCT dp.Deviation_Key, q.Problem_No AS problem_no
    FROM Quality_v_Deviation_Problem AS dp
    JOIN Quality_v_Problem_2 AS q
      ON dp.Problem_Key = q.Problem_Key
  ) AS x
  GROUP BY x.Deviation_Key
),

part_links AS (
  SELECT x.Deviation_Key,
         STRING_AGG(x.Part_No, ', ') WITHIN GROUP (ORDER BY x.Part_No) AS part_nos
  FROM (
    SELECT DISTINCT dpt.Deviation_Key, p.Part_No
    FROM Quality_v_Deviation_Part AS dpt
    LEFT JOIN Part_v_Part AS p
      ON dpt.Part_Key = p.Part_Key
  ) AS x
  GROUP BY x.Deviation_Key
),

workcenter_links AS (
  SELECT x.Deviation_Key,
         STRING_AGG(x.Name, ', ') WITHIN GROUP (ORDER BY x.Name) AS workcenters
  FROM (
    SELECT DISTINCT dw.Deviation_Key, wc.Name
    FROM Quality_v_Deviation_Workcenter AS dw
    LEFT JOIN Part_v_Workcenter AS wc
      ON dw.Workcenter_Key = wc.Workcenter_Key
  ) AS x
  GROUP BY x.Deviation_Key
)

SELECT
  d.Deviation_No                                  AS deviation_no,
  d.Code_No                                       AS code_no,
  dt.Deviation_Type                               AS deviation_type,
  ds.Deviation_Status                             AS deviation_status,
  CAST(ds.Approved AS int)                        AS status_is_approved,
  CAST(ds.Rejected AS int)                        AS status_is_rejected,
  CAST(ds.Awaiting_Approval AS int)               AS status_is_awaiting_approval,
  d.Pieces_Affected                               AS pieces_affected,
  d.Reason                                        AS reason,
  d.Note                                          AS note,
  jl.job_nos                                      AS job_nos,
  pl.problem_nos                                  AS problem_nos,
  pt.part_nos                                     AS part_nos,
  wl.workcenters                                  AS workcenters,
  d.Approved_By                                   AS approved_by,
  CAST(d.Approved_Date AS date)                   AS approved_date,
  CAST(d.Effective_Date AS date)                  AS effective_date,
  CAST(d.Expiration_Date AS date)                 AS expiration_date,
  CAST(d.Add_Date AS date)                        AS add_date,
  DATEFROMPARTS(YEAR(d.Add_Date), MONTH(d.Add_Date), 1) AS deviation_month
FROM Quality_v_Deviation AS d
LEFT JOIN Quality_v_Deviation_Type AS dt
  ON d.Deviation_Type_Key = dt.Deviation_Type_Key
LEFT JOIN Quality_v_Deviation_Status AS ds
  ON d.Deviation_Status_Key = ds.Deviation_Status_Key
LEFT JOIN job_links AS jl
  ON d.Deviation_Key = jl.Deviation_Key
LEFT JOIN problem_links AS pl
  ON d.Deviation_Key = pl.Deviation_Key
LEFT JOIN part_links AS pt
  ON d.Deviation_Key = pt.Deviation_Key
LEFT JOIN workcenter_links AS wl
  ON d.Deviation_Key = wl.Deviation_Key;
