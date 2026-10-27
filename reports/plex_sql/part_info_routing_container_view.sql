-- part_info_routing_container_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/part_info_routing_container_view.sql
-- confidence: high
-- plex_views: Part_v_Part, Part_v_Part_Status, Part_v_Part_Group, Part_v_Part_Operation, Part_v_Operation, Part_v_Part_Operation_Approved_Container, Part_v_Container_Type, Plexus_Control_v_Plexus_User, Plexus_Control_v_Customer_Group_Member
-- notes: Mechanical translation; bit columns cast to bit, Primary bracketed because it is a reserved word. No extraction-time filters.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part x shippable routing operation x approved container type.
-- RULE: only shippable operations; the MATL placeholder part is excluded.
WITH op_container_counts AS (
  SELECT poac_n.Part_Operation_Key AS part_operation_key,
         COUNT(*)                  AS n
  FROM Part_v_Part_Operation_Approved_Container AS poac_n
  GROUP BY poac_n.Part_Operation_Key
),

primary_counts AS (
  SELECT poac_p.Part_Operation_Key AS part_operation_key,
         poac_p.Container_Type_Key AS container_type_key,
         poac_p.Part_Key           AS part_key,
         poac_p.PCN                AS pcn,
         COUNT(*)                  AS n
  FROM Part_v_Part_Operation_Approved_Container AS poac_p
  WHERE CAST(poac_p.[Primary] AS bit) = 1
  GROUP BY poac_p.Part_Operation_Key, poac_p.Container_Type_Key, poac_p.Part_Key, poac_p.PCN
)

SELECT
  cgm.Plexus_Customer_No                                AS plexus_customer_no,
  cgm.Plexus_Customer_Code                              AS plexus_customer_code,
  p.Part_No                                             AS part_no,
  p.Revision                                            AS revision,
  p.Part_Status                                         AS part_status,
  CAST(ps.Active AS bit)                                AS part_active,
  p.Created_Date                                        AS created_date,
  p.Part_Type                                           AS part_type,
  pg.Part_Group                                         AS part_group,
  pu.Last_Name                                          AS created_by_last_name,
  po.Operation_No                                       AS operation_no,
  o.Operation_Code                                      AS operation_code,
  CAST(po.Shippable AS bit)                             AS shippable,
  CAST(po.Active AS bit)                                AS op_active,
  o.Inventory_Type                                      AS inventory_type,
  ct.Container_Type                                     AS container_type,
  CAST(poac.[Primary] AS bit)                           AS [primary],
  COALESCE(occ.n, 0)                                    AS tot_number_container_types,
  COALESCE(pc.n, 0)                                     AS is_primary,
  poac.Standard_Pack_Quantity                           AS standard_pack_quantity,
  poac.Containers_Per_Master                            AS containers_per_master
FROM Part_v_Part AS p
LEFT JOIN Part_v_Part_Status AS ps
  ON UPPER(RTRIM(ps.Part_Status)) = UPPER(RTRIM(p.Part_Status))
 AND ps.Plexus_Customer_No = p.Plexus_Customer_No
JOIN Part_v_Part_Group AS pg
  ON pg.Part_Group_Key = p.Part_Group_Key
 AND pg.Plexus_Customer_No = p.Plexus_Customer_No
JOIN Part_v_Part_Operation AS po
  ON po.Part_Key = p.Part_Key
 AND po.Plexus_Customer_No = p.Plexus_Customer_No
JOIN Part_v_Operation AS o
  ON o.Operation_Key = po.Operation_Key
 AND o.Plexus_Customer_No = po.Plexus_Customer_No
LEFT JOIN Part_v_Part_Operation_Approved_Container AS poac
  ON poac.Part_Key = po.Part_Key
 AND poac.Part_Operation_Key = po.Part_Operation_Key
 AND poac.PCN = po.Plexus_Customer_No          -- this view names its customer column PCN
LEFT JOIN Part_v_Container_Type AS ct
  ON ct.Container_Type_Key = poac.Container_Type_Key
 AND ct.Plexus_Customer_No = poac.PCN
JOIN Plexus_Control_v_Plexus_User AS pu
  ON pu.Plexus_User_No = p.Created_By
 AND pu.Plexus_Customer_No = p.Plexus_Customer_No
LEFT JOIN op_container_counts AS occ
  ON occ.part_operation_key = po.Part_Operation_Key
LEFT JOIN primary_counts AS pc
  ON pc.part_operation_key = poac.Part_Operation_Key
 AND pc.container_type_key = poac.Container_Type_Key
 AND pc.part_key = poac.Part_Key
 AND pc.pcn = poac.PCN
JOIN Plexus_Control_v_Customer_Group_Member AS cgm
  ON cgm.Plexus_Customer_No = p.Plexus_Customer_No
WHERE UPPER(RTRIM(p.Part_No)) <> 'MATL'
  AND CAST(po.Shippable AS bit) = 1
ORDER BY cgm.Plexus_Customer_Code, p.Part_No, p.Revision, po.Operation_No;
