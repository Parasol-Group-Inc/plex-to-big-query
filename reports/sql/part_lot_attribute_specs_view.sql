-- ─────────────────────────────────────────────────────────────────────────────
-- part_lot_attribute_specs_report — "Part Lot Attribute Specs"
--
-- The Plex screen Part > Part Lot Attributes, for every active part at once
-- (Jennilyn, 2026-10-21). GRAIN: one row per active part x active lot
-- attribute. Inactive Part_Lot_Attribute rows are retired versions and are not
-- extracted at all (filter in part_lot.yaml).
--
-- Screen column -> source:
--   Lot Attribute Code  Common_v_Attribute.Attribute_Code, reached through the
--                       TEMPLATE (pla.Attribute_Key is NULL in practice). Falls
--                       back to the template Description when the template has
--                       no attribute (seen once, on an inherited template).
--   Group / order       template -> Part_v_Lot_Attribute_Group; template Sort_Order
--   Display Type        Part_Lot_Attribute_Display_Type_Code; Reference likewise
--   Success Values      list specs with Success = 1, " | "-joined; numeric specs
--                       as "<= high | => low"; text specs' default value
--   Test Method / COA   Part_v_Part_Lot_Attribute_Test_Method / _Report lookups
--   Attachment          "Required" for a Document attribute whose test method
--                       is Required — the screen derives it; no column holds it
--
-- Verified 2026-10-21 against the screen for part 12149-01VOXNU-1 Rev 00
-- (34 attributes). Plex flags arrive as BOOL or INT depending on the driver,
-- hence the LOWER(CAST(... AS STRING)) IN ('1', 'true') tests.
-- Every key join SAFE_CASTs both sides (CLAUDE.md).
-- ─────────────────────────────────────────────────────────────────────────────

WITH
parts AS (
  SELECT
    SAFE_CAST(p.Part_Key AS INT64) AS part_key,
    p.Part_No, p.Revision, p.Name, p.Part_Type, p.Part_Status, g.Part_Group
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part` AS p
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Group` AS g
    ON SAFE_CAST(g.Part_Group_Key AS INT64) = SAFE_CAST(p.Part_Group_Key AS INT64)
  WHERE p.Part_Status = 'Active'
),

list_specs AS (
  SELECT
    SAFE_CAST(ls.Part_Lot_Attribute_Key AS INT64) AS pla_key,
    STRING_AGG(IF(LOWER(CAST(ls.Success AS STRING)) IN ('1', 'true'),
                  COALESCE(NULLIF(TRIM(ls.Display_Value), ''), ls.Value), NULL), ' | '
               ORDER BY SAFE_CAST(ls.Part_Lot_Attribute_List_Specification_Key AS INT64)) AS success_values,
    STRING_AGG(IF(LOWER(CAST(ls.Success AS STRING)) IN ('1', 'true'),
                  NULL, COALESCE(NULLIF(TRIM(ls.Display_Value), ''), ls.Value)), ' | '
               ORDER BY SAFE_CAST(ls.Part_Lot_Attribute_List_Specification_Key AS INT64)) AS fail_values,
    STRING_AGG(IF(LOWER(CAST(ls.`Default` AS STRING)) IN ('1', 'true'),
                  COALESCE(NULLIF(TRIM(ls.Display_Value), ''), ls.Value), NULL), ' | ') AS list_default
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Attribute_List_Specification` AS ls
  GROUP BY pla_key
),

numeric_specs AS (
  SELECT
    SAFE_CAST(ns.Part_Lot_Attribute_Key AS INT64) AS pla_key,
    -- ARRAY_TO_STRING drops NULL entries, so only the limits set appear. The
    -- IFs matter: FORMAT renders a NULL argument as the text "NULL".
    STRING_AGG(NULLIF(ARRAY_TO_STRING([
        IF(ns.High_Tolerance IS NULL, NULL, FORMAT('<= %.2f', SAFE_CAST(ns.High_Tolerance AS FLOAT64))),
        IF(ns.Low_Tolerance  IS NULL, NULL, FORMAT('=> %.2f', SAFE_CAST(ns.Low_Tolerance  AS FLOAT64))),
        IF(ns.Target_Value   IS NULL, NULL, FORMAT('target %.2f', SAFE_CAST(ns.Target_Value AS FLOAT64)))
      ], ' | '), ''), ' | ') AS numeric_values,
    MAX(SAFE_CAST(ns.Low_Tolerance  AS FLOAT64)) AS low_tolerance,
    MAX(SAFE_CAST(ns.High_Tolerance AS FLOAT64)) AS high_tolerance,
    MAX(SAFE_CAST(ns.Target_Value   AS FLOAT64)) AS target_value,
    MAX(CAST(ns.Default_Value AS STRING))        AS numeric_default
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Attribute_Numeric_Specification` AS ns
  GROUP BY pla_key
),

