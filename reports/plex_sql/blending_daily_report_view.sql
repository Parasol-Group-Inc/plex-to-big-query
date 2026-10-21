-- blending_daily_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/blending_daily_report_view.sql
-- confidence: high
-- plex_views: Part_v_Production, Part_v_Job_Op, Part_v_Workcenter, Part_v_Job, Part_v_Part, Personnel_v_Employee
-- notes: BigQuery STRING_AGG(DISTINCT ...) rewritten as DISTINCT subqueries + STRING_AGG ... WITHIN GROUP; otherwise mechanical.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.
--
-- GRAIN: one row per production date x workcenter (Blending / Pre-Weigh group only).
-- Source is Part_v_Production (Plex's "Job Production" report); Rejected <> 0 counts as scrap.

WITH prod_rows AS (
  SELECT
    pr.Quantity,
    pr.Rejected,
    pr.Job_Op_Key,
    pr.Workcenter_Key,
    pr.Record_By,
    pr.Report_Shift,
    CAST(pr.Record_Date AS date) AS production_date
  FROM Part_v_Production AS pr
),

-- One row per production record with every lookup resolved.
detail AS (
  SELECT
    pd.production_date,
    wc.Name              AS workcenter,
    wc.Workcenter_Group  AS workcenter_group,
    part.Part_No         AS Part_No,
    j.Job_Key            AS Job_Key,
    emp.Plexus_User_No   AS Plexus_User_No,
    emp.Common_Name      AS Common_Name,
    pd.Report_Shift      AS Report_Shift,
    pd.Quantity          AS Quantity,
    pd.Rejected          AS Rejected
  FROM prod_rows AS pd
  LEFT JOIN Part_v_Job_Op AS jo
    ON pd.Job_Op_Key = jo.Job_Op_Key
  JOIN Part_v_Workcenter AS wc
    ON pd.Workcenter_Key = wc.Workcenter_Key
  LEFT JOIN Part_v_Job AS j
    ON jo.Job_Key = j.Job_Key
  LEFT JOIN Part_v_Part AS part
    ON j.Part_Key = part.Part_Key
  LEFT JOIN Personnel_v_Employee AS emp
    ON pd.Record_By = emp.Plexus_User_No
  WHERE wc.Workcenter_Group IN ('Blending', 'Pre-Weigh')
),

-- DISTINCT string lists (SQL Server has no STRING_AGG(DISTINCT ...)).
parts AS (
  SELECT x.production_date, x.workcenter, x.workcenter_group,
         STRING_AGG(x.Part_No, ', ') WITHIN GROUP (ORDER BY x.Part_No) AS parts_run
  FROM (SELECT DISTINCT d1.production_date, d1.workcenter, d1.workcenter_group, d1.Part_No
        FROM detail AS d1 WHERE d1.Part_No IS NOT NULL) AS x
  GROUP BY x.production_date, x.workcenter, x.workcenter_group
),
emps AS (
  SELECT x.production_date, x.workcenter, x.workcenter_group,
         STRING_AGG(x.Common_Name, ', ') WITHIN GROUP (ORDER BY x.Common_Name) AS employees
  FROM (SELECT DISTINCT d2.production_date, d2.workcenter, d2.workcenter_group, d2.Common_Name
        FROM detail AS d2 WHERE d2.Common_Name IS NOT NULL) AS x
  GROUP BY x.production_date, x.workcenter, x.workcenter_group
),
shifts AS (
  SELECT x.production_date, x.workcenter, x.workcenter_group,
         STRING_AGG(x.Report_Shift, ', ') WITHIN GROUP (ORDER BY x.Report_Shift) AS shifts
  FROM (SELECT DISTINCT d3.production_date, d3.workcenter, d3.workcenter_group, d3.Report_Shift
        FROM detail AS d3 WHERE d3.Report_Shift IS NOT NULL) AS x
  GROUP BY x.production_date, x.workcenter, x.workcenter_group
),

totals AS (
  SELECT
    d.production_date,
    d.workcenter,
    d.workcenter_group,
    COUNT(DISTINCT d.Job_Key)         AS job_count,
    COUNT(DISTINCT d.Plexus_User_No)  AS employee_count,
    SUM(CASE WHEN ISNULL(d.Rejected, 0) = 0 THEN d.Quantity ELSE 0 END) AS actual_qty,
    SUM(CASE WHEN ISNULL(d.Rejected, 0) <> 0 THEN d.Quantity ELSE 0 END) AS scrap_qty
  FROM detail AS d
  GROUP BY d.production_date, d.workcenter, d.workcenter_group
)

SELECT
  t.production_date,
  t.workcenter,
  t.workcenter_group,
  pa.parts_run,
  t.job_count,
  t.employee_count,
  em.employees,
  sh.shifts,
  t.actual_qty,
  t.scrap_qty
FROM totals AS t
LEFT JOIN parts AS pa
  ON pa.workcenter = t.workcenter AND pa.workcenter_group = t.workcenter_group
 AND (pa.production_date = t.production_date OR (pa.production_date IS NULL AND t.production_date IS NULL))
LEFT JOIN emps AS em
  ON em.workcenter = t.workcenter AND em.workcenter_group = t.workcenter_group
 AND (em.production_date = t.production_date OR (em.production_date IS NULL AND t.production_date IS NULL))
LEFT JOIN shifts AS sh
  ON sh.workcenter = t.workcenter AND sh.workcenter_group = t.workcenter_group
 AND (sh.production_date = t.production_date OR (sh.production_date IS NULL AND t.production_date IS NULL))
ORDER BY t.production_date DESC, t.workcenter;
