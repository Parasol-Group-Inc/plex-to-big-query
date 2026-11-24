SELECT REPLACE(c.Last_Action, 'Retired at ', '') AS used_at, COUNT(*) AS n, MAX(w.Workcenter_Group) AS grp, MAX(w.Workcenter_Code) AS wc
FROM Part_v_Container_Change2 AS c LEFT JOIN Part_v_Workcenter AS w ON w.Workcenter_Code = REPLACE(c.Last_Action, 'Retired at ', '')
WHERE c.Last_Action LIKE 'Retired at %' AND c.Change_Date >= DATEADD(day, -45, GETDATE())
GROUP BY REPLACE(c.Last_Action, 'Retired at ', '') ORDER BY COUNT(*) DESC
