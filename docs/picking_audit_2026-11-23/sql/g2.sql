SELECT TOP 30 c.Serial_No, CONVERT(varchar(23), c.Change_Date, 121) AS d, c.Last_Action, c.Location, c.Master_Unit_Key
FROM Part_v_Container_Change2 AS c WHERE c.Change_By IN (SELECT u.Plexus_User_No FROM Plexus_Control_v_Plexus_User AS u WHERE u.User_ID = 'gcp.odbc.vox')
 AND c.Change_Date >= '2026-11-20' AND c.Change_Date < '2026-11-21' ORDER BY c.Change_Date
