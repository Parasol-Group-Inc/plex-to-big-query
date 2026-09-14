# Label Design sync — BigQuery → Sheet → Monday

Replaces a twice-daily manual loop: download a report from NetSuite, paste it
into a Google Sheet, check it for duplicates by hand, upload the new rows to
Monday.

```
Plex ──► label_design_report ──► [this script] ──► Sheet (MONDAY tab)
 (Cloud Run job, 09:30/13:30)          │
                                       └────────► Monday HOLDING board
```

The Cloud Run job refreshes BigQuery; **this script decides what is new** and
pushes it onward. That is why the notifications live here: the pipeline knows a
query succeeded, only this knows what reached Monday.

**The ETL runs 30 minutes before this script does.** Apps Script only guarantees
the *hour* of a trigger, so the job is at 09:30/13:30 and the script fires in
the 10:00/14:00 hours. Move one and you must move the other.

## Schedules

| What | When | Why |
|---|---|---|
| ETL job (`plex-etl-label-design`) | 09:30, 13:30 Mountain — **every day** | Orders are entered at the weekend; a weekday-only refresh hands the team a two-day-stale queue on Monday morning |
| `syncNow` | 10:00, 14:00 hours — **every day** | Follows the ETL |
| `sendDailySummary` | 18:00 — **Monday to Friday** | Nobody wants a Sunday email |

Monday's summary covers **Saturday and Sunday too**. The sync runs seven days a
week but the summary does not, so the summary window is "since the last summary
was sent" rather than "today" — otherwise two days of weekend activity would be
reported to nobody at all.

## Notifications

No "errors only" filter. **Every run emails**, pass or fail — a silent success
and a job that never fired look identical from the outside, and the reason this
was automated is that nobody notices when a manual step stops happening.

| When | Who | What |
|---|---|---|
| **Technical** — every run (10:00, 14:00, daily) | Jennilyn, Emilio, `marketing@parasolgroupinc.com` | Counts, the new rows, column flags, any problems |
| **Summary** — 18:00, weekdays | Ashley, Kelli, Jennilyn, Emilio, `marketing@parasolgroupinc.com` | One digest: added, pushed, queue size, runs |

The summary calls out the states that matter and reads differently for each:
**no sync ran at all**, **problems occurred**, **held for review**, and
**nothing new**. The last is normal and says so, so a quiet day doesn't look
like a broken one.

Both emails are Vox-branded HTML matching `templates/report.html`, with a
plain-text body alongside — that is what phone notification previews and screen
readers actually use. Addresses are at the top of `Code.gs` rather than in
Script Properties: they are a business decision that belongs in review, not a
deployment setting.

## The sheet

**`SHEET_MAP` in `Code.gs` is the MONDAY tab's real header row, in its real
order.** Rows are written by looking up each column's position *on the tab*, so
if someone reorders the columns their order is respected rather than producing
a scrambled sheet.

Four columns are blank **by design** — *Reason Code*, *Label*, *Bottle
Material*, *LCR* are filled in by a person during review. Two are blank because
**Plex has no source for them**: *WO Number* (raised after the label is
approved, so an order still in Label Design usually has none) and *Item* (the
NetSuite item name; no Plex column reproduces it).

Those two kinds are reported **separately** in every run email, along with any
column on the tab we don't recognise and any mapped column the tab is missing.
The split matters: a section that flags the same four review columns as
"problems" every single run is a section everyone learns to skip, and the real
gaps go with it.

## Deduplication

**Order number + Label SKU (the customer part number)**, checked against
**both** tabs.

Not the date, and not a row id: dates change, and an order can be cancelled and
reopened. The same customer part on a *different* order is legitimately new and
must repeat.

The two sides spell the order number differently — the sheet says
`Sales Order #SO0110212`, Plex says `SO0110212` — so both are reduced to a
token first (`orderToken_`).

