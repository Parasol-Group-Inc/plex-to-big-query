WITH d AS (SELECT DISTINCT c.Serial_No, REPLACE(c.Last_Action, 'Depleted at ', '') AS wc FROM Part_v_Container_Change2 AS c
  WHERE c.Last_Action LIKE 'Depleted at %' AND c.Change_Date >= DATEADD(day, -45, GETDATE())),
r AS (SELECT DISTINCT c.Serial_No FROM Part_v_Container_Change2 AS c WHERE c.Last_Action LIKE 'Retired at %')
SELECT w.Workcenter_Group, COUNT(*) AS depleted_serials, SUM(CASE WHEN r.Serial_No IS NULL THEN 1 ELSE 0 END) AS not_retired
FROM d LEFT JOIN r ON r.Serial_No = d.Serial_No LEFT JOIN Part_v_Workcenter AS w ON w.Workcenter_Code = d.wc
GROUP BY w.Workcenter_Group
