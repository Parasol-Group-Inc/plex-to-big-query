# Label Design sync — BigQuery → Sheet → Monday

Replaces a twice-daily manual loop: download a report from NetSuite, paste it
into a Google Sheet, check it for duplicates by hand, upload the new rows to
Monday.

```
Plex ──► label_design_report ──► [this script] ──► Sheet (main tab)
 (Cloud Run job, 10:00/14:00)          │
                                       └────────► Monday HOLDING board
```

The Cloud Run job refreshes BigQuery; **this script decides what is new** and
pushes it onward. That is why the notifications live here: the pipeline knows a
query succeeded, only this knows what reached Monday.

## Notifications

No "errors only" filter. **Every run emails**, pass or fail — a silent success
and a job that never fired look identical from the outside, and the reason this
was automated is that nobody notices when a manual step stops happening.

| When | Who | What |
|---|---|---|
| **Every run** (10:00, 14:00) | `emilio.dominguez@parasolgroupinc.com`, `marketing@parasolgroupinc.com` | Counts, the new rows themselves, and any problems |
| **Nightly** (18:00) | `ashley.quintana@voxnutrition.com`, `kelli.gooch@voxnutrition.com`, `jennilyn.tockstein@parasolgroupinc.com` | One digest: added today, pushed, queue size, runs |

The nightly summary calls out the three states that matter and reads
differently for each: **no sync ran at all**, **problems occurred**, and
**nothing new today**. The last is normal and says so, so a quiet day doesn't
look like a broken one.

Addresses are in `Code.gs` at the top rather than in Script Properties — they
are a business decision that belongs in review, not a deployment setting.

## Deduplication

**Order number + customer part number**, checked against **both** tabs.

Not the date, and not a row id: dates change, and an order can be cancelled and
reopened. The same customer part on a *different* order is legitimately new and
must repeat.

The **`historical` tab is read and never written**. People edit notes and
reason codes there by hand; re-writing a row would overwrite that work. It is
also the reason rows land in a Monday *holding* board rather than the live one
— the review step is the point, not an obstacle.

If either tab is missing its order-number or customer-part column, the run
**stops** rather than continuing. Without those columns nothing can be
deduplicated, and the failure mode is writing the entire queue again.

## Setup

1. Create the Apps Script project. Paste in `Code.gs`.
2. **Services (+) → BigQuery API → Add.**
3. **Project Settings → set the timezone to `America/Denver`** before
   installing triggers — Apps Script hour triggers follow the script timezone,
   so the wrong one silently runs the sync at the wrong times.
4. **Script Properties:**

   | Property | Value |
   |---|---|
   | `GCP_PROJECT` | `parasoldatalake` — jobs run and bill here |
   | `BQ_DATA_PROJECT` | `voxdatalake` — where the tables are |
   | `BQ_DATASET` | `PlexTest` → `PlexProd` at go-live |
   | `SHEET_ID` | **the duplicate sheet**, not the live one |
   | `MONDAY_API_KEY` | long-lived token |
   | `MONDAY_BOARD_ID` | from the holding board's URL |

5. Run **`testReadOnly()`** — writes nothing, pushes nothing, emails nobody.
   It reports what it *would* write.
6. Run **`installTriggers()`** once.

## Design notes worth knowing before changing it

- **Monday items are created one at a time.** A batch that fails halfway is
  worse than a few individual failures: the sheet has already been written and
  there is no way to tell which half landed.
- **Monday answers `200` with an `errors` array** rather than an HTTP error, so
  the status code alone reports success on a rejected mutation. The response
  body is checked.
- **A Monday failure does not undo the sheet write.** The row stays, the key is
  recorded, and the next run will not repeat it — so a failed push means "on
  the sheet, not on the board", which is exactly what the email says. Fixing it
  is a manual re-push of named rows, not a re-run.
- **The 14-day window lives in the view, not here.** Filtering again in two
  places means two places to change one rule.
- **The run log is in Script Properties**, capped at 30 entries. It is
  scaffolding for the nightly summary, not business data, and nobody should
  have to look at it or be able to edit it.
- **Column order is explicit**, not derived from the query, so a column added
  to the view doesn't silently shift the sheet.

## The deployment trap

**Saving the code does not update anything that runs on a trigger** the way a
web app needs a new version — but triggers *do* pick up saved code. The trap
here is different: `installTriggers()` **deletes every existing trigger** in
the project first. Don't run it in a project that has other triggers you care
about.

## Still to do

- Column IDs in `pushToMonday_` (`text_order`, `date_due`, …) are **placeholders
  until the holding board exists**. Monday column IDs are per-board and are not
  the column titles. Read them from the board, then update the map.
- The rep name arrives as plain text. It can be mapped to Monday's status
  column for reps on the board side, or linked when an item moves from holding
  to the live board — the latter was thought to be easier.
