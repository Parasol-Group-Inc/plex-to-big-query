-- quality_disposition_cost_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/quality_disposition_cost_view.sql
-- confidence: medium
-- plex_views: Quality_v_Problem_2, Part_v_Part
-- notes: Upstream quality_nonconformance_report inlined (needed columns only). GROUP BY uses the raw Final_Disposition column as in the BigQuery view; if BigQuery resolved it to the SELECT alias instead, NULL and blank dispositions would merge into one row there.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per (final disposition, month).
-- RULE: Plex has no "Destroy" value; final disposition Scrap = Destruction.
-- RULE: a blank final disposition is split 3 ways: open = (not yet dispositioned);
--       closed with no material = (closed, no material); closed with material = (closed, disposition missing).
--       closed = Closed_Date set or status Closed; material = a part, or any non-zero quantity/rejected/scrapped.
-- RULE: records_missing_cost counts NULL-or-0 cost on Scrap/Rework records only.
WITH nc AS (
  SELECT
    p.Part_No                       AS part_no,
    q.Problem_Status                AS problem_status,
    q.Final_Disposition             AS final_disposition,
    q.Quantity                      AS quantity,
    q.Quantity_Rejected             AS quantity_rejected,
    q.Quantity_Scrapped             AS quantity_scrapped,
    q.Cost                          AS cost,
    CAST(q.Problem_Date AS date)    AS problem_date,
    CAST(q.Closed_Date AS date)     AS closed_date
  FROM Quality_v_Problem_2 AS q
  LEFT JOIN Part_v_Part AS p
    ON q.Part_Key = p.Part_Key
),

classified AS (
  SELECT
    n.*,
    CASE
      WHEN UPPER(LTRIM(RTRIM(n.final_disposition))) = 'SCRAP'        THEN 'Destruction'
      WHEN UPPER(LTRIM(RTRIM(n.final_disposition))) = 'REWORK'       THEN 'Rework'
      WHEN UPPER(LTRIM(RTRIM(n.final_disposition))) = 'RETURN'       THEN 'Return'
      WHEN UPPER(LTRIM(RTRIM(n.final_disposition))) = 'USE AS IS'    THEN 'Use as is'
      WHEN UPPER(LTRIM(RTRIM(n.final_disposition))) = 'RE-INTRODUCE' THEN 'Re-introduce'
      WHEN (n.final_disposition IS NULL OR LTRIM(RTRIM(n.final_disposition)) = '')
       AND n.closed_date IS NULL
       AND UPPER(LTRIM(RTRIM(ISNULL(n.problem_status, '')))) <> 'CLOSED'
                                                                     THEN '(not yet dispositioned)'
      WHEN (n.final_disposition IS NULL OR LTRIM(RTRIM(n.final_disposition)) = '')
       AND n.part_no IS NULL
       AND COALESCE(n.quantity, 0) = 0
       AND COALESCE(n.quantity_rejected, 0) = 0
       AND COALESCE(n.quantity_scrapped, 0) = 0
                                                                     THEN '(closed, no material)'
      WHEN n.final_disposition IS NULL OR LTRIM(RTRIM(n.final_disposition)) = ''
                                                                     THEN '(closed, disposition missing)'
      ELSE n.final_disposition
    END AS disposition_class
  FROM nc AS n
)

SELECT
  COALESCE(NULLIF(LTRIM(RTRIM(c.final_disposition)), ''), '(blank)')       AS final_disposition,
  c.disposition_class                                                      AS disposition_class,
  DATEFROMPARTS(YEAR(c.problem_date), MONTH(c.problem_date), 1)            AS problem_month,
  COUNT(*)                                                                 AS nc_count,
  SUM(COALESCE(c.quantity_rejected, 0))                                    AS qty_rejected,
  SUM(c.cost)                                                              AS total_cost,
  SUM(CASE WHEN (c.cost IS NULL OR c.cost = 0)
            AND UPPER(LTRIM(RTRIM(c.final_disposition))) IN ('SCRAP', 'REWORK')
           THEN 1 ELSE 0 END)                                              AS records_missing_cost
FROM classified AS c
WHERE c.problem_date IS NOT NULL
GROUP BY c.final_disposition, c.disposition_class, DATEFROMPARTS(YEAR(c.problem_date), MONTH(c.problem_date), 1)
ORDER BY problem_month DESC, total_cost DESC;
