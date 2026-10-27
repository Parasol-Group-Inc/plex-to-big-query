# Change probe for every ETL — build plan

*Started 2026-10-19. Owner: Emilio. Status per phase is at the bottom.*

## Why

Every nightly pipeline is a full refresh: each extraction pulls the whole Plex
view and `WRITE_TRUNCATE`s its raw table (`date_col` only orders the pull; no
pipeline is incremental). Running those more often than once a night means
paying for 99 full table pulls each time, whether or not anything moved.

Label Design already solved this for itself on 2026-10-01 with a change probe:
a few cheap queries are fingerprinted, and when the fingerprint matches the last
clean run, the run is skipped. This plan extends that to every prod pipeline
and runs them **four times a day** on times kept in a table.

## Decisions (Emilio, 2026-10-19)

| Question | Decision |
|---|---|
| When | Prod pipelines run at **1 PM, 6 PM, 11 PM and 4 AM** Mountain. 1/6/11 PM probe first. **4 AM is always a full run**, the daily safety net. |
| Where the times live | A BigQuery table, `PlexProd.etl_schedule`, editable on demand without a deploy. |
| Test | Unchanged: one full run a night on its existing scheduler, no probe. |
| Label Design | Its own probe, every 15 min 5 AM-5:45 PM weekdays since 2026-10-22 (hourly before); a run that extracts starts the push itself. Kept as the reference for how fast Plex prod reaches ODBC. |
| Retries | **None.** Prod `-retry` schedulers are removed: the next probe run is the retry. A run that fails emails FAILED with its errors, as today, and the dispatcher runs **one** follow-up probe **15 minutes** later. If that fails too, nothing more until the next scheduled time. Cloud Run task retries (`max_retries`) go to 0 for the same reason: an immediate re-run usually hits the same error. |
| Email | One email per job per run, as today. **The subject does not change**: `[Plex ETL] - {Category}: {Pipeline} — {date}`, so every run of a pipeline that day lands in one Gmail thread. A probe that found nothing sends a short **"Probe ran — nothing to update"** email. The full email is tidier, and the per-table fetch/write lines become a compact table at the bottom. **No external log or link-out page**: everything is in the email. |
| New reports | The three stored-procedure reports in progress (Part Info and Routing, the container-type variant, Item List with Shelf Life) are built as normal pipelines and get the same probe. |

## How the probe works

`probe_mode: auto` at the top of a report YAML turns it on. Each extraction then
contributes one aggregate, built from its own view and filter:

```sql
SELECT COUNT(*), MAX(Update_Date), MAX(PO_Line_Key) FROM Sales_v_PO_Line
```

- `COUNT(*)` catches rows added or removed.
- The `MAX` columns come from the extraction's `probe: [...]` list: a change
  date and/or the view's own key. They make an **edit** visible.
  `scripts/generate_probe_columns.py` picked them from the schema catalog.
  As of the 2026-10-21 audit, 88 of the 100 `auto` extractions per
  environment (13 pipelines) have a list. The 12 without one are small
  status/type lookups with neither column, so they probe by count only.
  The audit added `sum:` columns where an edit changes a quantity or price
  but no date (shipper lines, allocations, job distribution, production,
  cell production/depletion, requisitions) and change dates the generator
  had missed (`Loaded_Date`, `Price_Updated_Date`, `Closed_Date`,
  `Inspection_Date`).
- The report's **YAML and SQL files are part of the fingerprint**, so a
  `deploy.sh` that changes either always runs in full. That fixes OPEN_ITEMS **L10**, where
  a SQL-only deploy sat unapplied for as long as Plex stayed quiet.
- The probe stores a per-table **snapshot** next to the fingerprint, so the
  email can say which tables changed ("3 of 27 tables changed: ...").

**Measured 2026-10-19 on Plex test:** Plex runs these aggregates on its side.
- One table: 0.2-0.5 s. `Part_v_Flat_BOM` (235,550 rows) counts in 0.27 s,
  against 6.5 s to pull it in full.
- All 82 generated probe queries across the 12 pipelines: 12.4 s in total,
  with 0 failures. The largest, Sales Orders at 27 tables, takes 4.0 s.

**Known limits.**
- **Code changes are not in the fingerprint.** A Cloud Build image change, for
  example to how `write_to_bigquery` types columns, reaches a quiet
  pipeline's tables at the next run that extracts: a probe that sees a change,
  or the 4 AM full run. To apply it sooner, start the job by hand. A hand
  start is a `scheduled` run, which is always full for a nightly pipeline.
