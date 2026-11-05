# Plex prod ODBC degradation and outage, 2026-11-02 → 2026-11-05

*Written 2026-11-05 ~02:30 UTC (2026-11-04 evening MT), while the outage was still
open. Continues OPEN_ITEMS **D20** (Plex prod ODBC refuses sessions, since
2026-10-22; Plex case opened through the Plex champion). All times UTC unless
marked MT.*

## Summary

Since **Monday 2026-11-02 12:32 UTC** the Plex **production** ODBC host
(`vox.odbc.plex.com:19995`) has been getting worse in three ways:

1. **Connects get no answer within 60 s.** Before 11-02 12:00, every prod run
   connected on its first attempt. Since then a share of connects time out
   every hour, and from **11-04 19:19 UTC (12:19 PM MT)** most of them do.
2. **Sessions are reset mid-query** (`08S01 ... TCP/IP, connection reset by
   peer (2310)`). First seen 11-02 20:37 on `Part_v_Container`.
3. **Queries hang until Cloud Run kills the task.** For example, on 11-04 22:24
   `part-on-hand-inventory` connected (second attempt), ran its probe in 20 s,
   then sat on `SELECT ... FROM Part_v_Container` for 17.5 min, until the
   1200 s task timeout at 22:42. A killed task writes no outcome, so the
   dispatcher logs "execution failed or was cancelled before the job wrote its
   outcome". First kill: 11-03 01:31.

The **Plex test host** (`vox.test.odbc.plex.com`) was unaffected. Every
nightly test job connected on the first attempt from 11-02 through 11-05,
including during tonight's prod outage. Both environments run the same image,
from the same GCP project, region and egress. **The fault is on the Plex
production ODBC service, not our network, code or credentials.**

## Evidence

### Prod connect outcomes per hour (Cloud Logging, all prod `plex-etl-*` jobs)

`ok` = "ODBC connection established (attempt 1)", `retry` = connected on
attempt 2 or 3, `no answer` = one 60 s attempt with no answer, `reset` = 08S01,
`killed` = Cloud Run task timeout.

| Window (UTC) | What the logs show |
|---|---|
| up to 11-02 11:59 | every connect `ok` on attempt 1 |
| 11-02 12:00 → 20:00 | 1–4 `no answer` per hour, mostly Label Design's 15-min probes; the retry connects |
| 11-02 20:00 → 11-03 07:00 | first `reset`s (13 on 11-02 20–21 h, 10 at 06 h); first `killed` runs |
| 11-03 → 11-04 18:00 | same mix; every 4 AM / 1 PM / 6 PM / 11 PM MT batch loses 2–5 runs to kills |
| **11-04 19:00 → now** | outage: 12–29 `no answer` per hour; the breaker holds 13 jobs at 20:05–20:55; canaries fail every 15 min; recovery runs that do connect hang and are killed |

`no answer` events since 11-02, by job: label-design 64, sales-quotes 28 (it
is the canary), sales-orders 9, part-lot 8, work-orders 7, part-obsolescence 7,
others 1–6.

### Dispatcher (`PlexOps.etl_dispatch_log`, non-skip outcomes)

| Day | success | partial | failed: no connect | failed: killed | held-outage |
|---|---|---|---|---|---|
| 11-01 | 16 | 0 | 0 | 1 | 0 |
| 11-02 | 18 | 4 | 0 | 0 | 0 |
| 11-03 | 31 | 4 | 0 | 8 | 0 |
| 11-04 | 20 | 0 | 16 | 15 | 13 |
| 11-05 (to 02:30) | 2 | 0 | 12 | 7 | 4 |

Partials before the outage are all `08S01` mid-query: `Part_v_Part`
(part-lot), `Part_v_Container` (part-on-hand-inventory) and `Sales_v_PO`
(sales-orders).

### Test host (Cloud Logging, `plex-etl-*-test`)

