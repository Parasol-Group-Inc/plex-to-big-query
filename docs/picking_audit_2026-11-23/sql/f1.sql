SELECT c.Serial_No, CONVERT(varchar(23), c.Change_Date, 121) AS d, c.Last_Action, c.Location, CONVERT(varchar(23), GETDATE(), 121) AS now_srv, CONVERT(varchar(23), GETUTCDATE(), 121) AS now_utc
FROM Part_v_Container_Change2 AS c WHERE c.Serial_No IN ('S029901', 'S029940', '68GCE8-0401', 'A4E7G7-0004') AND c.Change_Date >= '2026-11-23'
ORDER BY c.Change_Date
