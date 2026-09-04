-- shipping_pending_revenue_report — dollar value of units that are ready
-- to ship but haven't left the building yet (Plex-native candidate for
-- the Vox Nutrition Scorecard's "Total in Shipping"/"Revenue in Shipping"
-- Operational Health tile — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-01, per the Emilio/Jennilyn meeting (meetings-reference/Sep-1/).
-- Jennilyn was explicit this is a distinct concept from WIP
-- (sales_order_value_by_status_report): "this is revenue that is — it's
-- the revenue value of items that are done. They're in shipping, but they
-- haven't left the building yet... they might have 10,000 units ordered,
-- but 5,000 units are ready, and we'd only want the value of the 5,000
-- units that are ready to ship, not the 10,000 total... anything that's
-- open or pending is what we'd want to sum."
--
-- SCOPE: Sales_v_Shipper records that exist (i.e. units have been picked/
-- packed onto a shipment) but whose status isn't yet "Shipped" and isn't
-- "Canceled" — this is exactly the "open or pending" scope Jennilyn
-- described, and Shipper_Line.Quantity is already the "ready" quantity,
-- not the order's full quantity.
--
-- PRICE FALLBACK — DECIDED 2026-09-01: on this tenant's one real
-- not-yet-shipped Shipper_Line, Price was $0 (Plex appears to only
-- finalize Shipper_Line.Price once a shipment actually goes out). Rather
-- than report $0 for everything pending, this falls back to the
-- customer's base-tier price list (same join already used throughout this
-- pipeline) whenever Shipper_Line.Price is 0 or unset. This is an
-- estimate, not the eventual invoiced price — flag for review once more
-- pending shipments exist to compare against.
--
-- BOOLEAN CONVENTION: Sales_v_Shipper_Status uses 1 = true here (confirmed
-- live 2026-09-01) — see shipping_revenue_report.sql's header for the
-- full warning about this NOT being the -1 convention used elsewhere.
--
-- BLANKET ORDER FLAG: Jennilyn also asked to see "orders that are pending
-- that are labeled blanket" — bridges back through
-- Shipper_Line_Release -> Release -> PO_Line -> PO -> PO_Type.Blanket
-- (confirmed live: Sales_v_PO_Type.Blanket is a real boolean column).
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml, same
-- Sales_v_Shipper* tables as shipping_revenue_report.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per Shipper_Line that's ready but not yet shipped.

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
)

SELECT

  s.Shipper_No                                          AS shipper_no,
  ss.Shipper_Status                                     AS shipper_status,
  cust.Name                                             AS customer_name,
  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,

  SAFE_CAST(sl.Quantity AS FLOAT64)                     AS qty_ready,
  SAFE_CAST(sl.Price AS FLOAT64)                        AS shipper_line_price,
  bp.Price                                              AS customer_price_fallback,
  COALESCE(NULLIF(SAFE_CAST(sl.Price AS FLOAT64), 0), bp.Price)
                                                         AS effective_price,
  (SAFE_CAST(sl.Quantity AS FLOAT64)
    * COALESCE(NULLIF(SAFE_CAST(sl.Price AS FLOAT64), 0), bp.Price))
                                                         AS ready_value,

  (SAFE_CAST(potype.Blanket AS INT64) = 1)               AS is_blanket_order

FROM `{gcp_project}.{dataset}.raw_Sales_v_Shipper` s

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Line` sl
  ON SAFE_CAST(s.Shipper_Key AS INT64) = SAFE_CAST(sl.Shipper_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Status` ss
  ON SAFE_CAST(s.Shipper_Status_Key AS INT64) = SAFE_CAST(ss.Shipper_Status_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Customer` cust
  ON SAFE_CAST(s.Customer_No AS INT64) = SAFE_CAST(cust.Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON SAFE_CAST(sl.Part_Key AS INT64) = p.Part_Key

LEFT JOIN base_price bp
  ON SAFE_CAST(sl.Customer_Part_Key AS INT64) = bp.Customer_Part_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Shipper_Line_Release` slr
  ON SAFE_CAST(sl.Shipper_Line_Key AS INT64) = SAFE_CAST(slr.Shipper_Line_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_Release` rel
  ON SAFE_CAST(slr.Release_Key AS INT64) = SAFE_CAST(rel.Release_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Line` pol
  ON SAFE_CAST(rel.PO_Line_Key AS INT64) = SAFE_CAST(pol.PO_Line_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO` po
  ON SAFE_CAST(pol.PO_Key AS INT64) = SAFE_CAST(po.PO_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Sales_v_PO_Type` potype
  ON SAFE_CAST(po.PO_Type_Key AS INT64) = SAFE_CAST(potype.PO_Type_Key AS INT64)

WHERE COALESCE(SAFE_CAST(ss.Shipped AS INT64), 0) != 1
  AND COALESCE(SAFE_CAST(ss.Cancel_Status AS INT64), 0) != 1
