# Picking & staging app (2026-11-20)

Jennilyn asked on 2026-11-20 for "a simple web interface that pulls inventory and the job schedule"
so the Vox team can pick and stage scheduled jobs, which takes them hours in Plex today. This is
that app: code in `deploy/picking_app/`, tests in `tests/test_picking_app.py`, tested end to end
against **Plex TEST** on 11-20. It runs on Cloud Run (service `picking-app`, company Google sign-in) since 11-20:
Plex TEST until 11-23, Plex production with moves OFF from 11-23 (revision 00004), and back to Plex TEST after the
11-23 audit fixes (deploy with `PLEX_ENV_FOR_APP=test`). It has never moved anything in production.
**Read [PICKING_AUDIT_2026-11-23.md](PICKING_AUDIT_2026-11-23.md)** (three independent audits and what was fixed).

## In short

- **Job sets are the pick lists.** In Plex every blend job comes as a job set: the Blending job plus
  one Pre-Weigh job per ingredient (set 832: 1 blend + 9 pre-weigh). 782 sets since go-live; 1,186
  of 1,373 open jobs are in one. The app lists the sets due in the next N days and, per set, what
  has to be picked: each Pre-Weigh job's raw material, quantity = job quantity x the job's own BOM.
- **Containers are read live** from Plex's REST API, filtered by part, and the app suggests which
  to pick: status OK, in a Warehouse location, first-expiring lot first.
- **The move goes through Plex's own Move Container screen**, called the way the screen calls it.
  Neither the REST API nor ODBC can move a container (below). One move takes 0.2 to 0.5 s.
- **Tested in Plex TEST:** single containers, a Hold container, whole pallets (LP), bad serial, bad
  location, through the screen, the direct call, the app and the command line; everything moved
  was moved back and checked through the API.

## Moving a container: what each source can do (tested 2026-11-20)

| Source | Can it move? | Evidence |
|---|---|---|
| REST API (`connect.plex.com`) | **No** | In TEST, with a serial that does not exist (nothing can move): `POST .../inventory-control/containers/{serial}/scrap` answers 400 "ScrapReason is required" (the route exists); `/retire` answers 404 naming the serial (exists, container unknown). Every move, location, transfer, status, split and adjust variant, under inventory-control, inventory-tracking and v1-beta1, answers a bare 404. Unknown API families answer 401 to any path, so a move API in a family our key is not subscribed to cannot be ruled out: ask Plex. |
| ODBC | **No** | On the TEST host a zero-row `UPDATE ... WHERE 1=0` and `DELETE ... WHERE 1=0` are refused with "Functionality is not supported"; stored procedures cannot be called ("Invalid Procedure"). It is also a copy about 4 h old. |
| Plex screens (portal) | **Yes** | The Move Container screen (Main Menu > Inventory Management > Inventory Control > Inventory Transactions, `/Inventory/MoveContainer`) moved containers in TEST, checked through the API right after. |

### The screen's request

On Apply, the screen sends one request:

```
POST https://vox.test.on.plex.com/inventory/MoveContainer/ContainerMove?sourceActionKey=11984
{"SerialNo": "84F47G-0003", "Location": "Pre-Weigh Staging", "Putaway": false, "Confirmed": false}

{"ValidationResult": {"Success": true, "Message": "Container 84F47G-0003 was successfully moved.", ...}}
```

The app logs in once with the same Playwright login every screen job uses (`plex_web_export.login`,
about 10 s), hands the cookies to a plain HTTP session and sends that request directly. Without a
session Plex answers HTTP 419; the app then logs in again once.

### What the TEST runs showed

| Case | Result |
|---|---|
| Move through the screen (form + Apply), and back | moved; API showed the new location at once |
| Direct request, and back | 0.47 to 0.53 s each; same answer as the screen |
| Location that does not exist | `Success: false`, "The selected location was not found." (0.19 s) |
| Serial that does not exist | `Success: false`, "Serial No. ZZZ-NOPE-0000 was not found in the system." (0.11 s) |
| Container on **Hold** | **moved without any confirmation.** Plex does not stop it, so the app does: only status OK is moved |
| **LP number** in SerialNo | **the whole pallet moved in one call** ("2 Containers of 12105-01VOXNU-1 were moved to ..."); the containers keep their LP |
| Containers of a pallet moved **one by one** | each moved, but **each left its pallet**: LP-087265's 4 containers lost the LP and the LP record went inactive (`Active=0`). Not restored in TEST (TEST is reloaded from production by Plex) |
| Through the app: 2 suggested containers + 1 bad serial | 2 moved and verified, the bad one refused before any Plex call; the pick line then counted them as staged |
| Through the app: all containers of LP-079411 ticked | moved as the pallet in one call, LP kept; moved back as the pallet |

Every TEST container touched was put back where it was and checked through the API. Containers
used: 84F47G-0003, S040303 (Hold), S026696, S031084, EE8B18-0001/-0002 (LP-079411), and
4829B3-0023/25/26/27 (LP-087265, back in place but no longer on the LP).

## Where each piece of data comes from

