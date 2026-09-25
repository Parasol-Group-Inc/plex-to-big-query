-- sales_reps_report — who counts as a sales rep, from Plex's own role roster
--
-- HOW TO EDIT (no deployment required):
--   gcloud storage cp reports/sql/sales_reps_view.sql gs://voxdatalake-report-configs/sql/
--   The next pipeline run will recreate the view with the updated SQL.
--
-- PLACEHOLDERS: {gcp_project} and {dataset} are replaced at runtime.
-- GRAIN: one row per (rep, role).
--
-- WHY THIS EXISTS
-- ─────────────────────────────────────────────────────────────────────────
-- The manual-data web app's "Applies to" dropdown on a sales goal used to read
-- `DISTINCT sales_rep FROM sales_mtd_summary_report` — which lists only reps
-- who already have a qualifying sale THIS MONTH. A new rep, or a quiet one,
-- simply did not appear, and you cannot set a goal for somebody the form will
-- not offer. That is backwards: a goal is most needed exactly where there are
-- no sales yet.
--
-- Plex knows the answer already. `Inside Sales` (Role_Key 55369) is the role
-- Vox uses, and its roster contained all 7 reps who currently carry a goal in
-- scorecard_goals — Aishah Alqasim, Janet Pacheco, Kami Butcher, Landen
-- Epperson, Ruben Espinosa, Tyler Hall, Zeljan Avdic — plus several who do not
-- yet, which is the gap being reported. Confirmed live 2026-09-22: 82 roles
-- exist, `Inside Sales` is active, and `Outside Sales` (55371) is a different
-- roster that overlaps on one person and otherwise pulls in people who match
-- no known rep, so it is deliberately NOT included here.
--
-- MATCHED ON THE ROLE NAME, NOT THE KEY. The repo has been bitten once by a
-- numeric key vanishing under a status consolidation (see
-- sales_orders_pending_accounting_approval_view.sql), and a role key is no
-- more permanent. Adding a second role means adding a string below.
--
-- NAME FORMAT IS LOAD-BEARING: `CONCAT(First_Name, ' ', Last_Name)`, the same
-- convention every other rep-name view here uses. A goal's scope is matched to
-- a rep by EXACT STRING, and a mismatch produces no error — just a goal that
-- silently never lines up with any sales. Same failure mode as the work centre
-- group `Encapsulating` vs "Encapsulation".

SELECT

  CONCAT(u.First_Name, ' ', u.Last_Name)          AS sales_rep,
  u.First_Name                                    AS first_name,
  u.Last_Name                                     AS last_name,
  u.Email                                         AS email,
  SAFE_CAST(u.Plexus_User_No AS INT64)            AS plexus_user_no,

  r.Name                                          AS role_name,
  SAFE_CAST(r.Role_Key AS INT64)                  AS role_key,

  -- Plex's own flag for "this role earns commission". Exposed rather than
  -- filtered on — and that turned out to be the right call: verified
  -- 2026-09-22, `Inside Sales` has Commissionable = FALSE, so this flag is
  -- NOT how Vox marks a sales role. Filtering on it would have returned
  -- nobody. Kept visible so the next person does not have to rediscover it.
  SAFE_CAST(r.Commissionable AS BOOL)             AS role_is_commissionable,

  SAFE_CAST(ur.Admin AS BOOL)                     AS is_role_admin

FROM `{gcp_project}.{dataset}.raw_Plexus_Control_v_User_Role` ur

JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Role` r
  ON SAFE_CAST(ur.Role_Key AS INT64) = SAFE_CAST(r.Role_Key AS INT64)

JOIN `{gcp_project}.{dataset}.raw_Plexus_Control_v_Plexus_User` u
  ON SAFE_CAST(ur.Plexus_User_No AS INT64) = SAFE_CAST(u.Plexus_User_No AS INT64)

WHERE
  -- The roster Vox uses for sales. Add a name here to widen it.
  r.Name IN ('Inside Sales')
  -- Inactive roles and departed users must not reach a goals dropdown.
  AND SAFE_CAST(r.Active AS BOOL) IS TRUE
  AND SAFE_CAST(u.Active AS BOOL) IS TRUE
  AND u.First_Name IS NOT NULL
  AND u.Last_Name  IS NOT NULL

ORDER BY sales_rep
