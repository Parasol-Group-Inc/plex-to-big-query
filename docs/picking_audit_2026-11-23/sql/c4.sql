SELECT s.Job_Set_No, j.Job_No, js.Job_Status, j.Quantity AS Job_Qty, p.Part_No, p.Unit AS Part_Unit, w.Workcenter_Code, o.Op_No,
  cp.Part_No AS Comp, cp.Unit AS Comp_Unit, b.Quantity AS Bom_Qty, b.Depletion_Unit, b.Depletion_Conversion, b.Fixed_Quantity, b.Scaling, b.Unit_Conversion_Key
FROM Part_v_Job_Set s
JOIN Part_v_Job_Set_Member m ON m.Job_Set_Key = s.Job_Set_Key
JOIN Part_v_Job j ON j.Job_Key = m.Job_Key
JOIN Part_v_Job_Status js ON js.Job_Status_Key = j.Job_Status_Key
JOIN Part_v_Part p ON p.Part_Key = j.Part_Key
LEFT JOIN Part_v_Job_Op o ON o.Job_Key = j.Job_Key
LEFT JOIN Part_v_Workcenter w ON w.Workcenter_Key = o.Workcenter_Key
LEFT JOIN Part_v_Job_Bom b ON b.Job_Op_Key = o.Job_Op_Key AND b.Active = 1
LEFT JOIN Part_v_Part cp ON cp.Part_Key = b.Component_Part_Key
WHERE s.Job_Set_No = '756' ORDER BY j.Job_No, o.Op_No