- **Edits without a change date.** On a table with no change date, an edit to an existing row
keeps the same count and keys, so the probe cannot see it. The 4 AM full run
bounds that at one day. Two known cases (2026-10-21 audit): a requisition's
status flip (`Requisition_Status_Key` is refused by the key-like SUM rule;
needs an allowlist in `main.py`, so an image) and a rep reassignment in
`Sales_v_Order_Salesperson` (only key columns).

**What to expect.** Busy tables such as `Part_v_Production` and
`Part_v_Container` move all day, so Work Orders and inventory will usually run
in full at 1 PM and 6 PM. The skips come from the quieter pipelines and from
11 PM. That is the probe being correct, not a fault.

### Run modes (`RUN_MODE`)

| Value | Started by | Behaviour |
|---|---|---|
| `scheduled` | a plain scheduler fire, or by hand | Full run, as before. Explicit probes (label_design) still probe and may skip. |
| `probe` | dispatcher, at a `probe` time | Probe; skip if unchanged; otherwise full run. |
| `full` | dispatcher, at a `full` time (4 AM) | Never skips; records the probe as the next reference. |
| `retry` | legacy 9:45 PM retry scheduler | Unchanged. Only test jobs keep it after phase 2. |

### Fail open

Anything that stops the probe being evaluated runs the full extraction and
logs an `inconclusive` row:
- a query error;
- a probe column that is not a plain identifier;
- an aggregate that returns no row;
- since 2026-10-19, an unreadable `probe_log` (before, that failed the whole run).

The probe may never be the reason a change is missed.

## The dispatcher (phase 2), as built 2026-10-19

Cloud Scheduler cannot read BigQuery, so a Gen 2 Cloud Function,
**`etl-dispatcher`** (`deploy/etl_dispatcher/main.py`), does. The Cloud
Scheduler job **`plex-etl-dispatcher`** calls it every 5 minutes. Its tables
live in their own dataset, **`PlexOps`**, because they are about running jobs
in every environment, not report data:

- **`PlexOps.etl_schedule`:** one row per job per time. Columns: `job_name`,
  `run_time` (`HH:MM`, America/Denver), `mode` (`probe`/`full`), `enabled`,
  `note`, `updated_by`, `updated_at`.
  - Seeded by `deploy/etl_dispatcher/seed_schedule.sql`: 13 prod jobs × (13:00,
    18:00, 23:00 probe; 04:00 full) = 52 rows.
  - Staggered **4 minutes** apart (13:00, 13:04, … 13:48), so 13 jobs don't
    open Plex ODBC sessions at once. Not 5: 12 × 5 would put the last 11 PM
    slot at "24:00".
- **`PlexOps.etl_dispatch_log`:** one row per start: `dispatch_id`,
  `job_name`, `mode`, `reason` (`schedule`/`follow-up`), `scheduled_for`,
  `followup_of`, `dispatched_at`, `execution_name`, `outcome`, `finished_at`,
  `detail`.

**Each tick:**
1. **Reconcile.** A run writes its own outcome when it finishes
   (`record_dispatch_outcome`; the dispatcher passes
   `DISPATCH_LOG_TABLE=PlexOps.etl_dispatch_log`).
   - If a run crashed before that, the dispatcher reads the Cloud Run
     execution and records `failed`.
   - Succeeded at the Cloud Run level but never recorded:
     `succeeded-unrecorded`.
   - No outcome and no finished execution after 2 hours: `lost`.
2. **Dispatch due slots.** A slot is an enabled row whose time came within the
   last **30 minutes**, so a missed tick still runs it. A late slot (23:55)
   still runs after midnight.
   - **Idempotency key:** (`job_name`, `scheduled_for`). Two overlapping ticks,
     a Cloud Scheduler retry, or the same row entered twice all start the job
     once.
   - **A job whose previous run is still open isn't started twice.** The slot
     is logged as `skipped-busy`.
   - **The log row is inserted before the run starts,** so a crash in between
     leaves a row (reconciled as `lost`), never an orphan run that would be
     started again.
3. **Follow up.** A run that ended `failed`, `partial` or `lost` gets **one**
   `probe` run, 15 minutes after it finished. It gets none if more than 6
   hours have passed; the next scheduled time covers it. A follow-up never
   gets a follow-up.

**The run is started** with env overrides `RUN_MODE`, `DISPATCH_ID` and
`DISPATCH_LOG_TABLE`. That needs `run.jobs.runWithOverrides`, held by the
ETL service account through the `plexEtlRunWithOverrides` custom role
(OPEN_ITEMS D2). Reading an execution's status needs `run.executions.get`,
added to the same role. The function runs as the ETL service account, with
`--max-instances=1`.

**`?dry_run=1`** returns what a tick would do, with no writes and no runs.

**Changing a time** is one statement, with no deploy:

```sql
UPDATE `voxdatalake.PlexOps.etl_schedule`
SET run_time = '13:30', updated_by = 'emilio', updated_at = CURRENT_TIMESTAMP()
WHERE job_name = 'plex-etl-sales-orders' AND run_time = '13:00';
```

### Rollout in two stages
- **Stage A:** the dataset, tables, dispatcher and its scheduler. The prod rows
  are seeded **disabled**, and the nightly prod schedulers keep running. Then
  an end-to-end test on test jobs, with temporary test rows: a probe slot, a
  full slot, and a forced failure to see the follow-up. Test jobs still have
  `max_retries = 1`, so a failed test run gets a Cloud Run retry as well;
  that's expected during the test. Prod goes to 0 in stage B.
- **Stage B:** enable the prod rows (one `UPDATE`), then remove the prod nightly
  and `-retry` schedulers, and set `max_retries = 0` on the prod jobs. Test
  jobs keep their nightly scheduler and retry.

## Delivery

| Phase | PR | Contents | Behaviour change when deployed |
|---|---|---|---|
| 1 | this one | Probe engine (`probe_mode: auto`, snapshots, config/SQL fingerprint, fail-open fix, dispatch outcome); both email templates; probe columns in all 24 YAMLs; `tests/test_probe.py`; docs | Email look changes for every job, and times show in Mountain. Label Design runs in full once, because its fingerprint now includes config. Nothing else: no prod job is started in `probe` or `full` mode yet. |
| 2 | next | `etl_schedule` + `etl_dispatch_log` (Terraform), the dispatcher function and its scheduler, the seed rows, prod nightly schedulers and prod `-retry` removed, prod `max_retries = 0` | Prod moves from one nightly run to four runs a day. |

Phase 1 ships as both a Cloud Build image (code) and a `deploy.sh` (the YAMLs).
Either order is safe, and so is rolling the image back:
- **The report-level key is `probe_mode: auto`, not `probe: auto`, on purpose.**
  An image from before 2026-10-19 treats any truthy `probe:` as an explicit
  block and crashes on a string. The independent review caught this. Older
  images ignore `probe_mode`, and they ignore the per-extraction `probe: [...]`
  lists too.
- The new image does a full run of a nightly pipeline in `scheduled` mode.

## Verification

- `python tests/test_probe.py`: 16 tests. They cover:
  - the run-mode rules and the old-key guard;
  - the generated SQL;
  - fingerprint stability and sensitivity, and config/SQL changes;
  - fail-open, including a cursor error;
  - the label_design explicit probe, including two queries on the same view;
  - all three emails: the same subject, the local date, no unfilled
    placeholders, errors first;
  - the REAL `main()` crashing after loading its config, which must still
    keep the pipeline's subject.
- An independent review agent read the whole change against this plan and
  found 12 issues. All of them were fixed before the PR, apart from one
  harmless nit (the first `snapshot` row after the schema upgrade can be lost
  to BigQuery's streaming lag, which only costs one full run). The fixes
  include:
  - the `probe_mode` key;
  - failed runs keeping their subject;
  - the FAILED email no longer saying "every table was extracted";
  - two remaining fail-open gaps;
  - UTF-8 and line-ending safety in the generator, for Windows;
  - pinning `tzdata`.
- Every generated probe query was run against Plex test (above).
- Before each PR, an independent review agent checks the diff against this plan.
- After the phase 1 deploy, L10 is proven by the **next** SQL-only deploy: the
  following quiet run must log `applied`, not `skipped`. The first run after
  this deploy runs in full regardless, because the fingerprint's format
  changed.

## Status

- **Phase 1:** built 2026-10-19 on `dev`. PR open.
- **Phase 2: live in prod since 2026-10-19 18:20 MT.** Stage A was tested end to end on test jobs. Stage B removed the 25 prod schedulers (prod `max_retries = 0`). First rounds: 6 PM 12 ran / 1 skipped; 11 PM 4 ran / 9 skipped; 4 AM full, 13 ran; no failures or follow-ups. CHANGELOG 2026-10-20.
- **First new pipeline on the probe: `part_routing`** (Audit - Part Info and
  Routing, built 2026-10-19). It added two engine features:
  - **`page_key` keyset paging** for large views;
  - **`sum:` probe columns**, so edits show on views with no change date.
    Measured on Plex test: SUM of a key column overflows Plex's 32-bit
    integer, so that is refused.

  Its prod job starts nightly and joins the dispatcher in phase 2 like the rest.
- **Second view on `part_routing`: Container Types** (2026-10-19). It reuses
  all of report 1's tables plus two more. Plex refuses `SUM` on bit columns,
  so a primary-container flip is seen at the 4 AM full run, not by the probe.
