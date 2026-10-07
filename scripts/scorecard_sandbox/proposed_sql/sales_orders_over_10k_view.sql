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

-- PROPOSED (sandbox only, 2026-10-07): the order-line price.
-- This view priced solely off base_price (Part_v_Customer_Part_Price). Plex
-- has returned 0 rows for that view since the 2026-09-24 tenant cut-back, so
-- the table is frozen with keys that join 0/2,119 to current customer parts
-- and every price_ea/price_total in PlexTest is NULL. The same CTE already
-- lives in sales_mtd_by_status_change / sales_order_value_by_status /
-- pipeline_plex_value, where it prices 80-90% of rows; the 2026-09-04 switch
-- to the line item price was simply never applied here.
-- TIER RULE: prefer Primary_Price, then the lowest Breakpoint_Quantity, then
-- the most recent Effective_Date. Inactive rows are dropped.
line_price AS (
  SELECT
    PO_Line_Key,
    Price
  FROM (
    SELECT
      SAFE_CAST(PO_Line_Key AS INT64)             AS PO_Line_Key,
      SAFE_CAST(Price AS FLOAT64)                 AS Price,
      ROW_NUMBER() OVER (
        PARTITION BY SAFE_CAST(PO_Line_Key AS INT64)
        ORDER BY
          COALESCE(SAFE_CAST(Primary_Price AS INT64), 0) DESC,
          SAFE_CAST(Breakpoint_Quantity AS FLOAT64) ASC,
          SAFE_CAST(CAST(Effective_Date AS STRING) AS STRING) DESC
      ) AS rn
    FROM `{gcp_project}.{dataset}.raw_Sales_v_Price`
    WHERE COALESCE(SAFE_CAST(Active AS INT64), 1) != 0
  )
  WHERE rn = 1
),

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
    SUM(COALESCE(lp.Price, bp.Price) * SAFE_CAST(rel.Quantity AS FLOAT64)) AS order_total_computed
  FROM `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
    ON pol.PO_Line_Key = rel.PO_Line_Key
  LEFT JOIN base_price bp
    ON pol.Customer_Part_Key = bp.Customer_Part_Key

  LEFT JOIN line_price lp
    ON SAFE_CAST(pol.PO_Line_Key AS INT64) = lp.PO_Line_Key
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
