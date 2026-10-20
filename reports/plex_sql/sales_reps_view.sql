-- sales_reps_report — Plex SQL Developer equivalent
-- plex_equivalent_of: reports/sql/sales_reps_view.sql
-- confidence: medium
-- plex_views: Plexus_Control_v_User_Role, Plexus_Control_v_Role, Plexus_Control_v_Plexus_User
-- notes: Active flags tested as <> 0 (BigQuery cast them to BOOL; Plex may use -1 for true); unverified.
-- Translated 2026-10-20 from the BigQuery view. Not yet run in Plex SQL Developer.

-- Active users holding the Inside Sales role.
SELECT
  u.First_Name + ' ' + u.Last_Name   AS sales_rep,
  u.First_Name                       AS first_name,
  u.Last_Name                        AS last_name,
  u.Email                            AS email,
  u.Plexus_User_No                   AS plexus_user_no,
  r.Name                             AS role_name,
  r.Role_Key                         AS role_key,
  r.Commissionable                   AS role_is_commissionable,
  ur.Admin                           AS is_role_admin
FROM Plexus_Control_v_User_Role AS ur
JOIN Plexus_Control_v_Role AS r ON ur.Role_Key = r.Role_Key
JOIN Plexus_Control_v_Plexus_User AS u ON ur.Plexus_User_No = u.Plexus_User_No
WHERE r.Name IN ('Inside Sales')
  AND r.Active <> 0
  AND u.Active <> 0
  AND u.First_Name IS NOT NULL
  AND u.Last_Name IS NOT NULL
ORDER BY u.First_Name + ' ' + u.Last_Name
