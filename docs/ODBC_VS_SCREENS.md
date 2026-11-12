# ODBC and the Plex screens: how they work together

Current as of **2026-11-12**. This page holds all the rules in one place. The runbook is
`docs/PLEX_SCREEN_EXTRACTION.md` ("Reconciliation (cloud job)"). The code is:

| Code | Where |
|---|---|
| The screens job | `scripts/screen_recon.py` |
| Combining ODBC and screen lines | `reports/sql/label_design_view.sql` |
| Filling in blanks on Monday | `label_design_service/fill.py` |
| `live_source`, `data_freshness` and the schedulers | `terraform/main.tf` |
| The daytime stale-data alert | `check_odbc_freshness` in `main.py` |
| "Does ODBC lack a Plex change?" (every alert, since 11-12) | `plex_api_lag.py` |

## In short

- **Label Design: the screens bring new orders fast, and ODBC brings the details.** The report
  reads ODBC plus any Label Design line the screens show that ODBC does not have yet. The new
  line reaches Monday within the hour. When ODBC catches up, the push fills the item's blank
  cells and marks it "confirmed by ODBC". There is no switching, so the two never compete.
- **Shipments and revenue: ODBC only.** Jennilyn: not time critical, the data comes every day.
  The screens check them every 4 hours as an audit. Only a lag that survives the overnight
  catch-up (12 h) emails.

## ODBC is a copy refreshed about every 4 hours (11-11)

Plex's champion (Amber) told Jennilyn that ODBC runs up to 4 hours behind. Our logs agree: ODBC's
newest data moves forward only in jumps, seen at about 09:00, 13:00 and 17:00 MT. Each jump brings
data about an hour old, and nothing moves in between (11-10 16:47→17:02, 11-11 08:46→09:21,
12:46→13:01). So a lag of 1 to 5 hours is normal: about 1 h right after a refresh, about 5 h just
before the next one.

The alerts and timings follow from that:
- **6 h means a refresh was missed.** That is the line for the stale-data email, the watchdog's
  `odbc_vs_plex`, and the Label Design screens email.
- **`behind` starts at 5 h** (`RECON_LAG_TOLERANCE_MIN` = 300): a normal pre-refresh lag is no
  longer a "behind" verdict.
- **Full screen checks run at :20 just after each refresh:** 01, 05, 09, 13, 17 and 21. The
  digests ride the 09:20, 13:20 and 17:20 runs.

## One measure for every alert: Plex changes ODBC lacks (11-12)

Until 11-12 three checks asked **"how old is ODBC's newest change?"**: the stale-data email
(`main.py`), the screens job's `behind` verdict, and the watchdog's `odbc_vs_plex`. That age
also grows when nobody works in Plex, so it raised false alarms:

| When | What fired | Why it was false |
|---|---|---|
| 11-11 14:21-16:41 | screens behind/diverged, watchdog, stale email | the normal wait before the 17:00 refresh (2 h lines then) |
| 11-12 02:11-03:41 | watchdog `odbc_vs_plex`, 6.1-7.6 h | it measured our copy to "now"; we do not load between 23:00 and 04:00 |
| 11-12 07:21 | screens problem digest, "554 min behind" | 4 new Label Design lines under 1 h old, aged from ODBC's newest change (22:08, a quiet night) |

Now every check asks: **is there a change in Plex, older than X, that ODBC does not have?**
Plex's REST API returns every sales order with its `modifiedDate` in about a second
(`plex_api_lag.plex_order_changes`). `odbc_plex_lag(changes, odbc_newest, as_of)` counts the
changes after ODBC's newest order update and up to `as_of`, and returns how long the oldest had
waited at `as_of`. A quiet Plex gives 0; a frozen ODBC (11-10) grows minute by minute.

| Check | ODBC side | as_of | If the API cannot be read |
|---|---|---|---|
| Watchdog `odbc_vs_plex` | our copy's newest order change (`data_freshness`) | the last time we asked ODBC: a load **or a Label Design probe that came back "skipped"** (so a frozen ODBC, where every probe skips, still grows) | skipped, logged |
| Stale-data email (`main.py`) | ODBC's newest order update, read live in the run | now | the old newest-change age |
| Screens `behind` (`screen_recon.py`) | ODBC's newest order update, read live | now | the old newest-change age |

Also since 11-12:
- **Two in a row.** The watchdog mails `odbc_vs_plex` only when the previous run (within 75 min)
  also failed it; the first is logged as `pending:`.
- **One owner per incident.** The watchdog owns "ODBC is behind". The stale-data email is not sent
  when the watchdog mailed `odbc_vs_plex` in the last 24 h (on 11-11 one afternoon lag mailed three
  ways).
- **Working hours only for the watchdog's mail** (weekdays 06:00-18:00 MT). Outside them a breach is
  logged `pending:`; a freeze that lasts into the morning mails at about 06:10.
- **A Plex API that cannot be read** (or answers with under 100 orders) makes the watchdog report
  that the check is blind: pending first, then mailed once a day. The stale email and the screens job
  fall back to the old age.