| Data | Source | Why |
|---|---|---|
| Job sets, member jobs, per-job BOM | Plex SQL screen (SQL Development Environment's CSV download) through the same web session | Not in the REST API (`/scheduling/v1/job-sets` is a 404); not in our BigQuery raw tables; ODBC needs a driver the app's image does not have. In production it is Plex's reporting copy (about 4 h behind), fine for job sets; in TEST it is live |
| Location groups | Same, `Common_v_Location` + `Common_v_Location_Group`, cached 1 h | Tells Warehouse from Retains, Shipping, Quarantine, ... |
| Containers, lots (best-by), one container | REST API, live | On 11-20 the API had container changes 4 h newer than ODBC, and 1,530 of 65,300 containers were in a different location in the copy |
| The move | Move Container screen's request | The only way (above) |

REST API facts the app relies on (probed 11-20): containers filter by `partId` and `locationId`
(`partNo`, `location` and `masterUnitNo` are ignored and return all ~66,000, 64 MB); lots carry
best-by / use-by / sell-by; parts' `Resource_ID` in Plex SQL equals the API's part id (lower case).
A part number can exist twice (two revisions), so the app always works by id.

## The picking rules (`deploy/picking_app/picking.py`)

- **Which job sets:** those with an open (Scheduled / Production) member job due within N days
  (1 to 14, default 3), or overdue by at most M days (default 14: TEST and production still carry
  October jobs marked Scheduled).
- **Pick lines:** each open job's BOM components, except a component made by another job of the
  same set (the weighed WIP the blend consumes). For a blend set that leaves the raw materials of the
  Pre-Weigh jobs. Required = job quantity x job BOM quantity.
- **Suggested containers (since the 11-23 audit):** first the containers Plex has **allocated to this line's
  job** (the floor stages through job allocations); then OK, unallocated containers already at the line's
  target; then OK, unallocated containers in a **Warehouse** location group (not "R and D", not "DO NOT USE"),
  first-expiring lot first, until the required quantity is covered. Containers that **earlier-due job sets of
  the same ingredient** will use are "reserved", never counted twice (demand netting, `app.net_claims`).
  Shown but not suggested: allocated to another job (`reserved`), allocated to a job Plex's copy does not show
  yet (`blocked`), other groups (`not-here`), other destinations, any other status (`blocked`).
  Details: "Allocations and netting" below.
- **Where to move:** where material used at the line's work center was moved before use (Plex history; "Where
  the team moves material" below), defaulting to the bin where this job's allocated containers already are.
- **Pallets:** if every container of an LP (for that part) is ticked, the LP moves as one and stays
  a pallet. Otherwise each container moves alone and the app says which pallet it left.
- **Before each move** the container is read live: not found, not OK, quantity 0 or already there
  means not moved. **After each move** it is read again and the new location recorded.

The first TEST pick lists, before the location rules, suggested dozens of 0.05-unit retain samples
(R5-3, R and D, Ship, "z**DO NOT USE**"). For one part in TEST the stock sat in: Manufacturing bins
"PW - B9" / "PS - A8" (much of it Lot Hold), Shipping "ODF/SC", Retains "R5-3", and 8 OK containers
(about 200) in warehouse bins. The warehouse-only rule then suggests the 25-unit warehouse containers.

## Who moved it

Plex records every move as the company user **gcp.odbc.vox** ("User, GCP"), because the app logs in
as that user. The app's own log is the only record of which person asked: each attempt, with
`requested_by` (the IAP user when deployed, `PICKING_USER` locally), set, job, serial, from, to,
result, the location read back, and the pallet it left. JSON lines in `PICKING_LOG`
(default `etl-manual/picking_moves.jsonl`); with `PICKING_BQ_LOG=1` also BigQuery
`PlexOps.picking_move_log` (a Terraform table; inserts never create it). Page: `/log`.

## Running it

Local, against Plex TEST (Playwright with Chromium, Flask, requests; the `.env` of the primary
folder gives the Plex login and the API key):

```
pip install -r deploy/picking_app/requirements.txt && python -m playwright install chromium
PLEX_ENV=test PICKING_USER=you python deploy/picking_app/app.py
```

then http://127.0.0.1:8085. The first page takes about 12 s (Plex login and the job-set read); after
that the login is saved in `etl-manual/plex_session_test.json` and reused.

Command line (TEST unless `--prod`, which asks you to type PROD); writes an undo file:

```
python deploy/picking_app/move_cli.py --to "Pre-Weigh Staging" 84F47G-0003 LP-079411
python deploy/picking_app/move_cli.py --undo etl-manual/picking_undo_YYYYMMDD_HHMMSS.json
```

Settings: `PLEX_ENV` (test | prod, default test), `PICKING_ALLOW_PROD_MOVES=1` (needed for any
production move), `PICKING_FROM_GROUPS` (default Warehouse), `PICKING_EXCLUDE_LOCATIONS` (default
"R and D"), `PICKING_SETS_TTL` (job sets, 600 s), `PICKING_LOTS_TTL` (3600 s),
`PICKING_CONTAINERS_TTL` (display only, 60 s), `PICKING_WORKERS` (16), `PICKING_SESSION_GCS`
(where the Plex login is saved), `PICKING_LOG`, `PICKING_BQ_LOG`.

## Speed (second pass, 2026-11-20)

Measured against Plex TEST from a laptop, before and after:

| Step | First version | Now |
|---|---|---|
| First page after a fresh start (Plex login included) | 12 to 15 s | 11.6 s; **about 1 s** when the saved login is reused |
| Open a job set, nothing cached | 24 to 36 s (8 ingredients) | **6.4 s** (8), 6.6 s (15), 9.5 s (26 ingredients) |
| Open it again, or a set with the same ingredients | 24 to 36 s | **0.02 to 0.05 s** |
| Move 2 containers | about 4.4 s | about 6 s, of which 5 s are the two reads of the part's 155 containers; each further container adds about 0.5 s (350 containers: about 3 min, was about 10) |

What changed (`app.py`, `plex_web.py`):
- **Parallel:** every ingredient's containers and lots are fetched at once (16 at a time,
  `PICKING_WORKERS`). They used to be 2 calls per ingredient, one after the other.
- **Caches:** job sets 10 min (Plex's copy is about 4 h behind anyway; a set opened from any cached
  list is found there), location groups and lots 1 h, containers **60 s for display only**.
  A move always reads the part's containers fresh first, so a cached list can never move the wrong
  thing. "reload containers" on a set page skips the cache.
- **Saved Plex login:** after a login the cookies are saved (Cloud Run:
  `gs://voxdatalake-plex-screenshots/picking-app/plex_session_test.json`, private bucket;
  locally `etl-manual/plex_session_test.json`, mode 600, gitignored) and the next instance checks them
  with `SELECT 1` and reuses them. A TEST session is never used for production (the host is stored).
  The cookies ARE a Plex session for gcp.odbc.vox: whoever can read that object can act in Plex as
  that user until the session expires.
- **Moves:** one live read of the part before, the moves (a fully ticked pallet as its LP), one live
  read after to verify. It used to be one read before and one after per container.