| Day | connected on attempt 1 | retried | no answer | reset |
|---|---|---|---|---|
| 11-02 | 29 | 1 | 0 | 0 |
| 11-03 | 31 | 0 | 0 | 0 |
| 11-04 | 31 | 0 | 0 | 0 |
| 11-05 (so far) | 2 | 0 | 0 | 0 |

## Update 2026-11-05 16:00 UTC (09:00 MST): still down

Between 11-05 03:30 and 16:00 UTC, about 135 connect attempts were made. 98
got no answer in 60 s and 37 connected (13 on the first attempt). Of the runs
that connected, 20 hung on a read until they were killed, and the 08S01 resets
continue. `Sales_v_PO` was read 6 times and never returned; one of those reads
ran 1,562 s, from 04:55 to 05:21 MST.

The only successes are small jobs. The sales-quotes canary succeeded at 04:40,
05:25 and 07:45 MST, but each run took 370–437 s, against an average of 95 s
from 10-25 to 11-01.

| Since | Jobs |
|---|---|
| 11-04 04:00–04:55 MST (last full run) | sales-orders, work-orders, purchasing-open-orders, part-on-hand-inventory, part-routing, part-lot |
| 11-02 | part-obsolescence, inventory-snapshot |
| 11-04 09:04 MST | label-design (last push to Monday 09:05) |

The 11-05 4 AM MST full batch failed or was held for every job. Second email
sent to Plex Support with `output/plex_odbc_failures_2026-11-04_to_05_update.csv`
(116 rows) and `output/plex_odbc_hung_reads_2026-11-02_to_05.csv` (63 hung
reads across 15 views).

## What it is not

- **Not BigQuery (D19).** The killed runs are stuck on the Plex read (the log's
  last line is `Querying Plex [...]`), not on a load job.
- **Not our timeouts.** Live Cloud Run timeouts match Terraform: 600 s for the
  small jobs, 1200 s for part-on-hand-inventory, part-routing,
  purchasing-open-orders and work-orders, 1800 s for sales-orders, 2400 s for
  part-lot. Raising them would not help a read that never returns.
- **Not concurrency.** D20 already showed 8 concurrent prod sessions opening
  fine. Tonight, single canaries fail alone.
- **Not a deploy.** Every run since 11-02 is on build `800785e`. Nothing was
  deployed between the last clean day (11-01) and the first failure.

## What worked

- **The outage breaker** (CLAUDE.md, "A Plex outage trips a breaker") did its
  job. After two connect failures it held 13 scheduled jobs and sent one
  canary every 15 min. The emails were limited to the first canary failure.
- **The test environment ran normally.** The PlexTest data is current.
- **The data stays readable.** PlexProd keeps yesterday's rows (D3), so views
  are stale, not empty. The 4 AM MT full run on 11-04 refreshed 12 of 15
  jobs before the outage began.

## Gaps this exposed

1. **No Plex query timeout.** `main.py` sets a 30 s login timeout and connect
   deadlines, but nothing bounds `cursor.execute` on a Plex read. A hung read
   runs to the Cloud Run task timeout, the task is killed, and no
   `job_run_log` or dispatch outcome is written. Proposed: set `conn.timeout`
   (pyodbc `SQL_ATTR_QUERY_TIMEOUT`) to about 5 min per query, so a hung read
   fails as a normal partial with its error recorded. **First test whether
   the OpenAccess driver honours it,** against the test host with a deliberately
   slow query. Tracked as D28.
2. **Killed runs vanish from `job_run_log`.** Only the dispatcher's reconcile
   sees them. The digest and hub runs table under-count failures.
3. **The breaker only counts connect failures.** Before 11-04 19:00 the
   problem looked like hangs and resets after a good connect, which the breaker
   does not count. It took the full outage to trip it.

## Local Docker check (2026-11-05)

Same amd64 image, same `.env` credentials, run from Emilio's Mac on a home or
office network, entirely outside Google Cloud:

