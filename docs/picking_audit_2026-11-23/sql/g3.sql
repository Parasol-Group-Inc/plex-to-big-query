SELECT TOP 40 c.Serial_No, CONVERT(varchar(23), c.Change_Date, 121) AS d, c.Last_Action, c.Location, c.Change_By, c.Master_Unit_Key
FROM Part_v_Container_Change2 AS c WHERE c.Change_By = (SELECT TOP 1 h.Change_By FROM Part_v_Container_Change2 AS h WHERE h.Serial_No = 'S029901' AND h.Change_Date >= '2026-11-23 14:10:00')
 AND c.Change_Date >= '2026-11-20' ORDER BY c.Change_Date