- **Keep-warm:** `/warm` checks the Plex session and refreshes the default job-set list (3 days).

Still slow, and from Plex: some parts' container lists take 2 to 3 s in Plex's API.

## Speed (third pass, 2026-11-20 evening): live only, so show the wait

Decision (Emilio): **old data is not acceptable**, so no faster but older source is used. The best
available is to open the page at once and show what is loading.

- **The pick list opens at once** (0.1 to 0.2 s) with each ingredient's header and need, and a loader
  ("Reading live containers from Plex..."). Each ingredient fills in on its own as Plex answers, from
  `/set/<no>/line/<part_id>` (an HTML fragment). The header counts "N of M ingredients" and ends with the
  total time. A failed ingredient shows "Try again" for that ingredient only. `?all=1` renders the
  whole page on the server in one go (the old way; also the link shown when JavaScript is off).
- **One pooled HTTPS session** for the REST API (`requests.Session`, pool 32, `PICKING_API_POOL`) instead
  of a new connection and TLS handshake per call: about 20% faster (set 600: 9-12 s became 7-10 s).
- gunicorn runs 12 threads (was 8), so a 26-ingredient page loads in parallel with room for a move. (40 since the
  11-23 live audit, with Cloud Run `--concurrency=40`.)

Measured in Plex TEST, set 600 (26 ingredients, 3,599 containers), headless browser against a local
server: page open 0.22 s, first ingredient 1.5 to 2.5 s, all 26 in 10 to 11 s. The total is Plex's
time: its API takes about 2.4 s per ingredient on its side. A local browser opens only 6
connections to one server; Cloud Run serves HTTP/2, so there all ingredients are asked at once.

What was measured and set aside (all in TEST, 2026-11-20):

| Angle | Result | Why not |
|---|---|---|
| 32 parallel calls instead of 16 | no faster | Plex caps the calls it serves at once |
| Ask the API for less | not possible | no compression; 16 filter, paging and field parameters (active, status, limit, fields, updatedAfter, ...) are all ignored; every container it returns has quantity > 0 |
| One SQL screen query for all ingredients | 0.5 to 0.9 s, identical containers in TEST | in **production** the SQL screen reads the same copy as ODBC (it froze with ODBC on 11-04; refreshed about every 4 h). In TEST it is live (a move showed 0.2 s later). Old data is not acceptable |
| Copy for candidates + live check of the suggestions | about 3 to 4 s (estimate) | still shows a list built from old data, and misses containers received since the copy |

Can the SQL screen write? **No** (TEST, zero-row statements): UPDATE / DELETE / INSERT / MERGE on a view
or base table and EXEC are refused (HTTP 400); only #temp tables and table variables can be written.

## Live audit and tests (2026-11-23)

Run against the deployed app (revision `picking-app-00002-cfp`, image `8806c7f` = PR #163, Plex TEST),
through IAP in a real Chrome signed in as Emilio. Repeatable with `deploy/picking_app/live_test.py`
(`--login` once, then `--move` to include T6); it writes screenshots and `results.json` to
`etl-manual/picking_live_test/<timestamp>/`.

### Status and audit

| Check | Found |
|---|---|
| Revision serving | `picking-app-00002-cfp`, 100% traffic, image `picking-app:8806c7f` (Cloud Build 7656ded2, SUCCESS). The first deploy attempt built `02c2d03` (folder not yet pulled) and was cancelled |
| Access | IAP on. `iap.httpsResourceAccessor`: Emilio, Jennilyn (`jennilyn.tockstein@`), `plex-etl-sa` (for a future ping). `run.invoker`: only the IAP service agent. Signed out, `/`, `/health` and `/set/600` on both URLs redirect to Google sign-in (302) |
| Settings | 1 vCPU, 2 GiB, max 1 instance, min 0, request-based billing, startup CPU boost on, timeout 300 s, runs as `plex-etl-sa`, Plex login and API key from Secret Manager, `PLEX_ENV=test` |
| Saved Plex login | `gs://voxdatalake-plex-screenshots/picking-app/plex_session_test.json`; the 11-21 one had expired by 11-23, so the first page logged in again (20.7 s) and saved a new one |
| Use since deploy | none before these tests (2 page views on revision 1 on 11-21) |
| Keep-warm ping | none (parked: needs a custom OAuth client) |
| **Bug: Move log page** | the BigQuery read failed (`at` is a reserved word; unquoted in `ORDER BY at`), so `/log` silently showed only the running instance's own file, which is lost on every restart. **Fixed** (`LOG_SQL`, test). Writes to `PlexOps.picking_move_log` were fine |
| **Bug: queueing** | Cloud Run let in 8 requests at a time (`--concurrency=8`, set before the pick list loaded ingredients in parallel). Leaving a 26-ingredient page while it loads left its requests running, and the next page waited about 10 s to OPEN (server time 0.003 s; the rest was Cloud Run holding the request). **Fixed**: `--concurrency=40`, gunicorn 40 threads, and at most 16 Plex API calls in flight per instance (`PICKING_API_PARALLEL`) so Plex is not asked harder than before |
| `/favicon.ico` | 404 on every first visit (cosmetic). Now 204 |

### Test results (2026-11-23, 16:08-16:15 UTC)

| # | Test | Result |
|---|---|---|
| T1 | `/health` (cold instance) | 200 in 1.9 s; env `test` |
| T2 | Job-set list, 7 days | 120 sets in 21.0 s (cold: new instance + fresh Plex login + job-set query) |
| T3 | Set 600 (26 ingredients), fresh | idle: opens 2.3 s, first ingredient 4.4 s, all 26 in 12.5 s; 0 failed, every fragment 200 |
| T3 | Set 600, again within a minute (cached) | opens 0.4 s, all 26 in 0.9 s |
| T4 | Set 221 (4 ingredients), fresh | opens 0.5 s, first 3.3 s, all in 5.6 s |
| T4b | Set 221 right after leaving set 600 mid-load | opened after **10.3 s** (the queueing bug above) |
| T5 | `?all=1` (one-go page, cached) | 0.8 s, 26 ingredients, no loaders |
| T6 | Move: `68GCE8-0401` (lone container, status OK, 2.910) from `103-11C-01` to Pre-Weigh Staging | moved in 11.2 s; app said "successfully moved (now at Pre-Weigh Staging)"; API confirmed |
| T6 | Logged | `PlexOps.picking_move_log`: requested_by `emilio.dominguez@`, set 600, ok, verified Pre-Weigh Staging |
| T6 | Put back (from the laptop, Plex web session) | back at `103-11C-01`, API confirmed. This put-back is in Plex's history only, not in the app's log |
| T7 | Move log page | 0.65 s, shows the move (from the instance file, because of the bug above) |

Still slow, from Plex: about 2.4 s per ingredient in Plex's API (a 26-ingredient set takes about 12 s to
fill in; the page itself opens at once), and a first page after a quiet spell (new instance + Plex
login, about 20 s) until the keep-warm ping exists.

