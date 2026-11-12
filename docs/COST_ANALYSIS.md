# What the Plex ETL costs, and what was cut (2026-11-12)

The numbers below are an **estimate from usage × list price.** There is no billing export, and BigQuery
job history and Logging ingestion are not readable with our accounts. Turning on the billing export
to BigQuery is free and would make this exact.

## Where the money goes (per month, steady state 11-08 to 11-12)

| Service | Usage | About $/month |
|---|---|---|
| Cloud Run jobs | ~795k vCPU-s, ~676k GiB-s | ~$10.4 after the free tier (~$15.7 if the free tier is used elsewhere) |
| Cloud Build | 26 builds, 197 min on E2_HIGHCPU_8 (not in the free tier) | ~$3.2 |
| Cloud Scheduler | 33 jobs, 3 free | $3.0 |
| Artifact Registry | 11.6 GB plex-pipeline + 1.2 GB cloud-run-source-deploy, no cleanup policy | ~$1.2 |
| Secret Manager | ~15 secrets, ~40k accesses | ~$0.5-1 |
| BigQuery storage | 1.85 GiB (plex_mirror 1.14) | $0 (10 GiB free) |
| BigQuery queries | not readable; the largest table is 0.24 GiB | likely $0 (Looker Studio is the unknown) |
| Cloud Functions, GCS, Logging | dispatcher every 5 min; screenshots 3 MB, already deleted after 365 days | ~$0 |
| **Total** | | **~$18-24** |

### Cloud Run, by job (wall seconds a month)

- **Prod ETL, 14 jobs:** ~218k s. Most of it is about 80 s of start-up per run (boot, ODBC driver,
  connect, probe).
- **Label Design:** ~117k s. It runs 40 times a weekday; 78% of runs are "skipped" but still pay the
  boot.
- **Watchdog:** ~122k s.
- **Test cascade:** ~107k s.
- **Label Design test:** ~27k s.
- **Push:** ~18k s.
- **Screens:** ~93k s, but at 2 vCPU / 4 GiB that is 186k vCPU-s.
- **About 55% of all Cloud Run seconds are start-up overhead.**

## Done on 11-12 (PR #147)

| Change | About $/month |
|---|---|
| Cloud Build on the default machine (free minutes), timeout 3600 s | 3.1 |
| The 12 `*_test_retry` schedulers removed (nightly no-op containers) | 1.75 |
| Label Design test scheduler paused | 0.6 |
| Test cascade Monday-Friday only | 0.6 |
| Weekends: prod probes only, 04:xx and 23:xx (`etl_schedule.days`) | 0.5 |
| Watchdog hourly on weekends | ~0.4 |
| Screens 3 runs a day on weekends (was 6) | 0.35 |
| **Total** | **~7.3** |

## Projected, by service (hub tab "Budget", `scripts/hub/budget_tab.py`)

| Service | Before 11-12 | Now (projected) |
|---|---|---|
| Cloud Run jobs | 10.4 | 7.4 |
| Cloud Build | 3.2 | 0.1 |
| Cloud Scheduler (33 jobs to 23) | 3.0 | 2.0 |
| Artifact Registry | 1.2 | 1.2 |
| Secret Manager | 0.75 | 0.8 |
| Everything else | 0 | 0 |
| **Total (midpoints)** | **~19 (range 18-24)** | **~12 (range 11-17)** |

With the four cuts below, about $6-10 a month. Keep this table and `budget_tab.py` in step.

## Not done yet, ranked

1. **Decide "skip" before starting a container** (~$2-5). The dispatcher, or a Plex API check, would
   do this for Label Design and the probes that skip, instead of paying ~80 s of boot first. The
   Label Design API trigger (D38) is the same idea.
2. **Screens job at 1 vCPU / 2 GiB** (~$1.7). Watch for timeouts and running out of memory.
3. **Artifact Registry cleanup policy** (keep the last ~10 images) and delete the unused
   `cloud-run-source-deploy` repository (~$1.1).
4. **Watchdog hourly at night on weekdays too** (~$0.4).

## Evidence (read-only)

- `gcloud run jobs describe` (limits) and `gcloud run jobs executions list` (durations).
- `PlexProd.job_run_log` / `PlexTest.job_run_log`, `PlexOps.watchdog_log`, `PlexOps.screen_recon`.
- Dataset sizes from `__TABLES__`; `gcloud artifacts repositories list`; `gcloud builds list`.
- `gcloud storage du` on the screenshots bucket.
