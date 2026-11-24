# Picking app audit, 2026-11-23

Three independent audits of the picking & staging app (`deploy/picking_app/`, branch dev-picking at 74d0339 =
PR #167), each run by a separate Claude Opus agent at high effort, read-only (no moves, no deploys, no
production Plex). Requested by Emilio after the review dialog and undo were built.

- **Audit 1: move, review and undo correctness.** Unit tests plus 5 repro tests with fakes:
  [picking_audit_2026-11-23/repro_tests_audit1.py](picking_audit_2026-11-23/repro_tests_audit1.py). These tests
  PROVE the bugs, so they fail once the bugs are fixed. Kept as a record, not in `tests/`.
- **Audit 2: data and business logic.** SELECT queries on Plex TEST's SQL screen plus BigQuery. Queries are in
  [picking_audit_2026-11-23/sql/](picking_audit_2026-11-23/sql/), named as in the report (d3, h1, ...).
- **Audit 3: security, operations, docs.** Live Cloud Run, IAM and BigQuery read as claude-readonly.

Status column (updated with the fix PR, same day): what was done about each finding, in the fix PR that follows this file ("Fix" = fixed and
tested; "Ops" = needs an admin or a deploy; "Doc" = docs corrected; "Open" = not done, with the reason).

## Summary, ranked

| # | Sev. | Finding | Audit | Status |
|---|---|---|---|---|
| 1 | Critical | Undo sends a whole LP back, carrying a container the review said it would NOT put back, and does not log it | 1 | Fix |
| 2 | High | Approve sends an LP without checking what is on it now: containers added after the review, other parts' (even Hold) containers ride along unlogged | 1 | Fix |
| 3 | High | A move Plex made can end with no log row (logging only after all moves and read-backs; a read-back error or restart loses the batch) | 1 | Fix |
| 4 | High | Reflected XSS on the `/set/<x>/line/<y>` 404 page lets a crafted link run review + approve as the victim | 1, 3 | Fix |
| 5 | Critical | The floor stages per job through Plex job allocations: 71% of containers moved into PW bins were status Allocated at the move; the app refuses Allocated and ignores allocations | 2 | Fix |
| 6 | Critical | "PW - B9 holds 1,225 against 148" counts one receipt that 8 job sets (756-763) need almost entirely; per-line "all there" double counts; the buffer/replenishment conclusion is wrong | 2 | Fix + Doc |
| 7 | High | Time estimate from the last-action snapshot: full history has 17,631 Container Moves / 30 days by 57 users (~8,800 picking-type, ~147 h/month at 1 min), daily trend was an artifact | 2 | Doc |
| 8 | High | App runs as `plex-etl-sa` (all secrets, project BigQuery editor, run.invoker, bucket objectAdmin) | 3 | Ops |
| 9 | High | Log table has 13 columns live; #166's 18 new ones not applied; deploying #167 first breaks undo and drops the audit detail silently | 3 | Ops + Fix (deploy guard) |
| 10 | Medium | Pallet split after a refusal: no "leaves pallet" warning, `left_pallet` null | 1 | Fix |
| 11 | Medium | A move Plex made but read back wrong (`ok=false`) can never be undone | 1 | Fix |
| 12 | Medium | Undo would refuse every container moved off a pallet (Plex logs "Remove from Master Unit" just before the move; counted as outside activity) | 2 | Fix |
| 13 | Medium | Move log is editable by ETL jobs and Editors, not backed up; refused prod-gate attempts not logged; laptop tools log `$USER` | 3 | Fix (backup, refused log) + Open (append-only sink) |
| 14 | Medium | Prod gate is one env var; CLIs `--prod` skip the app gate; plain `deploy.sh` silently switches prod -> TEST | 3 | Fix (deploy.sh needs PLEX_ENV_FOR_APP) + Open (alert on service changes, allowlist) |
| 15 | Medium | Saved Plex session in GCS readable by Editors and plex-etl-sa, never expires | 3 | Ops |
| 16 | Medium | Any IAP user can approve anyone's review or undo | 1, 3 | Fix |
| 17 | Medium | The two "move" action lists disagree (`destinations_sql` vs `undo.MOVE_ACTIONS`); PW bin is the step before the work center ("Move via Inventory Location Move") | 2 | Fix + Doc |
| 18 | Medium | 189 open jobs have an operation with no work center: only Staging targets | 2 | Open (shown; team) |
| 19 | Low | Undo apply reuses the history read at review (up to 10 min old) | 1 | Fix |
| 20 | Low | `_plans` pruned without a lock (possible 500); cancel on an undo plan raises KeyError | 1 | Fix |
| 21 | Low | Large batches overflow the flash cookie (results lost) | 1 | Fix (capped at 12 lines + pointer) |
| 22 | Low | `set.html` title block holds a copy of the dialog | 1, 3 | Fix |
| 23 | Low | A ticked serial is not checked to belong to the line's part | 1 | Fix |
| 24 | Low | `who()` trusts the unsigned IAP email header (safe only while IAP is on); plex-etl-sa still has IAP access | 3 | Fix (JWT check when present) + Ops |
| 25 | Low | Plex API serial path not fully encoded (`../`) | 3 | Fix |
| 26 | Low | `days` / `overdue` unbounded; cache never shrinks | 3 | Fix |
| 27 | Low | Unpinned google-cloud deps, base image by tag, runs as root | 3 | Fix (pins, non-root) + Open (image digest) |
| 28 | Low | Component on two operations of one job dropped once; no netting of material already used on Production jobs; never-moved Blending containers dropped from destinations | 2 | Open (documented) |
| 29 | Low | Daylight-saving fall-back hour ambiguous in history times | 1, 2 | Open (documented) |
| 30 | Doc | Five files disagree on prod vs TEST after #167; stale Staging map, "12 threads", "8 requests", "created on first use", "works before and after Terraform"; hub says "recorded on the deployed app"; two counts not reproduced (Packaging Staging 110 not 106; Bottling 1-6 9,181 not 7,200) | 2, 3 | Doc |