text_specs AS (
  SELECT
    SAFE_CAST(ts.Part_Lot_Attribute_Key AS INT64) AS pla_key,
    STRING_AGG(NULLIF(TRIM(ts.Default_Value), ''), ' | ') AS text_default
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Attribute_Text_Specification` AS ts
  GROUP BY pla_key
),

test_methods AS (
  SELECT
    SAFE_CAST(ptm.Part_Lot_Attribute_Key AS INT64) AS pla_key,
    STRING_AGG(DISTINCT tm.Description, ', ')       AS test_method,
    -- Reference lands as INT64 (numeric-only values), so cast before TRIM.
    STRING_AGG(DISTINCT NULLIF(TRIM(CAST(ptm.Reference AS STRING)), ''), ', ') AS test_method_reference,
    LOGICAL_OR(LOWER(CAST(ptm.Required AS STRING)) IN ('1', 'true')) AS test_method_required
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Attribute_Test_Method` AS ptm
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot_Attribute_Test_Method` AS tm
    ON SAFE_CAST(tm.Lot_Attribute_Test_Method_Key AS INT64) = SAFE_CAST(ptm.Lot_Attribute_Test_Method_Key AS INT64)
  GROUP BY pla_key
),

coa AS (
  SELECT
    SAFE_CAST(r.Part_Lot_Attribute_Key AS INT64) AS pla_key,
    STRING_AGG(DISTINCT rdt.Description, ', ')    AS coa_display
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Attribute_Report` AS r
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot_Attribute_Report_Display_Type` AS rdt
    ON SAFE_CAST(rdt.Lot_Attribute_Report_Display_Type_Key AS INT64) = SAFE_CAST(r.Lot_Attribute_Report_Display_Type_Key AS INT64)
  GROUP BY pla_key
),

-- Components this part inherits a given attribute (template) from.
inherited AS (
  SELECT
    SAFE_CAST(ai.Part_Key AS INT64)                   AS part_key,
    SAFE_CAST(ai.Lot_Attribute_Template_Key AS INT64) AS template_key,
    STRING_AGG(DISTINCT cp.Part_No, ', ')             AS inherited_from
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Operation_Lot_Attribute_Inheritance` AS ai
  LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part` AS cp
    ON SAFE_CAST(cp.Part_Key AS INT64) = SAFE_CAST(ai.Component_Part_Key AS INT64)
  WHERE LOWER(CAST(ai.Active AS STRING)) IN ('1', 'true')
  GROUP BY part_key, template_key
)

SELECT
  p.Part_No                                             AS part_no,
  p.Revision                                            AS part_rev,
  p.Name                                                AS part_name,
  p.Part_Type                                           AS part_type,
  p.Part_Group                                          AS part_group,
  SAFE_CAST(t.Sort_Order AS INT64)                      AS sort_order,
  COALESCE(a.Attribute_Code, t.Description)             AS lot_attribute_code,
  grp.Lot_Attribute_Group_Code                          AS attribute_group,
  dt.Part_Lot_Attribute_Display_Type_Code               AS display_type,
  dt.Reference                                          AS reference,
  COALESCE(ls.success_values, nsp.numeric_values)       AS success_values,
  ls.fail_values                                        AS fail_values,
  COALESCE(ls.list_default, nsp.numeric_default, tsp.text_default) AS default_value,
  nsp.low_tolerance,
  nsp.high_tolerance,
  nsp.target_value,
  u.Unit                                                AS unit,
  tm.test_method,
  tm.test_method_reference,
  COALESCE(tm.test_method_required, FALSE)              AS test_method_required,
  c.coa_display,
  IF(dt.Part_Lot_Attribute_Display_Type_Code = 'Document' AND tm.test_method_required,
     'Required', NULL)                                  AS attachment,
  LOWER(CAST(pla.Mandatory AS STRING)) IN ('1', 'true') AS mandatory,
  pla.Note                                              AS note,
  inh.inherited_from,
  LOWER(CAST(t.Active AS STRING)) IN ('1', 'true')      AS template_active,
  SAFE_CAST(pla.Part_Lot_Attribute_Key AS INT64)        AS part_lot_attribute_key

FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Attribute` AS pla

JOIN parts AS p
  ON p.part_key = SAFE_CAST(pla.Part_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot_Attribute_Template` AS t
  ON SAFE_CAST(t.Lot_Attribute_Template_Key AS INT64) = SAFE_CAST(pla.Lot_Attribute_Template_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Attribute` AS a
  ON SAFE_CAST(a.Attribute_Key AS INT64) = COALESCE(SAFE_CAST(pla.Attribute_Key AS INT64), SAFE_CAST(t.Attribute_Key AS INT64))

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Lot_Attribute_Group` AS grp
  ON SAFE_CAST(grp.Lot_Attribute_Group_Key AS INT64) = SAFE_CAST(t.Lot_Attribute_Group_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Lot_Attribute_Display_Type` AS dt
  ON SAFE_CAST(dt.Part_Lot_Attribute_Display_Type_Key AS INT64)
   = COALESCE(SAFE_CAST(pla.Part_Lot_Attribute_Display_Type_Key AS INT64),
              SAFE_CAST(t.Part_Lot_Attribute_Display_Type_Key AS INT64))

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Unit` AS u
  ON SAFE_CAST(u.Unit_Key AS INT64) = SAFE_CAST(pla.Unit_Key AS INT64)

LEFT JOIN list_specs    AS ls  ON ls.pla_key  = SAFE_CAST(pla.Part_Lot_Attribute_Key AS INT64)
LEFT JOIN numeric_specs AS nsp ON nsp.pla_key = SAFE_CAST(pla.Part_Lot_Attribute_Key AS INT64)
LEFT JOIN text_specs    AS tsp ON tsp.pla_key = SAFE_CAST(pla.Part_Lot_Attribute_Key AS INT64)
LEFT JOIN test_methods  AS tm  ON tm.pla_key  = SAFE_CAST(pla.Part_Lot_Attribute_Key AS INT64)
LEFT JOIN coa           AS c   ON c.pla_key   = SAFE_CAST(pla.Part_Lot_Attribute_Key AS INT64)
LEFT JOIN inherited     AS inh
  ON inh.part_key = p.part_key
 AND inh.template_key = SAFE_CAST(pla.Lot_Attribute_Template_Key AS INT64)

WHERE LOWER(CAST(pla.Active AS STRING)) IN ('1', 'true')
