-- part_lot_attribute_specs_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/part_lot_attribute_specs_view.sql
-- confidence: medium
-- plex_views: Part_v_Part, Part_v_Part_Group, Part_v_Part_Lot_Attribute, Part_v_Lot_Attribute_Template, Common_v_Attribute, Part_v_Lot_Attribute_Group, Part_v_Part_Lot_Attribute_Display_Type, Part_v_Part_Lot_Attribute_List_Specification, Part_v_Part_Lot_Attribute_Numeric_Specification, Part_v_Part_Lot_Attribute_Test_Method, Part_v_Lot_Attribute_Test_Method, Common_v_Unit
-- notes: The joins were run in Plex SQL Developer on 2026-10-21 (part 12149-01VOXNU-1 Rev 00, 34 attributes); this aggregated form was not. STRING_AGG needs SQL Server 2017+. Text specs, COA display and inherited_from omitted. Filtered to ONE part: remove the Part_No line for all parts (150k rows).
-- Translated 2026-10-21 from the BigQuery view.

-- GRAIN: one row per active part x active lot attribute.
SELECT
  p.Part_No                                   AS part_no,
  p.Revision                                  AS part_rev,
  p.Name                                      AS part_name,
  g.Part_Group                                AS part_group,
  t.Sort_Order                                AS sort_order,
  COALESCE(a.Attribute_Code, t.Description)   AS lot_attribute_code,
  grp.Lot_Attribute_Group_Code                AS attribute_group,
  dt.Part_Lot_Attribute_Display_Type_Code     AS display_type,
  dt.Reference                                AS reference,
  COALESCE(
    (SELECT STRING_AGG(COALESCE(NULLIF(ls.Display_Value, ''), ls.Value), ' | ')
       FROM Part_v_Part_Lot_Attribute_List_Specification AS ls
      WHERE ls.Part_Lot_Attribute_Key = pla.Part_Lot_Attribute_Key AND ls.Success = 1),
    (SELECT STRING_AGG(CONCAT('<= ', ns.High_Tolerance, ' | => ', ns.Low_Tolerance), ' | ')
       FROM Part_v_Part_Lot_Attribute_Numeric_Specification AS ns
      WHERE ns.Part_Lot_Attribute_Key = pla.Part_Lot_Attribute_Key)
  )                                           AS success_values,
  u.Unit                                      AS unit,
  (SELECT STRING_AGG(tm.Description, ', ')
     FROM Part_v_Part_Lot_Attribute_Test_Method AS ptm
     JOIN Part_v_Lot_Attribute_Test_Method AS tm
       ON tm.Lot_Attribute_Test_Method_Key = ptm.Lot_Attribute_Test_Method_Key
    WHERE ptm.Part_Lot_Attribute_Key = pla.Part_Lot_Attribute_Key) AS test_method,
  pla.Mandatory                               AS mandatory,
  pla.Note                                    AS note,
  pla.Part_Lot_Attribute_Key                  AS part_lot_attribute_key
FROM Part_v_Part_Lot_Attribute AS pla
JOIN Part_v_Part AS p
  ON p.Part_Key = pla.Part_Key
LEFT JOIN Part_v_Part_Group AS g
  ON g.Part_Group_Key = p.Part_Group_Key
LEFT JOIN Part_v_Lot_Attribute_Template AS t
  ON t.Lot_Attribute_Template_Key = pla.Lot_Attribute_Template_Key
LEFT JOIN Common_v_Attribute AS a
  ON a.Attribute_Key = COALESCE(pla.Attribute_Key, t.Attribute_Key)
LEFT JOIN Part_v_Lot_Attribute_Group AS grp
  ON grp.Lot_Attribute_Group_Key = t.Lot_Attribute_Group_Key
LEFT JOIN Part_v_Part_Lot_Attribute_Display_Type AS dt
  ON dt.Part_Lot_Attribute_Display_Type_Key = COALESCE(pla.Part_Lot_Attribute_Display_Type_Key, t.Part_Lot_Attribute_Display_Type_Key)
LEFT JOIN Common_v_Unit AS u
  ON u.Unit_Key = pla.Unit_Key
WHERE pla.Active = 1
  AND p.Part_Status = 'Active'
  AND p.Part_No = '12149-01VOXNU-1' AND p.Revision = 'Rev 00'
ORDER BY p.Part_No, p.Revision, t.Sort_Order;
