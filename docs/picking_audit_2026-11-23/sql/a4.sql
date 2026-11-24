SELECT c.Serial_No, CONVERT(varchar(23), c.Change_Date, 121) AS d, c.Last_Action, c.Location, c.Quantity, c.Container_Status, c.Change_By
FROM Part_v_Container_Change2 AS c
WHERE c.Serial_No IN (SELECT TOP 2 r.Serial_No FROM Part_v_Container_Change2 AS r WHERE r.Last_Action = 'Retired at Pre-Weigh 1' AND r.Change_Date >= '2026-11-10' ORDER BY r.Change_Date)
ORDER BY c.Serial_No, c.Change_Date, c.Change_Key
