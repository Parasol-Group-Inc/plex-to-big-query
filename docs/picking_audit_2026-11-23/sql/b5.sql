SELECT TOP 15 c.Location, COUNT(*) AS n FROM Part_v_Container_Change2 AS c
WHERE c.Last_Action = 'Master Unit Moved' AND c.Change_Date >= DATEADD(day, -45, GETDATE()) GROUP BY c.Location ORDER BY COUNT(*) DESC
