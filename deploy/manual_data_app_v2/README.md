# Manual-data app v2 ("Vox Goals", database-direct): what is LIVE

Copied from the live Apps Script project on 2026-11-10 (Emilio, editor). This, not
`deploy/manual_data_app/`, is what runs.

- **Saves write straight to BigQuery** (`PlexProd`), append-only: newest row per key wins, a removal is a
  row with `is_deleted = TRUE`. Tables: `scorecard_goals_app`, `safety_incidents`, `msl_item_inputs`,
  `msl_rules`, `manual_data_access`. **No Google Sheet, no hourly push, no trigger**: a table that has not
  changed for days just means nobody saved there.
- **Access:** `PlexProd.manual_data_access` lists who may edit each area; admins manage it on the "User
  access" tab; every save checks it on the server.
- **Reads** `v2_scorecard_goals_resolved`, `production_monthly_by_workcenter_group_report`,
  `sales_reps_report`, `raw_Part_v_Part`.
- **Files:** `Code.gs` (here, as deployed plus the 183-day MSL rule of 2026-11-10). `Index.html`: still
  to be copied in (OPEN_ITEMS D36).

**Changing it:** edit only what changed in the Apps Script editor (never paste the old
`deploy/manual_data_app/` over it), save, then Deploy > Manage deployments > edit > New version.
Keep `MSL_RULES` defaults in step with the `cfg` CTE in `reports/sql/approaching_msl_view.sql`.
