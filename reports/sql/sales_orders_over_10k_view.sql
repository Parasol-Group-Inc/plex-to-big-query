-- sales_orders_over_10k_report — Vox | Orders over $10k (NetSuite parity,
-- reports-list/sales.md)
--
-- BEST-CRITERIA ASSUMPTION, NOT NETSUITE-CONFIRMED: Sales_v_PO_Line/
-- Sales_v_PO carry no direct "order total" dollar column (confirmed live
-- 2026-08-14 — Sales_v_PO_Line has only quantity/shipping fields). The
-- $10k basis used here is the same computed line total the base
-- sales_orders_report already exposes: base-tier Part_v_Customer_Part_Price
-- x Sales_v_Release.Quantity, summed per order. This does NOT include tax,
-- freight, or any Master_Price override on Sales_v_PO — flag for
-- data-scientist review: confirm whether "$10k" should be measured against
-- this computed total or something else (e.g. po.Master_Price directly,
-- where populated) before trusting this report.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per order (aggregated across lines) — different from the
-- line-level grain of sales_orders_report.

WITH

base_price AS (
  SELECT
    SAFE_CAST(Customer_Part_Key AS INT64)      AS Customer_Part_Key,
    SAFE_CAST(Price AS FLOAT64)                AS Price
  FROM (
    SELECT
      *,
      ROW_NUMBER() OVER (
        PARTITION BY Customer_Part_Key
        ORDER BY SAFE_CAST(Breakpoint_Quantity AS FLOAT64) ASC
      ) AS rn
    FROM `{gcp_project}.{dataset}.raw_Part_v_Customer_Part_Price`
  )
  WHERE rn = 1
),

line_totals AS (
  SELECT
    pol.PO_Key,
    SUM(bp.Price * SAFE_CAST(rel.Quantity AS FLOAT64)) AS order_total_computed
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
    ON pol.PO_Line_Key = rel.PO_Line_Key
  LEFT JOIN base_price bp
    ON pol.Customer_Part_Key = bp.Customer_Part_Key
  GROUP BY pol.PO_Key
)

SELECT

  po.PO_No                                              AS document_so,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(po.PO_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(po.PO_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS date_created,

  po.PO_Status_Key                                      AS status_key,
  sts.PO_Status                                         AS status,

  po.Customer_No,
  cust.Name                                             AS customer_name,

  lt.order_total_computed,
  po.Master_Price                                       AS order_total_master_price

FROM `{gcp_project}.{dataset}.raw_Sales_v_PO` po

JOIN line_totals lt
  ON po.PO_Key = lt.PO_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Status` sts
  ON po.PO_Status_Key = sts.PO_Status_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON po.Customer_No = cust.Customer_No

-- $10k threshold — see header note on basis.
WHERE lt.order_total_computed >= 10000
