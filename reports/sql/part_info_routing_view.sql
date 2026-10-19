-- ─────────────────────────────────────────────────────────────────────────────
-- part_info_routing_report — "Audit - Part Info and Routing"
--
-- A line-by-line rebuild of the Plex stored procedure Audit - Part_Info_and_Routing
-- (Shannon Hadley, SQL Development Environment), 2026-10-19. Same joins, same
-- join TYPES (JOIN vs LEFT JOIN), same filter, same column order. Only the
-- names change: BigQuery columns cannot hold spaces, so 'Part Active' becomes
-- part_active and so on.
--
-- GRAIN, as in the procedure: one row per part operation x approved workcenter
-- x approved supplier. An operation with three approved workcenters and two
-- approved suppliers appears six times. That fan-out is the procedure's own;
-- count distinct (part_no, revision, operation_no) for "how many operations".
--
-- INNER joins that drop rows, kept on purpose to match Plex:
--   Part_Group     a part with no group is not in the procedure's output
--   Part_Operation a part with no routing is not either
--   Operation      nor an operation step whose operation is missing
--   Plexus_User    nor a part whose creator user no longer exists
--   Customer_Group_Member  the PCN row
--
-- Parameters the procedure takes and this view does not:
--   @PCN_Keys        this connection sees one PCN (338756, Vox Nutrition)
--   @Building_Codes  filter on main_building in Looker instead
--
-- Every join compares SAFE_CAST(... AS INT64) on BOTH sides: raw columns can
-- land as STRING when a table was empty at extraction (CLAUDE.md).
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
  cgm.Plexus_Customer_No                                AS plexus_customer_no,
  cgm.Plexus_Customer_Code                              AS plexus_customer_code,
  p.Part_No                                             AS part_no,
  p.Revision                                            AS revision,
  p.Old_Part_No                                         AS old_part_no,
  p.Part_Status                                         AS part_status,
  COALESCE(SAFE_CAST(CAST(ps.Active AS STRING) AS BOOL),
           SAFE_CAST(CAST(ps.Active AS STRING) AS INT64) <> 0) AS part_active,  -- CAST(x AS BIT): any non-zero is 1
  -- Plex dates land as INT64 nanoseconds or as a string, depending on the
  -- table; 1970-01-01 is an empty date, not a real one.
  COALESCE(
    TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(p.Created_Date AS STRING) AS INT64), 0), 1000)),
    NULLIF(SAFE_CAST(CAST(p.Created_Date AS STRING) AS TIMESTAMP), TIMESTAMP '1970-01-01')
  )                                                     AS created_date,
  COALESCE(
    TIMESTAMP_MICROS(DIV(NULLIF(SAFE_CAST(CAST(po.Update_Date AS STRING) AS INT64), 0), 1000)),
    NULLIF(SAFE_CAST(CAST(po.Update_Date AS STRING) AS TIMESTAMP), TIMESTAMP '1970-01-01')
  )                                                     AS update_date,
  -- The procedure concatenates with +, which yields NULL when either half is
  -- NULL; CONCAT does the same in BigQuery.
  CONCAT(pu2.First_Name, ' ', pu2.Last_Name)            AS routing_updated_by,
  p.Part_Type                                           AS part_type,
  pg.Part_Group                                         AS part_group,
  b.Building_Code                                       AS main_building,
  pu.Last_Name                                          AS created_by_last_name,
  po.Operation_No                                       AS operation_no,
  po.Interplant_Transfer_Allow                          AS interplant_transfer_allow,
  po.Net_Weight                                         AS net_weight,
  l.Location                                            AS process_routing_location,
  w.Workcenter_Code                                     AS workcenter_code,
  aw.Standard_Production_Rate                           AS standard_production_rate,
  aw.Ideal_Rate                                         AS ideal_rate,
  aw.Target_Rate                                        AS target_rate,
  aw.Crew_Size                                          AS crew_size,
  s.Supplier_Code                                       AS supplier_code,
  apps.Lead_Time                                        AS lead_time,
  o.Operation_Code                                      AS operation_code,
  o.Inventory_Type                                      AS inventory_type,
  COALESCE(SAFE_CAST(CAST(po.Active AS STRING) AS BOOL),
           SAFE_CAST(CAST(po.Active AS STRING) AS INT64) <> 0) AS op_active,
  po.Description                                        AS routing_operation_description,
  po.Multiple                                           AS multiple,
  pot.Description                                       AS part_op_type

