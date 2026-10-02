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
| D3 | **ETL keeps yesterday's rows when Plex returns 0** (`main.py` `write_to_bigquery`). A table that genuinely empties shows stale data, silently. | Decision | Keep the guard against transient failures but mark staleness, e.g. log it in the run email or add a `last_nonempty_at`. Discuss before changing. |
| D4 | **Every YAML's `sql_file` hard-codes `gs://voxdatalake-report-configs`.** That breaks a move to another project or bucket. | Low | Template the bucket if a move is ever planned. |
| D5 | **The sandbox snapshot expires after 2026-09-30.** BigQuery time travel only reaches 7 days back. | whoever rebuilds | Before rebuilding: `python scripts/scorecard_sandbox/snapshot_check.py "<instant>" now`, pick an instant where every relation joins, and set `build.SNAPSHOT`. |
| D6 | `docs/CLICKUP_TEAM_GUIDE.md` is partly stale (counts, pipelines). | Low | Regenerate with the `team-guide` skill. |
| D7 | **Developer access as code is undecided.** A `terraform/developer_access.tf` (read access to secrets, driver/state buckets, BigQuery, logs for everyone in `developer_members`) was drafted 2026-09-30 and blocked by Claude Code's permission classifier. Until then an Owner grants the roles in `docs/ONBOARDING.md` by hand. | Emilio | Write or approve the file, or keep granting by hand. |
| D9 | **Fast-follow: gate the nightly ETL per RAW TABLE, not per run.** The 2026-10-01 probe skips a whole run and only pays off at hourly cadence — nightly, the chance nothing moved is ~0. The nightly win is a different shape: a fingerprint per `raw_*` table, so `sales_orders` skips the extractions that didn't move and still rebuilds all 22 views, and the duplicated pulls stop repeating themselves (`Sales_v_Release` and `Part_v_Part` are each extracted by three pipelines into the same table). Also gives D3 its staleness marker. **Nightly pipelines keep their `-retry` triggers** — "the probe is the retry" only works hourly. | Claude, in `ptbq-dev` on `dev`, from merged `main` | **First, one measurement:** does Plex ODBC push `SELECT COUNT(*), MAX(t.Update_Date) FROM <view> AS t` down, or scan and ship rows? If it doesn't push down, the probe costs as much as the pull and the idea dies. Don't build before that answer. |
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
| L5 | **Confirm the 09-30 Label Design deploy end to end.** `deploy/2026-09-30T1551Z` carried the part line, Bottle Material and the per-line key (`88907c4`). Check that the push image was rebuilt after it, and that a scheduled push logs `16/16 mapped columns` and `13 already on the board, 0 new` (the 13 reference items were re-keyed in place). | Emilio | Cloud Run logs for `plex-etl-label-design-push-test`. If it says 13 new, pause `plex-label-design-push-sync-test` and check the push log. **Note the 2026-10-01 gate changes what a quiet run looks like:** with nothing new in the view, the push stops at `Nothing in the view that the audit table hasn't seen` and never logs the mapped-columns line at all. To see that line, look at a run from before 2026-10-01, or trigger the job with `DRY_RUN=true` (which deliberately skips the gate). |
| L6 | **Chain the push onto the ETL.** The on-demand button (L2) runs only the ETL, so Monday waits for the 10:10/14:10 push. Options: A, the ETL job runs the push as its last step (recommended); B, the button waits for the ETL, then starts the push; C, a Cloud Workflow runs both. | Emilio | Pick A/B/C. |
| L7 | **Ashley's open board points:** delete the WO column; optionally automate the people "Sales Rep" from the status one (the push fills status). Email and phone are the customer's company-level contact; switching to the order line's contact person is possible if asked. | Ashley | On the board. |
| L9 | **Does the labeling team work the queue at weekends?** Half-answered: Jennilyn gave the hours the same day (5 AM - 5 PM, shipped 2026-10-01), but not the days, so it still runs Saturday and Sunday. Cheap either way — a weekend probe that finds nothing costs seconds and no Monday API calls — so this is tidiness, not urgency. The answer also settles the **prod** push schedule for L3. | Emilio / Ashley | Asked in the team chat 2026-10-01. On an answer: narrow the three Label Design schedules in `terraform/main.tf` to `* * 1-5`, update `docs/reports/label_design_report.md` and CHANGELOG, `./scripts/deploy.sh`. L8 numbering is retired — it was the 10-01 deploy, closed the same day. |
| L2 | **On-demand trigger app** (`deploy/label_design_trigger/`) is in `main` but not set up in Apps Script. | Emilio | Follow its README: an Apps Script project in `parasoldatalake` with the Cloud Run Admin API enabled; set `JOB_NAME` and `ALLOWED_EMAILS`; run `testSetup()`; deploy as a web app. Targets the **test** job until promoted. |
| L3 | **Before the 19 Oct cutover:** add a **prod** push job (PlexProd → "Plex Import" `18432111755`, the board the team will use; the view picks `vox.on.plex.com` for PlexProd by itself), and **repoint the test push job to a sandbox board** (e.g. Emilio's own) so test data never lands on the team's board. Still open: a pre-cutover dedupe fallback (hand-typed items carry no hash LCR, so an order inside the 14-day window can be pushed twice; match Sales Order + Item text for the first 14 days), and whether the push sets a starting Design Status. | Emilio | Days before go-live. |
