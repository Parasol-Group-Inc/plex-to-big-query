-- inventory_out_of_stock_report — parts that are genuinely out of stock,
-- by Vox's own definition (Plex-native candidate for the Vox Nutrition
-- Scorecard's "OOS" Operational Health tile, replacing the earlier guess
-- at inventory_risk_analysis_report.is_at_risk — see
-- score-card-reference/VOX_SCORECARD_PLEX_MIGRATION_MAP.md)
--
-- NEW 2026-09-01, per the Emilio/Jennilyn meeting (meetings-reference/Sep-1/).
-- Jennilyn gave the exact rule, not a general risk heuristic:
-- "for us to be out of stock, it has to start with 33 for the part
-- number, and it has to have a minimum stock level... if the inventory
-- amount is negative, or we have zero inventory and we have demand...
-- sometimes we make custom parts, those are okay to be negative, because
-- that's just showing us we're in the process of making this part, it's
-- not actually something we stock."
--
-- Three conditions, all required:
--   1. Part_No LIKE '33%'
--   2. Part_v_Part.Minimum_Inventory_Quantity > 0 — DECIDED 2026-09-01: a
--      literal 0 counts as "not assigned," not a valid zero threshold (2
--      of the 7 real '33' parts on this tenant have exactly 0.0 here).
--   3. quantity_available (on-hand minus allocated) < 0, EXCLUDING parts
--      whose Product_Type indicates Custom (Part_v_Part_Product_Type has
--      real "Custom Formula Capsules"/"Custom Blank Bottle"/etc. values
--      confirmed live, vs. "Stock Formula Capsules"/etc. — see
--      part_on_hand_inventory_view.sql's header for the same lookup).
--
-- On-hand quantity reuses part_on_hand_inventory_view.sql's exact,
-- already-confirmed-live pattern (Part_v_Container.Active = -1 AND
-- Container_Status.OK_Status = -1) rather than re-deriving it — same
-- shared raw tables, not re-extracted here (owned by the
-- part_on_hand_inventory pipeline).
--
-- Allocated quantity comes from Sales_v_Release_Allocation.Quantity_Allocated
-- (added 2026-09-01, same session) — CURRENTLY 0 ROWS on this tenant, so
-- this view returns 0 rows for a genuinely empty-upstream reason, not a
-- bug. Its boolean/Active convention (if any) has never been checked
-- against real data since there's none to check yet — re-verify once rows
-- exist before trusting an Active filter here; none is applied for now.
--
-- BOOLEAN CONVENTION: Part_v_Container.Active/Container_Status.OK_Status
-- use -1 = true (the OTHER convention confirmed elsewhere in this
-- pipeline) — do not confuse with the 1 = true convention just confirmed
-- on Sales_v_Shipper_Status/Sales_v_PO_Status in the sibling views built
-- this same session.
--
-- Not re-extracted — bq_view entry in reports/sales_orders.yaml.
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per out-of-stock part.

WITH

on_hand AS (
  SELECT
    SAFE_CAST(c.Part_Key AS INT64)        AS part_key,
    SUM(SAFE_CAST(c.Quantity AS FLOAT64)) AS on_hand_qty
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

allocated AS (
  SELECT
    SAFE_CAST(Part_Key AS INT64)                       AS part_key,
    SUM(SAFE_CAST(Quantity_Allocated AS FLOAT64))      AS allocated_qty
  FROM `{gcp_project}.{dataset}.raw_Sales_v_Release_Allocation`
  GROUP BY part_key
)

SELECT

  p.Part_No                                             AS part_no,
  p.Name                                                AS part_name,
  pt.Product_Type                                       AS product_type,
  SAFE_CAST(p.Minimum_Inventory_Quantity AS FLOAT64)    AS minimum_inventory_quantity,
  COALESCE(oh.on_hand_qty, 0)                           AS on_hand_qty,
  COALESCE(al.allocated_qty, 0)                         AS allocated_qty,
  (COALESCE(oh.on_hand_qty, 0) - COALESCE(al.allocated_qty, 0))
                                                         AS quantity_available

FROM `{gcp_project}.{dataset}.raw_Part_v_Part` p

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Product_Type` pt
  ON SAFE_CAST(p.Product_Type_Key AS FLOAT64) = SAFE_CAST(pt.Product_Type_Key AS FLOAT64)

LEFT JOIN on_hand oh
  ON SAFE_CAST(p.Part_Key AS INT64) = oh.part_key

LEFT JOIN allocated al
  ON SAFE_CAST(p.Part_Key AS INT64) = al.part_key

WHERE p.Part_No LIKE '33%'
  AND SAFE_CAST(p.Minimum_Inventory_Quantity AS FLOAT64) > 0
  AND (COALESCE(oh.on_hand_qty, 0) - COALESCE(al.allocated_qty, 0)) < 0
  AND COALESCE(pt.Product_Type, '') NOT LIKE 'Custom%'
