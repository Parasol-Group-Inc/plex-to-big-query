WITH mv AS (SELECT m.Serial_No, m.Change_Date, m.Container_Status FROM Part_v_Container_Change2 AS m
  WHERE m.Last_Action IN ('Container Move', 'Master Unit Move') AND m.Location LIKE 'PW - %' AND m.Change_Date >= DATEADD(day, -45, GETDATE())),
al AS (SELECT DISTINCT x.Serial_No, x.Change_Date FROM mv AS x JOIN Part_v_Container_Change2 AS a ON a.Serial_No = x.Serial_No
  AND a.Last_Action LIKE 'Added new job allocation%' AND a.Change_Date BETWEEN DATEADD(hour, -24, x.Change_Date) AND x.Change_Date)
SELECT y.Container_Status, COUNT(*) AS moves, COUNT(z.Serial_No) AS alloc_24h_before
FROM mv AS y LEFT JOIN al AS z ON z.Serial_No = y.Serial_No AND z.Change_Date = y.Change_Date
GROUP BY y.Container_Status
