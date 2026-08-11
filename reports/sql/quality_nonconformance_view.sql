-- quality_nonconformance_report — Vox Nutrition NC (non-conformance) records
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/quality_nonconformance_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- GRAIN: one row per NC record (Quality_v_Problem.Problem_No).
--
-- Problem_Category / Problem_Status / Problem_Type / Defect_Type are inline
-- text on Quality_v_Problem — confirmed live 2026-08-11, no lookup join
-- needed (same pattern as Part_v_Part.Part_Status).
--
-- LIMITATION: no Job_Key/Job_Op_Key on this view — an NC links to a part,
-- not a specific production job. See reports/quality_nonconformance.yaml
-- header for the full caveat.

SELECT

  q.Problem_No                                    AS nc_no,
  p.Part_No                                       AS part_no,
  p.Name                                           AS part_name,

  q.Problem_Type                                  AS problem_type,
  q.Problem_Category                              AS problem_category,
  q.Problem_Status                                AS problem_status,
  q.Defect_Type                                   AS defect_type,
  SAFE_CAST(q.Severity AS INT64)                  AS severity,

  q.Brief_Description                             AS brief_description,
  q.Full_Description                               AS full_description,

  SAFE_CAST(q.Quantity AS FLOAT64)                AS quantity,
  SAFE_CAST(q.Quantity_Rejected AS FLOAT64)       AS quantity_rejected,
  SAFE_CAST(q.Quantity_Returned AS FLOAT64)       AS quantity_returned,

  q.Root_Cause                                    AS root_cause,
  q.Corrective_Action                             AS corrective_action,
  q.Final_Disposition                             AS final_disposition,

  SAFE_CAST(q.Cost AS FLOAT64)                    AS cost,

  -- DATE CONVERSION PATTERN: see reports/sql/work_orders_view.sql header —
  -- raw date columns can be INT64 nanoseconds, TIMESTAMP, or STRING.
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS problem_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS closed_date

FROM `{gcp_project}.{dataset}.raw_Quality_v_Problem` q

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(q.Part_Key AS INT64) = p.Part_Key
