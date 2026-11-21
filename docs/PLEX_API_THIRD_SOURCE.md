# Plex's REST API: the third source for Label Design

Since 2026-11-20 (Emilio: "let's roll with the API as third source"). Code: `plex_api_releases.py`
(shared by `main.py` and `watchdog.py`); tests: `tests/test_plex_api_releases.py`. How ODBC and the
screens work together: `docs/ODBC_VS_SCREENS.md`.

## In short

Label Design had two sources: ODBC (every 15 min, but Plex refreshes its ODBC copy only about
every 4 h) and the Plex releases screen (hourly on weekdays). The API is now the third. It never
writes a Label Design line itself; it does two things:

- **Trigger.** Every prod Label Design run (every 15 min, weekdays 5:00 AM to 5:50 PM MT) first asks
  the API. If Plex has a Label Design line that neither ODBC nor the last screen read has, and it
  changed after that read, the run starts a releases screen read right away. A new line reaches
  Monday in about 15 to 25 min instead of up to an hour.
- **Coverage check.** The watchdog (every 30 min) asks the API too. A Label Design line that Plex has
  had for over 75 min (5 h outside weekday working hours) and that is in neither ODBC nor the screens
  is a line Monday does not have. Two runs in a row, it emails.

## The three sources side by side

| | ODBC | Releases screen | REST API |
|---|---|---|---|
| What it is | Plex's reporting copy, read by our ETL | Plex's Order Entry screens, read by a browser (`plex-live-screens`) | `connect.plex.com`, read with a key |
| How fresh | Plex refreshes it about every 4 h (1 to 5 h behind is normal) | Live at the moment of the read | Live |
| How often we read it | Every 15 min (Label Design), weekdays 5 AM to 5:45 PM | Hourly 6:20 AM to 5:20 PM weekdays; every 4 h otherwise; now also when the API triggers it | Every 15 min (trigger) and every 30 min (watchdog) |
| Keys | Integer keys (PO_Line_Key, Release_Key) and Resource_ID UUIDs | Integer keys | UUIDs only |
| What it covers | Every order and release | Pending Fulfillment orders dated 2026-10-18 or later | Every order and release |
| Details it carries | Everything (customer, reps, part attributes, BOM) | Keys, status, due date, part, Job Note | Release status, part number, quantity, dates; order status, customer UUID |
| Feeds Monday | Yes | Yes (new lines; ODBC fills the blanks later) | No: it starts a screen read |
| Fails how | Refused connections; frozen data while runs "succeed" (11-10) | Login or page problems (0 failed reads in the 7 days to 11-20) | HTTP 500/504 (11-19 07:11-07:41 and 15:11-17:41 MT); cut-off answers |

## What the API has (probed 2026-11-20, GET only)

The first survey (2026-11-11) is the hub's **Label Design API** tab (`docs/hub/label_api_survey.json`):
it timed the calls and listed the fields. This probe adds the order-to-release mapping and the rule.


| Endpoint | Answer | Notes |
|---|---|---|
| `/sales/v1/orders` | every order (745) | paging is ignored; ~750 KB. `?status=Pending%20Fulfillment` works: 367, ~2 s |
| `/sales/v1/orders/{id}` | one order | same fields as the list |
| `/sales/v1/orders/{id}/lines` | that order's lines | id, lineNumber, partId, customerPartId, active, note |
| `/sales/v1/releases` | every release (1,717) | `?status=Label%20Design` works (192, ~2 s), as does `modifiedDateBegin`; `?orderId=` is ignored |
| `/sales/v1/orders/{id}/releases`, `/sales/v1/order-lines`, `/sales/v1/lines`, `/sales/v1/order-releases`, `/scheduling/v1/releases`, `/sales/v2/orders` | 404 | do not exist |

A release carries: `id`, `orderLineId`, `releaseNumber`, `status`, `type`, `partNumber`, `quantity`,
`quantityShipped`, `dueDate`, `shipDate`, `shipToAddressId`, `note`, `packagingNote`, created and
modified dates. An order carries `orderNumber`, `status`, `type`, `orderDate`, `poNumber`,
`customerId`, `insideSalesId`, `outsideSalesIds`, the notes and the addresses.

Release statuses on 11-20: Open 632, Closed 540, Service 231, Label Design 193, Canceled 86,
Blanket 17, Scheduled 4. Order statuses: Pending Fulfillment 367, Closed 250, Quote 51, Deposit
Review 45, Pending Sales Approval 17, Cancelled 15. They are the same names as ODBC's.

**The UUIDs are ODBC's `Resource_ID`.** On 11-20, 1,697 of 1,697 ODBC releases, 1,697 of 1,697 order
lines and 736 of 736 orders matched an API record by `Resource_ID`. The API had 6 more releases and
2 more orders: the ones ODBC had not caught up with yet.

## What counts as a Label Design line

The same rule as `reports/sql/label_design_view.sql`: a release whose status is **Label Design** on an
order whose status is **Pending Fulfillment**. On 11-20 the API had 192 releases in Label Design, but
only 90 of them on Pending Fulfillment orders; ODBC had all 90, the screen 74 (the other 16 are on
orders dated before 10-18, which the screen does not search; ODBC has them).

Three cases from 11-20 that the rule gets right:

- **Order 806** (5 releases, created 08:20 MT): the API had them at once, the screen at 09:21, ODBC
  not by 14:00. They are **Open**, not Label Design, so they never belong on the board.
