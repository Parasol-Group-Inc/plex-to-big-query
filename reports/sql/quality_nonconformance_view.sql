-- quality_nonconformance_report — Vox Nutrition NC (non-conformance) records
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/quality_nonconformance_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- GRAIN: one row per NC record (Quality_v_Problem_2.Problem_No).
--
-- ⚠ READS Quality_v_Problem_2, NOT Quality_v_Problem — CHANGED 2026-09-22
-- ─────────────────────────────────────────────────────────────────────────
-- Vox records problems on Plex's **UX** Problem Control screen, which writes
-- `Quality_v_Problem_2`. `Quality_v_Problem` is the CLASSIC table and is
-- permanently empty on this tenant — verified live 2026-09-22: 19 records
-- visible in the Problem Control UI, 22 rows in Quality_v_Problem_2, and
-- **0 rows in Quality_v_Problem**. The pipeline had been reading the classic
-- table since the report was built, so this view — and turnaround time, cost
-- by category and disposition cost, which all read it — returned 0 rows
-- while every job exited 0: the zero-row guard in write_to_bigquery logs
-- "existing table left untouched" and the run still reports success.
--
-- The classic table is still extracted, deliberately: if anything is ever
-- recorded on the classic screen the rows land somewhere, and the contrast
-- between the two raw tables is the evidence for this decision.
--
-- WHAT Problem_2 ADDS over the classic table (all verified live 2026-09-22):
--   - Problem_Form_Key → Quality_v_Problem_Form. THE dimension Quality
--     actually classifies by: Material Destruction, Non-Conformance Form,
--     Risk Assessment, Complaint Form, 8D, 5P, Initial Problem Report,
--     System Audit CAR, CAPA Report, Deviation Form. Destruction is a FORM
--     here, not a Final_Disposition — see quality_disposition_cost_view.sql.
--   - Job_Key / Job_Op_Key ON THE RECORD. This retires the caveat in
--     reports/quality_nonconformance.yaml that an NC links to a part and not
--     to a job, and with it the reason the Deviation junction tables were
--     added as a workaround. Both are 0 on every record today — the
--     capability is there, nobody is using it yet.
--   - Recorded_Date alongside Problem_Date, both populated and genuinely
--     different (Problem_Date is usually date-only, Recorded_Date a precise
--     timestamp). The open Problem-vs-Entered TAT question can now be
--     answered from data rather than argued — see
--     quality_turnaround_time_view.sql, which exposes both.
--   - Champion, Department_No, Building_Key, Workcenter_Key,
--     Problem_Due_Date, Recurrence, Quantity_Scrapped.
--
-- ⚠ Cost IS 0.0 ON EVERY RECORD (22 of 22, verified 2026-09-22). Quality is
-- typing the value into Brief_Description instead — records 6, 11 and 17
-- read "1.5", "600" and "$2305.57" and nothing else. Any dollar tile built
-- on `cost` reads $0 until that changes. Open with Quality; not papered over
-- here, because a fabricated cost is worse than a visible zero.
--
-- ⚠ Final_Disposition is blank on all 22, including the one Closed record.
--
-- Problem_Category / Problem_Status / Problem_Type / Defect_Type are inline
-- text on Problem_2 as they were on the classic view — no lookup join.

SELECT

  q.Problem_No                                    AS nc_no,

  -- The form chosen when the record was created — how Quality classifies.
  -- LEFT JOIN, so an unmapped key surfaces as NULL rather than dropping the
  -- record entirely.
  f.Name                                          AS problem_form,
  SAFE_CAST(q.Problem_Form_Key AS INT64)          AS problem_form_key,

  p.Part_No                                       AS part_no,
  p.Name                                          AS part_name,

  q.Problem_Type                                  AS problem_type,
  q.Problem_Category                              AS problem_category,
  q.Problem_Status                                AS problem_status,
  q.Defect_Type                                   AS defect_type,
  SAFE_CAST(q.Severity AS INT64)                  AS severity,

  -- Brief_Description is a RICH TEXT field on the UX form: real records
  -- arrive as "<p>**TEST**&nbsp;Capsule was burnt...</p>". Tags and the
  -- handful of entities Plex emits are stripped so the text renders as text
  -- on a tile or in an email; the untouched value is kept beside it.
  TRIM(
    REGEXP_REPLACE(
      REGEXP_REPLACE(
        REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
          q.Brief_Description,
          '&nbsp;', ' '), '&amp;', '&'), '&lt;', '<'), '&gt;', '>'), '&quot;', '"'),
        r'<[^>]*>', ''),
      r'\s+', ' ')
  )                                               AS brief_description,
  q.Brief_Description                             AS brief_description_html,
  q.Full_Description                              AS full_description,

  SAFE_CAST(q.Quantity AS FLOAT64)                AS quantity,
  SAFE_CAST(q.Quantity_Rejected AS FLOAT64)       AS quantity_rejected,
  SAFE_CAST(q.Quantity_Returned AS FLOAT64)       AS quantity_returned,
  SAFE_CAST(q.Quantity_Scrapped AS FLOAT64)       AS quantity_scrapped,

  q.Root_Cause                                    AS root_cause,
  q.Root_Cause_Response                           AS root_cause_response,

  -- ⚠ NO `corrective_action` COLUMN ANY MORE, and that is not an oversight:
  -- Problem_2 has no Corrective_Action field. On the UX form the corrective
  -- and preventive actions live in the Problem Action family
  -- (Quality_v_Problem_Action_2 and friends), one row per action rather than
  -- one text box on the record — which is also why the CAPA/8D workflow can
  -- track several actions per problem. Those tables are not extracted yet;
  -- add them when somebody needs action-level reporting. `Response_Action`
  -- below is the record-level response text, NOT the same concept.
  q.Response_Action                               AS response_action,

  q.Final_Disposition                             AS final_disposition,

  SAFE_CAST(q.Cost AS FLOAT64)                    AS cost,

  -- Accountability / routing columns the classic view never exposed.
  -- Champion is a USER KEY, not a name — no user lookup is extracted yet, so
  -- it is surfaced as a key and named as one.
  SAFE_CAST(q.Champion AS INT64)                  AS champion_key,
  q.Department_No                                 AS department_no,
  SAFE_CAST(q.Building_Key AS INT64)              AS building_key,
  SAFE_CAST(q.Workcenter_Key AS INT64)            AS workcenter_key,
  SAFE_CAST(q.Job_Key AS INT64)                   AS job_key,
  SAFE_CAST(q.Job_Op_Key AS INT64)                AS job_op_key,
  SAFE_CAST(q.Recurrence AS INT64)                AS recurrence,

  -- DATE CONVERSION PATTERN: see reports/sql/work_orders_view.sql header —
  -- raw date columns can be INT64 nanoseconds, TIMESTAMP, or STRING.
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Problem_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS problem_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Recorded_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Recorded_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Recorded_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS recorded_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Problem_Due_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Problem_Due_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Problem_Due_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS due_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(q.Closed_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                               AS closed_date

FROM `{gcp_project}.{dataset}.raw_Quality_v_Problem_2` q

-- SAFE_CAST on both sides of every join — the repo rule, cheap insurance
-- against a nullable int landing as FLOAT64 or a 0-row table typed STRING.
LEFT JOIN `{gcp_project}.{dataset}.raw_Quality_v_Problem_Form` f
  ON SAFE_CAST(q.Problem_Form_Key AS INT64) = SAFE_CAST(f.Problem_Form_Key AS INT64)

-- Part_Key is -1 on a record with no part — the join simply finds nothing.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(q.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)
