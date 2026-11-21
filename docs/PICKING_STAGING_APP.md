# Picking & staging app (2026-11-20)

Jennilyn asked on 2026-11-20 for "a simple web interface that pulls inventory and the job schedule"
so the Vox team can pick and stage scheduled jobs, which takes them hours in Plex today. This is
that app: code in `deploy/picking_app/`, tests in `tests/test_picking_app.py`, tested end to end
against **Plex TEST** on 11-20. It runs on Cloud Run (service `picking-app`, company Google sign-in,
Plex TEST) once deployed with `deploy/picking_app/deploy.sh`; it has never moved anything in production.

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
- **Suggested containers:** status OK, quantity above 0, in a **Warehouse** location group, not in
  "R and D" (Warehouse group, but 0.1-unit samples), not in a location named "DO NOT USE", not already
  in a staging location; first-expiring lot first (lot best-by, then oldest container) until the
  required quantity is covered. Containers already in the target count as staged.
  Shown but not suggested: other groups (`not-here`, with the group), other staging locations,
  and any status but OK (`blocked`).
- **Where to stage:** by the job's workcenter group: Pre-Weigh and Blending to "Pre-Weigh Staging",
  Encapsulating / Bottling / Packaging to "Packaging Staging", Labeling to "Labeling Staging". The
  person can pick another staging location. **To confirm with the team.**
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
`PlexOps.picking_move_log` (created on first use). Page: `/log`.

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
- gunicorn runs 12 threads (was 8), so a 26-ingredient page loads in parallel with room for a move.

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
   - runs as `plex-etl-sa`, with the Plex login and API key from Secret Manager
     (`plex-portal-username` / `-password`, `plex-api-consumer-key` / `-secret`);
   - `--iap --no-allow-unauthenticated`, 1 vCPU, 2 GiB (Chromium for the login), 8 requests at a
     time, at most 1 instance, scaled to zero, request-based billing;
   - `PLEX_ENV=test`, moves logged to BigQuery (`PICKING_BQ_LOG=1`), the saved session in GCS.
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
- The team confirms the staging map, the pick-from rule (are "PW - *" / "PS - *" Manufacturing bins
  already staged?) and whether Lot Hold stock is ever picked.
- **A Plex user of its own.** The app logs in as gcp.odbc.vox, the same user as the screens job, and
  two logins as one user can end each other's session (`docs/PLEX_SCREEN_EXTRACTION.md`). A user
  for the app also makes Plex's own history show who moved it.
- Ask Plex whether a container move API exists for our subscription; if so, swap `PlexWeb.move`.
- `PLEX_ENV_FOR_APP=prod ./deploy/picking_app/deploy.sh` with moves off, then on with
  `PICKING_ALLOW_PROD_MOVES=1` (an env var on the service) after a supervised first run.

## Open questions for the team

- Staging locations per workcenter group (the map above).
- Are the Manufacturing bins ("PW - B9", "PS - A8") already staged for Pre-Weigh, or picked from?
- Lot Hold stock: never picked (current rule), or pickable for some cases?
- Units: job quantities and container quantities are compared as they are; Plex shows no unit on
  many parts (`Part_v_Part.Unit` empty), so check a few lines by hand before trusting the totals.
- Four staging locations are typed Storage; Plex's own Staging location type is unused. Retyping
  them would let any report tell staging from storage.