Confirmed sound by the audits: quantities and units (all 2,170 active BOM lines on open jobs have conversion 1),
job-set logic, the work-center join (all 40 "Retired at" texts match a Workcenter_Code), Plex history time zone
(America/New_York with DST; app moves 16:12:24 UTC = 11:12:22 and 19:10:23 UTC = 14:10:23 Plex), single-use
plans, expiry, the prod gate on preview/move/undo, live re-check before every move, `_move_lock`, no double
move from retries, Jinja autoescaping, `history_sql` quoting, parameterized BigQuery in `restore_moves.py`, IAP
(only the IAP agent holds run.invoker), secrets from Secret Manager, cost (about $1 a month). The Pre-Weigh
destination table and the "next change after a move" table reproduced exactly.

## Audit 1: move, review and undo correctness (full report)

**1. CRITICAL: undo moves a container it just said it will not put back.** `app.py:559-560`, `restore_moves.py:99`.
`undo_apply` passes only rows that passed the check (`ok_rows`) to `plan_restore`, which sends the LP when
`len(ready) == len(rs)`, where `rs` is only those rows. Scenario: batch moved LP-1 (A, B); B then partly used
(qty 5 -> 2) but still on LP-1 at the target. Review: "A: can put back, B: not put back". Approve sends `LP-1`, so
B goes back too, and only A gets a `restore` row. Repro: `moves: [('LP-1', '103')] B now at: 103`,
`restore rows logged: ['A']`. It also takes back any container added to LP-1 after our move. Fix: send the LP only
if every original row with that `moved_as` passed and the LP's live membership is exactly the logged set; else
per container or refuse.

**2. HIGH: approve can move containers nobody reviewed.** `app.py:426-436`, `picking.py:244-266`. An LP item is sent
after checking only the containers it covers. Containers added to the LP between review and approve are not
detected (A's and B's `masterUnitNo` unchanged). Repro: Z added to LP-1 after review; approve sends LP-1; Z
moves with no log row. By design the same for other parts' containers on the LP (including Hold) and
zero-quantity members. Fix: before sending an LP, read every container on it and require exactly the reviewed set.

**3. HIGH: a Plex move can be left with no log row.** `app.py:423-450`. All logging after the lock, after every
move and read-back. If the verify read raises (API 5xx after retries) or the instance dies, the batch is moved
and nothing logged: no undo, no record of who asked. Repro: `status: 500 moves: ['A'] events: ['preview']`.
`undo_apply` same (line 567). `log_move` writes the file first and raises on I/O errors. Fix: log each move right
after `move_detail`, update after verify; wrap read-backs.

**4. MEDIUM (raised to High with audit 3): reflected XSS -> arbitrary moves.** `app.py:284` returns
`f"...job set {set_no}.</div>"` unescaped as text/html. `/set/<img src=x onerror=alert(1)>/line/x` comes back with
the tag. Same-origin script can call `/move/preview`, read `plan_id`, POST `/move`, which defeats the plan-id
protection against CSRF. Fix: escape or render a template.

**5. MEDIUM: pallet split after a refusal gives no "leaves pallet" warning.** `app.py:343-351`. When a fully ticked
LP has a member that may not move, the others go one by one, and `breaks_pallet(item, req["serials"], ...)` is
None because all mates were ticked. Repro: B on LP-1 to Hold -> items `[('A', None), (None, None)]`. Approve
(line 446) same. Fix: compute `left_pallet` against the set actually sent.

