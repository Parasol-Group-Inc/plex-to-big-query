SELECT c.Serial_No, CONVERT(varchar(23), c.Change_Date, 121) AS d, c.Last_Action, c.Location, c.Quantity, c.Container_Status
FROM Part_v_Container_Change2 AS c WHERE c.Serial_No IN (
 SELECT TOP 2 x.Serial_No FROM Part_v_Container AS x JOIN Part_v_Part AS p ON p.Part_Key = x.Part_Key
 WHERE p.Part_No = '12743-01VOXNU-1' AND x.Location = 'PW - B9' AND x.Active = 1 ORDER BY x.Serial_No)
ORDER BY c.Serial_No, c.Change_Date, c.Change_Key
