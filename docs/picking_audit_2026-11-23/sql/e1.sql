WITH mv AS (SELECT m.Serial_No, m.Change_Date, m.Change_Key,
   CASE WHEN m.Location LIKE 'PW - %' THEN 'PW' WHEN m.Location LIKE 'Bottling [0-9]%' THEN 'Bottling' WHEN m.Location LIKE 'Labeling [0-9]%' OR m.Location = 'First 48' THEN 'Labeling' ELSE NULL END AS dest
  FROM Part_v_Container_Change2 AS m
  WHERE m.Last_Action IN ('Container Move', 'Master Unit Move') AND m.Change_Date >= '2026-10-07' AND m.Change_Date < '2026-11-22'),
nx AS (SELECT x.dest, (SELECT MIN(n.Change_Date) FROM Part_v_Container_Change2 AS n WHERE n.Serial_No = x.Serial_No AND n.Change_Key > x.Change_Key AND n.Change_Date >= x.Change_Date) AS nd, x.Change_Date
  FROM mv AS x WHERE x.dest IS NOT NULL)
SELECT y.dest, COUNT(*) AS moves,
 SUM(CASE WHEN DATEDIFF(second, y.Change_Date, y.nd) <= 300 THEN 1 ELSE 0 END) AS m5,
 SUM(CASE WHEN DATEDIFF(second, y.Change_Date, y.nd) <= 3600 THEN 1 ELSE 0 END) AS h1,
 SUM(CASE WHEN DATEDIFF(second, y.Change_Date, y.nd) <= 86400 THEN 1 ELSE 0 END) AS h24,
 SUM(CASE WHEN y.nd IS NULL THEN 1 ELSE 0 END) AS never
FROM nx AS y GROUP BY y.dest
