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

At 02:30 UTC, during the prod outage, local Docker (amd64 image, `.env`,
**test** host) connected on attempt 1 in 4 s and fetched 622 rows. The same
container against the **prod** host was not run: that is a production read,
which Claude is not allowed to make, so a human has to run it. The command is in
[HEALTH_CHECK_2026-11-04.md](HEALTH_CHECK_2026-11-04.md) § 5. If the prod host
also fails from outside Google Cloud, the fault is Plex's.

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
