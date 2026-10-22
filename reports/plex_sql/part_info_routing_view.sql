-- part_info_routing_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/part_info_routing_view.sql
-- confidence: high
-- plex_views: Part_v_Part, Part_v_Part_Status, Part_v_Part_Group, Common_v_Building, Part_v_Part_Operation, Part_v_Operation, Part_v_Approved_Workcenter, Part_v_Workcenter, Part_v_Part_Op_Type, Common_v_Location, Plexus_Control_v_Plexus_User, Part_v_Approved_Supplier, Common_v_Supplier, Plexus_Control_v_Customer_Group_Member
-- notes: Mechanical translation (this report mirrors a Plex classic-report query); no extraction-time filters. Bit columns cast to bit.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- GRAIN: one row per part x routing operation x approved workcenter x approved supplier.
-- RULE: every join is scoped by Plexus_Customer_No (PCN); the MATL placeholder part is excluded.
SELECT
  cgm.Plexus_Customer_No                                AS plexus_customer_no,
  cgm.Plexus_Customer_Code                              AS plexus_customer_code,
  p.Part_No                                             AS part_no,
  p.Revision                                            AS revision,
  p.Old_Part_No                                         AS old_part_no,
  p.Part_Status                                         AS part_status,
  CAST(ps.Active AS bit)                                AS part_active,
  p.Created_Date                                        AS created_date,
  po.Update_Date                                        AS update_date,
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
  CAST(po.Active AS bit)                                AS op_active,
  po.Description                                        AS routing_operation_description,
  po.Multiple                                           AS multiple,
  pot.Description                                       AS part_op_type
FROM Part_v_Part AS p
LEFT JOIN Part_v_Part_Status AS ps
  ON UPPER(RTRIM(ps.Part_Status)) = UPPER(RTRIM(p.Part_Status))
 AND ps.Plexus_Customer_No = p.Plexus_Customer_No
JOIN Part_v_Part_Group AS pg
  ON pg.Part_Group_Key = p.Part_Group_Key
 AND pg.Plexus_Customer_No = p.Plexus_Customer_No
LEFT JOIN Common_v_Building AS b
  ON b.Building_Key = p.Building_Key
 AND b.Plexus_Customer_No = p.Plexus_Customer_No
JOIN Part_v_Part_Operation AS po
  ON po.Part_Key = p.Part_Key
 AND po.Plexus_Customer_No = p.Plexus_Customer_No
JOIN Part_v_Operation AS o
  ON o.Operation_Key = po.Operation_Key
 AND o.Plexus_Customer_No = po.Plexus_Customer_No
LEFT JOIN Part_v_Approved_Workcenter AS aw
  ON aw.Part_Operation_Key = po.Part_Operation_Key
 AND aw.Plexus_Customer_No = po.Plexus_Customer_No
LEFT JOIN Part_v_Workcenter AS w
  ON w.Workcenter_Key = aw.Workcenter_Key
 AND w.Plexus_Customer_No = aw.Plexus_Customer_No
LEFT JOIN Part_v_Part_Op_Type AS pot
  ON pot.Part_Op_Type_Key = po.Part_Op_Type_Key
 AND pot.PCN = po.Plexus_Customer_No          -- this view names its customer column PCN
LEFT JOIN Common_v_Location AS l
  ON l.Location_Key = po.Location_Key
 AND l.Plexus_Customer_No = po.Plexus_Customer_No
JOIN Plexus_Control_v_Plexus_User AS pu       -- creator of the part
  ON pu.Plexus_User_No = p.Created_By
 AND pu.Plexus_Customer_No = p.Plexus_Customer_No
LEFT JOIN Part_v_Approved_Supplier AS apps
  ON apps.Part_Operation_Key = po.Part_Operation_Key
 AND apps.Plexus_Customer_No = po.Plexus_Customer_No
LEFT JOIN Common_v_Supplier AS s
  ON s.Supplier_No = apps.Supplier_No
 AND s.Plexus_Customer_No = apps.Plexus_Customer_No
LEFT JOIN Plexus_Control_v_Plexus_User AS pu2 -- last updater of the routing operation
  ON pu2.Plexus_User_No = po.Update_By
 AND pu2.Plexus_Customer_No = po.Plexus_Customer_No
JOIN Plexus_Control_v_Customer_Group_Member AS cgm
  ON cgm.Plexus_Customer_No = p.Plexus_Customer_No
WHERE UPPER(RTRIM(p.Part_No)) <> 'MATL'
ORDER BY cgm.Plexus_Customer_Code, p.Part_No;
