-- part_on_hand_inventory_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/part_on_hand_inventory_view.sql
-- confidence: high
-- plex_views: Part_v_Container, Part_v_Part, Part_v_Part_Product_Type
-- notes: STRING_AGG(DISTINCT) is not T-SQL, so locations are de-duplicated in a subquery first (STRING_AGG needs SQL Server 2017+).
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part.
-- RULE: on hand = Active containers (Active = 1) whose Container_Status is OK, Hold,
--       Inspection Required or Hold for Design Order (name list, not OK_Status).
WITH on_hand AS (
  SELECT
    c.Part_Key              AS part_key,
    SUM(c.Quantity)         AS on_hand_qty,
    COUNT(*)                AS container_count,
    SUM(c.Net_Weight)       AS on_hand_weight   -- Net_Weight, not Gross_Weight
  FROM Part_v_Container AS c
  WHERE c.Active = 1
    AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  GROUP BY c.Part_Key
),

-- distinct container locations per part (a set, since location is per container)
locs AS (
  SELECT d.part_key,
         STRING_AGG(d.location, ', ') WITHIN GROUP (ORDER BY d.location) AS container_locations
  FROM (
    SELECT DISTINCT c.Part_Key AS part_key, NULLIF(LTRIM(RTRIM(c.Location)), '') AS location
    FROM Part_v_Container AS c
    WHERE c.Active = 1
      AND UPPER(LTRIM(RTRIM(c.Container_Status))) IN ('OK', 'HOLD', 'INSPECTION REQUIRED', 'HOLD FOR DESIGN ORDER')
  ) AS d
  GROUP BY d.part_key
)

SELECT
  oh.part_key              AS part_key,
  p.Part_No                AS part_no,
  p.Revision               AS revision,
  p.Name                   AS part_name,
  pt.Product_Type          AS part_product_type,
  p.Unit                   AS unit,
  oh.on_hand_qty           AS on_hand_qty,
  oh.on_hand_weight        AS on_hand_weight,
  oh.container_count       AS container_count,
  lc.container_locations   AS container_locations
FROM on_hand AS oh
JOIN Part_v_Part AS p
  ON oh.part_key = p.Part_Key
LEFT JOIN locs AS lc
  ON lc.part_key = oh.part_key
LEFT JOIN Part_v_Part_Product_Type AS pt
  ON p.Product_Type_Key = pt.Product_Type_Key;
