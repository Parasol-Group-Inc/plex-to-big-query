-- inventory_top_quantity_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/inventory_top_quantity_view.sql
-- confidence: high
-- plex_views: Part_v_Container, Part_v_Part, Part_v_Part_Product_Type
-- notes: part_on_hand_inventory_report inlined as CTEs (locations and weight dropped, not output); RANK() by on-hand quantity.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part, ranked by on-hand quantity (highest first).
WITH on_hand AS (
  SELECT c.Part_Key AS part_key, SUM(c.Quantity) AS on_hand_qty, COUNT(*) AS container_count
  FROM Part_v_Container AS c
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY c.Part_Key
),

part_on_hand AS (
  SELECT
    p.Part_No          AS part_no,
    p.Name             AS part_name,
    pt.Product_Type    AS part_product_type,
    oh.on_hand_qty     AS on_hand_qty,
    oh.container_count AS container_count
  FROM on_hand AS oh
  JOIN Part_v_Part AS p
    ON oh.part_key = p.Part_Key
  LEFT JOIN Part_v_Part_Product_Type AS pt
    ON p.Product_Type_Key = pt.Product_Type_Key
)

SELECT
  h.part_no,
  h.part_name,
  h.part_product_type,
  h.on_hand_qty,
  h.container_count,
  RANK() OVER (ORDER BY h.on_hand_qty DESC) AS qty_rank
FROM part_on_hand AS h
ORDER BY qty_rank;
