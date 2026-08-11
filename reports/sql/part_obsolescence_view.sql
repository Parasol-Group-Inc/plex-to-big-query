-- part_obsolescence_report — VOX | Products to be discontinued (NetSuite parity)
--
-- Schema confirmed via live query against vox.test.odbc.plex.com on 2026-08-10.
-- See docs/NETSUITE_REPORT_BUILD_PLAN.md (#77) for the confirmation log.
--
-- No joins needed: Part_v_Part.Part_Status is an inline text column, filtered
-- at extraction time in reports/part_obsolescence.yaml (WHERE Part_Status IN
-- ('Obsolete', 'Phase Out')). This view just does date conversion / column
-- selection on top of that already-filtered raw table.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- GRAIN: one row per part.

SELECT
  Part_No                                               AS part_number,
  Name                                                  AS part_name,
  Part_Type                                             AS part_type,
  Part_Status                                           AS part_status,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Updated_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(Updated_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(Updated_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS status_last_updated

FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Obsolescence`
