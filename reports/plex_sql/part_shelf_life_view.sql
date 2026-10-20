-- part_shelf_life_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/part_shelf_life_view.sql
-- confidence: high
-- plex_views: Part_v_Part, Part_v_Part_Shelf_Life, Part_v_Shelf_Life_Type
-- notes: Mechanical translation; shelf_life_missing returned as 1/0. No extraction-time filters.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part (and shelf-life record, if any).
-- RULE: parts without a shelf-life record are kept, flagged shelf_life_missing = 1.
SELECT
  p.Part_No                                  AS part_no,
  p.Revision                                 AS part_rev,
  p.Name                                     AS part_name,
  p.Part_Type                                AS part_type,
  slt.Description                            AS shelf_life_type,
  sl.Shelf_Life                              AS shelf_life,
  sl.Unit                                    AS shelf_life_units,
  p.Part_Status                              AS part_status,
  CASE WHEN sl.Shelf_Life IS NULL THEN 1 ELSE 0 END AS shelf_life_missing
FROM Part_v_Part AS p
LEFT JOIN Part_v_Part_Shelf_Life AS sl
  ON sl.PCN = p.Plexus_Customer_No             -- this view names its customer column PCN
 AND sl.Part_Key = p.Part_Key
LEFT JOIN Part_v_Shelf_Life_Type AS slt
  ON slt.PCN = sl.PCN
 AND slt.Shelf_Life_Type_Key = sl.Shelf_Life_Type_Key
ORDER BY p.Part_No, p.Revision, slt.Description;
