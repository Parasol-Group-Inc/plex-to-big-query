-- ─────────────────────────────────────────────────────────────────────────────
-- part_info_routing_container_report — "Audit - Part Info and Routing (Container Types)"
--
-- A line-by-line rebuild of the Plex stored procedure
-- Audit - Part_Info_and_Routing_wContainerType (Shannon Hadley), 2026-10-19.
-- Second view on the part_routing pipeline: it reuses every raw table that
-- part_info_routing_report already pulls, plus two of its own
-- (Part_v_Part_Operation_Approved_Container, Part_v_Container_Type).
--
-- GRAIN, as in the procedure: one row per SHIPPABLE part operation x approved
-- container type. An operation with no approved container appears once, with
-- the container columns NULL.
--
-- The procedure's two APPLY subqueries become pre-counts:
--   CROSS APPLY (SELECT COUNT(*) ... WHERE Part_Operation_Key = PO's)
--     -> op_container_counts; a COUNT always returns a row, so CROSS APPLY never
--        drops an operation — hence LEFT JOIN + COALESCE(…, 0) here.
--        Like the procedure, it does not filter by PCN (one PCN here anyway).
--   OUTER APPLY (COUNT of rows for the same op + container type + part + PCN
--     with [Primary] = 1)
--     -> primary_counts. 0 or 1 in practice (no operation lists a container
--        type twice — checked on Plex test 2026-10-19), and 0 when the row has
--        no container, because the procedure's comparisons against NULL match
--        nothing.
--
-- Joined in the procedure but never selected, so left out: Part_Op_Type and
-- Location are LEFT JOINs on their unique key (0 duplicate keys on PlexTest,
-- checked 2026-10-19), so they cannot add or remove a row.
--
-- primary / shippable / part_active / op_active come out as BOOL. Plex shows
-- [Primary] and Shippable as 1/0 (bit in Plex; INT64 0/1 in the raw tables).
-- Same values, different display.
--
-- INNER joins kept on purpose, exactly as in Plex: Part_Group, Part_Operation,
-- Operation, Plexus_User (part creator), Customer_Group_Member.
--
-- Two columns are ADDED after the procedure's own: standard_pack_quantity and
-- containers_per_master. The request was "a full list of these per part with
-- quantities per container", and the procedure selects no quantity. Drop them
-- here if strict parity with the Plex output is wanted.
--
-- Text compares are normalised (UPPER/RTRIM) because Plex's SQL Server ignores
-- case and trailing spaces; every key join SAFE_CASTs both sides (CLAUDE.md).
-- ─────────────────────────────────────────────────────────────────────────────

WITH op_container_counts AS (
  SELECT SAFE_CAST(Part_Operation_Key AS INT64) AS part_operation_key,
         COUNT(*)                               AS n
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Operation_Approved_Container`
  GROUP BY 1
),

primary_counts AS (
  SELECT SAFE_CAST(Part_Operation_Key AS INT64) AS part_operation_key,
         SAFE_CAST(Container_Type_Key AS INT64) AS container_type_key,
         SAFE_CAST(Part_Key AS INT64)           AS part_key,
         SAFE_CAST(PCN AS INT64)                AS pcn,
         COUNT(*)                               AS n
  FROM `{gcp_project}.{dataset}.raw_Part_v_Part_Operation_Approved_Container`
  WHERE COALESCE(SAFE_CAST(CAST(`Primary` AS STRING) AS BOOL),
                 SAFE_CAST(CAST(`Primary` AS STRING) AS INT64) <> 0) IS TRUE
  GROUP BY 1, 2, 3, 4
)

SELECT
  cgm.Plexus_Customer_No                                AS plexus_customer_no,
  cgm.Plexus_Customer_Code                              AS plexus_customer_code,
  p.Part_No                                             AS part_no,
  p.Revision                                            AS revision,
  p.Part_Status                                         AS part_status,
  COALESCE(SAFE_CAST(CAST(ps.Active AS STRING) AS BOOL),
           SAFE_CAST(CAST(ps.Active AS STRING) AS INT64) <> 0) AS part_active,  -- CAST(x AS BIT)
  COALESCE(
    TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(p.Created_Date AS STRING) AS INT64), 0), 1000)),
    NULLIF(SAFE_CAST(CAST(p.Created_Date AS STRING) AS TIMESTAMP), TIMESTAMP '1970-01-01')
  )                                                     AS created_date,
  p.Part_Type                                           AS part_type,
  pg.Part_Group                                         AS part_group,
  pu.Last_Name                                          AS created_by_last_name,
  po.Operation_No                                       AS operation_no,
  o.Operation_Code                                      AS operation_code,
  COALESCE(SAFE_CAST(CAST(po.Shippable AS STRING) AS BOOL),
           SAFE_CAST(CAST(po.Shippable AS STRING) AS INT64) <> 0) AS shippable,
  COALESCE(SAFE_CAST(CAST(po.Active AS STRING) AS BOOL),
           SAFE_CAST(CAST(po.Active AS STRING) AS INT64) <> 0) AS op_active,
  o.Inventory_Type                                      AS inventory_type,
  ct.Container_Type                                     AS container_type,
  COALESCE(SAFE_CAST(CAST(poac.`Primary` AS STRING) AS BOOL),
           SAFE_CAST(CAST(poac.`Primary` AS STRING) AS INT64) <> 0) AS `primary`,
  COALESCE(occ.n, 0)                                    AS tot_number_container_types,
  COALESCE(pc.n, 0)                                     AS is_primary,
  -- Added (not in the procedure) — see the header.
  poac.Standard_Pack_Quantity                           AS standard_pack_quantity,
  poac.Containers_Per_Master                            AS containers_per_master

FROM `{gcp_project}.{dataset}.raw_Part_v_Part` AS p

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Status` AS ps
  ON UPPER(RTRIM(ps.Part_Status)) = UPPER(RTRIM(p.Part_Status))
 AND SAFE_CAST(ps.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Group` AS pg
  ON SAFE_CAST(pg.Part_Group_Key AS INT64) = SAFE_CAST(p.Part_Group_Key AS INT64)
 AND SAFE_CAST(pg.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Operation` AS po
  ON SAFE_CAST(po.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)
 AND SAFE_CAST(po.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Operation` AS o
  ON SAFE_CAST(o.Operation_Key AS INT64) = SAFE_CAST(po.Operation_Key AS INT64)
 AND SAFE_CAST(o.Plexus_Customer_No AS INT64) = SAFE_CAST(po.Plexus_Customer_No AS INT64)

-- The procedure joins on Part_Key AND Part_Operation_Key, and the company
-- column is named PCN here.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Operation_Approved_Container` AS poac
  ON SAFE_CAST(poac.Part_Key AS INT64) = SAFE_CAST(po.Part_Key AS INT64)
 AND SAFE_CAST(poac.Part_Operation_Key AS INT64) = SAFE_CAST(po.Part_Operation_Key AS INT64)
 AND SAFE_CAST(poac.PCN AS INT64) = SAFE_CAST(po.Plexus_Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Container_Type` AS ct
  ON SAFE_CAST(ct.Container_Type_Key AS INT64) = SAFE_CAST(poac.Container_Type_Key AS INT64)
 AND SAFE_CAST(ct.Plexus_Customer_No AS INT64) = SAFE_CAST(poac.PCN AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` AS pu
  ON SAFE_CAST(pu.Plexus_User_No AS INT64) = SAFE_CAST(p.Created_By AS INT64)
 AND SAFE_CAST(pu.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

LEFT JOIN op_container_counts AS occ
  ON occ.part_operation_key = SAFE_CAST(po.Part_Operation_Key AS INT64)

LEFT JOIN primary_counts AS pc
  ON pc.part_operation_key = SAFE_CAST(poac.Part_Operation_Key AS INT64)
 AND pc.container_type_key = SAFE_CAST(poac.Container_Type_Key AS INT64)
 AND pc.part_key = SAFE_CAST(poac.Part_Key AS INT64)
 AND pc.pcn = SAFE_CAST(poac.PCN AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Customer_Group_Member` AS cgm
  ON SAFE_CAST(cgm.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

WHERE UPPER(RTRIM(p.Part_No)) <> 'MATL'
  -- "Added 2023.07.17 per team discussion" in the procedure.
  AND COALESCE(SAFE_CAST(CAST(po.Shippable AS STRING) AS BOOL),
               SAFE_CAST(CAST(po.Shippable AS STRING) AS INT64) <> 0) IS TRUE

ORDER BY plexus_customer_code, part_no, revision, operation_no
