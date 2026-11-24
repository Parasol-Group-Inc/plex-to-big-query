SELECT TOP 40 c.Last_Action, COUNT(*) AS n FROM Part_v_Container_Change2 AS c
WHERE c.Change_Date >= DATEADD(day, -45, GETDATE()) GROUP BY c.Last_Action ORDER BY COUNT(*) DESC
