-- ─────────────────────────────────────────────────────────────────────────────
-- part_lot_inheritance_report — "Part Lot Inheritance"
--
-- The part's Lot Management box in Plex, for every active part (Jennilyn,
-- 2026-10-21: "only for active parts ... just a table so we can see gaps and
-- ensure things are lining up"). GRAIN: one row per active part.
--
-- What each column shows, as on the screen:
--   lot_no_inheritance      the component the lot number is taken from, as
--                           "<part no>-<rev> <name>"; "Generate" when the part
--                           has no active override (Plex builds the lot number
--                           from its lot format)
--   best_by_inheritance     the component the Best By date comes from; "None"
--   attribute_inheritance   "None" with no inherited attributes, the component
--                           with exactly one, "Multiple" with more (93001 shows
--                           "Multiple" with every attribute from one component)
--   *_from_part_nos         the component part numbers alone, comma-joined, for
--                           filtering and comparing
--
-- lot_no_matches_best_by is the "lining up" check: FALSE when the lot number
-- and the Best By date come from different components, or one is inherited
-- and the other is not.
--
-- Verified 2026-10-21 in Plex SQL Developer: 93001-00VOXNU-0 inherits all
-- three from 53001-00VOXNU-0; 93056-BKVOXNU-1 has none (Generate/None/None).
-- Every key join SAFE_CASTs both sides (CLAUDE.md).
-- ─────────────────────────────────────────────────────────────────────────────

WITH
all_parts AS (
  SELECT
    SAFE_CAST(p.Part_Key AS INT64) AS part_key,
    p.Part_No, p.Revision, p.Name, p.Part_Type, p.Part_Status, p.Part_Group_Key,
    CONCAT(p.Part_No, '-', COALESCE(p.Revision, ''), ' ', COALESCE(p.Name, '')) AS label
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part` AS p
),

lot_no AS (
  SELECT
    SAFE_CAST(o.Part_Key AS INT64)                 AS part_key,
    STRING_AGG(DISTINCT cp.label, ', ')            AS components,
    STRING_AGG(DISTINCT cp.Part_No, ', ')          AS part_nos
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Operation_Lot_No_Inheritance_Override` AS o
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Operation_Lot_No_Inheritance_Override_Component_Part` AS oc
    ON SAFE_CAST(oc.Part_Operation_Lot_No_Inheritance_Override_Key AS INT64)
     = SAFE_CAST(o.Part_Operation_Lot_No_Inheritance_Override_Key AS INT64)
   AND LOWER(CAST(oc.Active AS STRING)) IN ('1', 'true')
  LEFT JOIN all_parts AS cp
    ON cp.part_key = SAFE_CAST(oc.Component_Part_Key AS INT64)
  WHERE LOWER(CAST(o.Active AS STRING)) IN ('1', 'true')
  GROUP BY part_key
),

best_by AS (
  SELECT
    SAFE_CAST(d.Part_Key AS INT64)                 AS part_key,
    STRING_AGG(DISTINCT cp.label, ', ')            AS components,
    STRING_AGG(DISTINCT cp.Part_No, ', ')          AS part_nos
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Operation_Lot_Date_Inheritance` AS d
  LEFT JOIN all_parts AS cp
    ON cp.part_key = SAFE_CAST(d.Component_Part_Key AS INT64)
  WHERE LOWER(CAST(d.Active AS STRING)) IN ('1', 'true')
  GROUP BY part_key
),

attr AS (
  SELECT
    SAFE_CAST(ai.Part_Key AS INT64)                AS part_key,
    COUNT(*)                                       AS inherited_attribute_count,
    STRING_AGG(DISTINCT cp.label, ', ')            AS components,
    STRING_AGG(DISTINCT cp.Part_No, ', ')          AS part_nos
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Operation_Lot_Attribute_Inheritance` AS ai
  LEFT JOIN all_parts AS cp
    ON cp.part_key = SAFE_CAST(ai.Component_Part_Key AS INT64)
  WHERE LOWER(CAST(ai.Active AS STRING)) IN ('1', 'true')
  GROUP BY part_key
),

own_attr AS (
  SELECT SAFE_CAST(pla.Part_Key AS INT64) AS part_key, COUNT(*) AS own_lot_attribute_count
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Attribute` AS pla
  WHERE LOWER(CAST(pla.Active AS STRING)) IN ('1', 'true')
  GROUP BY part_key
),

lot_format AS (
  SELECT
    SAFE_CAST(plf.Part_Key AS INT64)          AS part_key,
    -- Lot_Format holds the token XML; the readable format (AABYYMMDD) is the description.
    STRING_AGG(DISTINCT lf.Lot_Format_Description, ', ')  AS lot_format
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Format` AS plf
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot_Format` AS lf
    ON SAFE_CAST(lf.Lot_Format_Key AS INT64) = SAFE_CAST(plf.Lot_Format_Key AS INT64)
  GROUP BY part_key
)

SELECT
  p.Part_No                                                     AS part_no,
  p.Revision                                                    AS part_rev,
  p.Name                                                        AS part_name,
  p.Part_Type                                                   AS part_type,
  g.Part_Group                                                  AS part_group,
  LOWER(CAST(ia.Lot_Required AS STRING)) IN ('1', 'true')       AS lot_required,
  LOWER(CAST(ia.Lot_Replenishable AS STRING)) IN ('1', 'true')  AS lot_replenishable,
  lf.lot_format,
  COALESCE(ln.components, IF(ln.part_key IS NULL, 'Generate', 'Inherited (component not found)'))
                                                                AS lot_no_inheritance,
  ln.part_nos                                                   AS lot_no_from_part_nos,
  COALESCE(bb.components, 'None')                               AS best_by_inheritance,
  bb.part_nos                                                   AS best_by_from_part_nos,
  CASE
    WHEN a.part_key IS NULL               THEN 'None'
    WHEN a.inherited_attribute_count = 1  THEN a.components
    ELSE 'Multiple'
  END                                                           AS attribute_inheritance,
  a.part_nos                                                    AS attribute_from_part_nos,
  COALESCE(a.inherited_attribute_count, 0)                      AS inherited_attribute_count,
  COALESCE(oa.own_lot_attribute_count, 0)                       AS own_lot_attribute_count,
  COALESCE(ln.part_nos, '') = COALESCE(bb.part_nos, '')         AS lot_no_matches_best_by

FROM all_parts AS p

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Group` AS g
  ON SAFE_CAST(g.Part_Group_Key AS INT64) = SAFE_CAST(p.Part_Group_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Inventory_Attributes` AS ia
  ON SAFE_CAST(ia.Part_Key AS INT64) = p.part_key

LEFT JOIN lot_format AS lf ON lf.part_key = p.part_key
LEFT JOIN lot_no     AS ln ON ln.part_key = p.part_key
LEFT JOIN best_by    AS bb ON bb.part_key = p.part_key
LEFT JOIN attr       AS a  ON a.part_key  = p.part_key
LEFT JOIN own_attr   AS oa ON oa.part_key = p.part_key

WHERE p.Part_Status = 'Active'