## Where the team's time goes: one container at a time (2026-11-23, corrected by the audit)

Emilio: a page that takes seconds is fine; the team spends **hours** because each container is moved on
its own in Plex's Move Container screen (find it, enter the location, confirm), not in batches.

**Corrected 11-23 (audit 2, finding 3).** The first version of this section counted from
`PlexProd.raw_Part_v_Container`, which keeps only each container's LAST action (2,061 "Container Move" in 30 days,
"at least 34 hours a month", and a daily rise to 701 on 11-20). Plex's full history (`Part_v_Container_Change2`,
TEST copy, same 30 days) shows the real volume:

| Plex history, 30 days to 11-21 | Rows |
|---|---|
| Container Move (one container on the screen) | 17,631, by 57 users |
| Move via Inventory Location Move | 6,093 |
| Picking-type Container Moves (from a Warehouse or Quality Holding location to a work center or Manufacturing bin) | about 8,800 |
| Container Moves per day | 656 to 1,314, by about 21 people, flat (no jump on 11-19 / 11-20) |

At about a minute per screen move (an assumption: **the team should time a few**), the picking-type moves alone
are about **147 hours a month** of screen work, before walking. Evidence queries: `docs/picking_audit_2026-11-23/sql/`
(`h1`, `h2`, `h3`).

What the app does instead: one review and one click per ingredient; a fully ticked pallet moves as one call
(when exactly those containers are on it). On TEST, 7 containers moved and confirmed in 5.8 s and 2 in 3.7 s.
The app saves screen time, not walking.

Next angle, not built: **"Stage the whole set"**, one review for every ingredient of a job set (set 600: 66
suggested containers over 26 ingredients), once the team trusts the per-ingredient flow.

## Demo videos (2026-11-23, third take, after the audit fixes)

Three takes on 11-23. The first showed moves to the "... Staging" locations, which the team does not use; the
second said the PW bins are a stocked buffer, which the audit disproved (the floor stages per job through
allocations). Both were **withdrawn**: removed from the hub, GCS and Emilio's Downloads (to the Trash). The third
take shows the app after the audit fixes. Recorded against a local server on **Plex TEST** running the PR #167 code
(the deployed revision was older), headless Chromium with captions, cursor and click ripples. H.264, 1400×860, no sound.

| File | Length | Size | Shows |
|---|---|---|---|
| `picking-app-1-pick-list-allocations-and-targets.mp4` | 1:39 | 4.0 MB | set 544: job 2305's allocated containers already in PW - B8 count as "there" (default target PW - B8); job 2308's allocated warehouse containers suggested first; targets from Plex history; set 757 showing set 756's containers as "reserved" |
| `picking-app-2-review-and-approve-a-move.mp4` | 1:26 | 2.0 MB | two warehouse containers to PW - B9: review dialog, pallet rule, Cancel vs Approve (reviewer only), moved and confirmed in 5 s, logged when Plex answers |
| `picking-app-3-undo-and-its-limit.mp4` | 1:24 | 0.8 MB | the Move log; "the floor" moves one container on; Undo puts back only the untouched one and shows the other's Plex activity; why the 30-minute limit |
| `picking-app-full-demo-v3.mp4` | 4:29 | 6.7 MB | the three in one |

Where: the hub's **Picking & staging** tab (`videos/`), `~/Downloads/picking-app-videos-2026-11-23-v3/`,
`gs://voxdatalake-plex-screenshots/picking-app/videos/2026-11-23-v3/`. Not in git.

Containers moved while recording (S029901 from 118-08C-01, S029940 from 117-08B-01, S029940 also moved on to
PW - B10 "as the floor") are back at 118-08C-01 and 117-08B-01, read back from the API.

Re-record: start the app on TEST locally (`PLEX_ENV=test python deploy/picking_app/app.py`, port 8085, or any
port) and run `PICKING_URL=http://127.0.0.1:<port> python deploy/picking_app/record_demo.py <dir> 1` (then 2; for 3
write the two serials of video 2 to `<dir>/../serials.json`). Without `PICKING_URL` it records the deployed app
through IAP (`live_test.py --login` first). Trim at the title card (ffmpeg `signalstats`, first frame with
YAVG < 60; look up to 60 s in), encode
`ffmpeg -ss <start> -i in.webm -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -r 25 -movflags +faststart -an out.mp4`,
join with the concat demuxer. Put the containers back afterwards.

## Live tests after the fixes (2026-11-23, revision 00003, image 71794da)

`live_test.py --move`, all passed: health 2.3 s (cold), job-set list 3.6 s (was 21 s cold), set 600 fresh opens
0.6 s and fills in 13.6 s, cached 1.1 s, set 221 11.2 s, `?all=1` 0.8 s, one move 5.4 s (was 11.2 s) and put back,
Move log page 1.2 s and shows it (now read from BigQuery).

## Production, moves off (since 2026-11-23)