**6. MEDIUM: a move Plex made but read back wrong can never be undone.** `app.py:444`, `497-498`,
`restore_moves.py:55`. `ok` requires read-back = target; a Plex success with lagging read-back or a client
timeout after Plex processed is `ok=false`, and undo / restore drop such rows. Fix: treat `plex_status == 200`
plus a Plex success message as moved for undo eligibility.

Risks: undo apply reuses review-time history (`app.py:558`); DST fall-back hour (`undo.py:50`); "our own move"
matched within 120 s of the log time written after the batch (`undo.py:74-76`); `_plans` iterated without a lock
(`app.py:366`); `move_cancel` with an undo plan raises `KeyError 'serials'`; `plan["by"]` never checked; flash
results in the session cookie (>4 KB lost); `set.html` title block holds a copy of the dialog; `a.quantity`
unescaped in log.html (numeric via `_num`); `_check_request` does not check a serial belongs to `part_id`.

Checked and sound: single use (`dict.pop` atomic), expiry on approve and undo, prod gate in preview / move / undo,
`_move_lock`, live re-check compares location / status / quantity / pallet with matching types, a second plan for
the same container refused, no double move from retries (`move_detail` never raises, `_post` retries only an
expired session, the API client retries only GETs), env check, 30-min window re-checked, already-back skipped,
`history_sql` quoting, `restore_moves` import works in the image, Jinja and `esc()` escaping, partial pallets with
a Hold member moved container by container with the warning.

## Audit 2: data and business logic (full report)

**1. CRITICAL: the team does stage per job, and the app ignores Plex job allocations.** 6,193 moves into `PW - %`
bins in 45 days (`d3`): at the moment of the move 4,389 (71%) had status **Allocated**, 3,016 had "Added new job
allocation" in the 24 h before; only 695 were OK. Example: 824DE8-0027 allocated to Pre-Weigh job 1195 at 09:15:43,
moved to PW - B8 at 09:15:50. `MOVABLE_STATUSES={"OK"}` blocks exactly what the floor picks and suggests OK
containers that may not be the allocated ones. Fix: read allocations; Allocated-to-this-job = pickable or staged.

**2. CRITICAL: "1,225 vs need 148" counts stock meant for other sets.** The 1,225 is one receipt (49 × 25) from
Receiving Dock straight to PW - B9 on 11-13, Lot Hold 11-19, released 11-20 (`d1`, `d2`, `d4`). Sets 756-763 each
need 147.96 of 12743-01VOXNU-1, all due 11-16: 1,183.7 in all. Set 641 needs 4,144.73 more by 11-27 against about
1,092 in Warehouse. `suggest()` judges each line alone: all 8 sets show "all there", and lines in different sets
can be offered the same containers. Fix: net demand per part across all open lines; withdraw the buffer narrative.

**3. HIGH: "at least 34 hours a month" is far below the real volume.** The 2,061 is from `raw_Part_v_Container`
(last action only; BigQuery gives 1,983). Plex's history: 17,631 Container Move rows by 57 users in the same 30
days, plus 6,093 "Move via Inventory Location Move" (`h2`); about 8,800 picking-type (Warehouse or Quality Holding
to a work center or Manufacturing bin, `h1`), so about 147 h/month at 1 minute (untimed; screen time only). The
daily "41-162 rising to 331 / 701" was a snapshot artifact: real 656-1,314 a day by about 21 people, flat (`h3`).

**4. MEDIUM: the move filter skips the real last move.** `destinations_sql` counts only Container Move / Master Unit
Move (`b3`). Pre-Weigh: 3,209 of 4,412 retired containers were last moved by "Move via Inventory Location Move"
into the work center itself, so the PW bin is the step before (still a plausible pick target). Labeling: 3,660
last moves are "Master Unit Moved" (pallet to Label Complete), skipped by the app but counted by
`undo.MOVE_ACTIONS`. Fix: describe PW bins as feeding the work center; align the two lists.

**5. MEDIUM: undo will probably refuse every container that left a pallet.** A single move off a pallet logs
"Remove from Master Unit" about 1 s before the "Container Move"; `activity_since` counts it. Untested (TEST was
refreshed; the 11-20 rows are gone).

**6. MEDIUM: 189 open jobs due within ±14 days have an operation with no work center** (a Printing job has no history
either): only the four Staging targets.

Low: a component on two operations of one job is dropped by `seen` (`c6`, job 3059-1 only); Production-status
jobs not netted for material already used; partly used containers excluded from history (4-9% per group, `b6`);
4,292 never-moved Blending containers dropped.