| Time (UTC) | Host | Connect | `SELECT ... FROM Part_v_Part` |
|---|---|---|---|
| 11-05 02:29:57 | `vox.test.odbc.plex.com` | attempt 1, **4 s** | 622 rows in **1.7 s** |
| 11-05 02:36:59 | `vox.odbc.plex.com` | attempt 1, **60 s** (02:37:59, at the edge of our 60 s deadline) | **no rows in 46 min**: the read was still hanging at 03:23, when the container was stopped |
| 11-05 03:22:06 | `vox.odbc.plex.com` | attempt 1: **no answer within 60 s**; retry interrupted by hand | not reached |

**This settles where the fault is.** Prod behaves the same from outside Google
Cloud: a connect that takes the full minute, then a read that never returns.
It is not Cloud Run, our egress, the image or the credentials. The fault is
Plex's production ODBC service.

## What to send Plex (add to the D20 case)

- Host `vox.odbc.plex.com:19995`, ODBC (OpenAccess SDK / DataDirect), IAM
  token auth, user `edominguez.parasol`, from Google Cloud Run `us-central1`.
- Degradation from **2026-11-02 12:32 UTC**. Outage from **2026-11-04 19:19 UTC**.
- Three symptoms, with timestamps from the logs above:
  - connect gets no answer in 60 s;
  - `08S01 connection reset by peer (2310)` mid-query on `Part_v_Container`,
    `Part_v_Part` and `Sales_v_PO`;
  - `SELECT` on `Part_v_Container` returns nothing for 17+ min after a good
    connect (11-04 22:24:47 → killed 22:42:18).
- The same queries from the same place against `vox.test.odbc.plex.com` are
  fine.
- **It reproduces outside Google Cloud.** From a laptop on 11-05 02:36 UTC,
  the prod connect took 60 s and `SELECT` on `Part_v_Part` returned nothing
  in 46 min; the next connect got no answer in 60 s. Test from the same laptop: 4 s connect, 622 rows in 1.7 s.

## Check it is over

```sql
SELECT FORMAT_TIMESTAMP('%m-%d %H', dispatched_at) AS hr, outcome, COUNT(*) AS n
FROM `voxdatalake.PlexOps.etl_dispatch_log`
WHERE dispatched_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY 1, 2 ORDER BY 1, 2
```

The outage is over when canaries succeed, `recovery` rows succeed, and the
next 4 AM MT full batch has no `failed` rows. D20 closes after a week with no
`held-outage` rows.

## Update 2026-11-05 ~17:30 UTC (10:30 MST): manual refresh of revenue and shipping

Ad-hoc reruns did not get through. sales-orders (16:17 UTC) connected on the
third attempt, then `Sales_v_PO` hung 24.5 min until the 1800 s timeout.
part-on-hand-inventory (16:48 UTC) connected on the third attempt, then hung
until the 1200 s timeout.

**Workaround:** Emilio exported the 9 raw views behind revenue and shipping from
Plex SQL Developer, which still answers, and they were loaded with
`scripts/load_plex_csv_dump.py` (CHANGELOG 2026-11-05). Backups of the replaced
tables are in `voxdatalake.Backups` as `PlexProd__raw_<view>_20261105`. To refresh
more areas the same way:

| Area | Views to export (`SELECT * FROM <view>`) |
|---|---|
| Revenue, shipping (done 11-05) | Sales_v_PO, Sales_v_PO_Line, Sales_v_Release, Sales_v_Price, Sales_v_Shipper, Sales_v_Shipper_Line, Sales_v_Shipper_Line_Release, Sales_v_Shipper_AR_Invoice, Accounting_v_AR_Invoice |
| Sales MTD (sale date) | Sales_v_PO_Change, Sales_v_Order_Salesperson |
| Parts / on hand | Part_v_Part, Part_v_Container |

Save them as `manual-dumps/<date>/<view>.csv` (gitignored), back up the raw tables,
run the script without `--swap`, read its comparison, then run it with `--swap`.