FROM `{gcp_project}.{dataset}.raw_Part_v_Part` AS p

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Status` AS ps
  -- Plex (SQL Server) compares text case-insensitively and ignores trailing
  -- spaces; BigQuery's = does neither, so both sides are normalised.
  ON UPPER(RTRIM(ps.Part_Status)) = UPPER(RTRIM(p.Part_Status))
 AND SAFE_CAST(ps.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Group` AS pg
  ON SAFE_CAST(pg.Part_Group_Key AS INT64) = SAFE_CAST(p.Part_Group_Key AS INT64)
 AND SAFE_CAST(pg.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Building` AS b
  ON SAFE_CAST(b.Building_Key AS INT64) = SAFE_CAST(p.Building_Key AS INT64)
 AND SAFE_CAST(b.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Operation` AS po
  ON SAFE_CAST(po.Part_Key AS INT64) = SAFE_CAST(p.Part_Key AS INT64)
 AND SAFE_CAST(po.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Part_v_Operation` AS o
  ON SAFE_CAST(o.Operation_Key AS INT64) = SAFE_CAST(po.Operation_Key AS INT64)
 AND SAFE_CAST(o.Plexus_Customer_No AS INT64) = SAFE_CAST(po.Plexus_Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Approved_Workcenter` AS aw
  ON SAFE_CAST(aw.Part_Operation_Key AS INT64) = SAFE_CAST(po.Part_Operation_Key AS INT64)
 AND SAFE_CAST(aw.Plexus_Customer_No AS INT64) = SAFE_CAST(po.Plexus_Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Workcenter` AS w
  ON SAFE_CAST(w.Workcenter_Key AS INT64) = SAFE_CAST(aw.Workcenter_Key AS INT64)
 AND SAFE_CAST(w.Plexus_Customer_No AS INT64) = SAFE_CAST(aw.Plexus_Customer_No AS INT64)

-- Part_Op_Type's company column is named PCN, not Plexus_Customer_No.
LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Part_Op_Type` AS pot
  ON SAFE_CAST(pot.Part_Op_Type_Key AS INT64) = SAFE_CAST(po.Part_Op_Type_Key AS INT64)
 AND SAFE_CAST(pot.PCN AS INT64) = SAFE_CAST(po.Plexus_Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Location` AS l
  ON SAFE_CAST(l.Location_Key AS INT64) = SAFE_CAST(po.Location_Key AS INT64)
 AND SAFE_CAST(l.Plexus_Customer_No AS INT64) = SAFE_CAST(po.Plexus_Customer_No AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` AS pu
  ON SAFE_CAST(pu.Plexus_User_No AS INT64) = SAFE_CAST(p.Created_By AS INT64)
 AND SAFE_CAST(pu.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Part_v_Approved_Supplier` AS apps
  ON SAFE_CAST(apps.Part_Operation_Key AS INT64) = SAFE_CAST(po.Part_Operation_Key AS INT64)
 AND SAFE_CAST(apps.Plexus_Customer_No AS INT64) = SAFE_CAST(po.Plexus_Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Common_v_Supplier` AS s
  ON SAFE_CAST(s.Supplier_No AS INT64) = SAFE_CAST(apps.Supplier_No AS INT64)
 AND SAFE_CAST(s.Plexus_Customer_No AS INT64) = SAFE_CAST(apps.Plexus_Customer_No AS INT64)

LEFT JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` AS pu2
  ON SAFE_CAST(pu2.Plexus_User_No AS INT64) = SAFE_CAST(po.Update_By AS INT64)
 AND SAFE_CAST(pu2.Plexus_Customer_No AS INT64) = SAFE_CAST(po.Plexus_Customer_No AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Customer_Group_Member` AS cgm
  ON SAFE_CAST(cgm.Plexus_Customer_No AS INT64) = SAFE_CAST(p.Plexus_Customer_No AS INT64)

-- Same collation point as the Part_Status join above.
WHERE UPPER(RTRIM(p.Part_No)) <> 'MATL'

ORDER BY plexus_customer_code, part_no
