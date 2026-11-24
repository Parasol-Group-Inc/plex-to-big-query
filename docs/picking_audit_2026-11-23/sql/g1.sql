SELECT c.Serial_No, CONVERT(varchar(23), c.Change_Date, 121) AS d, c.Last_Action, c.Location, c.Change_By
FROM Part_v_Container_Change2 AS c JOIN Part_v_Master_Unit AS mu ON mu.Master_Unit_Key = c.Master_Unit_Key
WHERE mu.Master_Unit_No = 'LP-087265' AND c.Change_Date >= '2026-11-20' ORDER BY c.Change_Date
