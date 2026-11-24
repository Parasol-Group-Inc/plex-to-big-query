SELECT CASE WHEN c.Last_Action LIKE 'Retired at %' THEN 'Retired' WHEN c.Last_Action LIKE 'Depleted at %' THEN 'Depleted'
 WHEN c.Last_Action LIKE '%Move%' THEN c.Last_Action ELSE 'x' END AS k, COUNT(*) AS n, COUNT(DISTINCT c.Serial_No) AS serials,
 MIN(c.Change_Date) AS mn, MAX(c.Change_Date) AS mx
FROM Part_v_Container_Change2 AS c
WHERE c.Change_Date >= DATEADD(day, -45, GETDATE())
GROUP BY CASE WHEN c.Last_Action LIKE 'Retired at %' THEN 'Retired' WHEN c.Last_Action LIKE 'Depleted at %' THEN 'Depleted'
 WHEN c.Last_Action LIKE '%Move%' THEN c.Last_Action ELSE 'x' END