Emilio asked to switch the app to production. Redeployed the same image (71794da) with
`PLEX_ENV_FOR_APP=prod ./deploy/picking_app/deploy.sh --no-build`: revision `picking-app-00004-29z`, env
`prod`, `PICKING_ALLOW_PROD_MOVES` **not** set. Checked the same day through IAP: header "PLEX PROD · moves off";
104 job sets due in 3 days; set 221 filled in live in 5.4 s; every "Move to staging" button disabled; a
forced `POST /move` was refused ("Moves are turned off in production"). Plex login for production is saved at
`gs://voxdatalake-plex-screenshots/picking-app/plex_session_prod.json`. IAP access unchanged (Emilio,
Jennilyn). Back to TEST: the same command without `PLEX_ENV_FOR_APP`.

In production the job sets come from the SQL screen, which reads Plex's reporting copy (about 4 h behind):
a job created in the last hours may be missing from the list. Containers are live.

### What the moves have shown, and what they have not

Shown (Plex TEST): every move the app made was re-read live before, sent through Plex's own Move Container
request, and read back after. The log has 9 cloud moves, all confirmed at the target, none wrong, none
breaking a pallet; every demo container was put back. A container is never sent when it is not status
OK, has no quantity, or is already there. Moves run one at a time (one instance, one lock).

Not shown yet, and the reason moves stay off in production:
- **No move has run in production.** TEST is a copy; the production tenant, its permissions for
  gcp.odbc.vox and its location rules are untested.
- **Where staged stock goes is not decided.** Production has Pre-Weigh / Packaging / Quality Released
  Staging, but in the last 30 days only 1 container was moved into a "... Staging" location; the team works
  from the PW-* and PS-* bins (344 single moves into PW bins). Moving stock to a location nobody looks
  at would make it hard to find on the floor, even though Plex knows exactly where it is.
- **Pallets:** a container moved alone leaves its pallet (LP-087265 lost all 4 in TEST on 11-20, by the
  command line, before the app moved whole pallets). The app now moves a fully ticked pallet as one, and
  says when a single move leaves a pallet, but a whole-pallet move has not been run from the cloud app.
- **Who:** Plex records every move as gcp.odbc.vox; only `PlexOps.picking_move_log` knows the person.
- **Undo** is on the Move log since 11-23, for 30 minutes and only for untouched containers (below).