**That reduction is the single point of failure for the whole thing.** If it
ever stops matching, every row looks new at once and the queue gets re-imported
onto the sheet and the board. So `assessKeys_()` watches for exactly that
shape — many new rows, *zero* matches against a non-empty archive — and holds
the run back rather than pushing. Nothing is discarded: the rows go to a dated
`REVIEW <date>` tab and a person looks first.

## Never writing `historical`

The **`historical` tab is read and never written.** People edit notes and
reason codes there by hand; re-writing a row would overwrite that work. It is
also the reason rows land in a Monday *holding* board rather than the live one
— the review step is the point, not an obstacle.

This is **enforced, not remembered**: every write path goes through
`assertNotHistory_()`, so a future edit cannot quietly break it.

If the archive tab is missing, or lacks its key columns, the run **stops**
rather than continuing. Without it nothing can be deduplicated, and the failure
mode is writing the entire queue again.

## Setup

1. Create the Apps Script project. Paste in `Code.gs` **and `Logo.gs`**.
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
   It reports what it *would* write, which tab it would go to, and which
   columns it can and cannot fill.
6. Run **`installTriggers()`** once.

## Testing changes

```bash
node deploy/label_design_sync/test_logic.js
```

25 checks of the pure logic against the **real** exports in `assets/` — the
actual 15-column MONDAY header row and all 5,182 historical rows, with their
real quirks (the trailing space in `"Label "`, `Phone` vs `Phone Number`, six
blank trailing headers). Needs no credentials and touches nothing.

**Run it after any change to `SHEET_MAP`, the tokenisers, or header
resolution.** Those three are where a silent, expensive mistake lives — a
broken dedupe doesn't throw, it re-imports the archive.

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
- **The run log is in Script Properties**, capped at 40 entries (a fortnight —
  it has to reach back over a weekend for Monday's summary). It is scaffolding
  for the summary email, not business data, and nobody should have to look at
  it or be able to edit it.
- **Email styles are inline attributes, not a `<style>` block** — Gmail strips
  `<style>` from a received message. The stats row is a table, not flexbox,
  because Outlook stacks flexbox vertically.
- **The logo is base64 in `Logo.gs`** because Apps Script cannot read a file
  out of this repo, a hosted URL would mean a public bucket object, and Gmail
  strips `data:` URIs. Regenerate it with `python scripts/build_logo_gs.py`.
- **`send_()` drops the `from` alias and retries** if MailApp rejects it. An
  email that arrives from the wrong address is far better than one that does
  not arrive.

## The deployment trap

**Saving the code does not update anything that runs on a trigger** the way a
web app needs a new version — but triggers *do* pick up saved code. The trap
here is different: `installTriggers()` **deletes every existing trigger** in
the project first. Don't run it in a project that has other triggers you care
about.

## Still to do

- **Map the Monday board's columns.** This is the *only* edit needed to turn
  the push on — the push code itself is finished.

  1. Create the holding board; set `MONDAY_BOARD_ID` and `MONDAY_API_KEY`.
  2. Run **`listMondayColumns()`** from the editor. It reads nothing, writes
     nothing and creates nothing — it prints every column's real id and type,
     plus a ready-to-paste `MONDAY_COLUMNS`.
  3. **Check the printed map**, then paste it over `MONDAY_COLUMNS` near the
     top of `Code.gs`. The title matching is a convenience guess, not a
     decision; a board with two "Email"-ish columns will guess one.

  Monday column ids are **per-board and are not the column titles**, so they
  cannot be guessed — and a wrong id fails *silently* (Monday answers 200 with
  an `errors` array), which is miserable to debug by hand. Until at least one
  id is filled in, the run reports the unmapped map as a problem rather than
  creating a board full of items with a name and no populated columns.

  A partly-filled map is fine: unmapped fields are skipped, not sent blank.
- The rep name arrives as plain text. It can be mapped to Monday's status
  column for reps on the board side, or linked when an item moves from holding
  to the live board — the latter was thought to be easier.
- **`Prop 65` is on the historical tab but not the MONDAY tab.** It is in
  `SHEET_MAP` so it fills automatically if the team adds the header, and is
  reported as "we can fill this, the tab doesn't have it" until they do.
