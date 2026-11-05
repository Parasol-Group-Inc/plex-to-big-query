# Health check 2026-11-04: ETL, Label Design, scorecard numbers

*Run 2026-11-04 15:30 UTC → 2026-11-05 02:35 UTC, read-only (no jobs started,
no data written). Three parts: ETL freshness and errors, the Label Design push,
and every scorecard figure on PlexProd, checked for double counting. The Plex
outage that began during this check has its own write-up:
[PLEX_PROD_ODBC_INCIDENT_2026-11-04.md](PLEX_PROD_ODBC_INCIDENT_2026-11-04.md).*

## 1. Verdicts

| Area | Verdict |
|---|---|
| ETL (prod) | **Degraded since 11-02, outage since 11-04 19:19 UTC**: Plex prod ODBC, see the incident doc. Before the outage, data was current: the 11-04 4 AM MT full run refreshed 12 of 15 jobs. |
| ETL (test) | Healthy apart from `sales-orders-test`, partial for 3 nights: `PlexTest.msl_rules` has no schema, so `approaching_msl_report` fails (D29). |
| Label Design push | **Healthy.** No failures, duplicates or misses since 10-28. |
| Scorecard numbers | **No double counting found.** October figures are distorted by the go-live, not by counting (S18). |
| Code | 98 of 98 tests pass in the ETL image. Local Docker check passes. |

## 2. ETL (as of 11-04 15:38 UTC, before the outage)

Per prod job, last 7 days, from `job_run_log` (skips excluded):

| Job | Runs | ok / partial / fail | Last clean run (UTC) |
|---|---|---|---|
| sales-orders | 34 | 29 / 2 / 3 | 11-04 11:04 |
| work-orders | 23 | 23 / 0 / 0 | 11-04 11:08 |
| purchasing-open-orders | 17 | 17 / 0 / 0 | 11-04 11:12 |
| inventory-activity | 7 | 7 / 0 / 0 | 11-04 11:22 |
| part-on-hand-inventory | 26 | 23 / 2 / 1 | 11-04 11:32 |
| purchasing-pending-requisitions | 7 | 7 / 0 / 0 | 11-04 11:37 |
| sales-quotes | 16 | 9 / 0 / 7 | 11-04 11:42 |
| sales-returns | 8 | 8 / 0 / 0 | 11-04 11:43 |
| quality-supplier-returns | 7 | 7 / 0 / 0 | 11-04 11:47 |
| part-routing | 20 | 20 / 0 / 0 | 11-04 11:53 |
| part-lot | 24 | 20 / 4 / 0 | 11-04 12:01 |
| label-design | 64 | 22 / 0 / 42 | 11-04 12:03 |
| quality-nonconformance | 8 | 7 / 0 / 1 | 11-03 11:26 |
| part-obsolescence | 10 | 9 / 0 / 1 | 11-03 20:17 (probe) |
| inventory-snapshot | 17 | 16 / 0 / 1 | 11-03 20:21 (probe) |

- `job_run_log` under-counts failures: a run killed at its Cloud Run timeout
  writes no row. The dispatcher log has them (incident doc).
- sales-quotes' 7 and label-design's 42 failures are from the 10-28 → 10-30
  outage (D20), not this week.
- All current runs are on build `800785e`.
- `PlexProd.msl_demand_daily` wrote one day per day from 10-30 to 11-04
  (about 2,850–2,920 rows each).
- 22 of 124 PlexProd `raw_*` tables are older than 24 h. 20 are quiet tables
  last changed June to September. The other 2 are `raw_Quality_v_Final_Disposition`
  and `raw_Quality_v_Initial_Disposition`, stale because quality-nonconformance's
  11-04 full run was killed.
- D19 (BigQuery load queueing) could not be measured: `claude-readonly` lacks
  `bigquery.jobs.listAll`. The incident doc shows the killed runs were stuck on
  Plex reads, not loads.

## 3. Label Design push (10-28 → 11-04)

From `PlexProd.label_design_push_log`, Cloud Logging and Monday reads:

- **41 items created in 14 push runs.** No `failed` or `partial` rows, and the
  fill step ran on every run since 10-29.
- **No duplicates.** No `dedupe_key` was created twice.
- **No misses.** All 64 rows of `label_design_report` have a created row in the log.
- **Nothing stuck.** Plex Import Test holds 0 live items. 58 logged items are
  live on Design & QA, and the team moved 20 to the archive.
- **Two alerts:** "Inside Sales Rep: add 'Emily Gray'" (10-28) and "Printing
  Material: add 'Metallic BOPP - Matte Lamination'" (11-02). Both are missing
  labels on Design & QA.
- **One pushed item was deleted by hand:** 13457483734 (SO 365,
  `70000-65CTEJO-0`, pushed 11-03 20:04). The push will not re-create it. L17.
- **Blank columns:** Phone is blank on 40 of 40 items since 10-28, and Inside
  Sales Rep on 36 of 40. Blank Plex attributes stay blank by design. The rep
  gap matches the Emily Gray alert.

