SELECT j.Job_No, p.Part_No, w.Workcenter_Code, js.Job_Status FROM Part_v_Job AS j JOIN Part_v_Part AS p ON p.Part_Key = j.Part_Key
JOIN Part_v_Job_Status AS js ON js.Job_Status_Key = j.Job_Status_Key
LEFT JOIN Part_v_Job_Op AS o ON o.Job_Key = j.Job_Key LEFT JOIN Part_v_Workcenter AS w ON w.Workcenter_Key = o.Workcenter_Key
WHERE j.Job_No IN ('1195', '1190')
