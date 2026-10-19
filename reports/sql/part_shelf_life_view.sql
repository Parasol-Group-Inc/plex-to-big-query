-- ─────────────────────────────────────────────────────────────────────────────
-- part_shelf_life_report — "Vox Nutrition Item List with Shelf Life Details"
--
-- A rebuild of the Plex SQL Development Environment query of the same name
-- (azancolli, 2025-04-02: "to validate shelf life configuration is enabled for
-- all items as appropriate"), 2026-10-19. Third view on the part_routing
-- pipeline: Part_v_Part is already pulled there; this adds Part_v_Part_Shelf_Life
-- and Part_v_Shelf_Life_Type.
--
-- GRAIN, as in Plex: one row per part x shelf-life record. A part with no
-- shelf life configured appears ONCE with the shelf-life columns NULL — that
-- is the row the report exists to find. A part configured with several
-- shelf-life types (e.g. sell-by and retest) appears once per type: 9,836
-- parts on PlexTest, 2026-10-19.
--
-- The procedure's commented-out filter `WHERE SL.Shelf_Life IS NULL` ("to see
-- items missing the shelf life") is exposed as the column
-- shelf_life_missing instead, so Looker can filter on it without a second view.
--
-- No MATL exclusion and no status filter: the procedure has neither.
-- Every key join SAFE_CASTs both sides (CLAUDE.md).
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
  p.Part_No                                  AS part_no,
  p.Revision                                 AS part_rev,
  p.Name                                     AS part_name,
  p.Part_Type                                AS part_type,
  slt.Description                            AS shelf_life_type,
  sl.Shelf_Life                              AS shelf_life,
  sl.Unit                                    AS shelf_life_units,
  p.Part_Status                              AS part_status,
  sl.Shelf_Life IS NULL                      AS shelf_life_missing

FROM `{gcp_project}.{dataset}.raw_Part_v_Part` AS p

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Shelf_Life` AS sl
  ON SAFE_CAST(sl.PCN AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)
 AND SAFE_CAST(sl.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Shelf_Life_Type` AS slt
  ON SAFE_CAST(slt.PCN AS INT64) = SAFE_CAST(sl.PCN AS INT64)
 AND SAFE_CAST(slt.Shelf_Life_Type_Key AS INT64) = SAFE_CAST(sl.Shelf_Life_Type_Key AS INT64)

ORDER BY part_no, part_rev, shelf_life_type
