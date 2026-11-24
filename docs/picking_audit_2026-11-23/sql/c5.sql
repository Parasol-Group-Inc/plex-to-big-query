SELECT COUNT(*) AS lines,
 SUM(CASE WHEN b.Depletion_Conversion <> 1 THEN 1 ELSE 0 END) AS conv_ne1,
 SUM(CASE WHEN b.Fixed_Quantity <> 0 THEN 1 ELSE 0 END) AS fixed,
 SUM(CASE WHEN b.Depletion_Unit <> '' THEN 1 ELSE 0 END) AS dep_unit,
 SUM(CASE WHEN b.Unit_Conversion_Key IS NOT NULL THEN 1 ELSE 0 END) AS uconv,
 SUM(CASE WHEN b.Scaling = 1 THEN 1 ELSE 0 END) AS scaling,
 SUM(CASE WHEN b.Deplete_By_Weight <> 0 THEN 1 ELSE 0 END) AS by_weight,
 COUNT(DISTINCT j.Job_Key) AS jobs
FROM Part_v_Job AS j JOIN Part_v_Job_Status AS js ON js.Job_Status_Key = j.Job_Status_Key
JOIN Part_v_Job_Op AS o ON o.Job_Key = j.Job_Key JOIN Part_v_Job_Bom AS b ON b.Job_Op_Key = o.Job_Op_Key AND b.Active = 1
WHERE js.Job_Status IN ('Scheduled', 'Production')
