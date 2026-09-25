# Open items — all projects

*Last updated: 2026-09-25. Newest decisions first within each section. When
an item closes, delete it here and record it in `CHANGELOG.md`; don't keep
closed items.*

Where the detail lives: `label-design/STATUS.md`,
[docs/SCORECARD_SANDBOX_FINDINGS.md](SCORECARD_SANDBOX_FINDINGS.md), the
[Migration Board](https://claude.ai/code/artifact/89e5211a-10c8-4a59-bf3d-c92f188c47a9),
and `CHANGELOG.md`.

---

## Deploy / shared

| # | Item | Owner | Next step |
|---|---|---|---|
| D1 | **Next `./scripts/deploy.sh` proposes 3 add / 3 change.** It adds the Label Design push job's secret, test Cloud Run job and test scheduler (from `2eff172`, merged in PR #3). It changes `label_design_view.sql` (BDM sales-rep fields, also from `2eff172`) plus two comment-only SQL files. | Emilio | Decide before deploying. The scheduled test push job **fails twice a day** until (a) a version of secret `monday-api-key` exists and (b) an image containing `label_design_service/` is built with Cloud Build. Either do (a) and (b) first, then deploy all 6, or decline at the prompt. See L1. |
| D2 | **The 9:45 PM retry has never produced a run.** `job_run_log` has 0 `run_mode='retry'` rows since 2026-07-21, despite 23 failed and 39 partial runs. | Claude, needs `gcloud` | `gcloud auth login`, then inspect the `*-retry` schedulers (state, last attempt) and a retry execution's logs. The retry's "today" is UTC while the schedules are Mountain; check that too. |
| D3 | **ETL keeps yesterday's rows when Plex returns 0** (`main.py` `write_to_bigquery`). A table that genuinely empties shows stale data, silently. | Decision | Keep the guard against transient failures but mark staleness, e.g. log it in the run email or add a `last_nonempty_at`. Discuss before changing. |
| D4 | **Every YAML's `sql_file` hard-codes `gs://voxdatalake-report-configs`.** That breaks a move to another project or bucket. | Low | Template the bucket if a move is ever planned. |
| D5 | **The sandbox snapshot expires after 2026-09-30.** BigQuery time travel only reaches 7 days back. | whoever rebuilds | Before rebuilding: `python scripts/scorecard_sandbox/snapshot_check.py "<instant>" now`, pick an instant where every relation joins, and set `build.SNAPSHOT`. |
| D6 | `docs/CLICKUP_TEAM_GUIDE.md` is partly stale (counts, pipelines). | Low | Regenerate with the `team-guide` skill. |

## Vox Scorecard

| # | Item | Owner | Next step |
|---|---|---|---|
| S1 | **Disable the old goals Apps Script project** (the one that pushed `deploy/goals_sheet_to_bigquery.gs`). Its trigger can still truncate `scorecard_goals`. | Emilio | Apps Script → that project → Triggers → delete; or archive the project. |
| S2 | **Point the manual-data app at PlexProd** once goals are confirmed. | Emilio | Set Script Property `BQ_DATASET=PlexProd`, then run `pushAll()`. `importLegacyGoals()` is **not** needed for prod: `PlexProd.scorecard_goals` is empty and the legacy goals were already imported through the shared sheet. |
| S3 | **Revenue goal** is a copy of the company sales goal. | Jennilyn | Confirm there is a separate revenue target, or keep the copy. |
| S4 | **Production goals are empty** in the app. The sandbox uses the live board's 100M / 1.5M / 700K. | Jennilyn | Enter the real monthly goals for Encapsulating, Bottling and Labeling, and say whether other areas have goals. |
| S5 | **A goal scoped "Sales Representative"** matches no person. | Jennilyn | Reassign or delete it. |
| S6 | **Safety incidents**: nothing logged since the 7/23 recordable. | Jennilyn | Name who logs them. An empty log reads as a clean record. |
| S7 | **TAT standards** are placeholders, and it's unclear which grouping applies: the old sheet's bottle types or Plex stock types. | Jennilyn / Quality | Supply the real Performance/Bonus days and the grouping. |
| S8 | **Destruction $ / Rework $**: Quality types the amounts into NC descriptions, so `Cost` is 0.00. | Quality | Use Plex's Cost field. The views' missing-cost flag now surfaces it. |
| S9 | **No home for:** the lab TAT target, the DPMO opportunities per unit (currently 1), and the pipeline stage probabilities. | Jennilyn | Decide each. |
| S10 | **Inventory value has no month-end trend.** `Part_v_Snapshot` has no quantity, so only the current snapshot is valued. | Decision | Store a daily on-hand copy, or find a Plex inventory-history source. The interim answer is NetSuite. |
| S11 | **Looker Studio report** to be built against `voxdatalake.ScorecardSandbox`. | Emilio | The tile-by-tile build list is in the findings doc. |

## Label Design

| # | Item | Owner | Next step |
|---|---|---|---|
| L1 | **Push service is not live.** Code is merged and verified against the "Plex Import" board (`18432111755`). | Emilio | 1. Add a secret version: `echo -n "$KEY" \| gcloud secrets versions add monday-api-key --data-file=- --project=voxdatalake`. 2. Build an image with Cloud Build (preflight first). 3. `deploy.sh` (D1). 4. Run `plex-etl-label-design-push-test`, then check the board. |
| L2 | **On-demand trigger app** (`deploy/label_design_trigger/`) is in `main` but not set up in Apps Script. | Emilio | Follow its README: an Apps Script project in `parasoldatalake` with the Cloud Run Admin API enabled; set `JOB_NAME` and `ALLOWED_EMAILS`; run `testSetup()`; deploy as a web app. Targets the **test** job until promoted. |
| L3 | **Still open from the design:** a prod push job and prod target board; the part-attribute → Monday column mapping (attributes sit on 7-parts, the queue carries 9-parts: BOM hop `93…→73…`); a pre-cutover dedupe fallback; whether the push sets a starting Design Status. | Emilio / Ashley | See `label-design/STATUS.md`. |
| L4 | **Monday seat licence:** the account holds CRM, not Work Management. | Monday billing admin | It blocks writing to the real Design & QA board; "Plex Import" works meanwhile. |