Confirmed: the work-center join (`b1`, `b2`); units (`c5`); 720 × 0.2055 = 147.96 for set 756; sibling-WIP logic;
time zone America/New_York with DST (REST `updateDateTime` UTC-4 on 10-21…10-24, UTC-5 on 11-18/19); the 30-min
window. Reproduced exactly: the Pre-Weigh table, PW-bin next-change table; within 2 points: Bottling and Labeling
next-change. Not reproduced: Packaging Staging 110 (doc 106), Bottling 1-6 9,181 (doc 7,200).

## Audit 3: security, operations, docs (full report)

**HIGH 1. Reflected XSS -> moves as the victim** (`app.py:284`; as audit 1 #4). Also add CSRF tokens and a CSP.

**HIGH 2. Runs as `plex-etl-sa`**: project-wide secretAccessor (every secret), bigquery.dataEditor, run.invoker, the
custom `plexEtlRunWithOverrides`, objectAdmin on the whole screenshots bucket. Fix: `picking-app-sa` with the 4
secrets, insert on `picking_move_log`, jobUser, objectAdmin on `picking-app/` by condition.

**HIGH 3. Live log table has 13 columns, the app writes 31 and drops the rest silently** (`ignore_unknown_values`).
Deploying #167 before `./scripts/deploy.sh`: undo finds no batches, `restore_moves.py --batch` fails, audit detail
lost. Fix: Terraform first; `deploy.sh` refuses unless `batch_id` exists.

**MEDIUM 4. Move log mutable and not backed up**: editable by plex-etl-sa (31 ETL jobs), Editors, dataset
projectWriters; in no backup list; BigQuery insert failure leaves only `/tmp`; prod-gate refusals not logged
(18:38:52 POST /move on 00004 left no row); laptop tools log `requested_by=$USER` ("parasol"). Fix: daily
snapshot, append-only sink, log refusals.

**MEDIUM 5. Prod gate is one env var** (anyone with run.services.update); `move_cli.py --prod` and
`restore_moves.py --prod` skip it (type PROD / RESTORE); plain `deploy.sh` defaults TEST. Fix: alert on service
changes, named-user allowlist.

**MEDIUM 6. Saved Plex session in GCS** (`plex_session_prod.json`) readable by Owners, Editors, plex-etl-sa; no
expiry. Fix: lifecycle rule or Secret Manager.

**MEDIUM 7. Every IAP user can do everything**; `plan["by"]` never checked.

Low: `who()` trusts unsigned `X-Goog-Authenticated-User-Email` (not bypassable today; verify the IAP JWT);
plex-etl-sa still has IAP access (parked ping); `set.html` lines 2-68 duplicate 106-172 inside the title block;
`api.container` quotes with `/` safe; `days` / `overdue` unbounded and the cache never shrinks; unpinned google-cloud
deps, base image by tag, root; service `maxScale: 20` (revision limit 1 holds); stored emails and user agents
readable by project-wide dataViewers; `etl-manual/picking_live_profile/` holds Emilio's Google sign-in (gitignored).

Doc inconsistencies: prod vs TEST after #167 (CHANGELOG #166 vs #167 entries, OPEN_ITEMS:40, CLAUDE.md:497,
DISASTER_RECOVERY.md:19); PICKING_STAGING_APP.md :6-7 "once deployed", :92-94 Staging map "to confirm", :182 "12
threads", :517 "8 requests", :112 "created on first use", :416 "works before and after the Terraform change",
:538-551 "Not done yet" and Open questions stale; picking_tab.py :59 "against Plex TEST since 2026-11-20", :41
"Recorded on the deployed app" (videos were local); DR row lacks undo, `PLEX_ENV_FOR_APP`, no log backup, Terraform
first; no runbook for the team after the 30 minutes.

Sound: only the IAP agent has run.invoker; both run.app URLs require sign-in; 2 people + the SA in IAP; secrets by
reference, never logged; session per host; review, live re-read, verify; Hold refused; one move at a time; prod
gate on preview / move / undo; 48-bit plan ids, 10-min expiry; quoted history SQL; parameterized BigQuery;
`live_test.py` refuses unless env test; Flask debug off; about $1 a month.

## Found while fixing

- **Allocated containers already in a PW bin were suggested to move bin to bin** (set 544, job 2305: 199 allocated
  containers in PW - B8, default target PW - B9). Fixed: allocated-to-this-job containers at any of the line's
  destinations count as there, and the default target is where they are (`picking.default_target`).
- The app's CSP blocks Playwright's in-page waits; the test and recording scripts use `bypass_csp`.