Before `PICKING_ALLOW_PROD_MOVES=1`: (1) the team confirms the targets the app now takes from Plex's history
(PW bins for Pre-Weigh, the line for Bottling / Labeling, machine or CSR rack for Encapsulation; "Where the team
moves material" above), (2) one supervised move of one container in production with
someone on the floor, read back and moved back, (3) one whole pallet the same way, (4) then on, for named
people first.

## Where the team moves material, and the targets the app offers (2026-11-23)

Emilio: "why would we want to move to staging?" We don't. The four "... Staging" locations came from Plex's
location names, not from how the floor works. Plex keeps every container change (`Part_v_Container_Change2`,
location, action, who, when; in the SQL screen, not in our BigQuery copy). For every container **used up** at a
work center ("Retired at <work center>") in the last 45 days, the app looks up where it was last moved before
that (TEST copy, 11-23; history from go-live 10-15):

| Used at | Containers | Last moved to before use |
|---|---|---|
| Pre-Weigh 1 | 1,300 | PW - B9 703, PW - B10 313, PW - B8 262, PW - B7 16 |
| Pre-Weigh 2 | 1,472 | PW - B7 551, PW - B10 360, PW - B8 244, PW - A4 137, PW - B6 97, PW - B9 49, PW - A3 30 |
| Pre-Weigh 3 | 1,640 | PW - B8 556, PW - B9 511, PW - B10 475, PW - B7 95 |
| Encapsulation 1-10 | 1,830 | the machine itself (e.g. Encapsulation 4: 313), or the CSR racks (C4 - CSR 46, C2 - CSR 30, A7 - CSR 14 ...) |
| Bottling 1-6 | 9,181 | the line itself (Bottling 4: 1,439 of 1,447); Packaging Staging 110 in all (corrected by the audit: first version said 7,200 and 106) |
| Labeling 1-7, First 48 | 7,500 | the line itself (Labeling 2: 2,110 of 2,136); Labeling Staging 17 in all |
| Blending 2-5a | 5,600 | mostly never moved (made where it is used); some via PS - B6 / PS - B8 |

Top destinations of all moves in the last 60 days: Quality Released Staging 5,727 (receiving / QA release, almost
all pallets; not picking), Ship 4,372, the Bottling and Labeling lines, PW - B9 1,894, PW - B8 1,535, PW - B10
1,422, PW - B7 1,051.

**What the app does now.** Each pick line's "Move ticked to" list is where material used at that line's work
center was moved before use, most used first, with the count ("PW - B9 · 703 used here"). It uses the job's own
work center when it has 20+ containers of history, else its work center group (jobs often sit on a
"SCHED - ..." placeholder). Putaway, shipping, retains and quarantine locations are left out, and anything under
1%. The four Staging locations stay at the end ("staging (rarely used)"). The server accepts only a target in
that line's list. History is read through the SQL screen (`picking.destinations_sql`), cached 6 h; in
production that is Plex's reporting copy, fine for a 45-day statistic. `PICKING_DEST_DAYS` changes the window.

**Withdrawn 11-23 (audit 2, findings 1 and 2):** this section first said the PW bins are a stocked buffer and the
team "does not stage per job". Both wrong:
- **The floor stages per job through Plex job allocations.** Of 6,193 moves into PW bins in 45 days, 4,389 (71%)
  were containers already **Allocated** at the move; 3,016 had "Added new job allocation" in the 24 h before; only
  695 were status OK. Example: 824DE8-0027 allocated to Pre-Weigh job 1195 at 09:15:43, moved to PW - B8 at 09:15:50.
- **The 1,225 in PW - B9 is one receipt** (49 × 25, Receiving Dock straight to PW - B9 on 11-13) that sets 756-763
  need almost entirely (8 × 147.96 = 1,183.7, all due 11-16).
- The PW bin is **the step before the work center**: for 3,209 of 4,412 containers used at Pre-Weigh, the very last
  move was "Move via Inventory Location Move" into the work center itself. As a target for whoever picks, the bin is
  right; it is not where the material is consumed.

The app now reads allocations and nets demand across job sets ("Allocations and netting" below).

## Allocations and netting (2026-11-23 audit fixes)

**Allocations.** Plex's REST API has no allocation endpoint (tested 11-23: six candidate paths, all 404); it shows
only `containerStatus` = "Allocated", live. Which job a container is allocated to comes from `Part_v_Job_Allocation`
through the SQL screen (`picking.allocations_sql`, cached 60 s, read fresh before any move). In production that is
Plex's reporting copy (about 4 h behind), so:
- allocated to **this line's job**: picked first, or "there" if already at one of the line's destinations (any PW
  bin for Pre-Weigh), and **movable** (status Allocated is moved only in this case);
- allocated to **another job**: "reserved (allocated to job N)", never suggested, refused if ticked;
- live status Allocated but **no allocation row in the copy** (a new allocation): "blocked: allocated to a job
  Plex's copy does not show yet"; move it in Plex.
- The line's default target is the destination where this job's allocated containers already are (set 544, job
  2305: its 199 allocated containers were in PW - B8 while the most used bin is PW - B9; the app had suggested
  moving them bin to bin).

**Netting.** Every open line of the same ingredient in job sets due within 30 days (`PICKING_NET_DAYS`) is
processed in due order (due date, set, job), each at its own default target; the containers an earlier line uses
are "reserved for set N job M (due ...)" on later lines. Checked on TEST: set 756 takes the first 6 containers in
PW - B9, set 757 sees those 6 reserved, set 763 sees 42 reserved; all 8 sets are covered (1,225 against 1,184).

## Review before every move (2026-11-23)

"Review move…" no longer moves anything. It asks the server for a plan (`POST /move/preview`), which reads every
ticked container live from Plex and returns, per container: serial, pallet, lot, quantity, status, from, to and
what will happen (move the container / move the whole pallet LP-x in one call / not moved and why), plus a
warning for each container that would leave its pallet. Nothing is sent to Plex. The page shows it in a dialog:

- **Cancel** (or Escape): nothing moves; the review is logged as cancelled.
- The result names the batch; it can be undone from the **Move log** for 30 minutes if nothing touches it
  ("Undo from the Move log, with a limit" below).
- **Approve: move N**: the server carries out exactly that review (`POST /move` with its id). It reads every
  container live again and **does not move one that changed since the review** (location, status, quantity or
  pallet), or that may not move. A review is valid 10 minutes (`PICKING_PLAN_TTL`) and can be used once.
- The result lists each container with Plex's answer and where it is now, and the **batch id** to undo it.

Tested 11-23 against Plex TEST (local server, real browser): set 756, 12743-01VOXNU-1, two warehouse containers
(S029901 from 118-08C-01, S029940 from 117-08B-01) to PW - B9: dialog correct, Cancel logged, Approve moved both
(924 ms in Plex for the first), then `restore_moves.py` put both back, and a second run found them "already back".

## The move log (since 2026-11-23)

One row per container per event in `PlexOps.picking_move_log` (and the instance's JSON lines file):

| Event | When |
|---|---|
| `preview` | a review was opened (the plan item and the container's full live record) |
| `cancelled` | the review was cancelled |
| `sent` | Plex answered the move request (logged that instant, before the read-back: audit 1, finding 3) |
| `move` | read back after the move (ok = Plex said success and the container is at the target) |
| `refused` | approved but not sent (changed since the review, not OK, pallet changed, ...) |
| `refused-gate` | refused before anything: production moves off, or the sign-in could not be verified |
| `undo-review` | someone opened Undo or Activity on the Move log (per container: can undo, or why not, and the activity since) |
| `restore` | put back by Undo on the Move log (or by Claude with `restore_moves.py`) |

Columns added 11-23 (Terraform): `event`, `batch_id`, `part_id`, `part_no`, `lp_before`, `status_before`,
`qty_before`, `before_json` / `after_json` (the container's full API record before and after), `plan_json`,
`plex_request` (the exact payload sent), `plex_response` (Plex's raw answer), `plex_status`, `plex_ms`,
`user_agent`, `revision`. The app inserts with `ignore_unknown_values`, so an insert never fails on a missing column,
but **without the columns the detail is dropped and undo finds no batches**: Terraform (`./scripts/deploy.sh`) must
run first, and `deploy/picking_app/deploy.sh` refuses to deploy until `batch_id` exists (audit 3, finding 3). Rows before 11-23 have `event` NULL (moves).

Useful queries:

```sql
SELECT `at`, requested_by, event, batch_id, serial, moved_as, from_location, to_location, ok, verified_location, message
FROM `voxdatalake.PlexOps.picking_move_log` WHERE DATE(`at`) = CURRENT_DATE() ORDER BY `at` DESC;

SELECT batch_id, requested_by, MIN(`at`) at, COUNTIF(event = 'move') moved, COUNTIF(event = 'move' AND NOT ok) failed,
       COUNTIF(event = 'refused') refused, ANY_VALUE(to_location) to_location
FROM `voxdatalake.PlexOps.picking_move_log` WHERE event IN ('move', 'refused') GROUP BY 1, 2 ORDER BY at DESC;
```

## Undo from the Move log, with a limit (2026-11-23)

Emilio: restoring should not be a command for the team; it belongs in the log, with a limit, and when the
containers have had more activity, show that activity instead, because restoring then would be a nightmare.

**The evidence.** Plex history (TEST copy, 45 days to 11-21): after a move, the next Plex change on the same
container came within

| Moved to | Moves | 5 min | 15 min | 30 min | 1 h | 4 h | 24 h | never |
|---|---|---|---|---|---|---|---|---|
| Bottling lines | 13,139 | 17% | 23% | 29% | 37% | 58% | 79% | 5% |
| Labeling lines | 9,379 | 20% | 29% | 41% | 49% | 73% | 92% | 3% |
| Encapsulation / CSR | 5,654 | 26% | 28% | 29% | 30% | 32% | 35% | 21% |
| PW bins (Pre-Weigh) | 6,185 | 2% | 4% | 6% | 8% | 14% | 50% | 6% |

The next action is real floor work: after a move to a PW bin, "Move via Inventory Location Move" 3,108, Mass
Update 877, Loaded to Workcenter 669, job allocations, pallet changes; after a move to a Bottling line, Loaded to
Workcenter 5,467, pallet moves 3,913, Unload during setup change 410, Remove from Master Unit 387. Putting such a
container back would undo that work and leave Plex's records of it (loaded to a work center, allocated to a job,
on a pallet) out of step with where the container is.

**The rule.** On the Move log (one row per approved batch):

- **Undo…** is shown for **30 minutes** after the move (`PICKING_UNDO_MINUTES`). It reads Plex first and moves
  nothing. A container can be put back only if it is **exactly as we left it**: its live record (location,
  quantity, status, pallet) equals the record read right after our move, **and** Plex's history shows no change
  since other than our own move. On Approve each one is read live again; one that changed meanwhile stays.
  A whole pallet that is still together goes back in one call.
- Anything else (touched since, or older than 30 minutes) is **not** put back. The dialog shows, per container,
  the **activity since the move** from Plex's history (`Part_v_Container_Change2`): when (MT), the Plex action,
  location, quantity, status, pallet (LP number) and who (name and Plex user ID). After 30 minutes the button is
  **Activity**: the same view, no undo.
- A container that **left its pallet** when moved is put back in its location but not on the pallet (Plex's Add
  to Master Unit screen); the dialog and the result say so.
- Every step is logged: `undo-review` (per container: can undo, or why not, with the activity) and `restore`
  (Plex's request and answer, where it is now), batch `restore-<batch>`.
- Production caveat: Plex history in production comes from Plex's reporting copy (about 4 h behind). The live
  check is current, so a location, quantity, status or pallet change is never missed; activity that changes none
  of those (a job allocation) may not show yet. The 30-minute window keeps that case rare.

Tested 11-23 against Plex TEST (local server, real browser): two containers moved to PW - B9; one then moved on to
PW - B10 "as the floor"; Undo offered 1: S029940 "not put back: location is now PW - B10 (was PW - B9 right after
our move); 1 change(s) in Plex since our move", with that change listed (time, Container Move, PW - B10, 24.6771,
GCP User (gcp.odbc.vox)); S029901 put back to 118-08C-01 and confirmed. Plex history times are US Eastern
(`PLEX_TZ`); our 19:10:12 UTC move appears as 14:10:10.

**For Claude (not the team):** `deploy/picking_app/restore_moves.py` remains as an admin tool for a case the
page will not undo (`--batch`, `--serial`, dry run unless `--apply`, `--force` for containers moved again, `--prod`
asks to type RESTORE). Use it only after reading the container's activity with the team: forcing a container back
that the floor has loaded or allocated is exactly what the page refuses to do.

## Move safety after the audit (2026-11-23)

Fixes from [PICKING_AUDIT_2026-11-23.md](PICKING_AUDIT_2026-11-23.md), each with a regression test in
`tests/test_picking_app.py` (`test_audit*`):

- **Pallets are read whole.** Before a pallet is sent as one move, the app reads every container on it live (any
  part, any quantity, from the pallet's location). It is sent whole only when exactly the ticked containers are on
  it; otherwise the ticked ones go one by one, each flagged "leaves pallet", and the dialog names the others
  (finding 2). On Approve the membership is read again; if it changed, the pallet is not sent (finding 2).
- **Undo never sends a pallet carrying a container that failed its check**, nor one that gained containers: a
  pallet goes back whole only if every container we moved on it qualifies and it holds exactly those; otherwise
  the qualifying ones go back one by one (finding 1). Undo re-reads Plex's history at Approve (finding 19).
- **Every Plex move is logged the moment Plex answers** (`sent`), then again after the read-back (`move`); a failed
  read-back or a restart can no longer lose a move, and a move Plex confirmed stays undoable (findings 3, 11).
- **Only the person who opened a review can approve it** (moves and undo, finding 16).
- **Form tokens (CSRF) on every POST, escaped error page, security headers (CSP, no framing)** (finding 4).
- **The sign-in is verified**: with `PICKING_IAP_REQUIRED=1` (set by `deploy.sh`) the IAP JWT is checked
  (`X-Goog-IAP-JWT-Assertion`, Google's IAP keys, issuer `https://cloud.google.com/iap`, audience when
  `PICKING_IAP_AUDIENCE` is set); without a valid one the person is "unverified" and nothing moves (finding 24).
- **A ticked serial must belong to the line's part** (finding 23); serials are fully URL-encoded for the API
  (finding 25); `days` / `overdue` are bounded (finding 26); the plan store is locked (finding 20); result
  messages are capped at 12 lines plus a pointer to the Move log (finding 21).
- **Our own "Remove from Master Unit"** (Plex writes it a second before moving a container off its pallet) is not
  counted as outside activity, so such a container can still be undone (finding 12).
- **The move log is backed up daily** (milestone backups, `Backups.PlexOps__picking_move_log_<date>`), refused
  production-gate attempts are logged, and laptop tools log `restore_moves.py (laptop user ...)` (finding 13).
- **Container image**: pinned Python dependencies, runs as the image's `pwuser`, not root (finding 27).

Browser automation (`live_test.py`, `record_demo.py`) opens pages with `bypass_csp`, because the app's CSP blocks
Playwright's in-page waits; the app itself keeps the CSP.

Checked against Plex TEST after the fixes (local server, real browser): sets 756 / 757 / 763 netted (6, then 6
reserved, then 42 reserved); set 544's allocated containers "there" in PW - B8 and job 2308's 53 allocated
warehouse containers suggested; a full review, approve, "floor" move and undo cycle with form tokens; 35 tests pass.

## Cost (Cloud Run, pay per use)

The team should not pay for an always-on instance. Options looked at (Google list prices, by hand;
check against the bill after the first month):

| Option | About a month | Speed |
|---|---|---|
| A. One instance always on | $55 to 60 | always instant |
| B. Warm in working hours only (scheduled min-instances) | about $20 | instant in hours, about 15 s first click outside |
| **C. Pay per use + keep-warm ping in working hours (chosen; ping not running yet, below)** | **about $1** | instant in hours; outside hours a cold start, usually without a new Plex login |
| D. Pay per use, no ping | under $1 | a wait after every quiet spell |

C in numbers: request-based billing charges only while a request runs. The ping (every 10 min,
weekdays 6:00 to 17:50 Mountain, about 1 s each) is about 1,600 s a month; a team's clicks are
perhaps 10,000 to 20,000 s. At 1 vCPU and 2 GiB that is well under $1, plus the scheduler job
($0.10; the project's 3 free scheduler jobs are used) and the image in Artifact Registry (about
$0.15). Our Cloud Run jobs already use the free tier, so none of this is free. Cloud Run can still
retire an idle instance between pings; the next click then waits a few seconds (container start),
plus about 10 s only if the saved Plex session has also expired. Switching to B later is one flag
(`--min-instances=1` with a scheduler that sets it back to 0 at night).

## Deploying

**Deployed 2026-11-20** (build a339ae8): https://picking-app-651304971296.us-central1.run.app, Plex TEST,
open to Emilio (`emilio.dominguez@`) and Jennilyn (`jennilyn.tockstein@`; `jennilyntockstein@` is a
mail alias, and IAP answers "User ... does not exist" for it). First page, cold, fresh Plex login: 18 s.

Steps, from the primary folder on a clean `main`:

1. `./scripts/deploy.sh` (Terraform): the IAP API (`iap.googleapis.com`) and `PlexOps.picking_move_log`.
   Cloud Run's built-in IAP is not in the pinned google provider (~> 5.40), so the service itself is
   deployed with gcloud, like the Cloud Functions.
2. `./deploy/picking_app/deploy.sh --access user:<email> ...` builds the image
   (`deploy/picking_app/cloudbuild.yaml`, `plex-pipeline/picking-app:<sha>`, about 3.5 min) and deploys:
   - `PLEX_ENV_FOR_APP=test` or `=prod` is **required** (11-23: a plain redeploy used to switch production back to
     TEST silently);
   - refuses unless `PlexOps.picking_move_log` has the 11-23 columns (Terraform first);
   - runs as `picking-app-sa` once an admin has created it (the script prints the commands: the four Plex secrets
     plus `picking-app-secret`, insert on the log table, jobUser, objectAdmin on `picking-app/` only), else
     `plex-etl-sa` (audit 3, finding 8: that account reads every secret and edits all of BigQuery);
   - `--iap --no-allow-unauthenticated`, 1 vCPU, 2 GiB (Chromium for the login), 40 requests at a time, at most
     1 instance, scaled to zero, request-based billing;
   - `PICKING_IAP_REQUIRED=1`: a request without a valid IAP JWT is "unverified" and cannot move; a fixed Flask
     secret from `picking-app-secret` when it exists (form tokens survive restarts);
   - moves logged to BigQuery (`PICKING_BQ_LOG=1`), the saved session in GCS.
3. **An admin pastes the access commands the script prints.** `claude-operator` may deploy the
   service but not set its IAM (`run.services.setIamPolicy` and the IAP policy are refused): the IAP
   service agent's `run.invoker`, and `roles/iap.httpsResourceAccessor` for each person.
4. Open the URL and sign in with a company Google account. `/log` reads the BigQuery log.

**The keep-warm ping is not running.** The scheduler `picking-app-warm` was created and got HTTP 401
from IAP every time (audience the service URL, either form): Cloud Run's built-in IAP uses a
Google-managed OAuth client, which signs people in through a browser but does not accept a service
account's OIDC token. It was deleted the same evening (a failing scheduler would alert the watchdog).
To turn it on: create a custom OAuth client for IAP in the console (APIs & Services, Credentials),
set it on the service's IAP settings, then `WARM_AUDIENCE=<client id> ./deploy/picking_app/deploy.sh`
(it grants the ETL service account IAP access and creates the scheduler). Until then the app is
option D with a saved login: the first click after a quiet spell waits for a container start, plus
about 10 s if the saved Plex session has expired.

Not done yet, before production:
- The team confirms the targets from Plex history (PW bins for Pre-Weigh, the line for Bottling / Labeling,
  machine or CSR rack for Encapsulation), that allocated containers are what they pick, and whether Lot Hold
  stock is ever picked.
- An admin creates `picking-app-sa` and `picking-app-secret` (commands printed by `deploy.sh`) and a lifecycle
  rule on the saved session (`gs://voxdatalake-plex-screenshots/picking-app/`, audit 3, finding 6).
- **A Plex user of its own.** The app logs in as gcp.odbc.vox, the same user as the screens job, and
  two logins as one user can end each other's session (`docs/PLEX_SCREEN_EXTRACTION.md`). A user
  for the app also makes Plex's own history show who moved it.
- Ask Plex whether a container move API exists for our subscription; if so, swap `PlexWeb.move`.
- Production with moves off was done 11-23 and reverted to TEST for the audit fixes. Next time:
  `PLEX_ENV_FOR_APP=prod ./deploy/picking_app/deploy.sh`, then `PICKING_ALLOW_PROD_MOVES=1` (an env var on the
  service, settable by anyone with run.services.update: audit 3, finding 5) after a supervised first run.

## Open questions for the team

- Do the history-based targets match how you work (PW bins, the line, CSR racks)? Should a bin be chosen per job?
- Are containers allocated to the job always the ones you pick? What when Plex has no allocation yet?
- Time a few screen moves: the time-saving estimate assumes about a minute each.
- Lot Hold stock: never picked (current rule), or pickable for some cases?
- Units: job quantities and container quantities are compared as they are; Plex shows no unit on
  many parts (`Part_v_Part.Unit` empty), so check a few lines by hand before trusting the totals.
- 189 open jobs due within ±14 days have an operation with no work center; their lines get only the Staging
  targets (audit 2, finding 6).
