-- shipping_revenue_report — shipped-unit revenue detail, sorted by invoice
-- date, with part-group breakdown (Plex-native replacement for the Vox
-- Nutrition Scorecard's Revenue tiles, corrected 2026-09-01 per the
-- Emilio/Jennilyn meeting — meetings-reference/Sep-1/. Jennilyn was
-- explicit that shipping revenue, not sales-order revenue, is correct:
-- "the shipping revenue should just be the units that went out the door,
-- the summed value of the units that went out the door... sorted by
-- invoice date... pretty nice to have by part group.")
--
-- LIVE-CONFIRMED 2026-09-01, not just tree-schema: the whole Sales_v_Shipper
-- family was extracted for the first time this session and returned real
-- rows on this tenant — 2 shippers, one actually Shipped with a real
-- $1.50 price x 17,000 qty = $25,500, 17 real cartons reconciling exactly
-- to that quantity, and 1 real AR invoice link.
--
-- BOOLEAN CONVENTION WARNING: Sales_v_Shipper_Status.Shipped uses 1 = true,
-- NOT the -1 = true convention already confirmed elsewhere in this
-- pipeline (Part_v_Container.Active, Container_Status.OK_Status, etc.) —
-- confirmed by checking this tenant's actual 4 status rows (Open/Pending/
-- Shipped/Canceled). Do not copy the -1 pattern here.
--
-- PRICE FIELD: uses Shipper_Line.Price (populated: $1.50 on the one real
-- Shipped line). Shipment_Price was 0 on that same row — appears to be an
-- unused override field, not populated by default — exposed as a
-- secondary column, not primary.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml. Raw
-- tables (Sales_v_Shipper/_Line/_Status/_AR_Invoice) added 2026-09-01,
-- same pipeline.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per Shipper_Line (one shipped part on one shipment).

SELECT
  s.Shipper_No                                          AS shipper_no,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(s.Ship_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS ship_date,
  COALESCE(
    DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(inv.Add_Date AS STRING) AS INT64), 0), 1000))),
    NULLIF(SAFE_CAST(CAST(inv.Add_Date AS STRING) AS DATE), DATE '1970-01-01'),
    NULLIF(DATE(SAFE_CAST(CAST(inv.Add_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
  )                                                     AS invoice_date,

  cust.Name                                             AS customer_name,
  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  pgrp.Part_Product_Group                               AS part_group,

  SAFE_CAST(sl.Quantity AS FLOAT64)                     AS quantity_shipped,
  SAFE_CAST(sl.Price AS FLOAT64)                        AS price,
  SAFE_CAST(sl.Shipment_Price AS FLOAT64)               AS shipment_price_override,
  (SAFE_CAST(sl.Quantity AS FLOAT64) * SAFE_CAST(sl.Price AS FLOAT64))
                                                         AS shipping_revenue

FROM `{gcp_project}.{dataset}.raw_Sales_v_Shipper` s

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Line` sl
  ON SAFE_CAST(s.Shipper_Key AS INT64) = SAFE_CAST(sl.Shipper_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Status` ss
  ON SAFE_CAST(s.Shipper_Status_Key AS INT64) = SAFE_CAST(ss.Shipper_Status_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_AR_Invoice` inv
  ON SAFE_CAST(sl.Shipper_Line_Key AS INT64) = SAFE_CAST(inv.Shipper_Line_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(s.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(sl.Part_Key AS INT64) = p.Part_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Group` pgrp
  ON SAFE_CAST(p.Part_Group_Key AS INT64) = SAFE_CAST(pgrp.Part_Product_Group_Key AS INT64)

WHERE SAFE_CAST(ss.Shipped AS INT64) = 1

ORDER BY invoice_date DESC
