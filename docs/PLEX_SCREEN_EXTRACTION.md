# Plex screen extraction (Playwright), the stopgap for the ODBC outage

> **Status (2026-11-05):** live, deployed (tag `deploy/2026-11-05T2156Z`); the first push
> from the screens created 10 Monday items. The hourly Windows task "Plex live screens" on Emilio's
> laptop loads three Plex screens into `PlexProd.live_*`. `label_design_report` reads
> one of them while it is fresh, and the task starts the Monday push.
> **Retire it when ODBC is back** (see [Retiring it](#retiring-it-when-odbc-returns)).
> Open item: OPEN_ITEMS **D30**. Incident: [PLEX_PROD_ODBC_INCIDENT_2026-11-04.md](PLEX_PROD_ODBC_INCIDENT_2026-11-04.md).

## Contents

- [Why it exists](#why-it-exists)
- [What runs, where, when](#what-runs-where-when)
- [The three screens](#the-three-screens)
- [How Label Design uses it](#how-label-design-uses-it)
- [Safeguards](#safeguards)
- [Why it cannot collide with the ETL](#why-it-cannot-collide-with-the-etl)
- [Checking it](#checking-it)
- [Changing it](#changing-it)
- [Restoring a table](#restoring-a-table)
- [Troubleshooting](#troubleshooting)
- [Retiring it when ODBC returns](#retiring-it-when-odbc-returns)
- [Related: the SQL Development Environment export](#related-the-sql-development-environment-export)
- [Security](#security)

## Why it exists

The ETL reads Plex through ODBC (`vox.odbc.plex.com`). From **2026-11-04 ~18:56 MT** that
path answers from a copy of the data that stopped updating, or does not answer at all
(OPEN_ITEMS D20). The SQL Development Environment reads the same frozen copy.
**Plex's own screens kept showing live data.** So the stopgap reads the screens:

- A headless Chromium browser (Playwright) logs in as a person would.
- It calls the same JSON endpoints each screen uses to draw its grid.
- It writes the rows to BigQuery.

Nothing about the ETL changes. These are separate tables with their own names, and one
view (`label_design_report`) chooses between them and the ETL's raw tables.

## What runs, where, when

| | |
|---|---|
| Script | `scripts/plex_live_screens.py` (Python 3.12, Playwright, google-cloud-bigquery) |
| Wrapper | `scripts/plex_live_screens.cmd`: `python scripts\plex_live_screens.py --load`, appends to the log |
| Scheduler | Windows Task Scheduler, task **"Plex live screens"**, user HP-ProBook, interactive logon |
| When | Daily, hourly from 06:00 to 20:00 laptop time (UTC-6), which is **05:00-19:00 Mountain**. On battery too. Missed runs (laptop asleep) start when it wakes. A run over 50 min is killed. A run never starts while the previous one is still going. |
| Code it runs | **The primary folder's copy**, `C:\F\Parasol\plex-to-big-query`, branch `main`. A change reaches the task only after it is merged **and** `git pull`ed there. |
| Log | `C:\F\Parasol\plex-to-big-query\etl-manual\live_screens.log` (gitignored). Rolled to `.log.1` at 5 MB. Each run starts with `=== <date> <time>` and ends with `exit <code>`. |
| Exit codes | `0` all screens loaded · `1` at least one screen (or the push start) failed; the others still loaded · `75` another Plex web run holds the lock, so nothing ran |
| Credentials | Plex: `PLEX_PORTAL_USERNAME` / `PLEX_PORTAL_PASSWORD` from the environment or the primary folder's `.env`. Google: the laptop's Application Default Credentials (`gcloud auth application-default login`). |

Manual runs (from any folder; they share the task's lock):

```bash
python scripts/plex_live_screens.py                         # fetch and check all three; writes nothing
python scripts/plex_live_screens.py --only releases         # one screen, dry
python scripts/plex_live_screens.py --load                  # what the task does
python scripts/plex_live_screens.py --load --no-push        # load, but do not start the Monday push
python scripts/plex_live_screens.py --load --only releases --force   # load even past the shrink floor
```

A run takes about 3-4 minutes. Releases is most of that: one page per Pending Fulfillment order, about 160 orders.

## The three screens

Every screen is fetched **one calendar month at a time**, from the go-live floor to today.
A long range can hit a screen's row cap and silently repeat or drop rows. A month that
hits the cap fails the screen instead of loading a short table. Dates go to Plex as local
midnight expressed in UTC (`2026-11-01T06:00:00.000Z`), as the screens send them. Dates
that come back are converted to Mountain-time dates.

### 1. `revenue`: Shipping Revenue by Part Group → `PlexProd.live_shipping_revenue`

- Screen: Shipping > Shipping Revenue by Part Group (`/Shipping/ShippingRevenueByPartGroupReport/Index`).
- Data: `POST .../Search` with `InvoiceDateBegin/End`, `CommissionReporting: true`, `SortBy: "5"`.
- The grid has one row per invoiced shipper line **per GL account**. October lines carry a
  second `41000-01-01` row at $0, and `Revenue` is repeated on both. Rows are collapsed back
  to one per line; the account amounts are kept as text in `gl_amounts`
  (`"40200-01-01: 1234.5; 41000-01-01: 0"`). Summing the raw screen rows would double October.
- The cap is 500 rows per request. A month at 500 rows fails the screen. The same line and
  account twice also fails it.
- One row per invoiced line: invoice date/no/link, shipper no, order no, PO no/key, customer,
  customer part, part no/revision/key/type/group, product group, quantity, net unit price,
  revenue, outside salesperson, region/city/state, `loaded_at`.

### 2. `history`: Shipper History → `PlexProd.live_shipper_history`

- Screen: VisionPlex Shipper History (`/VisionPlex/screen/Index?__actionKey=6776`).
- Data: `POST /api/MetaDataSource/2kLwnSjUa3C0DB9c5Qibkw?limit=true&sourceActionKey=6776`, body
  `[{"PCN": 338756, "ShipDateStart": ..., "ShipDateEnd": ...}]`.
- A month flagged `RecordLimitExceeded` fails the screen. A shipper line returned twice fails it too.
- One row per shipped shipper line: ship date/time, shipper no/key/line key/status, customer,
  part, order no/line, PO/line/release keys, quantity, container net weight, ship-to name,
  carrier. No prices: join `live_shipping_revenue` on `shipper_no` + `part_no` for dollars.

### 3. `releases`: Sales Orders + Rapid Entry → `PlexProd.live_order_releases`

Two steps.

1. **Order Entry search** (Sales > Sales Orders, `/SalesAndCRM/OrderEntry`).
   - Request: `POST /SalesAndCRM/OrderEntry/SearchJobShopOrder?limit=true&sourceActionKey=9925`.
     The body is the screen's own, captured from a Search click (`SEARCH_BODY` in the
     script), with `POStatusKey = "2073"` (Pending Fulfillment) and one month of
     `OrderBeginDate/OrderEndDate` from 2026-10-18. The screen refuses a search with no
     filter at all.
   - It returns one row per order line, with the order header: order no, PO no, PO date,
     status, customer, and Inside Sales as a name.
   - A month flagged `RecordLimitExceeded` fails the screen. So does a row that is not
     Pending Fulfillment, which would mean the filter stopped working.
2. **Rapid Entry page** per order (`GET /SalesAndCRM/OrderLineRapidEntry?PoKey=<k>`).
   - This classic page embeds its grid as `plex.parsing.parseJSON('<JS string>')`, which the
     script decodes. Each row is one release: `POLineKey, ReleaseKey, ReleaseStatusKey,
     PriorityKey, DueDate, Quantity, PartKey, PartNoRevision, CustomerPartKey,
     CustomerPartNoRevision, JobNote`.
   - Every row appears in two models on the page, so rows are deduped by `ReleaseKey`.
   - An order whose grid is empty (a line with no release yet) contributes nothing. A page
     with no grid model at all is retried, then fails the screen.
   - The Line Items page (`OrderLineEntry`) has the status text but **no Job Note**, so Rapid
     Entry is the one used. The two agreed on all 362 releases on 2026-11-05.

**Status names:** the release status arrives as a key and is named from
`PlexProd.raw_Sales_v_Release_Status`:

| Key | Status | Key | Status |
|---|---|---|---|
| 3015 | Canceled | 3019 | Staged |
| 3016 | Open | 3020 | Scheduled |
| 3017 | Hold | 3638 | Label Design |
| 3018 | Closed | 3639 | Blanket |
| | | 3640 | Service |

A key not in that table **fails the screen**: a new status must be looked at, not guessed.
A release key that shows up on two orders also fails it.

**Columns:** order header (`po_key, order_no, po_no, order_date, po_status, customer_no,
customer_code, customer_name, inside_sales`) + release (`po_line_key, release_key,
release_status_key, release_status, priority_key, due_date, quantity, part_key,
part_no_revision, part_no, part_revision, part_name, customer_part_key,
customer_part_no_revision, job_note`) + `loaded_at`.

**First load (2026-11-05):** 160 orders, 362 releases, 71 in Label Design.

## How Revenue uses it

Since 2026-11-05 `shipping_revenue_report` (and so `sales_revenue_summary_report` and the
scorecard Revenue tile) has the same `live_switch`, on `live_shipper_history`: one row per
shipped line from Shipper History, joined to `live_shipping_revenue` on `shipper_no` +
part number for the invoice number, date, net price and amount. Same rules as below: PlexProd
only, under 3 h old, never mixed, `data_source` column. Its view is recreated only by a
`sales_orders` run, so while the breaker holds that job it is created by hand once.

## How Label Design uses it

`reports/sql/label_design_view.sql` builds its release rows in one of two ways:

- `odbc_lines`: the original query over the raw tables, unchanged.
- `live_lines`: the same columns from `live_order_releases`. The raw tables are used only
  for lookups by key, all of them master data that changes rarely:
  - customer email/phone;
  - AM/BDM user names;
  - customer part description;
  - part attributes;
  - bottle/label BOM;
  - priority name.

  Where the frozen copy lacks a key, the screen's own text fills in: customer name, part
  number/revision/name, customer part number, and Inside Sales name.
- `live_switch`: live when the dataset is **PlexProd** and `MAX(loaded_at)` is within
  **3 hours**. Otherwise ODBC. One source per query, never mixed. The output column
  `data_source` says which one ran.

Consequences:
- **PlexTest is never affected.**
- **If the task stops** (laptop off, Plex login broken), prod falls back to the frozen ODBC
  copy by itself 3 hours after the last good load. It never shows a half-day-old screen
  copy as current.
- **Known gap:** an order created after the freeze has no `Sales_v_Order_Salesperson` row,
  so its **BDM is NULL** until ODBC returns. The AM comes from the screen's Inside Sales.
- **Newer values:** a shared line can differ from the frozen copy where Plex changed after
  the freeze, for example a customer PO "N/A" → "438" or an edited Job Note. The push
  only creates new items, so items already on Monday do not change.

**The view itself** is normally recreated by every `label_design` ETL run, from the SQL in
GCS. While the outage breaker holds that job it creates nothing. The 2026-11-05 version was
therefore created once by hand, from the deployed GCS SQL, with the same
`{gcp_project}`/`{dataset}` substitution `main.py` does. The next real run recreates it
identically.

**The Monday push.** The ETL starts `plex-etl-label-design-push` after a run that
extracted (POST_RUN_JOB). Its own scheduler runs only a 6:05 PM sweep. While the ETL is
held, `plex_live_screens.py` starts the push after a good releases load, but only when
**all** of these hold (`maybe_start_push`):

1. Mon-Fri, 05:00-17:50 Mountain. The 6:05 PM sweep is separate; two pushes at once would
   both create the same item.
2. The newest prod `label_design` run in the last 40 minutes is **not** success/partial.
   Once ODBC is back, the ETL pushes, and this steps aside without anyone touching it.
3. `label_design_report` returns `data_source = 'live'` only.
4. No execution of the push job is still running (Cloud Run executions list).

The log line says which happened: `started plex-etl-label-design-push: <execution>` or
`push not started: <reason>`. The push's own safety still applies:
- LCR dedupe against the board and `label_design_push_log`;
- `MAX_NEW_ITEMS` = 60 alarm;
- label-colour checks.

## Safeguards

| Risk | Guard |
|---|---|
| Two runs at once (task + manual, or task + `plex_web_export.py`) | `run_lock()` in `plex_web_export.py`. It is an OS lock (msvcrt/flock) on `etl-manual/plex_web.lock` in the primary folder. A second run exits 75. A killed run releases the lock with its process; the file keeps the last holder's pid and start time. The task also never starts a second instance and kills a run after 50 min. |
| One screen breaks | Each screen fetches and loads on its own. A failed one writes nothing (its table keeps the previous load); the others still load. The run exits 1. |
| Plex hiccup / session expiry | Each request is tried 3 times with 5 s / 10 s back-off. Plex's login page or a 401/403 triggers a fresh login. |
| A partial fetch replaces a good table | Floors: a screen with under 90% (revenue, history) or 50% (releases) of the current table's rows is not loaded without `--force`. Releases shrink legitimately as orders ship, hence the lower floor. |
| Row cap / truncated grids | One month per request. A month at the cap or flagged `RecordLimitExceeded` fails the screen. |
| Load did not land | After each `WRITE_TRUNCATE` the table's row count must equal the rows sent, or the screen fails. |
| A bad load needs undoing | The first load of each Denver day copies the table to `Backups.PlexProd__<table>_<yyyymmdd>` (7-day expiry). BigQuery time travel covers every hourly load in between ([Restoring](#restoring-a-table)). |
| Unknown data | An unknown release status key, a duplicate release key, or a non-Pending-Fulfillment order fails the releases screen. |
| Screen copy goes stale | The view uses it only while it is under 3 h old. |

## Why it cannot collide with the ETL

- **Different tables.** This writes only `PlexProd.live_shipping_revenue`,
  `live_shipper_history`, `live_order_releases` and their `Backups.PlexProd__live_*` copies.
  The ETL never writes or reads a `live_*` table, except `label_design_report`, which
  only *reads* one.
- **It writes nothing the ETL writes.** It reads `raw_Sales_v_Release_Status` (status
  names) and `job_run_log` / `label_design_report` (push gates); it never writes a `raw_*`
  table, a view, `probe_log` or `job_run_log`.
- **Different Plex path.** Screens are web sessions on `vox.on.plex.com`. The ETL is ODBC on
  `vox.odbc.plex.com`. Neither uses or holds the other's sessions.
- **The push** is started only under the gates above. That rules out overlapping the ETL's
  own push or the 6:05 PM sweep.
- **`plex_web_export.py`** (which *does* swap `raw_*` tables) shares the lock, and it already
  refuses to swap a raw table the ETL wrote after the export started.

## Checking it

```sql
-- freshness and size of each screen table
SELECT 'releases' t, COUNT(*) n, MAX(loaded_at) loaded FROM `voxdatalake.PlexProd.live_order_releases`
UNION ALL SELECT 'revenue', COUNT(*), MAX(loaded_at) FROM `voxdatalake.PlexProd.live_shipping_revenue`
UNION ALL SELECT 'history', COUNT(*), MAX(loaded_at) FROM `voxdatalake.PlexProd.live_shipper_history`;

-- which source Label Design is reading right now, and how many lines
SELECT data_source, COUNT(*) FROM `voxdatalake.PlexProd.label_design_report` GROUP BY 1;

-- what the push did today
SELECT pushed_at, outcome, dedupe_key, detail FROM `voxdatalake.PlexProd.label_design_push_log`
WHERE DATE(pushed_at, 'America/Denver') = CURRENT_DATE('America/Denver') ORDER BY pushed_at DESC;
```

PowerShell: `Get-ScheduledTaskInfo -TaskName "Plex live screens"` (last run, result, next run),
and `Get-Content C:\F\Parasol\plex-to-big-query\etl-manual\live_screens.log -Tail 30`.

## Changing it

1. Change and commit on a dev branch (`ptbq-dev`, branch `dev`), with a CHANGELOG entry.
2. Dry-run the changed screen from that folder: `python scripts/plex_live_screens.py --only <screen>`.
   It shares the task's lock, so it waits for nothing and never runs alongside the task.
3. PR to `main`, merge, then **`git pull` in `C:\F\Parasol\plex-to-big-query`**. Until the
   pull, the task keeps running the old copy.
4. A change to `label_design_view.sql` deploys like any report SQL (`./scripts/deploy.sh`).
   While the breaker holds the `label_design` job, the new view must also be created once by
   hand from the deployed SQL. See the CHANGELOG entry of 2026-11-05.

If Plex changes a screen, capture the new request:
1. Open the screen in a normal browser with DevTools > Network.
2. Click Search.
3. Copy the request URL and body into the script.

## Restoring a table

```sql
-- an earlier load from today (time travel, up to 7 days back)
CREATE OR REPLACE TABLE `voxdatalake.PlexProd.live_order_releases` AS
SELECT * FROM `voxdatalake.PlexProd.live_order_releases`
  FOR SYSTEM_TIME AS OF TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 2 HOUR);

-- the first copy of a given day
CREATE OR REPLACE TABLE `voxdatalake.PlexProd.live_order_releases` AS
SELECT * FROM `voxdatalake.Backups.PlexProd__live_order_releases_20261105`;
```

Writes need `--impersonate-service-account=claude-operator@voxdatalake.iam.gserviceaccount.com`
when run by Claude Code. A restore is overwritten by the next hourly load, so pause the task
first if the restore has to stick: `Disable-ScheduledTask -TaskName "Plex live screens"`.

## Troubleshooting

| Log says | Meaning / action |
|---|---|
| `another Plex web run holds plex_web.lock (pid ...)` + `exit 75` | A run is still going (or a manual one). Normal once in a while. Every hour in a row: check that pid is a real hung python (`Get-Process -Id <pid>`) and stop it. |
| `login did not reach ...` / repeated `logging in again` | The Plex password changed or the account is locked. Update `.env` in the primary folder. |
| `record limit exceeded` / `at the screen's cap` | A month has more rows than the screen returns. Split the request smaller (half-months) in the script. |
| `release status key(s) [...] not in raw_Sales_v_Release_Status` | Plex has a new release status. Add it to the table's knowledge (ask what it means), or wait for ODBC to bring the status table. |
| `returned order N in status '...'` | The Pending Fulfillment filter stopped working; Plex likely changed the search body. Recapture it. |
| `no page model after 3 attempts` | The Rapid Entry page changed shape. Open it in a browser and check for `plex.parsing.parseJSON`. |
| `N rows is under 50% of the M now in ...; not loaded` | A big drop. If real (many orders shipped), rerun with `--force`. Otherwise investigate. |
| `push not started: ...` | Normal outside the window, while the ETL is back, or while a push runs. `is not reading the live screens` means the view is on ODBC: check freshness. |
| `push: FAILED TO START: 403` | The laptop's ADC account lacks `run.jobs.run` on the push job. Run `gcloud auth application-default login` as a user who has it. |
| Task result `0x41306` / run killed | The run hit the 50-minute limit. Look at the log for the slow step. |

## Retiring it when ODBC returns

The ETL is back when `PlexOps.etl_dispatch_log` shows prod runs succeeding and
`label_design` runs in `job_run_log` read `success` again.

1. Nothing breaks if you do nothing at once:
   - the ETL starts pushing again;
   - this script stops starting the push (gate 2);
   - the view keeps preferring live while the task runs, and the live data is the same or fresher.
2. Stop the task: `Disable-ScheduledTask -TaskName "Plex live screens"` (or
   `Unregister-ScheduledTask` to remove it). Three hours later `label_design_report` returns
   `data_source = 'odbc'` with no deploy.
3. Check: `SELECT data_source, COUNT(*) FROM label_design_report GROUP BY 1` gives `odbc`. The
   line count should be close to the last live count.
4. Later, optionally:
   - remove `live_switch`/`live_lines` from the view (keep `data_source = 'odbc'` or drop the column);
   - drop the `live_*` tables;
   - close OPEN_ITEMS D30.

   Keeping the branch costs nothing and makes a future outage a matter of re-enabling the task.

## Related: the SQL Development Environment export

`scripts/plex_web_export.py` downloads whole Plex views through the SQL Development
Environment's "Download Results As CSV" request. It stages them, compares them, and with
`--swap` backs up and replaces `PlexProd.raw_<view>`. **Since 2026-11-04 ~18:56 the SQL
Development Environment reads the same frozen copy as ODBC**, so it cannot bring anything
newer. It is kept for an outage where ODBC is down but SQL Development is current. It
shares the lock above.

## Security

- The Plex login is a real user's. It lives only in `.env` (gitignored) and the process
  environment, and is never printed.
- Screen data is customer data. The tables live in BigQuery like any raw table.
  Screenshots and captured responses are kept out of the repo: `etl-manual/` and
  `docs/hub/screens/` are gitignored, and the hub embeds screenshots only in the
  gitignored `index_live.html` and the private published artifact.
- The task writes with the laptop owner's Application Default Credentials. It writes only
  the tables named above and starts one Cloud Run job.