## 4. Scorecard numbers (PlexProd, 11-04)

Every figure in `scripts/hub/figure_queries.py` was run for November to date
and for October as a whole. The hub was refreshed and republished with these
values (Data Hub v33, snapshot 2026-11-04 15:45 UTC).

### Checked for double counting: none found

| Check | Result |
|---|---|
| Duplicate keys in raw tables (Release, PO_Line, PO, Production, Part, Workcenter, Customer, Job, Job_Op, Plexus_User) | none: row count equals distinct key count in all 10 |
| `shipping_revenue_report` fan-out | 224 rows for 224 shipper lines, one `Shipper_Line_Release` per line, every line priced |
| Daily production views vs `production_vs_goal_report` | equal for Labeling and Bottling. Encapsulating differs by 2,745,294 in October, which is its scrap (monthly counts good + scrap) |
| Bottling 9-parts after the 11-01 cutover (D27) | raw Bottling on 9-parts fell from 20–47K a day to 25 a day (qty 1 each) on 11-02 and 11-03. `bottling_9part_with_5_bom_qty` = 0. No double credit |
| `mfg_job_open_caps_report` | one row per job. 172M of the 219M open caps are 26 Scheduled jobs entered at go-live |

### What distorts the numbers

1. **October sales include the go-live load.** On **2026-10-16**, 232 orders
   (446 lines) got their first Pending Fulfillment change in Plex, all on the
   same day: the migration of every open order. `sales_mtd_by_status_change_report`
   dates a sale by that change, so October reads about 133% to goal, and
   69% of it is that one day. Without 10-16, October is about a third as large.
   Sales YTD only holds October and November. S18.
2. **October production and revenue start on 10-19.** Plex production records
   and shipments begin 2026-10-19, so October compares 11 days with a
   full-month goal (Encapsulating 60%, revenue 22%). Daily encapsulation is a
   steady 4.5–7.6M. **November is the first clean month.**
3. **Quality tiles have no Plex data.** The newest nonconformance is 2026-09-28,
   there are 0 deviations, and TAT is NULL. Bottling and Labeling have never
   recorded a reject, so their FPY reads 100%. Printing shows rejects since
   11-01 (FPY 68%). S8 already covers the dollar side.
4. **"Total in Shipping" is $8.79.** Of 135 shippers, 1 is Open and 134 Shipped:
   shippers are created and shipped the same day, so nothing waits on an open
   shipper. The tile's idea does not match how Vox ships in Plex.
5. **The run-rate counts today as a full day** (`pct_into_month` = 4/30 on
   11-04), which slightly understates the projection early in the month.
   Cosmetic.

### November to date (11-04)

| Figure | Value |
|---|---|
| Revenue MTD | about $0.29M against a $5.0M goal (run-rate projection about $2.19M) |
| Sales MTD | about $0.53M against a $5.0M goal |
| Pipeline (Plex stages only) | about $0.93M (Quote, Pending Sales Approval) |
| WIP (open Pending Fulfillment) | about $5.81M |
| Encapsulating | 10.59M against 127M (8%) |
| Bottling | 157,604 against 1.35M |
| Labeling | 55,790 against 750K |
| Out of stock | 13 parts |
| Open caps / bottles | 218.9M / 2.29M |

## 5. Tests run

| Test | Result |
|---|---|
| `pytest tests` inside the ETL image (amd64) | 98 passed |
| Local Docker (`docker compose up`, `.env`, test host) | connected on attempt 1 in 4 s, 622 `Part_v_Part` rows, exit 0 |
| Same container against the **prod** host from the Mac (run by Emilio, 11-05 02:36 UTC) | connect took 60 s; `Part_v_Part` returned nothing in 46 min; a second connect got no answer in 60 s. **Plex prod fails outside Google Cloud too** |

On Apple Silicon the image must be built as amd64
(`export DOCKER_DEFAULT_PLATFORM=linux/amd64`, `docs/ONBOARDING.md`). An arm64
build fails with `Can't open lib ... ivoa27.so : file not found`. pyodbc does
not build on the Mac without unixODBC, so run the tests inside the image:

```bash
export DOCKER_DEFAULT_PLATFORM=linux/amd64
docker compose build
docker run --rm --entrypoint sh -v "$PWD/tests:/app/tests" -v "$PWD/deploy:/app/deploy" -v "$PWD/scripts:/app/scripts" -v "$PWD/reports:/app/reports" plex-to-big-query-etl -c 'pip install -q pytest && cd /app && python -m pytest tests -q'
```

Prod-host check from outside Google Cloud. If it also fails, the fault is
Plex's prod service. If it works, look at the Cloud Run egress path:

```bash
export DOCKER_DEFAULT_PLATFORM=linux/amd64
docker compose run --rm -e PLEX_HOST=vox.odbc.plex.com etl
```
