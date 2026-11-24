WITH h AS (SELECT c.Serial_No, c.Change_Date, c.Last_Action, c.Location, c.Change_By,
   LAG(c.Location) OVER (PARTITION BY c.Serial_No ORDER BY c.Change_Date, c.Change_Key) AS prev_loc
  FROM Part_v_Container_Change2 AS c WHERE c.Change_Date >= '2026-10-01'),
m AS (SELECT x.Serial_No, x.Change_By, x.prev_loc, x.Location, CONVERT(date, x.Change_Date) AS dd FROM h AS x
  WHERE x.Last_Action = 'Container Move' AND x.Change_Date >= '2026-10-22' AND x.Change_Date < '2026-11-21')
SELECT ISNULL(gf.Location_Group, CASE WHEN wf.Workcenter_Code IS NOT NULL THEN 'WC' ELSE '?' END) AS from_grp,
       ISNULL(gt.Location_Group, CASE WHEN wt.Workcenter_Code IS NOT NULL THEN 'WC' ELSE '?' END) AS to_grp,
       COUNT(*) AS moves, COUNT(DISTINCT y.Serial_No) AS serials
FROM m AS y
LEFT JOIN Common_v_Location AS lf ON lf.Location = y.prev_loc LEFT JOIN Common_v_Location_Group AS gf ON gf.Location_Group_Key = lf.Location_Group_Key
LEFT JOIN Common_v_Location AS lt ON lt.Location = y.Location LEFT JOIN Common_v_Location_Group AS gt ON gt.Location_Group_Key = lt.Location_Group_Key
LEFT JOIN Part_v_Workcenter AS wf ON wf.Workcenter_Code = y.prev_loc LEFT JOIN Part_v_Workcenter AS wt ON wt.Workcenter_Code = y.Location
GROUP BY ISNULL(gf.Location_Group, CASE WHEN wf.Workcenter_Code IS NOT NULL THEN 'WC' ELSE '?' END),
         ISNULL(gt.Location_Group, CASE WHEN wt.Workcenter_Code IS NOT NULL THEN 'WC' ELSE '?' END)
ORDER BY COUNT(*) DESC
