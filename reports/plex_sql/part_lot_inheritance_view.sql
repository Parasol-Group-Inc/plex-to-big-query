-- part_lot_inheritance_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/part_lot_inheritance_view.sql
-- confidence: medium
-- plex_views: Part_v_Part, Part_v_Part_Lot_Attribute, Part_v_Part_Operation_Lot_No_Inheritance_Override, Part_v_Part_Operation_Lot_No_Inheritance_Override_Component_Part, Part_v_Part_Operation_Lot_Date_Inheritance, Part_v_Part_Operation_Lot_Attribute_Inheritance, Part_v_Part_Inventory_Attributes, Part_v_Part_Lot_Format, Part_v_Lot_Format
-- notes: The per-table lookups were run in Plex SQL Developer on 2026-10-21 (93001-00VOXNU-0, 93056-BKVOXNU-1); this aggregated form was not. STRING_AGG needs SQL Server 2017+ (no DISTINCT there, so a component can repeat). Filtered to ONE part: remove the Part_No line for all active parts.
-- Translated 2026-10-21 from the BigQuery view.

-- GRAIN: one row per active part.
SELECT
  p.Part_No                                   AS part_no,
  p.Revision                                  AS part_rev,
  p.Name                                      AS part_name,
  ia.Lot_Required                             AS lot_required,
  ia.Lot_Replenishable                        AS lot_replenishable,
  (SELECT STRING_AGG(lf.Lot_Format, ', ')
     FROM Part_v_Part_Lot_Format AS plf
     JOIN Part_v_Lot_Format AS lf ON lf.Lot_Format_Key = plf.Lot_Format_Key
    WHERE plf.Part_Key = p.Part_Key)          AS lot_format,
  COALESCE(
    (SELECT STRING_AGG(CONCAT(cp.Part_No, '-', cp.Revision, ' ', cp.Name), ', ')
       FROM Part_v_Part_Operation_Lot_No_Inheritance_Override AS o
       JOIN Part_v_Part_Operation_Lot_No_Inheritance_Override_Component_Part AS oc
         ON oc.Part_Operation_Lot_No_Inheritance_Override_Key = o.Part_Operation_Lot_No_Inheritance_Override_Key
        AND oc.Active = 1
       JOIN Part_v_Part AS cp ON cp.Part_Key = oc.Component_Part_Key
      WHERE o.Part_Key = p.Part_Key AND o.Active = 1),
    'Generate')                               AS lot_no_inheritance,
  COALESCE(
    (SELECT STRING_AGG(CONCAT(cp.Part_No, '-', cp.Revision, ' ', cp.Name), ', ')
       FROM Part_v_Part_Operation_Lot_Date_Inheritance AS d
       JOIN Part_v_Part AS cp ON cp.Part_Key = d.Component_Part_Key
      WHERE d.Part_Key = p.Part_Key AND d.Active = 1),
    'None')                                   AS best_by_inheritance,
  (SELECT COUNT(*)
     FROM Part_v_Part_Operation_Lot_Attribute_Inheritance AS ai
    WHERE ai.Part_Key = p.Part_Key AND ai.Active = 1) AS inherited_attribute_count,
  (SELECT COUNT(*)
     FROM Part_v_Part_Lot_Attribute AS pla
    WHERE pla.Part_Key = p.Part_Key AND pla.Active = 1) AS own_lot_attribute_count
FROM Part_v_Part AS p
LEFT JOIN Part_v_Part_Inventory_Attributes AS ia
  ON ia.Part_Key = p.Part_Key
WHERE p.Part_Status = 'Active'
  AND p.Part_No = '93001-00VOXNU-0'
ORDER BY p.Part_No, p.Revision;
