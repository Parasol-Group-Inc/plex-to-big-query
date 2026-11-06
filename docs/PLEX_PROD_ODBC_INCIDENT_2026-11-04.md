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

## Second laptop check, and prod vs test from both places (2026-11-06)

A second check from Emilio's Mac (public IP `149.88.25.130`), separate from the
other PC's, while the outage was still open. The same 8 runs went out together at
17:45-17:48 UTC: prod and test host, a small job (`sales_returns`, 2 views) and a
big one (`sales_orders`, 29 views), from local Docker (OUTPUT_MODE=local, nothing
written) and from Cloud Run `us-central1`. Neither job was running at the time; the
`sales_quotes` canary and Label Design were left alone.

| Where | Host | Job | Connect | Reads | Result |
|---|---|---|---|---|---|
| Mac Docker | test | small | attempt 1, ~5 s | 1 row 1.2 s, 8 rows 1.1 s | OK, 9 rows in 15 s |
| Mac Docker | test | big | attempt 1 | paged normally | OK, 305,516 rows in 4.7 min |
| Cloud Run | test | small | attempt 1, 1.5 s | ~1-3 s each | OK, 9 rows |
| Cloud Run | test | big | attempt 1, 1.6 s | paged normally | 305,516 rows; one BigQuery view failed to build (not Plex) |
| Mac Docker | **prod** | small | no answer 60 s twice, **attempt 3** (17:48:54) | 1 row **24 s**, 8 rows **19 s** | OK, 9 rows |
| Mac Docker | **prod** | big | **no answer 60 s, 3 times** | - | failed |
| Cloud Run | **prod** | small | **no answer 60 s, 3 times** | - | failed |
| Cloud Run | **prod** | big | attempt 2 (17:50:31) | probe COUNTs 5-12 s; `Sales_v_PO` page 1 (500 rows) hung 150 s three times, with reconnects; then a COUNT on `Sales_v_PO_Line` hung | partial, 0 rows: the D28 guard stopped after 4 hangs, 22 min |

Prod connects: 1 of 6 succeeded from the Mac, 4 of 10 from Cloud Run. Every
failure was "no answer within 60 s", never a refusal or reset. At 17:48:54 the
Mac's prod connect succeeded while Cloud Run's attempt in the same minute got no
answer, so it is per session, not per network.

**The ODBC probe (`scripts/plex_odbc_probe.py`)** was written for this: one round
per host of DNS lookup, a bare TCP handshake to port 19995, the ODBC connect, an
8-row COUNT and a `TOP 10`, each with its own deadline, printed as a table to paste
into the case. From the Mac:

| UTC | Host | DNS | TCP | Connect | 8-row COUNT | TOP 10 `Sales_v_PO` |
|---|---|---|---|---|---|---|
| 11-06 18:25:55 | prod | 8.34.94.50 | 0.21 s | no answer in 90 s | - | - |
| 11-06 18:27:25 | test | 8.34.94.51 | 0.21 s | 3.9 s | 1.1 s | 1.0 s |
| 11-06 18:27:52 | prod | 8.34.94.50 | 0.22 s | 52.4 s | 6.1 s | 16.1 s |
| 11-06 18:29:07 | test | 8.34.94.51 | 0.19 s | 5.0 s | 1.1 s | 0.9 s |
| 11-06 18:34:48 | prod | 8.34.94.50 | 0.18 s | no answer in 90 s | - | - |
| 11-06 18:36:19 | test | 8.34.94.51 | 0.22 s | 4.0 s | 1.1 s | 1.1 s |

**The network reaches Plex fine:** prod's port completes a TCP handshake in 0.2 s,
the same as test's. What doesn't answer is the ODBC service behind it: the login
takes 50-90+ s or never completes, and a session that does log in reads 6-16x
slower than test. The two hosts resolve to neighbouring addresses (`.50` prod,
`.51` test), worth mentioning to Plex.

Side notes from the runs:
- A manual run of a prod job other than Label Design is invisible to the outage
  breaker: only `plex-etl-label-design` sets `OUTAGE_BREAKER_TABLE`, the rest log
  through the dispatcher. So the failed `sales_returns` run has no row in
  `etl_dispatch_log`. That's by design, but it means ad-hoc runs don't count as
  breaker evidence.
