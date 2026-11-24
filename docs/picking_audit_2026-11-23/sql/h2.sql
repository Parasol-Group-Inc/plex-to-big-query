SELECT c.Last_Action, COUNT(*) AS n, COUNT(DISTINCT c.Serial_No) AS serials, COUNT(DISTINCT c.Change_By) AS users
FROM Part_v_Container_Change2 AS c WHERE c.Change_Date >= '2026-10-22' AND c.Change_Date < '2026-11-21'
 AND c.Last_Action IN ('Container Move', 'Move', 'Move via Inventory Location Move', 'Master Unit Move', 'Master Unit Moved')
GROUP BY c.Last_Action
