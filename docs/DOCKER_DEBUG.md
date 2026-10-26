# Debugging with Docker

A short playbook for "is it Plex, our code, or the cloud?". Everything here is
**read-only**: local mode writes a CSV to `./output/`, never to BigQuery, and sends no
email. First-time setup (driver folder, `.env`) is in [LOCAL_SETUP.md](LOCAL_SETUP.md).

Run from a project folder (the Docker commands work in any of them). Docker Desktop
must be running; if `docker compose` says it can't reach `dockerDesktopLinuxEngine`,
start it and wait about a minute.

## 1. Can this machine reach Plex? (the 30-second check)

```bash
docker compose build && docker compose up      # then: docker compose down
```

Expected, in the log:

```
Connecting driver-direct to vox.test.odbc.plex.com:19995 (IAM token auth, UID=...)
ODBC connection established (attempt 1).
Fetched 621 rows from Plex [Part_v_Part].
=== ETL job complete — 621 rows written across 621 fetched ===
```

and a `local_prod_test_<timestamp>.csv` in `./output/`. It uses `.env`, which points at
the **test** host.

## 2. Same check against prod, without touching `.env`

```bash
docker compose run --rm -e PLEX_HOST=vox.odbc.plex.com -e BQ_TABLE=local_prod_host_check etl
```

`-e` overrides `.env` for this one run. `BQ_TABLE` only names the CSV. Use this when a
Cloud Run job is refused and you want to know whether the account and Plex prod are fine
from a different network. (2026-10-26: Cloud Run was refused at 9:20 and 9:29 AM MDT while
a laptop got in at 9:50 AM; see OPEN_ITEMS D20.)

## 3. Pull one specific Plex view (documented in LOCAL_SETUP, not re-run on 2026-10-26)

```bash
docker compose run --rm -e PLEX_VIEW=Sales_v_PO -e PLEX_FILTER="" -e BQ_TABLE=po_check etl
```

`PLEX_VIEW` is always `{Database}_v_{ViewName}`. `PLEX_FILTER` is a whole `WHERE ...`
clause, or empty. The default filter is `WHERE Part_Type = 'Raw Materials'`, so pass
`-e PLEX_FILTER=""` when you want every row. Handy for checking that a column exists
(for example `Order_No` on `Sales_v_PO`) before putting it in a view.

## 4. Check that a report's SQL still compiles

BigQuery views are not run locally; dry-run them against a dataset instead. Feed the file
on **stdin**: passing the SQL as an argument breaks on its leading `--` comments.

```bash
sed 's/{gcp_project}/voxdatalake/g; s/{dataset}/PlexProd/g' reports/sql/sales_orders_view.sql \
  | bq query --use_legacy_sql=false --project_id=voxdatalake --dry_run
```

Expected: `Query successfully validated.` An error here is the same error the pipeline would
log when it creates the view. Use `PlexTest` to check against test data.

## 5. Reading what happened in the cloud

Times in the logs are UTC; subtract 6 hours for MDT.

```bash
# Did the dispatcher start / hold the job? (UTC; add AT TIME ZONE for MDT)
bq query --use_legacy_sql=false --project_id=voxdatalake \
  "SELECT FORMAT_TIMESTAMP('%m-%d %H:%M', dispatched_at, 'America/Denver') mdt, job_name, mode, reason, outcome, SUBSTR(detail,1,80) d
   FROM \`voxdatalake.PlexOps.etl_dispatch_log\` WHERE job_name='plex-etl-sales-orders'
   ORDER BY dispatched_at DESC LIMIT 10"

# What each run did (also covers jobs the dispatcher does not start, e.g. Label Design)
bq query --use_legacy_sql=false --project_id=voxdatalake \
  "SELECT FORMAT_TIMESTAMP('%m-%d %H:%M', logged_at, 'America/Denver') mdt, job_name, status, rows_written, SUBSTR(detail,1,100) d
   FROM \`voxdatalake.PlexProd.job_run_log\` ORDER BY logged_at DESC LIMIT 15"
```

A manual `gcloud run jobs execute` does **not** write to `etl_dispatch_log`, and its email
says "Scheduled run".

## Reading the result

| What you see | It means |
|---|---|
| Local connects, Cloud Run refused | Not the account or the code. A Plex-side session problem or the cloud network path; check whether other jobs failed in the same window. |
| Local refused too, same error | Plex prod itself is refusing; wait, the dispatcher's outage breaker re-runs held jobs once a canary connects. |
| Local OK on test, refused on prod | Prod-specific. Say so to Plex. |
| `08S01` 2300 / 2310 / 2404 | Connection dropped / reset / session refused. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) § 2404 (it can be transient). |
| `3059 Token is expired` | Renew the secret `plex-access-token`; see TROUBLESHOOTING. |

Don't retry a refused prod job by hand in a loop: each attempt opens 3 sessions.
