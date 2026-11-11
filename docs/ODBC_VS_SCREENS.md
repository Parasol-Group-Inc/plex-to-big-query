# ODBC vs Plex screens: which source each report reads, and when we email

Current as of **2026-11-11**. This page holds all the rules in one place. The detailed runbook is
`docs/PLEX_SCREEN_EXTRACTION.md` ("Reconciliation (cloud job)"). The code is
`scripts/screen_recon.py`, the `live_source` and `data_freshness` views in `terraform/main.tf`, and
`check_odbc_freshness` in `main.py`.

## The two ways we read Plex

| | ODBC (`vox.odbc.plex.com`) | Plex screens (web, Playwright) |
|---|---|---|
| What | Plex's database feed, every table and column | three screens: Label Design releases, Shipper History, Shipping Revenue by Part Group |
| Who reads it | every ETL job (4 AM full run plus 1 PM / 6 PM / 11 PM probes; Label Design every 15 min, weekdays 5:00-5:45 PM) | the Cloud Run job `plex-live-screens`, every 4 h at :20 MT (00:20, 04:20, 08:20, 12:20, 16:20, 20:20) |
| How current | **runs behind Plex.** Measured 11-10: 2.5 to 5.5 h behind all afternoon, current again by 00:20 and at 04:20. On 11-10 it also froze for 4.5 h (08:10-12:50) while every run "succeeded". | what Plex shows at the moment of the read |
| Weak spots | can be late without any error | needs a portal login; about 2 min for the releases screen; only the fields on the screen |

## The rules, step by step (every 4 h)

1. The screens job logs in, reads the three screens and saves screenshots
   (`gs://voxdatalake-plex-screenshots/plex-screens/YYYY/MM/DD/HHMM-MT_<run>/`).
2. It reads the same records **live from ODBC**, on its own connection minutes after the screen
   read, not from our BigQuery copy. So "ODBC behind" is Plex's own lag, never our ETL schedule.
3. It compares the records one by one. Records under 15 min old are skipped (`RECON_GRACE_MIN`).
   There is one exception: a release or revenue line seen for the first time that ODBC lacks while
   ODBC's newest change is already over 2 h old. It counts at once (the 11-10 order-675 case).
4. **Lag** is the age of the oldest record or edit the screen shows and ODBC does not have yet.
5. Each screen gets a verdict:

   | Verdict | When |
   |---|---|
   | `current` | lag up to 2 h (`RECON_LAG_TOLERANCE_MIN` = 120) |
   | `behind` | lag over 2 h |
   | `diverged` | not a delay: ODBC changed a value after the screen showed another; a record is missing below ODBC's newest (a later-minute one) for over 2 h; or ODBC has records the screen lacks in two checks running **while ODBC itself is fresh** |
   | `odbc_unreachable` | ODBC connect or query failed |
   | `pipeline_behind` | ODBC has it, our `raw_*` table (loaded after it) does not: our ETL, not Plex |
   | `screens_failed` | a screen could not be read, or returned far fewer rows than last time |

6. **Switching** (`PlexOps.live_source`, one switch per group):
   - **Label Design** follows the releases screen.
   - **Revenue and shipments** follow the history and revenue screens.

   A group goes to the screens after **one** `behind`, `diverged` or `odbc_unreachable` check.
   It goes back to ODBC after **two** clean checks (8 h). While switched, each check reloads that
   group's `PlexProd.live_*` tables. A report reads them only while the switch is on **and** the
   table is under 5 h old. So if the screens job stops, every report is back on ODBC within 5 h,
   with no action needed.
7. **Emails (since 11-11):**
   - **A lag of 2 to 6 h switches quietly.** There is no email, and the digest reads
     "Screens Digest: ODBC catching up" (info).
   - **A lag over 6 h** (`RECON_ALERT_LAG_MIN` = 360), or any non-delay verdict, sends the
     "ODBC is behind the screens" email, at most once a day per group. It also makes the digest
     say ACTION NEEDED and send outside its usual hours.
   - **"Back on ODBC"** is mailed only if the first email went out.
   - Lag is measured only at the 4-hourly checks, so a 6 h lag shows up at the first check after
     it passes 6 h: in practice 6 to 10 h after the record was entered.
