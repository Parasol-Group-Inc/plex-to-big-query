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
--
-- ORDER / INVOICE NUMBERS (added 2026-10-29, Jennilyn's request):
--   order_no   — Sales_v_PO.Order_No, Plex's internal order number (162, 170…)
--   po_no      — Sales_v_PO.PO_No, the SO number plus customer PO as Plex
--                shows it ("SO0119700 / 1070")
--   invoice_no — Accounting_v_AR_Invoice.Invoice_No (INV0000004). The
--                shipper's AR link only carries Invoice_Link, a key that
--                does not equal the number, so the AR header is required.
-- The order chain joins on Shipper_Line.Release_Key directly: it matched
-- Sales_v_Shipper_Line_Release on every line in test and prod (2026-10-29),
-- and each line reaches exactly one PO, so these joins cannot fan out
-- revenue. A shipped-not-yet-invoiced line has a NULL invoice_no.
--
-- LIVE SOURCE (added 2026-11-05, OPEN_ITEMS D30): while Plex ODBC is frozen
-- (D20), the hourly laptop task loads Plex's own Shipper History and Shipping
-- Revenue by Part Group screens into PlexProd.live_shipper_history and
-- live_shipping_revenue (docs/PLEX_SCREEN_EXTRACTION.md). live_switch picks
-- them in PlexProd while the screens hold a shipper that ODBC's
-- raw_Sales_v_Shipper does not, i.e. until an ETL run brings fresh Plex data
-- (a frozen ODBC run still succeeds, so run status cannot be the test). Once
-- ODBC has caught up it reads ODBC again by itself; the two are never mixed.
-- data_source says which ran. PlexTest never changes. (Until 2026-11-06 the
-- test was "screens loaded within 3 hours", which fell back to the frozen
-- numbers every night after the 7 PM load.)
--   * One row per shipped line: Shipper History (ship date, quantity, order)
--     joined to the revenue screen on shipper_no + part number (unique on
--     both sides, every shipped line had its invoice row on 2026-11-05).
--   * price / shipping_revenue are the INVOICED net price and amount, where
--     ODBC uses Shipper_Line.Price. They agreed on every October line except
--     SH00105 (Shipper_Line.Price 2.53, invoiced at 1.265).
--   * Names come from the raw master tables by key, falling back to the
--     screen's own text for anything created after the freeze.
--   * The screens start 2026-10-01; this report's first ship date is 10-19.
--
-- AR INVOICE DEDUPE (2026-11-05): raw_Sales_v_Shipper_AR_Invoice held the same
-- (Shipper_Line_Key, Invoice_Link) row twice for SH00105, which doubled that
-- line. One row per (Shipper_Line_Key, Invoice_Link) is now kept.

WITH live_switch AS (
  SELECT
    '{dataset}' = 'PlexProd'
      AND EXISTS (
        SELECT 1
        FROM `{gcp_project}.PlexProd.live_shipper_history` lh
        WHERE lh.shipper_no NOT IN (
          SELECT os.Shipper_No
          FROM `{gcp_project}.{dataset}.raw_Sales_v_Shipper` os
          WHERE os.Shipper_No IS NOT NULL)
      ) AS use_live
),

live_lines AS (
  SELECT
    'live'                                              AS data_source,
    h.shipper_no                                        AS shipper_no,
    h.order_no                                          AS order_no,
    r.po_no                                             AS po_no,
    r.invoice_no                                        AS invoice_no,
    h.ship_date                                         AS ship_date,
    r.invoice_date                                      AS invoice_date,
    COALESCE(cust.Name, h.customer_code)                AS customer_name,
    COALESCE(p.Part_No, r.part_no,
             REGEXP_EXTRACT(h.part_no_revision, r'^(.*)-Rev '))
                                                         AS part_no,
    p.Name                                              AS part_name,
    r.part_group                                        AS part_group,
    h.quantity                                          AS quantity_shipped,
    r.net_unit_price                                    AS price,
    CAST(NULL AS FLOAT64)                               AS shipment_price_override,
    r.revenue                                           AS shipping_revenue
  FROM `{gcp_project}.PlexProd.live_shipper_history` h
  LEFT JOIN `{gcp_project}.PlexProd.live_shipping_revenue` r
    ON r.shipper_no = h.shipper_no
   AND r.part_no = REGEXP_EXTRACT(h.part_no_revision, r'^(.*)-Rev ')
  LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
    ON cust.Customer_Code = h.customer_code
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
    ON p.Part_Key = r.part_key
),

odbc_lines AS (
SELECT
  'odbc'                                                AS data_source,
  s.Shipper_No                                          AS shipper_no,
  po.Order_No                                           AS order_no,
  po.PO_No                                              AS po_no,
  ar.Invoice_No                                         AS invoice_no,
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
  pgrp.Part_Group                                       AS part_group,

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

LEFT JOIN (
  SELECT *
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Shipper_AR_Invoice`
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY SAFE_CAST(Shipper_Line_Key AS INT64), SAFE_CAST(Invoice_Link AS INT64)
    ORDER BY CAST(Add_Date AS STRING)) = 1
) inv
  ON SAFE_CAST(sl.Shipper_Line_Key AS INT64) = SAFE_CAST(inv.Shipper_Line_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Accounting_v_AR_Invoice` ar
  ON SAFE_CAST(inv.Invoice_Link AS INT64) = SAFE_CAST(ar.Invoice_Link AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON SAFE_CAST(sl.Release_Key AS INT64) = SAFE_CAST(rel.Release_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON SAFE_CAST(rel.PO_Line_Key AS INT64) = SAFE_CAST(pol.PO_Line_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO` po
  ON SAFE_CAST(pol.PO_Key AS INT64) = SAFE_CAST(po.PO_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(s.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(sl.Part_Key AS INT64) = p.Part_Key

-- Part group name. Part_v_Part.Part_Group_Key belongs to Part_v_Part_Group
-- (Capsule, Softgel, Label, ...), NOT Part_v_Part_Product_Group, which this
-- joined until 2026-09-24 and which is empty on this tenant (test and prod),
-- so every row read NULL -> one "(no group)" bar downstream.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Group` pgrp
  ON SAFE_CAST(p.Part_Group_Key AS INT64) = SAFE_CAST(pgrp.Part_Group_Key AS INT64)

WHERE SAFE_CAST(ss.Shipped AS INT64) = 1
)

SELECT * EXCEPT (data_source), data_source FROM (
  SELECT o.* FROM odbc_lines AS o CROSS JOIN live_switch AS sw WHERE NOT sw.use_live
  UNION ALL
  SELECT v.* FROM live_lines AS v CROSS JOIN live_switch AS sw WHERE sw.use_live
)
ORDER BY invoice_date DESC
