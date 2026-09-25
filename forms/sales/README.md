# Daily Sales Activity Log (Apps Script web app)

A form sales reps fill in once per workday. It records the day's emails,
calls, meetings, visits to Vox, social DMs and other outreach, plus leads
assigned and contacted, and a PTO flag. Each submission is written to
**`voxdatalake.VoxScorecardsLive.daily_sales_activity`**.

**It predates this repo's pipelines and is not part of the Plex ETL.** It
writes to the `VoxScorecardsLive` dataset (the live Monday-fed scorecard
dataset), not `PlexProd`/`PlexTest`. This folder is a copy of the code, kept
for reference and review; the live copy is Jennilyn's Apps Script project.
It is also the model the manual-data app (`deploy/manual_data_app/`) was
built after.

## Files

| File | What it is |
|---|---|
| `code.gs` | Form handler, BigQuery write, and reminder/summary emails |
| `SalesActivity.html` | The form itself (served by `doGet`) |

## How it behaves

| Function | When | Does |
|---|---|---|
| `doGet` | a rep opens the URL | Serves the form |
| `submitActivityLog(payload)` | a rep submits | Streams one row into `daily_sales_activity` (`BigQuery.Tabledata.insertAll`, insertId = rep + date + timestamp) |
| `dailyMorningCheck` | Mon–Fri, 07:00 (script time zone) | Emails every rep who hasn't logged the previous workday |
| `fridayManagerSummary` | Friday, 17:00 | Emails the manager (`MANAGER_EMAIL`) the week's missing entries, if any |
| `installTriggers()` | run once by hand | Replaces this project's triggers with the two above |

## Things to know before changing it

- **The rep list is hard-coded** (`REP_EMAILS` in `code.gs`): seven reps.
  Plex's Inside Sales roster (`sales_reps_report`) now lists 13, so a new
  rep gets neither the form nor reminders until someone edits this map.
- **`MANAGER_EMAIL` is hard-coded** (`ashley.quintana@voxnutrition.com`).
- **Streaming inserts** sit in BigQuery's streaming buffer for a while, so a
  just-submitted row can't be updated or deleted by DML straight away. The
  manual-data app uses load jobs for exactly this reason.
- **The trigger times follow the script's time zone setting.** Set it to
  `America/Denver` before running `installTriggers()`.
- **Changes here don't deploy anywhere.** To change the live form, edit the
  Apps Script project and deploy a new web-app version, then copy it back
  here so this stays the record.
