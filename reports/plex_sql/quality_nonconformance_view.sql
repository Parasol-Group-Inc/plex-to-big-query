-- quality_nonconformance_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/quality_nonconformance_view.sql
-- confidence: medium
-- plex_views: Quality_v_Problem_2, Quality_v_Problem_Form, Part_v_Part
-- notes: Rich-text stripping (REGEXP_REPLACE) rewritten as a recursive CTE that removes one <...> tag per step, then collapses whitespace; needs OPTION (MAXRECURSION 0). Unverified in Plex SQL Developer.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per NC record (Quality_v_Problem_2.Problem_No).
-- RULE: reads Quality_v_Problem_2 (the UX Problem Control table); the classic Quality_v_Problem is empty on this tenant.
-- RULE: Part_Key is -1 on a record with no part, so the part join simply finds nothing.
WITH strip AS (
  -- anchor: decode the few HTML entities Plex emits (same order as the BigQuery view)
  SELECT
    q.Problem_No AS problem_no,
    CAST(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
      q.Brief_Description,
      '&nbsp;', ' '), '&amp;', '&'), '&lt;', '<'), '&gt;', '>'), '&quot;', '"') AS nvarchar(max)) AS txt,
    0 AS depth
  FROM Quality_v_Problem_2 AS q

  UNION ALL

  -- recursive step: remove the first <...> tag
  SELECT
    s.problem_no,
    STUFF(s.txt,
          CHARINDEX('<', s.txt),
          CHARINDEX('>', s.txt, CHARINDEX('<', s.txt)) - CHARINDEX('<', s.txt) + 1,
          ''),
    s.depth + 1
  FROM strip AS s
  WHERE CHARINDEX('<', s.txt) > 0
    AND CHARINDEX('>', s.txt, CHARINDEX('<', s.txt)) > 0
),

strip_final AS (
  SELECT sr.problem_no, sr.txt
  FROM (
    SELECT s.problem_no, s.txt,
           ROW_NUMBER() OVER (PARTITION BY s.problem_no ORDER BY s.depth DESC) AS rn
    FROM strip AS s
  ) AS sr
  WHERE sr.rn = 1
)

SELECT
  q.Problem_No                                    AS nc_no,
  f.Name                                          AS problem_form,          -- how Quality classifies the record
  q.Problem_Form_Key                              AS problem_form_key,
  p.Part_No                                       AS part_no,
  p.Name                                          AS part_name,
  q.Problem_Type                                  AS problem_type,
  q.Problem_Category                              AS problem_category,
  q.Problem_Status                                AS problem_status,
  q.Defect_Type                                   AS defect_type,
  q.Severity                                      AS severity,
  -- Brief_Description is rich text: tags and entities stripped, whitespace collapsed; raw value kept below
  LTRIM(RTRIM(
    REPLACE(REPLACE(REPLACE(
      REPLACE(REPLACE(REPLACE(sf.txt, CHAR(9), ' '), CHAR(10), ' '), CHAR(13), ' '),
      '  ', ' ' + CHAR(7)), CHAR(7) + ' ', ''), CHAR(7), '')
  ))                                              AS brief_description,
  q.Brief_Description                             AS brief_description_html,
  q.Full_Description                              AS full_description,
  q.Quantity                                      AS quantity,
  q.Quantity_Rejected                             AS quantity_rejected,
  q.Quantity_Returned                             AS quantity_returned,
  q.Quantity_Scrapped                             AS quantity_scrapped,
  q.Root_Cause                                    AS root_cause,
  q.Root_Cause_Response                           AS root_cause_response,
  q.Response_Action                               AS response_action,       -- not a corrective_action column; Problem_2 has none
  q.Final_Disposition                             AS final_disposition,
  q.Cost                                          AS cost,                  -- 0.0 on every record today; Quality types the value into Brief_Description
  q.Champion                                      AS champion_key,          -- a user key, not a name
  q.Department_No                                 AS department_no,
  q.Building_Key                                  AS building_key,
  q.Workcenter_Key                                AS workcenter_key,
  q.Job_Key                                       AS job_key,
  q.Job_Op_Key                                    AS job_op_key,
  q.Recurrence                                    AS recurrence,
  CAST(q.Problem_Date AS date)                    AS problem_date,
  CAST(q.Recorded_Date AS date)                   AS recorded_date,
  CAST(q.Problem_Due_Date AS date)                AS due_date,
  CAST(q.Closed_Date AS date)                     AS closed_date
FROM Quality_v_Problem_2 AS q
LEFT JOIN strip_final AS sf
  ON sf.problem_no = q.Problem_No
LEFT JOIN Quality_v_Problem_Form AS f
  ON q.Problem_Form_Key = f.Problem_Form_Key
LEFT JOIN Part_v_Part AS p
  ON q.Part_Key = p.Part_Key
OPTION (MAXRECURSION 0);
