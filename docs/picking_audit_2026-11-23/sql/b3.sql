WITH ret AS (
  SELECT c.Serial_No, c.Change_Date, REPLACE(c.Last_Action, 'Retired at ', '') AS used_at, c.Location AS ret_loc
  FROM Part_v_Container_Change2 AS c
  WHERE c.Last_Action LIKE 'Retired at %' AND c.Change_Date >= DATEADD(day, -45, GETDATE())),
mv AS (
  SELECT r.used_at, r.ret_loc,
    (SELECT TOP 1 m.Last_Action + ' -> ' + m.Location FROM Part_v_Container_Change2 AS m
     WHERE m.Serial_No = r.Serial_No AND m.Change_Date <= r.Change_Date
       AND m.Last_Action IN ('Container Move', 'Master Unit Move', 'Master Unit Moved', 'Move', 'Move via Inventory Location Move', 'Moved with Master Unit')
     ORDER BY m.Change_Date DESC) AS last_any
  FROM ret AS r)
SELECT w.Workcenter_Group, LEFT(x.last_any, CHARINDEX(' -> ', x.last_any + ' -> ') - 1) AS act,
  SUM(CASE WHEN x.last_any LIKE '% -> ' + x.used_at THEN 1 ELSE 0 END) AS into_wc, COUNT(*) AS n
FROM mv AS x LEFT JOIN Part_v_Workcenter AS w ON w.Workcenter_Code = x.used_at
GROUP BY w.Workcenter_Group, LEFT(x.last_any, CHARINDEX(' -> ', x.last_any + ' -> ') - 1)
ORDER BY w.Workcenter_Group, COUNT(*) DESC