- **Orders 811 and 815** (new Label Design releases at 12:37 and 13:59 MT): the screen did not show
  them, because both orders are **Quotes**. Label Design keeps Pending Fulfillment only, so neither
  source is wrong; they appear once sales approves the order.
- **An approval** is the usual way a line becomes a Label Design line: the order goes from Quote or
  Deposit Review to Pending Fulfillment. So the trigger watches order changes too, not only new
  releases (its "changed" time is the later of the release's and the order's).

## Why the API does not push to Monday itself

Monday items are keyed by ODBC's integer line key: the LCR column holds a hash of
`<order>|L<po_line_key>`. The API has only UUIDs, and a brand-new line has no integer key until the
screens or ODBC have it. An item created from the API would get a different key, and the line would
become a second item when the screen or ODBC brought it later. Asking the screen for the line keeps
one key for every source.

The option set aside (2026-11-20): API rows as data when the screens are down too, keyed by the
line's UUID, and the push rekeying the Monday item once ODBC has the line. It covers ODBC and the
screens both down, at the cost of a bigger change to the push and the view and a real duplicate
risk if a rekey is missed. Revisit if the screens prove unreliable.

## The trigger, step by step

In `main.py`, at the start of every run of `plex-etl-label-design` with `API_SCREENS_TRIGGER=1`
(Terraform sets it on the prod job only), before ODBC is touched, so it works while ODBC is down.

1. Outside weekdays 5:00 AM to 5:50 PM MT (the push window), do nothing.
2. Read the Pending Fulfillment orders and the Label Design releases (two filtered calls, ~2 s each;
   retried twice on a 5xx or a cut-off answer; fewer than 50 orders counts as unreadable), our ODBC copy (PlexProd raw tables) and the last screen read (`live_order_releases`,
   `screen_recon`). A release whose line ODBC does not know is new: its order is found by asking
   `/orders/{id}/lines` of the Pending Fulfillment orders changed since (at most 40 calls).
3. Find Label Design lines in neither ODBC nor the screen, changed after the last screen read started.
   None: done.
4. Do not start a read when: the hourly read is due (from :08 to :19, 6 AM to 5 PM); a screens login
   happened in the last 12 min (a read is running or just ran; two Plex logins at once can end each
   other's session); a trigger already started one in the last 20 min.
5. Otherwise start `plex-live-screens` with `RECON_ONLY=releases`, exactly as the hourly scheduler
   does. The screens job loads the line and starts the push.
6. Log the decision in `PlexOps.api_trigger_log` (every start, and every time a line was waiting).

It cannot loop: a line that the read after its change did not show is never triggered again. That
case is what the coverage check reports. Any error is logged as a warning and the run goes on.

## The coverage check

`watchdog.py`, check `label_design_coverage`, every 30 min. A Label Design line that Plex has had
for over **75 min** (weekdays 6 AM to 6 PM; **5 h** otherwise, when the screens read every 4 h) and
that is in neither ODBC nor the screens fails the check. The first failure is logged as pending; the
second in a row emails (at most once a day per check, as for every watchdog check). An API that
cannot be read is not reported here: `odbc_vs_plex` already says so.

## When something is down

| Down | What happens to a new Label Design line |
|---|---|
| Nothing | ODBC within 1 to 5 h; the screens within the hour; now 15 to 25 min with the trigger |
| ODBC (refused or frozen) | The screens bring it (trigger or hourly); ODBC fills its blank cells when back |
| The screens job | ODBC brings it (1 to 5 h); the coverage check emails after 75 min |
| The API | Nothing changes: the hourly screens and ODBC as before; `odbc_vs_plex` reports the API |
| ODBC and the screens | No source can feed Monday; the coverage check emails after 75 min. The rekey option above is what would cover this |
| All three | The ODBC breaker and the screens' login alerts email; nothing reaches Monday |

## Checking it

```sql
-- Every trigger decision that mattered (starts, and lines waiting)
SELECT * FROM `voxdatalake.PlexOps.api_trigger_log` ORDER BY checked_at DESC LIMIT 50;

-- The coverage check
SELECT checked_at, ok, detail FROM `voxdatalake.PlexOps.watchdog_log`
WHERE check_id = 'label_design_coverage' ORDER BY checked_at DESC LIMIT 20;
```

Each Label Design run logs one line: `API third source: N Label Design lines in Plex, M in neither
ODBC nor the screens; started <execution> | no screens read (<why>)`.

## Cost, speed, credentials

- About 26 s per pass on 11-20, mostly the four small BigQuery reads; 2 API calls, plus one per
  changed order only when a release's line is new. Adds that to each Label Design run, and to the
  watchdog.
- The API key belongs to the company user `gcp.odbc.vox` (secrets `plex-api-consumer-key` /
  `-secret`, `docs/PLEX_CREDENTIALS.md`). The ETL service account already reads those secrets and
  already may start a job with overrides (`plexEtlRunWithOverrides`). No new permissions.

## Probing it again

From a laptop, with the `.env` pair `PLEX_GCP_API_CONSUMER_KEY` / `PLEX_GCP_API_CONSUMER_SECRET`
and the headers `X-Plex-Connect-Api-Key` / `X-Plex-Connect-Api-Secret`, GET
`https://connect.plex.com/sales/v1/releases`. Test is `https://test.connect.plex.com`. Never print the
key. `plex_api_releases.fetch(bq, get=...)` takes any GET function, so the full comparison runs
locally with the `.env` key instead of Secret Manager.
