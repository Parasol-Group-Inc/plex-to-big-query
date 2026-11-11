# ODBC and the Plex screens: how they work together

Current as of **2026-11-11**. This page holds all the rules in one place. The runbook is
`docs/PLEX_SCREEN_EXTRACTION.md` ("Reconciliation (cloud job)"). The code is:

| Code | Where |
|---|---|
| The screens job | `scripts/screen_recon.py` |
| Combining ODBC and screen lines | `reports/sql/label_design_view.sql` |
| Filling in blanks on Monday | `label_design_service/fill.py` |
| `live_source`, `data_freshness` and the schedulers | `terraform/main.tf` |
| The daytime stale-data alert | `check_odbc_freshness` in `main.py` |

## In short

- **Label Design: the screens bring new orders fast, and ODBC brings the details.** The report
  reads ODBC plus any Label Design line the screens show that ODBC does not have yet. The new
  line reaches Monday within the hour. When ODBC catches up, the push fills the item's blank
  cells and marks it "confirmed by ODBC". There is no switching, so the two never compete.
- **Shipments and revenue: ODBC only.** Jennilyn: not time critical, the data comes every day.
  The screens check them every 4 hours as an audit. Only a lag that survives the overnight
  catch-up (12 h) emails.

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
   - with all three screens every 4 h (00:20, 04:20, 08:20, 12:20, 16:20, 20:20).

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
| `current` | lag up to 2 h (`RECON_LAG_TOLERANCE_MIN` = 120) |
| `behind` | lag over 2 h. Lag = age of the oldest record or edit the screen shows and ODBC lacks |
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
| Screens digest | 8:20, 12:20, 4:20 PM. Also another run that needs action, at most once per 4 h | Emilio, Jennilyn, marketing |
| Plex login failed | once a day per cause | Emilio only |
| "Plex ODBC data is N h old" (`main.py`) | weekdays 9 to 5, newest ODBC record 2 h+ old, once a day; quiet while ODBC is behind the screens for Label Design | REPORT_TO_EMAILS |

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
| `RECON_LAG_TOLERANCE_MIN` | 120 | lag that counts as `behind` |
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