- The two prod Cloud Run runs ended failed/partial and sent the usual emails. No
  PlexProd table changed (0 rows written; a failed table keeps yesterday's rows).

### A third angle: the probe from AWS CloudShell

To show Plex the same result from a network that is neither Google Cloud nor
ours, run the probe in AWS CloudShell (a browser terminal on Amazon Linux in our
AWS account: no instance to create and nothing to pay for). It runs without
Docker: the bundle holds the Plex Linux driver (29 MB, gitignored), the probe
and `scripts/plex_odbc_probe_run.sh`, which installs unixODBC, pam and pyodbc and
points the driver at its own files. Checked on a clean `amazonlinux:2023` image
on 11-06 (rows 5-6 above).

1. Build the bundle on a machine with the repo and `driver/`, from the repo root:
   ```bash
   mkdir -p /tmp/b/plex_probe && cp -R driver scripts/plex_odbc_probe.py /tmp/b/plex_probe/ && cp scripts/plex_odbc_probe_run.sh /tmp/b/plex_probe/run.sh
   cd /tmp/b && COPYFILE_DISABLE=1 tar --no-mac-metadata --no-xattrs -czf plex_probe.tgz plex_probe
   ```
   (Drop `--no-mac-metadata --no-xattrs` on Linux.)
2. In the AWS console pick a region (us-east-1 or us-west-2 give a different
   path than our us-central1), open CloudShell, Actions → Upload file →
   `plex_probe.tgz`.
3. In CloudShell:
   ```bash
   tar xzf plex_probe.tgz
   read -rs PLEX_ACCESS_TOKEN && export PLEX_ACCESS_TOKEN
   ./plex_probe/run.sh --passes 3
   ```
   Paste the token from `.env` at the silent prompt. The first line of the output
   gives the AWS public IP for Plex to look up.
4. Afterwards: `rm -rf plex_probe plex_probe.tgz` (the CloudShell home persists
   between sessions).

**Result, 2026-11-06 18:49-19:00 UTC, AWS CloudShell us-east-2 (public IP
`18.224.22.68`), two runs of `--passes 3`:**

| UTC | Host | TCP | Connect | 8-row COUNT | TOP 10 `Sales_v_PO` |
|---|---|---|---|---|---|
| 18:49:08 | prod | 0.03 s | no answer in 90 s | - | - |
| 18:50:38 | test | 0.03 s | 1.3 s | 0.2 s | 0.4 s |
| 18:51:01 | prod | 0.03 s | no answer in 90 s | - | - |
| 18:52:31 | test | 0.03 s | 1.2 s | 0.3 s | 0.4 s |
| 18:52:53 | prod | 0.03 s | 43.4 s | 21.0 s | 11.6 s |
| 18:54:09 | test | 0.03 s | 0.4 s | 0.2 s | 0.2 s |
| 18:54:39 | prod | 0.03 s | no answer in 90 s | - | - |
| 18:56:09 | test | 0.03 s | 1.2 s | 0.2 s | 0.3 s |
| 18:56:31 | prod | 0.03 s | no answer in 90 s | - | - |
| 18:58:01 | test | 0.03 s | 0.5 s | 0.2 s | 0.3 s |
| 18:58:22 | prod | 0.03 s | 72.9 s | 7.1 s | 18.4 s |
| 19:00:02 | test | 0.03 s | 1.4 s | 0.6 s | 0.5 s |

Test: 6 of 6 logins in 0.4-1.4 s, queries 0.2-0.6 s. Prod, in the same minutes from
the same machine: 4 of 6 logins got no answer in 90 s, two took 43 s and 73 s, and
their queries took 7-21 s (30-100x test). TCP to both answered in 0.03 s. So from a
third network, neither Google Cloud nor ours, prod's ODBC service is the only thing
that fails.

The same probe runs anywhere the ETL image does:

```bash
docker run --rm --platform linux/amd64 --env-file .env -e PROBE_SOURCE="Mac" -v "$PWD/scripts:/scripts:ro" --entrypoint python plex-to-big-query-etl /scripts/plex_odbc_probe.py --passes 3
```

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
- **Still the same on 2026-11-06, from a second laptop (public IP `149.88.25.130`).**
  TCP to `vox.odbc.plex.com:19995` (8.34.94.50) completes in 0.2 s, so the network
  path is fine, but the ODBC login takes 52 s or gets no answer in 90 s; once in,
  an 8-row COUNT takes 6 s and `SELECT TOP 10` on `Sales_v_PO` 16 s. Test
  (8.34.94.51) from the same place: 4 s login, about 1 s per query. Cloud Run in
  the same window: 4 of 10 prod connects succeeded, then a 500-row page of
  `Sales_v_PO` hung for 150 s three times in a row.
- **And from AWS (us-east-2, public IP `18.224.22.68`), 2026-11-06 18:49-19:00 UTC:**
  TCP to both hosts in 0.03 s; test logged in 6 of 6 times in 0.4-1.4 s with
  queries in 0.2-0.6 s, while prod got no answer in 90 s on 4 of 6 logins, took
  43 s and 73 s on the other two, and then 7-21 s per tiny query. Three networks
  (Google Cloud us-central1, two office/home connections, AWS us-east-2), one result.
- **Partly better by the afternoon of 2026-11-06, still not usable.** From AWS
  (public IP `3.16.213.75`), 21:25-21:41 UTC: 8 of 9 prod logins got through, but
  each took 29-74 s and a 1-row or 10-row query took 3-16 s; test in the same
  minutes logged in in 0.4-1.3 s with 0.2-0.3 s queries. Our scheduled prod jobs
  kept failing (14:25 MT batch). Separately, the SQL Development Environment caught
  up to about 11:00 CT on 11-06 after being stuck at 11-04 ~18:56 MT, then stopped
  again: at 14:37 CT the Shipping Revenue screen had four invoices (INV0000180-183,
  $49,721.50) that SQL Development still did not show. So the data copy behind
  SQL Development seems to refresh in batches, and the ODBC login service is
  slow on top of that.

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

## Update 2026-11-05 afternoon: SQL Development froze too; Plex screens used instead

By the afternoon the SQL Development Environment returned the same frozen copy
as ODBC (newest rows from 2026-11-04 ~18:56 MT), so CSV exports could no longer
bring anything newer. Plex's own screens were still live. An hourly laptop task
now reads three of them (Shipping Revenue by Part Group, Shipper History, and the
Pending Fulfillment sales orders with their releases) into `PlexProd.live_*`, and
Label Design reads the releases table while it is fresh, pushing new Label Design
lines to Monday again. Details, safeguards and how to retire it:
[PLEX_SCREEN_EXTRACTION.md](PLEX_SCREEN_EXTRACTION.md) (OPEN_ITEMS D30).

## Update 2026-11-06 afternoon: logins mostly answer, slowly; SQL Development refreshed once

**AWS CloudShell us-east-2 (public IP `3.16.213.75`), 21:25-21:41 UTC, `--passes 3`
then `--passes 6`:**

| UTC | Host | TCP | Connect | 8-row COUNT | TOP 10 `Sales_v_PO` |
|---|---|---|---|---|---|
| 21:25:53 | prod | 0.03 s | no answer in 90 s | - | - |
| 21:27:45 | prod | 0.03 s | 36.6 s | 3.8 s | 9.0 s |
| 21:28:56 | prod | 0.04 s | 61.2 s | 7.6 s | 16.0 s |
| 21:33:13 | prod | 0.03 s | 73.8 s | 3.7 s | 9.2 s |
| 21:35:02 | prod | 0.03 s | 53.5 s | 5.3 s | 12.5 s |
| 21:36:35 | prod | 0.03 s | 32.2 s | 3.9 s | 9.0 s |
| 21:37:42 | prod | 0.03 s | 44.7 s | 4.4 s | 11.0 s |
| 21:39:03 | prod | 0.03 s | 40.6 s | 4.1 s | 10.5 s |
| 21:40:20 | prod | 0.03 s | 29.3 s | 3.0 s | 7.8 s |

Test, alternating with each prod row: 9 of 9 logins in 0.4-1.3 s, queries 0.2-0.3 s.
Compared with 18:49-19:00 UTC (2 of 6 prod logins), prod now answers almost every
login, but 15-50x slower than test on every step after TCP. The ETL allows 60 s per
connect attempt (2 of these 8 logins were longer) and reads 500-row pages, which
were still hanging, so scheduled jobs kept failing: the 14:15 MT sales-quotes canary
succeeded, the 14:25 MT batch failed, and `PlexOps.odbc_health` still reported 0 clean runs.

**SQL Development refreshed once, then stopped.** A freshness query in the SQL
Development Environment (newest `Accounting_v_AR_Invoice.Created_Date`,
`Sales_v_Shipper.Add_Date`, `Sales_v_Shipper_AR_Invoice.Add_Date`) returned 11-06
10:57-11:01 CT twice, about an hour apart, instead of 11-04. A November revenue query
by part group (invoice lines on accounts `4%` in `Accounting_v_AR_Invoice_Dist`,
which matched the Shipping Revenue screen to the cent on every day from 10-19 to
11-03) gave 249,001 units and $652,135.67. That is exactly the 13:00 MT screen load.
The screen's own export at 14:37 CT had four more invoices, INV0000180-183 (11,950
units, $49,721.50 on 40200), that SQL Development lacked. So SQL Development is a
copy that refreshed around 11:00 CT, not live. A CSV export from it
(`scripts/plex_web_export.py`) is current only to that point.

**The screen's Grand Total columns** are quantity, account 40200, account 41000 and
revenue (40200 + 41000). The 11-06 total was 260,951 units, $701,857.17, -$1,765.80
and $700,091.37. The -$1,765.80 is one line: INV0000180, Go-Live Temp part 14535 to
CHAM1, $1,962.00 on 40200 and -$1,765.80 on 41000.
