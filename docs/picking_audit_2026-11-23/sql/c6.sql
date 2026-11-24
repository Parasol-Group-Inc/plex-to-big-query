SELECT TOP 20 j.Job_No, cp.Part_No, COUNT(*) AS n_ops, SUM(b.Quantity) AS tot
FROM Part_v_Job AS j JOIN Part_v_Job_Status AS js ON js.Job_Status_Key = j.Job_Status_Key
JOIN Part_v_Job_Op AS o ON o.Job_Key = j.Job_Key JOIN Part_v_Job_Bom AS b ON b.Job_Op_Key = o.Job_Op_Key AND b.Active = 1
JOIN Part_v_Part AS cp ON cp.Part_Key = b.Component_Part_Key
WHERE js.Job_Status IN ('Scheduled', 'Production')
GROUP BY j.Job_No, cp.Part_No HAVING COUNT(*) > 1
