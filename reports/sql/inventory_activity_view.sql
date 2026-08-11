-- inventory_activity_report — Inventory Activity Detail Usage Per Month (NetSuite parity)
--
-- Schema confirmed via live query against vox.test.odbc.plex.com on 2026-08-10
-- (both source views EMPTY on the test tenant — columns confirmed, no sample
-- data to validate actual values against). See docs/NETSUITE_REPORT_BUILD_PLAN.md
-- (#29) for the confirmation log and the genealogy-vs-activity caveat.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- GRAIN: one row per part per calendar month — production and usage
-- (depletion) quantities summed separately, netted into net_change.
--
-- See the DATE CONVERSION PATTERN comment in reports/sql/sales_orders_view.sql
-- for why every date column below routes through CAST(... AS STRING) first.

WITH

production_dated AS (
  SELECT
    SAFE_CAST(Part_Key AS INT64) AS Part_Key,
    SAFE_CAST(Quantity AS FLOAT64) AS Quantity,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Production_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(Production_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(Production_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS production_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Cell_Production`
),

depletion_dated AS (
  SELECT
    SAFE_CAST(Part_Key AS INT64) AS Part_Key,
    SAFE_CAST(Quantity AS FLOAT64) AS Quantity,
    COALESCE(
      DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(Production_Date AS STRING) AS INT64), 0), 1000))),
      NULLIF(SAFE_CAST(CAST(Production_Date AS STRING) AS DATE), DATE '1970-01-01'),
      NULLIF(DATE(SAFE_CAST(CAST(Production_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
    ) AS depletion_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Cell_Depletion`
),

production_monthly AS (
  SELECT
    Part_Key,
    DATE_TRUNC(production_date, MONTH) AS activity_month,
    SUM(Quantity) AS produced_quantity
  FROM production_dated
  WHERE production_date IS NOT NULL
  GROUP BY Part_Key, activity_month
),

depletion_monthly AS (
  SELECT
    Part_Key,
    DATE_TRUNC(depletion_date, MONTH) AS activity_month,
    SUM(Quantity) AS depleted_quantity
  FROM depletion_dated
  WHERE depletion_date IS NOT NULL
  GROUP BY Part_Key, activity_month
)

SELECT
  COALESCE(prod.Part_Key, dep.Part_Key)           AS part_key,
  p.Part_No                                       AS part_number,
  p.Name                                          AS part_name,
  COALESCE(prod.activity_month, dep.activity_month) AS activity_month,
  COALESCE(prod.produced_quantity, 0)             AS produced_quantity,
  COALESCE(dep.depleted_quantity, 0)              AS depleted_quantity,
  COALESCE(prod.produced_quantity, 0) - COALESCE(dep.depleted_quantity, 0) AS net_change

FROM production_monthly prod
FULL OUTER JOIN depletion_monthly dep
  ON prod.Part_Key = dep.Part_Key AND prod.activity_month = dep.activity_month

-- Part_v_Part is shared with the sales_orders pipeline — not re-extracted here.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON COALESCE(prod.Part_Key, dep.Part_Key) = p.Part_Key
