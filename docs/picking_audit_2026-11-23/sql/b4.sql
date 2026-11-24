SELECT TOP 8 c.Serial_No, CONVERT(varchar(23), c.Change_Date, 121) AS d, c.Last_Action, c.Location, c.Quantity, c.Master_Unit_Key
FROM Part_v_Container_Change2 AS c WHERE c.Serial_No IN (
 SELECT TOP 1 r.Serial_No FROM Part_v_Container_Change2 AS r WHERE r.Last_Action = 'Retired at Labeling 2' AND r.Change_Date >= '2026-11-12'
   AND EXISTS (SELECT 1 FROM Part_v_Container_Change2 AS q WHERE q.Serial_No = r.Serial_No AND q.Last_Action = 'Master Unit Moved'))
ORDER BY c.Change_Date DESC
