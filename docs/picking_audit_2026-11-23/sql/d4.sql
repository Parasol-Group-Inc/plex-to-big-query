SELECT s.Job_Set_No, j.Job_No, js.Job_Status, CONVERT(varchar(10), j.Due_Date, 120) AS due, j.Quantity * b.Quantity AS need
FROM Part_v_Job AS j JOIN Part_v_Job_Status AS js ON js.Job_Status_Key = j.Job_Status_Key
JOIN Part_v_Job_Op AS o ON o.Job_Key = j.Job_Key JOIN Part_v_Job_Bom AS b ON b.Job_Op_Key = o.Job_Op_Key AND b.Active = 1
JOIN Part_v_Part AS cp ON cp.Part_Key = b.Component_Part_Key JOIN Part_v_Part AS p ON p.Part_Key = j.Part_Key
LEFT JOIN Part_v_Job_Set_Member AS sm ON sm.Job_Key = j.Job_Key LEFT JOIN Part_v_Job_Set AS s ON s.Job_Set_Key = sm.Job_Set_Key
WHERE js.Job_Status IN ('Scheduled', 'Production') AND cp.Part_No = '12743-01VOXNU-1' AND p.Part_No = '12743-01VOXNU-1'
ORDER BY j.Due_Date
