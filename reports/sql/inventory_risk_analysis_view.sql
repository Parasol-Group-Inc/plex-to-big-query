-- inventory_risk_analysis_report — Vox | Inventory Risk Analysis (best-
-- criteria NetSuite parity for BOTH "Inventory Risk Analysis - Custom
-- Formula" and "Inventory Risk Analysis - Item Stock Type",
-- reports-list/supply-chain.md)
--
-- BEST-CRITERIA ASSUMPTION, NOT NETSUITE-CONFIRMED: Plex has no packaged
-- "risk"/"slow moving"/"aged inventory" concept anywhere in the schema or
-- the 14,350-row stored-procedure catalog (confirmed —
-- mapping/netsuite-report-mapping.md Round 2). This view assembles the raw
-- ingredients an aging/slow-moving analysis needs — on-hand quantity (same
-- source as part_on_hand_inventory_report) plus days since the container was
-- last touched (Part_v_Container.Update_Date).
--
-- DECIDED 2026-08-21 (best-criteria, not a NetSuite/business confirmation —
-- adjust if reports come out wrong): 90+ days since last container activity
-- (or no activity record at all) marks a part `is_at_risk`. 90 days is a
-- common general-purpose slow-moving-inventory convention, not something
-- derived from Vox's own policy — days_since_activity is still exposed
-- alongside the flag so the threshold can be changed with zero
-- recomputation if 90 turns out to be wrong for this business. Whether
-- Update_Date (last edit to the container row) is an acceptable proxy for
-- "last transaction date" is also still unconfirmed — Plex has no
-- dedicated last-transaction-date column on Part_v_Container.
--
-- "Item Stock Type" angle: Part_v_Part.Part_Type is inline text (no lookup
-- table — same pattern as Part_Status) and is included per-part below so
-- the same view can be grouped/filtered by stock type without a second
-- pipeline. Part_Type is generically "Raw Materials" for nearly every
-- part, though, so it's a weak stock-type signal — part_product_type
-- (added 2026-08-19, Part_v_Part.Product_Type_Key -> Part_v_Part_Product_Type,
-- already populated for 64/80 live parts) is the real one: it distinguishes
-- Vitamin/Mineral/Botanical Extract raw materials, Stock vs Custom Formula
-- Blend/Capsules, Blank/Custom/Labeled Bottle variants, Product/Fancy/
-- Outsourced Label, etc. — a far more actionable dimension for aging/risk
-- analysis than the generic Part_Type. Shared table, already extracted by
-- the sales_orders pipeline.
--
-- Not re-extracted — bq_view entry in reports/part_on_hand_inventory.yaml,
-- same raw_Part_v_Container / raw_Part_v_Container_Status / raw_Part_v_Part
-- tables as part_on_hand_inventory_report.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per part.

WITH

container_activity AS (
  SELECT
    SAFE_CAST(c.Part_Key AS INT64)        AS part_key,
    SUM(SAFE_CAST(c.Quantity AS FLOAT64)) AS on_hand_qty,
    COUNT(*)                              AS container_count,
    MAX(
      COALESCE(
        DATE(TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(c.Update_Date AS STRING) AS INT64), 0), 1000))),
        NULLIF(SAFE_CAST(CAST(c.Update_Date AS STRING) AS DATE), DATE '1970-01-01'),
        NULLIF(DATE(SAFE_CAST(CAST(c.Update_Date AS STRING) AS TIMESTAMP)), DATE '1970-01-01')
      )
    ) AS last_activity_date
  FROM `{gcp_project}.{dataset}.raw_Part_v_Container` c
  JOIN `{gcp_project}.{dataset}.raw_Part_v_Container_Status` cs
    ON CAST(c.Container_Status AS STRING) = CAST(cs.Container_Status AS STRING)
  WHERE SAFE_CAST(c.Active AS INT64) = -1
    AND SAFE_CAST(cs.OK_Status AS INT64) = -1
  GROUP BY part_key
)

SELECT

  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  p.Part_Type                                           AS part_type,
  pt.Product_Type                                       AS part_product_type,

  ca.on_hand_qty,
  ca.container_count,
  ca.last_activity_date,
  DATE_DIFF(CURRENT_DATE(), ca.last_activity_date, DAY) AS days_since_activity,

  -- 90-day threshold decision — see header note.
  (ca.last_activity_date IS NULL
    OR DATE_DIFF(CURRENT_DATE(), ca.last_activity_date, DAY) >= 90)  AS is_at_risk

FROM container_activity ca

JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON ca.part_key = p.Part_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` pt
  ON SAFE_CAST(p.Product_Type_Key AS FLOAT64) = SAFE_CAST(pt.Product_Type_Key AS FLOAT64)
