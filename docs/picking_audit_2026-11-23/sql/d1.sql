SELECT c.Location, c.Container_Status, COUNT(*) AS n, SUM(c.Quantity) AS qty, MIN(c.Quantity) AS mnq, MAX(c.Quantity) AS mxq,
  SUM(CASE WHEN c.From_Container <> '' THEN 1 ELSE 0 END) AS from_split, SUM(CASE WHEN c.Job_Key IS NOT NULL THEN 1 ELSE 0 END) AS has_job,
  MIN(c.Last_Action) AS la1, MAX(c.Last_Action) AS la2
FROM Part_v_Container AS c JOIN Part_v_Part AS p ON p.Part_Key = c.Part_Key
WHERE p.Part_No = '12743-01VOXNU-1' AND c.Active = 1 AND c.Quantity > 0
GROUP BY c.Location, c.Container_Status ORDER BY c.Location
