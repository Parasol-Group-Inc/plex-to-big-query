SELECT w.Workcenter_Code, COUNT(*) AS n, COUNT(DISTINCT w.Workcenter_Group) AS groups, MIN(w.Workcenter_Group) AS g1, MAX(w.Workcenter_Group) AS g2
FROM Part_v_Workcenter AS w GROUP BY w.Workcenter_Code HAVING COUNT(*) > 1
