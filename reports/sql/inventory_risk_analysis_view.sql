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
  -- ⚠ REWRITTEN 2026-09-04 — the previous filter matched ZERO rows.
  -- It read `c.Active = -1 AND cs.OK_Status = -1`. Confirmed live against
  -- this tenant: Part_v_Container.Active holds 1/0 and
  -- Part_v_Container_Status.OK_Status holds 1/0 — NOT the -1 convention the
  -- old comment claimed. 122 real containers existed the whole time while
  -- every inventory report reported 0 rows and the docs blamed an "empty
  -- upstream extract."
  --
  -- The status test is now an explicit name list, not OK_Status, because
  -- OK_Status cannot express Vox's rule (given 2026-09-04): on-hand =
  -- Hold + Inspection Required + OK + Hold for Design Order, excluding
  -- Defective and Expired. Against the real lookup, OK_Status is 0 on Hold
  -- and Inspection Required (which must be INCLUDED) and 1 on Allocated,
  -- Loaded, Shipped and Staged (which must NOT be, or shipped goods count
  -- as on hand). Naming the four statuses is the only faithful encoding.
  --
  -- The Container_Status lookup join is gone on purpose: nothing here
  -- selected from it, and the extracted copy is STALE — Plex has 16
  -- statuses including 'HOLD FOR DESIGN ORDER' (key 10281) while the raw
  -- table has 15 and is missing exactly that one. An INNER join would drop
  -- any container in a status the stale lookup hasn't caught up with, which
  -- is the same class of silent-row-loss bug already fixed in the 4 Daily
  -- Reports. Filtering on the container's own status string avoids it.
  WHERE SAFE_CAST(c.Active AS INT64) = 1
    AND UPPER(TRIM(CAST(c.Container_Status AS STRING))) IN (
          'OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY part_key
),

-- BigQuery can't reference a SELECT-list alias from another expression in
-- the same SELECT list, so days_since_activity is computed once here and
-- reused below for both days_since_activity and is_at_risk instead of
-- evaluating the same DATE_DIFF twice per row.
enriched AS (
  SELECT

    p.Part_No                                             AS part_no,
    p.Name                                                AS part_name,
    p.Part_Type                                           AS part_type,
    pt.Product_Type                                       AS part_product_type,

    ca.on_hand_qty,
    ca.container_count,
    ca.last_activity_date,
    DATE_DIFF(CURRENT_DATE(), ca.last_activity_date, DAY) AS days_since_activity

  FROM container_activity ca

  JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
    ON ca.part_key = p.Part_Key

  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` pt
    ON SAFE_CAST(p.Product_Type_Key AS FLOAT64) = SAFE_CAST(pt.Product_Type_Key AS FLOAT64)
)

SELECT
  *,
  -- 90-day threshold decision — see header note.
  (last_activity_date IS NULL OR days_since_activity >= 90) AS is_at_risk
FROM enriched
