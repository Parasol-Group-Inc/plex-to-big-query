# Open items — all projects

*Last updated: 2026-10-01. Newest decisions first within each section. When
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
| D2 | **The 9:45 PM retry has never produced a run.** `job_run_log` has 0 `run_mode='retry'` rows since 2026-07-21, despite 23 failed and 39 partial runs. | Claude, needs `gcloud` | `gcloud auth login`, then inspect the `*-retry` schedulers (state, last attempt) and a retry execution's logs. The retry's "today" is UTC while the schedules are Mountain; check that too. |
| D3 | **ETL keeps yesterday's rows when Plex returns 0** (`main.py` `write_to_bigquery`). A table that genuinely empties shows stale data, silently. | Decision | Keep the guard against transient failures but mark staleness, e.g. log it in the run email or add a `last_nonempty_at`. Discuss before changing. |
| D4 | **Every YAML's `sql_file` hard-codes `gs://voxdatalake-report-configs`.** That breaks a move to another project or bucket. | Low | Template the bucket if a move is ever planned. |
| D5 | **The sandbox snapshot expires after 2026-09-30.** BigQuery time travel only reaches 7 days back. | whoever rebuilds | Before rebuilding: `python scripts/scorecard_sandbox/snapshot_check.py "<instant>" now`, pick an instant where every relation joins, and set `build.SNAPSHOT`. |
| D6 | `docs/CLICKUP_TEAM_GUIDE.md` is partly stale (counts, pipelines). | Low | Regenerate with the `team-guide` skill. |
| D7 | **Developer access as code is undecided.** A `terraform/developer_access.tf` (read access to secrets, driver/state buckets, BigQuery, logs for everyone in `developer_members`) was drafted 2026-09-30 and blocked by Claude Code's permission classifier. Until then an Owner grants the roles in `docs/ONBOARDING.md` by hand. | Emilio | Write or approve the file, or keep granting by hand. |
| D8 | **Backups live in the same GCP project.** `secrets.env`, tfvars, driver and zipfiles are in `gs://voxdatalake-terraform-state/…/backups/`, so a deleted project takes them too. Accepted for now (company-only bucket). | Emilio | Optional: copy `backups/latest/` somewhere outside GCP. |

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
| L1 | **Reference board: 13 items in "New from Plex" on "Plex Import"** from the real Plex test orders #4–#7, with the part line and Bottle Material. Re-keyed per order line 2026-09-30. Ashley settled one item per line and the status Sales Rep column. | Emilio / Ashley | Team: delete the **WO** column; optionally automate the people "Sales Rep" from the status one. |
| L5 | **Confirm the 09-30 Label Design deploy end to end.** `deploy/2026-09-30T1551Z` carried the part line, Bottle Material and the per-line key (`88907c4`). Check that the push image was rebuilt after it, and that a scheduled push logs `16/16 mapped columns` and `13 already on the board, 0 new` (the 13 reference items were re-keyed in place). | Emilio | Cloud Run logs for `plex-etl-label-design-push-test`. If it says 13 new, pause `plex-label-design-push-sync-test` and check the push log. |
| L6 | **Chain the push onto the ETL.** The on-demand button (L2) runs only the ETL, so Monday waits for the 10:10/14:10 push. Options: A, the ETL job runs the push as its last step (recommended); B, the button waits for the ETL, then starts the push; C, a Cloud Workflow runs both. | Emilio | Pick A/B/C. |
| L7 | **Ashley's open board points:** delete the WO column; optionally automate the people "Sales Rep" from the status one (the push fills status). Email and phone are the customer's company-level contact; switching to the order line's contact person is possible if asked. | Ashley | On the board. |
| L2 | **On-demand trigger app** (`deploy/label_design_trigger/`) is in `main` but not set up in Apps Script. | Emilio | Follow its README: an Apps Script project in `parasoldatalake` with the Cloud Run Admin API enabled; set `JOB_NAME` and `ALLOWED_EMAILS`; run `testSetup()`; deploy as a web app. Targets the **test** job until promoted. |
| L3 | **Before the 19 Oct cutover:** add a **prod** push job (PlexProd → "Plex Import" `18432111755`, the board the team will use; the view picks `vox.on.plex.com` for PlexProd by itself), and **repoint the test push job to a sandbox board** (e.g. Emilio's own) so test data never lands on the team's board. Still open: a pre-cutover dedupe fallback (hand-typed items carry no hash LCR, so an order inside the 14-day window can be pushed twice; match Sales Order + Item text for the first 14 days), and whether the push sets a starting Design Status. | Emilio | Days before go-live. |