- **Limits, by design:**
  - The measure covers sales orders only (`Sales_v_PO.Update_Date` against the API's `modifiedDate`).
    A production-only or shipments-only lag shows through the screens' revenue and shipments
    comparison (12 h line) and raw freshness, not through this measure.
  - A freeze under the 6 h line is not mailed, because ODBC's normal lag is 1-5 h. The real 11-10
    freeze (4.5 h) would be quiet today. Label Design is covered by the screens either way.
- **Replay tests** from the real days: `tests/test_plex_api_lag.py` (11-10 freeze must alert;
  11-11 afternoon, 11-12 overnight, 11-12 07:21 and a quiet weekend must stay quiet).

## Why

| | ODBC (`vox.odbc.plex.com`) | Plex screens (web, Playwright) |
|---|---|---|
| Has | every table and column | three screens: Label Design releases, Shipper History, Shipping Revenue by Part Group |
| How current | **behind Plex.** Approval to Monday took about 1.7 h typically and 3.3 to 5.5 h for the slowest quarter (74 items, 10-27 to 11-10). On 11-10, shipments ran 2.5 to 5.5 h behind all afternoon and were current again by 00:20. ODBC also froze for 4.5 h that morning while every run "succeeded". | what Plex shows at the moment of the read |
| Weak spots | late without any error | needs a portal login; about 2 min for the releases screen; only the fields on the screen |

## Label Design, step by step

1. **Read.** `plex-live-screens` reads the releases screen:
   - hourly on weekdays at :20, from 6:20 AM to 5:20 PM MT, with
     `plex-live-screens-releases-sync` setting `RECON_ONLY=releases`;
   - with all three screens every 4 h, just after ODBC's refreshes (01:20, 05:20, 09:20, 13:20, 17:20, 21:20; since 11-11).

   Each read replaces `PlexProd.live_order_releases`.
2. **Combine** (`label_design_report`):
   - Every line ODBC has in Label Design comes from ODBC (`data_source = 'odbc'`).
   - A line the screens show that ODBC does not have yet comes from the screens
     (`data_source = 'live'`). Its customer, part, reps and label attributes are looked up
     in our ODBC copy, so they are blank only for a brand-new customer or part.
   - Screen lines are used only on PlexProd, and only while the screen read is under 3 h old.
     If the job stops, the report is pure ODBC.
3. **Push.** When the view has a screen line, the job starts the Label Design push
   (weekdays 5:00 AM to 5:50 PM). The push creates the item once, as for any line.
   Data Source reads "Plex screens, read 11-11 09:20 MT".
4. **Confirm and fill.** When ODBC has the line, the next push run (every 15 min with the
   Label Design ETL, plus the 6:05 PM sweep) does two things:
   - It fills that item's **empty** cells: Customer Name, Description, Customer PO, Email,
     Phone Number, Sales Rep, Inside Sales Rep, Priority, Bottle Material, and the label
     fields (Label Part #, Label Size, Printing Material, Allergen).
   - It changes Data Source to "Plex screens, read 11-11 09:20 MT; confirmed by ODBC 11-11
     11:05 MT".

   The rules for both:
   - **Only empty cells.** A value the push sent or the team typed is never overwritten.
   - **Data Source is the exception.** It is the only cell rewritten, and only while it still
     holds the push's own "Plex screens" text.
   - **Once per item and field.** It is logged as `outcome = 'filled'` in
     `label_design_push_log`, so a cell the team clears is not filled again.
   - **One write per cell.** A column Monday refuses for our account (Priority and Reason
     Code on Design & QA) is logged as "refused" and settled, and does not block the others.
   - **Only items created from the screens** get the wider list. Items created from ODBC
     already had those fields; they keep the label fields as before.
5. **Check.** Every screen read is compared with ODBC as before. The digest lists the
   Label Design lines that only the screens have so far, by order number. A release ODBC
   still lacks after 6 h is emailed once a day: that means ODBC never delivered it, or it
   was cancelled in Plex.

## Shipments and revenue

- The reports read ODBC only. `live_source.use_live` is FALSE for `revenue`, and its `live_*`
  tables are kept empty.
- Every 4 h the screens are compared with ODBC. An afternoon lag is normal and silent.
- **Email when:**
  - the lag passes 12 h (`RECON_REVENUE_ALERT_LAG_MIN` = 720), which means ODBC missed its
    overnight catch-up; or
  - a verdict is not a delay (diverged, odbc_unreachable).

## Verdicts (per screen, per read)

| Verdict | When |
|---|---|
| `current` | lag up to 5 h (`RECON_LAG_TOLERANCE_MIN` = 300 since 11-11; was 120) |
| `behind` | lag over 5 h. Lag = age of the oldest record or edit the screen shows and ODBC lacks |
| `diverged` | not a delay: ODBC changed a value after the screen showed another; a record missing below a later ODBC record for 2 h+; or records ODBC has and the screen lacks in two reads, while ODBC itself is fresh |
| `odbc_unreachable` | ODBC connect or query failed |
| `pipeline_behind` | ODBC has it, our `raw_*` table (loaded after it) does not: our ETL, not Plex |
| `screens_failed` | a screen could not be read, or came back far smaller than last time |

`PlexOps.live_source` per group:
- `odbc_behind`: any of the last 2 good reads of its screens was behind, diverged or unreachable.
- `use_live`: TRUE for label_design, FALSE for revenue.

## Emails

| Email | When | To |
|---|---|---|
| "Plex ODBC is behind or disagrees with the screens: Label Design" | releases lag over 6 h, or diverged / unreachable. Once a day | REPORT_TO_EMAILS |
| "... : shipments and revenue" | lag over 12 h, or diverged / unreachable. Once a day | REPORT_TO_EMAILS |
| "Plex ODBC caught up: ..." | all current again, only after one of the above. Once | REPORT_TO_EMAILS |
| BigQuery missing records (pipeline_behind) | once a day per screen | REPORT_TO_EMAILS |
| Screen failed twice running | once a day per screen | REPORT_TO_EMAILS |
| Screens digest | 9:20, 13:20, 17:20 MT (just after ODBC refreshes). Also another run that needs action, at most once per 4 h | Emilio, Jennilyn, marketing |
| Plex login failed | once a day per cause | Emilio only |
| "Plex ODBC data is N h old" (`main.py`) | weekdays 9 to 5, a Plex change ODBC lacks for 6 h+ (since 11-12; the newest record's age before, and still if Plex's API cannot be read), once a day, and not when the watchdog already mailed `odbc_vs_plex` in 24 h | REPORT_TO_EMAILS |
| Watchdog `odbc_connect` | weekdays, 3 of the last 4 Label Design runs could not connect to ODBC | REPORT_TO_EMAILS, once a day |
| Watchdog `odbc_vs_plex` | Plex's REST API shows an order change our ODBC copy lacked for over 6 h **when we last asked ODBC** (a missed refresh), two runs in a row (since 11-12), any hour | REPORT_TO_EMAILS, once a day |

A lag under the lines above shows in the digest as "ODBC catching up" (info) and sends nothing of its own.

## Labels

| Report rows | `data_source` | `data_label` |
|---|---|---|
| Label Design line from ODBC | `odbc` | "ODBC, loaded 11-11 07:01, newest change 11-10 16:10 MT" |
| Label Design line from the screens | `live` | "Plex screens, read 11-11 09:20 MT" |

Reports built on Label Design carry the group label, which adds "; new lines from Plex screens,
read ..." while a screen read under 3 h old exists. Monday's Data Source column shows the row's
label, and later "confirmed by ODBC".

## Settings

| Setting | Value | Meaning |
|---|---|---|
| `RECON_LAG_TOLERANCE_MIN` | 300 | lag that counts as `behind` (was 120 until 11-11) |
| `RECON_ALERT_LAG_MIN` | 360 | releases lag that emails |
| `RECON_REVENUE_ALERT_LAG_MIN` | 720 | shipments/revenue lag that emails |
| `RECON_CLEAN_RUNS` | 2 | clean reads before `odbc_behind` clears |
| `RECON_GRACE_MIN` | 15 | records younger than this are not compared |
| `RECON_DIGEST_HOURS` | 8,12,16 | digest runs (MT) |
| `plex-live-screens-sync` | `20 */4 * * *` MT | all three screens |
| `plex-live-screens-releases-sync` | `20 6,7,9,10,11,13,14,15,17 * * 1-5` MT | releases only (`RECON_ONLY`) |

Cost: about $2.40/month for the 4-hourly runs, plus about $3.50 for the weekday hourly releases reads.

## Worked example: 11-10 to 11-11 (before this change)

| Check (MT) | history | revenue | releases |
|---|---|---|---|
| 11-10 14:58 | behind 158 min | behind 253 | current |
| 11-10 16:21 | behind 241 | behind 337 | current (5 extras) |
| 11-10 20:21 | "diverged" 254 | behind 240 | "diverged" (5 extras) |
| 11-11 00:21 | current | current | current |
| 11-11 04:21 | current | current | current |

Under the 11-11 rules this day sends no email:
- Every shipments/revenue lag stayed under 12 h.
- Both "diverged" verdicts were false and no longer happen.
- Order 675, approved at 9:35, would have reached Monday from the screens by 10:20 instead
  of a hand push at 13:00.

## Check it yourself

```sql
-- what Label Design takes from the screens right now
SELECT data_source, order_number, data_label FROM `voxdatalake.PlexProd.label_design_report`
WHERE data_source = 'live';
-- items confirmed / filled later
SELECT pushed_at, order_number, detail FROM `voxdatalake.PlexProd.label_design_push_log`
WHERE outcome = 'filled' ORDER BY pushed_at DESC LIMIT 20;
-- the checks
SELECT FORMAT_TIMESTAMP('%m-%d %H:%M', run_started_at, 'America/Denver') t, screen, verdict,
       odbc_lag_min, missing_tail, odbc_extra, live_action, alert
FROM `voxdatalake.PlexOps.screen_recon` ORDER BY run_started_at DESC LIMIT 18;
SELECT * FROM `voxdatalake.PlexOps.live_source`;
```
