SELECT TOP 30 c.Serial_No, COUNT(*) AS n FROM Part_v_Container_Change2 AS c
WHERE c.Last_Action = 'Retired at Pre-Weigh 1' AND c.Change_Date >= DATEADD(day, -10, GETDATE())
GROUP BY c.Serial_No ORDER BY COUNT(*) DESC
