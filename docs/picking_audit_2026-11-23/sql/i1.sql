SELECT w.Workcenter_Code, w.Workcenter_Group, COUNT(DISTINCT j.Job_Key) AS open_jobs
FROM Part_v_Job AS j JOIN Part_v_Job_Status AS js ON js.Job_Status_Key = j.Job_Status_Key
JOIN Part_v_Job_Op AS o ON o.Job_Key = j.Job_Key LEFT JOIN Part_v_Workcenter AS w ON w.Workcenter_Key = o.Workcenter_Key
WHERE js.Job_Status IN ('Scheduled', 'Production') AND j.Due_Date < DATEADD(day, 14, GETDATE()) AND j.Due_Date >= DATEADD(day, -14, GETDATE())
GROUP BY w.Workcenter_Code, w.Workcenter_Group ORDER BY COUNT(DISTINCT j.Job_Key) DESC