8. **Labels.** Every report built on Label Design, shipping revenue or production carries
   `data_source` (odbc / live), `data_as_of` and `data_label`. Monday's "Data Source" column
   shows `data_label`.

## Per group, in plain words

| | Label Design | Revenue and shipments |
|---|---|---|
| Screen | Label Design order releases | Shipper History + Shipping Revenue by Part Group |
| Goes to the screens | when ODBC is over 2 h behind on any release, or a brand-new release is missing while ODBC's newest change is over 2 h old | when ODBC is over 2 h behind on any shipment or revenue line |
| What the screens replace | the order lines: order, release, part, quantity, due date, status | the shipped lines and their revenue |
| What still comes from ODBC while on the screens | order header (sales reps), customer, customer part, part, bottle/label attributes: our last extracted copy of those tables | customer and part details (our last extracted copy) |
| Monday | while on the screens, the screens job starts the Label Design push itself | n/a |
| Email | only a lag over 6 h, or a real disagreement | the same |

## Other ODBC emails that are not part of the screens job

- **"Plex ODBC data is N h old"** (`check_odbc_freshness` in `main.py`, every prod run). It fires
  on weekdays 9-5 MT when ODBC's newest order update, production record or shipper is 2 h or more
  old (`STALE_ALERT_MINUTES` = 120), at most once a day. It measures how old the newest record is,
  not the screens lag, and it stays quiet while a group is on the screens. On 11-10 it caught the
  real 08:10-12:50 freeze. It was left at 2 h on purpose. Raising it to 6 h would match the
  screens email but would miss a freeze like 11-10's.
- **"Plex ODBC failing for 6 h, start the live screens"**: ODBC does not connect at all.
- The ETL digest's health line lists a group on the screens.

## Worked example: 11-10 to 11-11

| Check (MT) | history | revenue | releases | What happened |
|---|---|---|---|---|
| 11-10 14:58 | behind 158 min | behind 253 min | current | revenue to the screens |
| 11-10 16:21 | behind 241 | behind 337 | current (5 extras) | |
| 11-10 20:21 | "diverged" 254 | behind 240 | "diverged" (5 extras again) | ACTION NEEDED digest. Both "diverged" verdicts were false: fixed 11-11. |
| 11-11 00:21 | current | current | current | ODBC caught up |
| 11-11 04:21 | current | current | current | after the 4 AM run: both groups back on ODBC |

Under the 11-11 rules the same day sends no email. Every lag stayed under 6 h, and neither
"diverged" verdict happens anymore. The reports still read the screens from 14:58 until ODBC
caught up.

## Settings (Terraform env on `plex-live-screens`)

| Setting | Value | Meaning |
|---|---|---|
| `RECON_LAG_TOLERANCE_MIN` | 120 | lag that switches a group to the screens |
| `RECON_ALERT_LAG_MIN` | 360 | lag that emails |
| `RECON_CLEAN_RUNS` | 2 | clean checks before switching back |
| `RECON_GRACE_MIN` | 15 | records younger than this are not compared |
| `RECON_DIGEST_HOURS` | 8,12,16 | digest runs (MT) when nothing needs action |
| schedule | `20 */4 * * *` MT | 6 checks a day (about $2.40/month) |

## Check it yourself

```sql
SELECT * FROM `voxdatalake.PlexOps.data_freshness` WHERE dataset = 'PlexProd';
SELECT FORMAT_TIMESTAMP('%m-%d %H:%M', run_started_at, 'America/Denver') t, screen, verdict,
       odbc_lag_min, missing_tail, missing_hole, odbc_extra, live_action, alert
FROM `voxdatalake.PlexOps.screen_recon` ORDER BY run_started_at DESC LIMIT 18;
```
