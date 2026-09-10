-- part_on_hand_inventory_report — Vox Nutrition on-hand inventory by part
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/part_on_hand_inventory_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime by the
-- container using the GCP_PROJECT and BQ_DATASET environment variables.
--
-- GRAIN: one row per part. On-hand quantity is SUM(Quantity) across all
-- Part_v_Container rows for that part, filtered to containers that are
-- both Active and in an OK-type status (see the WHERE clause below — the status rule is an explicit
-- name list, and Active is 1, not -1).
--
-- Part_v_Container is the real on-hand-inventory carrier in this Plex
-- tenant — it lives under the Part module, not Warehouse
-- (Warehouse_v_Part_Quantity does not exist). See
-- reports/part_on_hand_inventory.yaml header for the confirmation note.
--
-- SAFE_CAST numeric comparisons throughout: Part_v_Container may be empty
-- (and therefore all-STRING) on a given tenant/run, while raw_Part_v_Part
-- already has a real INT64 schema. Container_Status itself is NOT cast to
-- INT64 -- like Part_v_Part.Part_Status, it has no "_Key" suffix, which in
-- this codebase's confirmed pattern means it's an inline TEXT value that
-- matches Container_Status_Lookup.Container_Status by text, not a numeric
-- key. Casting it to INT64 would compile but silently match zero rows
-- once real data appears.
--
-- part_product_type (added 2026-08-19): Part_v_Part.Product_Type_Key ->
-- Part_v_Part_Product_Type.Product_Type -- a real, already-populated
-- (64/80 parts live) classification (Vitamin, Mineral, Botanical Extract,
-- Stock/Custom Formula Blend, Blank/Custom/Labeled Bottle, Product Label,
-- etc.), unlike Part_v_Part.Part_Type which is inline text and generically
-- "Raw Materials" for nearly every part. Shared table, already extracted
-- by the sales_orders pipeline -- not re-extracted here.

WITH

on_hand AS (
  SELECT
    SAFE_CAST(c.Part_Key AS INT64)      AS part_key,
    SUM(SAFE_CAST(c.Quantity AS FLOAT64)) AS on_hand_qty,
    COUNT(*)                             AS container_count,
    -- Added 2026-09-09 for parity with Plex's own "Inventory Summary" (VP)
    -- screen, which Amber named as the place to see on-hand: its columns are
    -- Part Number / Revision / Description / Containers / Quantity / Weight.
    -- Quantity and Containers were already here; Weight is Net_Weight (NOT
    -- Gross_Weight, which includes the container's own Tare_Weight, nor
    -- Part_Operation_Weight, which is a per-operation standard, not what is
    -- physically in the container).
    SUM(SAFE_CAST(c.Net_Weight AS FLOAT64)) AS on_hand_weight,
    -- Location is per-container, so at part grain it can only be a set. The
    -- screen offers a Building filter rather than a column; this keeps the
    -- information without inventing a single "the" location for a part whose
    -- containers are spread across several.
    STRING_AGG(DISTINCT NULLIF(TRIM(CAST(c.Location AS STRING)), ''), ', '
               ORDER BY NULLIF(TRIM(CAST(c.Location AS STRING)), ''))
                                         AS container_locations
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
)

SELECT

  -- part_key exposed 2026-09-09 so downstream views can join on the key
  -- instead of matching on part_no text. inventory_available_to_sell_view
  -- reads this view rather than re-deriving the container filter for a THIRD
  -- time — the copy-paste of that filter is exactly how the `= -1` bug
  -- survived in three places at once until 2026-09-04.
  oh.part_key                  AS part_key,
  p.Part_No                   AS part_no,
  p.Revision                   AS revision,
  p.Name                      AS part_name,
  pt.Product_Type              AS part_product_type,
  p.Unit                       AS unit,
  oh.on_hand_qty               AS on_hand_qty,
  oh.on_hand_weight            AS on_hand_weight,
  oh.container_count           AS container_count,
  oh.container_locations       AS container_locations

FROM on_hand oh

JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` p
  ON oh.part_key = p.Part_Key

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` pt
  ON SAFE_CAST(p.Product_Type_Key AS FLOAT64) = SAFE_CAST(pt.Product_Type_Key AS FLOAT64)
