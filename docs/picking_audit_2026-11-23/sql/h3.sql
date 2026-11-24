SELECT CONVERT(varchar(10), DATEADD(hour, -2, c.Change_Date), 120) AS day_mt, COUNT(*) AS n, COUNT(DISTINCT c.Change_By) AS users
FROM Part_v_Container_Change2 AS c WHERE c.Change_Date >= '2026-11-10 02:00' AND c.Change_Date < '2026-11-21 02:00' AND c.Last_Action = 'Container Move'
GROUP BY CONVERT(varchar(10), DATEADD(hour, -2, c.Change_Date), 120) ORDER BY 1
