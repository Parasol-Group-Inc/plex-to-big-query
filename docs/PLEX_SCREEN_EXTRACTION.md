# Plex screen extraction (Playwright), the stopgap for the ODBC outage

> **Status (2026-11-10): a cloud job, every 4 hours, permanent.** The screens are no longer a
> laptop stopgap. Cloud Run job `plex-live-screens` (scheduler `plex-live-screens-sync`,
> every 4 hours at :20 MT from 00:20, Dockerfile.screens) runs `scripts/screen_recon.py`: it reads three
> screens (Label Design releases, revenue, shipments), compares them with ODBC and BigQuery, and switches a report to the screens
> only while ODBC is behind or disagrees. See
> [Reconciliation (cloud job)](#reconciliation-cloud-job). The laptop task is not needed
> any more; the history below is kept for the record.

> **Status (2026-11-05):** live, deployed (tag `deploy/2026-11-05T2156Z`); the first push
> from the screens created 10 Monday items. The hourly Windows task "Plex live screens" on Emilio's
> laptop loads three Plex screens into `PlexProd.live_*`. `label_design_report` reads
> one of them while it is fresh, and the task starts the Monday push.
> **Retire it when ODBC is back** (see [Retiring it](#retiring-it-when-odbc-returns)).
>
> **Closed 2026-11-10:** the task is disabled, and the `live_*` tables were backed up to
> `Backups.PlexProd__live_*_20261110` and emptied, so revenue, production and Label Design read
> ODBC (one shipper removed in Plex had kept revenue on the stale screen copy; incident doc,
> "Check, 2026-11-10"). **When starting it for an outage, its first `--load` refills the tables.**
>
> **Status (2026-11-09): retired, ready to restart.** ODBC is back since 11-08 ~04:45 MT;
> revenue and production went back to ODBC by themselves on 11-08, Label Design matched
> ODBC exactly on 11-09, and the laptop task is disabled. The tables and the live
> branches stay. **Next outage:** the ETL emails "ACTION NEEDED: Plex ODBC failing for
> 6 h, start the live screens"; then follow [Starting it](#starting-it-for-an-outage).
> Open item: OPEN_ITEMS **D30**. Incident: [PLEX_PROD_ODBC_INCIDENT_2026-11-04.md](PLEX_PROD_ODBC_INCIDENT_2026-11-04.md).

## Contents

- [Reconciliation (cloud job)](#reconciliation-cloud-job)
- [Why it exists](#why-it-exists)
- [What runs, where, when](#what-runs-where-when)
- [The three screens](#the-three-screens)
- [4. `production`](#4-production-job-production--production-history--plexprodlive_production)
- [How Revenue uses it](#how-revenue-uses-it)
- [How the production reports use it](#how-the-production-reports-use-it)
- [How Label Design uses it](#how-label-design-uses-it)
- [Safeguards](#safeguards)
- [Why it cannot collide with the ETL](#why-it-cannot-collide-with-the-etl)
- [Checking it](#checking-it)
- [Changing it](#changing-it)
- [Restoring a table](#restoring-a-table)
- [Troubleshooting](#troubleshooting)
- [Starting it for an outage](#starting-it-for-an-outage)
- [Retiring it when ODBC returns](#retiring-it-when-odbc-returns)
- [Related: writing a customer note](#related-writing-a-customer-note-plex_customer_notepy)
- [Related: the SQL Development Environment export](#related-the-sql-development-environment-export)
- [Security](#security)

## Reconciliation (cloud job)

**Why.** Plex ODBC failed in two ways in November 2026: no answer (11-04 to 11-08), and,
on 11-10, answers from data frozen ~08:10-12:50 MT while every ETL run succeeded. The
screens were right both times. So every 4 hours a job checks ODBC against them (Label Design, revenue and
shipments; production was dropped from the check on 11-10, its view stays on ODBC).

**One cycle** (`scripts/screen_recon.py`, about 5 min):
1. Logs into Plex (secrets `plex-portal-username` / `plex-portal-password`) and reads
   three screens: `releases` (Sales Orders + Rapid Entry), `history` (Shipper History)
   and `revenue` (Shipping Revenue by Part Group, half-month windows, each halved again
   while it hits the 500-row cap). `--only production` still compares production by hand.
   **Every login** (first and any re-login mid-screen) is timed and written to
   `PlexOps.plex_login_log` (ok, error, seconds, final page, screenshot). **A failed
   login is emailed on its own to `LOGIN_ALERT_EMAILS`** (Emilio), with a diagnosis: the
   cause is read from the error and the page text (`wrong_credentials`, `password_change`,
   `verification`, `locked`, `plex_down`, `network`, `timeout`, `unknown`) and the email gives
   that cause's fix, what Plex showed, the run streak and the last good login. Only
   `plex_down`, `network` and a `timeout` that did not stop on Plex's sign-in page are retried
   (once, after 60 s). Anything else (a rejected, locked or MFA login, a timeout on the sign-in
   page, or words we don't recognise) is not retried, and **the job then does not log in at all
   for 24 h** (`login_suspended`), so it can never lock the user by repetition. After fixing
   it, start a run by hand with `--force-login`:
   `gcloud run jobs execute plex-live-screens --region=us-central1 --args=python,scripts/screen_recon.py,--force-login`.
   Credential and lock causes are read from the page text, transport causes from the error, so
   the "Reset password" link on every sign-in page is not mistaken for a password change. The
   password is masked out of every error and page text before anything is printed or stored.
   One email per cause per 24 h (`reason = 'login-alert'`, `detail = '<cause>: sent'` rows in
   `etl_dispatch_log`); `plex_login_log.error` starts with the cause. **Screenshots** of every
   login and screen read go to `gs://voxdatalake-plex-screenshots/plex-screens/YYYY/MM/DD/
   HHMM-MT_<run>/NN_<what>.png` (e.g. `01_login_ok.png`, `02_releases_ok_461rows.png`,
   `..._FAILED.png`), kept 365 days. Each screen's read logs `extraction <screen>: ok,
   N rows, S s` and `screen_recon.fetch_seconds`.
2. Appends every record to `PlexOps.screen_snapshot` (30 days).
3. Reads the same records from ODBC (one connection, filtered queries with `TOP`) and
   the keys of the matching `raw_*` tables.
4. Classifies each difference into `PlexOps.screen_recon_diff`:

   | Kind | Meaning |
   |---|---|
   | `missing_tail` | the screen has it, ODBC does not, and it is at least as new as anything ODBC has: lag |
   | `missing_hole` | ODBC lacks it although ODBC has strictly newer records (same minute counts as tail since 11-11) |
   | `status_diff` / `value_diff` | in both, a compared value differs |
   | `odbc_extra` | ODBC has it, the screen does not (deleted in Plex?) |
   | `odbc_newer` | ODBC changed after the screen was read: ignored |
   | `bq_missing` | ODBC has it, our `raw_*` table (loaded after it) does not |

   Records newer than `RECON_GRACE_MIN` (15) are not compared, except a revenue or
   release record seen for the first time that ODBC lacks while ODBC's newest change is
   already older than the tolerance: that is stale ODBC now (the 11-10 order-675 case),
   not something to wait 4 h for. The age of a record
   comes from its own time (production record time, ship time) or, for revenue and
   releases, from when the snapshot first showed its current values.
5. Writes one verdict per screen to `PlexOps.screen_recon`:

   | Verdict | Rule |
   |---|---|
   | `current` | lag at most `RECON_LAG_TOLERANCE_MIN` (120, Terraform env) |
   | `behind` | the oldest missing record or unseen edit is older than the tolerance |
   | `diverged` | a hole older than the tolerance, ODBC changed a value after the screen showed a different one, or ODBC has records the screen lacks in two runs running while ODBC's own newest change is within the tolerance (extras while ODBC is stale are lag: 11-10's five "open" releases cleared overnight) |
   | `odbc_unreachable` | ODBC connect or query failed, or a query hit its `TOP` |
   | `pipeline_behind` | ODBC is fine but BigQuery lacks records ODBC had before our last load |
   | `screens_failed` | a screen could not be read, or read under 90% (50% releases/production) of last run |

6. **Since 2026-11-11 there is no switching** (`docs/ODBC_VS_SCREENS.md`):
   - **Label Design always combines.** The releases screen is loaded into
     `live_order_releases` on every read: hourly on weekdays from 6:20 AM to 5:20 PM
     (`plex-live-screens-releases-sync`, `RECON_ONLY=releases`), and every 4 h.
     `label_design_view.sql` adds the lines ODBC lacks. The job starts the push when there
     are any. Later push runs fill those items' blank cells from ODBC and mark Data Source
     "confirmed by ODBC".
   - **Revenue never switches** (`use_live` FALSE), and its live tables are kept empty.

   `live_source` also has `odbc_behind`, which is what main.py's alerts read.
   The text below is the 11-10 design, kept for history.

   **(11-10 design) Switching.** `PlexOps.live_source` (a view) sets `use_live` per report group
   (`label_design` ← releases, `revenue` ← history + revenue) when any of the screen's
   last 2 good runs was `behind`, `diverged` or
   `odbc_unreachable`. While `use_live`, the job reloads that group's `PlexProd.live_*`
   tables on each run (and starts the Label Design push, skipping the "ETL reached Plex"
   gate). When it turns false (2 clean runs, 8 h), it backs the tables up to
   `Backups.PlexProd__live_*_<stamp>` (7 days) and empties them. The two views read
   the screens only when `use_live` is true **and** their live table is under 5 h old,
   so if the job stops they are back on ODBC within 5 hours.
7. **Emails** (SendGrid). **Since 2026-11-11 (afternoon), mails go out only when a person is
   needed:**
   - "Plex ODBC is behind or disagrees with the screens", per group, once a day. It fires
     when releases are over 6 h behind, shipments/revenue over 12 h
     (`RECON_REVENUE_ALERT_LAG_MIN` = 720, a missed overnight catch-up), or a verdict is not
     a delay.
   - "caught up", once, only after such a mail.

   The paragraph below is the 11-11 morning version. **Earlier the same day a delay alone
   switched quietly:** `behind` up to `RECON_ALERT_LAG_MIN` (360, 6 h) moves the reports to
   the screens with no email and no ACTION NEEDED. On 11-10 ODBC ran 2.5 to 5.5 h behind all
   afternoon and was current again at the 00:20 and 04:20 checks (after the 4 AM full run).
   Mailed: a group on the screens with a lag over 6 h or a non-delay verdict (once a day),
   that group back on ODBC (for information, only if the first was mailed), `diverged` / `pipeline_behind` (daily), and a
   screen that failed twice running (daily). Google Monitoring separately mails if the
   job's `recon heartbeat` log line is missing for 9 h.

   The whole rule set in one page: `docs/ODBC_VS_SCREENS.md`.

8. **Digest** (`send_screens_digest`), to REPORT_TO_EMAILS (Emilio, Jennilyn, marketing):
   at the 9:20, 13:20 and 17:20 MT runs (`RECON_DIGEST_HOURS`, just after ODBC's refreshes; 8/12/16 until 11-11). Another run with a problem
   (needs_action, a failed login) sends one too, at most once per 4 h, so the hourly
   releases runs do not mail every hour. The digest also lists the Label Design lines
   that only the screens have so far. A lag under 6 h shows as
   "Screens Digest: ODBC catching up" (info) and does not add a mail of its own. One line per report group (its `data_label`), one per screen (verdict, rows,
   seconds, compared / missing / differing), logins and the screenshot folder.
9. **Labels.** `PlexOps.data_freshness` turns the same rule into `data_source`,
   `data_as_of` and `data_label`, carried by every report built on the three base views
   and written to Monday's "Data Source" column (`docs/reports/data_freshness.md`).

**What "ODBC is behind" is measured against (2026-11-10).** Three different clocks, so it
is worth being exact:

| Comparison | ODBC side | How fresh that side is |
|---|---|---|
| Screen vs ODBC (`behind`, `diverged`, `odbc_lag_min`) | **queried live** by the screens job itself (`odbc_connect()` + `odbc_records()`), one connection per run, minutes after the screen read | as fresh as Plex's ODBC is at that moment: it does **not** depend on when our ETL last extracted |
| ODBC vs BigQuery (`pipeline_behind`, `bq_missing`) | the `raw_*` tables our ETL wrote | as old as the last extraction (Label Design: a 15-min check on weekdays 5 AM-5:45 PM, extracting only on change; Sales Orders: full at 4 AM, change checks at 1 PM, 6 PM and 11 PM) |
| `main.py` stale-data alert (`check_odbc_freshness`) | three live ODBC reads at the start of every prod ETL run | live, every run (Label Design's every 15 min gives the most frequent reading) |

So a quiet ETL never makes ODBC look behind: the screens job asks ODBC directly every 4 h, and
a lag there is Plex's. Only `pipeline_behind` uses our extracted copy, and it allows for the
extraction schedule (a record must predate our last load by more than the 120-min tolerance).
The flip side: between screens runs (4 h) the only live reading is the stale-data alert, which
measures the newest change ODBC holds, not a comparison with the screens.

**Check it:**
```sql
SELECT * FROM `voxdatalake.PlexOps.live_source`;
SELECT attempted_at, reason, ok, error, seconds, screenshot
FROM `voxdatalake.PlexOps.plex_login_log` ORDER BY attempted_at DESC LIMIT 20;
SELECT run_started_at, screen, verdict, odbc_lag_min, compared, missing_tail, missing_hole,
       status_diff, value_diff, odbc_extra, bq_missing, fetch_error, odbc_error
FROM `voxdatalake.PlexOps.screen_recon` ORDER BY run_started_at DESC LIMIT 20;
```
**Run it by hand:** `gcloud run jobs execute plex-live-screens --region=us-central1`
(writes). A read-only pass: use `--args=python,scripts/screen_recon.py,--dry-run` (the job's
args replace the whole command). Locally on Apple Silicon the amd64 image is too slow for Plex's
login; test in Cloud Run.

**Cost** (Cloud Run, us-central1, 2 vCPU / 4 GiB, ~5 min a run, before the free tier):
every 4 h = 180 runs/month ≈ $1.95 CPU + $0.45 memory ≈ **$2.40/month** (hourly would be
≈ $10). Screenshots: ~10 PNGs a run, well under 1 GB a year (< $0.03/month). The watchdog (30 s every 30 min) ≈ $1. BigQuery reads and the
snapshot storage stay inside the free tier. A screens image per build adds ~1.5 GB to
Artifact Registry (~$0.15/month each until old ones are cleaned).

**Adding a screen** (OPEN_ITEMS D35): a fetcher in `plex_live_screens.py` (`SCREENS`),
then in `screen_recon.py` its key and measures (`screen_records`), its ODBC query
(`ODBC_SQL`, `odbc_records`), its raw table (`BQ_SQL`) and, if a report should switch,
a group in `GROUPS` and in the `live_source` view.

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
- The screen cuts an answer at about 520 rows (11-13: Nov 1-14 came back as 520; split, it was
  558). We treat 500 as the cap. Since 2026-11-13 a half-month window at the cap is read again
  in halves (`read_windows`), down to one day; a capped answer is never used. Only a single day
  at the cap fails the screen (`ScreenCapError`). The same line and account twice also fails it.
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

### 4. `production`: Job Production + Production History → `PlexProd.live_production`

Added 2026-11-06. One row per production record (Plex `Part_v_Production`) since 2026-11-01.

- **Job Production report** (VisionPlex action 6571, data source
  `jpBWrHptieaF_6xmHXP5-w`) gives the job, op, part + revision, workcenter, quantity,
  rejected flag, serial and record time. Its employee is the last name only (ambiguous for
  17 of 60 users).
- **Production History** (`ProductionTracking/ProductionHistory`) gives the employee's
  full name, matched by production number.
- Both stop at 1,000 rows. The script asks per day; a capped day is asked again per
  workcenter (6571 by `WorkcenterCode`, a prefix match, so "Blending 5" also returns
  "Blending 5a", which is skipped; Production History by `WorkcenterKey`). A workcenter that
  is itself capped, or capped rows missing from the union, fail the screen.
- Neither screen's day filter is the Mountain record date (6571 asked for 11-01 returned
  11-02's records, the DST change). So it reads from the day before to tomorrow, de-duplicates
  by production number and keeps each record by its own record date.
- First run of each Mountain day: everything since 11-01 (about 3 min). Later runs: only
  the last 3 days, keeping older rows from the table.
- Fails if more than 2 % + 5 records have no Production History name.
- **Checked 2026-11-06:** on the 2,100 records ODBC holds (11-02, 11-03), every production
  number, record date and quantity matched, and so did every resolved key (below).
- Columns: `production_no, record_date, record_time, report_date, shift, job_no, op_no,
  operation_code, part_no, revision, workcenter_code, serial_no, quantity, rejected,
  employee, employee_last_name, product_type, price, fetched_at, loaded_at`.

**First load (2026-11-06):** 4,828 records, 11-02 to 11-06.

## How Revenue uses it

Since 2026-11-05 `shipping_revenue_report` (and so `sales_revenue_summary_report` and the
scorecard Revenue tile) has the same `live_switch`, on `live_shipper_history`: one row per
shipped line from Shipper History, joined to `live_shipping_revenue` on `shipper_no` +
part number for the invoice number, date, net price and amount. PlexProd only, never mixed,
`data_source` column, like Label Design below, but the switch is different:

- **Live until ODBC is trusted again**, which needs both:
  1. **Stable connections for 6 h:** `PlexOps.odbc_health.odbc_stable` (below).
  2. **Fresh data:** every `live_shipper_history.shipper_no` is in `raw_Sales_v_Shipper`.
     A frozen ODBC copy connects and "succeeds", so (1) alone cannot prove fresh data.
- So the overnight gap is closed: after the 7 PM load the report keeps the screens' numbers,
  and if the task stops it keeps the last load, still newer than the frozen copy.
- Once ODBC is back, `sales_orders` brings the missing shippers, and 6 h after the last
  failure the report reads ODBC again by itself. Then disable the task: while it still runs,
  a shipper made in the last hour can briefly put the report back on the screens (ODBC
  trails Plex ~50 min).
- Until 2026-11-06 the test was "loaded within 3 h", which fell back every night.

**`PlexOps.odbc_health`** (a view, Terraform `odbc_health`, from `etl_dispatch_log`) is one
row: `last_bad_at`, `stable_since`, `last_ok_at`, `ok_runs`, `stable_hours`, `odbc_stable`.
- **Bad:** a `held-outage` slot, a `lost` run, a `failed` run whose detail starts
  `ODBC connection failed` or `execution failed or was cancelled`, or a run still open 2 h
  after dispatch. Failures of other kinds (a SQL error) do not count, so one broken report
  cannot hold everything on the screens.
- **Stable:** at least 2 `success`/`skipped` runs dispatched after the last bad one, the
  first finished 6+ h ago. Any new bad run resets the clock.
- Backtest on 2026-11-06: false every hour from 11-04 13:00 MT to now; during the flaky
  10-27 to 10-30 week it flipped several times, which is the instability it waits out.
- To ask "is ODBC back?": `SELECT * FROM voxdatalake.PlexOps.odbc_health`.

On 2026-11-06 the screens held 32 shippers ODBC did not (SH00189-SH00225, ODBC's newest is
SH00188). Its view is recreated only by a `sales_orders` run, so while the breaker holds
that job it is created by hand once.

## How the production reports use it

Since 2026-11-06 every report that counts production reads the view
**`part_production_current`** instead of `raw_Part_v_Production`: the 5 daily reports
(Blending, Encapsulating, Labeling, Packaging), Weekly Production Update, Production by
Work Center Group (so the Production vs Goal tile), FPY by area, MFG Job Schedule success
metrics and Approaching MSL. It is the first `bq_view` in `work_orders.yaml`.

- Same columns and conventions as `raw_Part_v_Production` (Record_Date/Report_Date are
  Mountain wall time stored as UTC nanoseconds; Report_Date is 22:00 the evening before),
  plus `data_source`.
- **Live** (PlexProd only, while `live_production` is loaded): every live record plus
  every ODBC record the screens do not have. Back to ODBC alone, by itself, once
  `PlexOps.odbc_health.odbc_stable` and ODBC holds every live record more than 3 h older
  than the last load.
- Keys come from the raw master tables: `Job_Op_Key`/`Part_Operation_Key` by job no + op no,
  `Part_Key` by part no + revision, `Workcenter_Key` by code, `Record_By` by full name.
  Shift `1st` = `7824`, none = `0`.
- **Known gap:** jobs created after the freeze are not in the frozen `raw_Part_v_Job_Op`,
  so their records have no `Job_Op_Key` (232 of 4,828 on 11-06). Reports that join Job_Op
  (the daily reports, FPY, weekly, job schedule metrics) do not count them; Production by
  Work Center Group does, and so does Approaching MSL: `Part_Operation_Key` falls back to the
  part's routing (`raw_Part_v_Part_Operation`, part + op no), which agreed with Job_Op on all
  4,596 records that have both.
- Checked against the deployed views 2026-11-06: rows before November unchanged (rounding
  aside); the differences are November days and the 274 jobs with November production.

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
   A `skipped` run counts as reaching Plex too, unless its detail starts "Held" (since
   2026-11-09).
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
| Screen copy goes stale | Label Design uses it only while it is under 3 h old. Revenue uses it only while it holds a shipper ODBC lacks. |

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

## Starting it for an outage

**When:** the ETL sends `[Plex ETL] - ACTION NEEDED: Plex ODBC failing for 6 h, start
the live screens` (since 2026-11-09), once ODBC has failed in every one of the last 6
hours and fewer than a quarter of the runs reached Plex. Or `[Plex ETL] - ACTION NEEDED:
Plex ODBC data is N h old` (since 2026-11-10): ODBC answers but its newest data is 2 h+
old on a weekday 9-5 MT; start the task if it lasts. The rules and their backtests are
in [OPERATIONS.md](OPERATIONS.md#plex-outages-breaker-canary-recovery-since-2026-10-22).
It repeats at most daily and stays quiet while the screens already load. To check by
hand: `SELECT * FROM voxdatalake.PlexOps.odbc_health` (`odbc_stable = false` for hours)
and the probe ([PLEX_ODBC_PROBE.md](PLEX_ODBC_PROBE.md)).

**On the Windows laptop** (logged in, awake, on the network), in PowerShell:

```powershell
cd C:\F\Parasol\plex-to-big-query
git pull
Enable-ScheduledTask -TaskName "Plex live screens"
Start-ScheduledTask -TaskName "Plex live screens"
```

`git pull` first: the task runs the primary folder's copy. Then, after about 10 minutes:

```powershell
Get-Content C:\F\Parasol\plex-to-big-query\etl-manual\live_screens.log -Tail 20
Get-ScheduledTaskInfo -TaskName "Plex live screens"
```

The log's last run should end `exit 0`, and `LastTaskResult` should be `0`. Then in
BigQuery `SELECT data_source, COUNT(*) FROM voxdatalake.PlexProd.label_design_report
GROUP BY 1` gives `live`. Revenue and production switch on `odbc_health` by themselves.
If the Plex login fails, see [Troubleshooting](#troubleshooting). Tell Plex support
(customercare@plex.com) when it started, with probe output.

## Retiring it when ODBC returns

**Done 2026-11-09** (assessment in the incident doc, "Recovery"). Disable it from
PowerShell on the laptop, and check:

```powershell
Disable-ScheduledTask -TaskName "Plex live screens"
Get-ScheduledTask -TaskName "Plex live screens" | Select-Object TaskName, State
```

`State` should read `Disabled`. A run already under way finishes; nothing else is
needed. Lessons for next time:
- Revenue and production switch on `odbc_health`, so they need 6 h of clean runs and
  come back on any day. Label Design switches on the task stopping, and its own ETL runs
  only Mon-Fri, so check it on the first weekday after recovery.
- To compare the two sources before switching, run `label_design_view.sql` twice with
  `use_live` forced to `TRUE` and to `FALSE`, and compare on `dedupe_key`. On 11-09 they
  differed only in empty vs NULL `job_note`.
- Gate 2 of the push used to miss `skipped` runs (a healthy ETL whose change probe found
  nothing), so the task kept starting the push every hour after recovery. Fixed 11-09.

The ETL is back when `PlexOps.etl_dispatch_log` shows prod runs succeeding and
`label_design` runs in `job_run_log` read `success` again.

1. Nothing breaks if you do nothing at once:
   - the ETL starts pushing again;
   - this script stops starting the push (gate 2);
   - the view keeps preferring live while the task runs, and the live data is the same or fresher.
2. Stop the task: `Disable-ScheduledTask -TaskName "Plex live screens"`. **Then back up and empty the
   `live_*` tables** (lesson of 2026-11-10): a row Plex later deletes keeps revenue and production on
   the frozen screen copy for good otherwise. (or
   `Unregister-ScheduledTask` to remove it). Three hours later `label_design_report` returns
   `data_source = 'odbc'` with no deploy.
3. Check: `SELECT data_source, COUNT(*) FROM label_design_report GROUP BY 1` gives `odbc`. The
   line count should be close to the last live count. `part_production_current` and
   `shipping_revenue_report` switch on `odbc_health` instead: check their `data_source` too.
4. Later, optionally:
   - remove `live_switch`/`live_lines` from the view (keep `data_source = 'odbc'` or drop the column);
   - drop the `live_*` tables;
   - close OPEN_ITEMS D30.

   Keeping the branch costs nothing and makes a future outage a matter of re-enabling the task.

## Related: writing a customer note (`plex_customer_note.py`)

`scripts/plex_customer_note.py` sets a customer's **Note** (Customer Details screen,
Contact Information section, `textarea[name="Note"]`) through the same login and lock.
- **Why the screen, not the API:** `PUT /mdm/v1/customers/{id}` with `note` on a
  test-tenant customer that had no note (AEREL, 2026-11-09) returned 200 and stamped
  the record modified, but the note stayed empty. Reads of `note` work.
- **How:** opens `SalesAndCRM/customeraddresses?__sk=3&__sak=23&CustomerNo=<no>`, clicks
  the "Customer Details" side tab, reads the note, types the text, clicks Apply, then
  reloads and reads it back. It refuses to replace a note that is not empty unless
  `--overwrite`. Screenshots go to `etl-manual/customer_note/` (gitignored). In a headless
  screenshot the Note box draws blank even when filled; trust the read-back.
- **First use:** 2026-11-09, production, 101 Via Imports (808258): `PLACEHOLDER` written
  and read back; Plex shows "Updated 11/9/2026 10:26 AM, Dominguez, Emilio".

```bash
python scripts/plex_customer_note.py 808258                        # read only
python scripts/plex_customer_note.py 808258 --set "PLACEHOLDER"    # write if empty
```

Needs `PLEX_PORTAL_USERNAME` / `PLEX_PORTAL_PASSWORD` in `.env` and Playwright with
Chromium (`pip install playwright` then `python -m playwright install chromium`).

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
