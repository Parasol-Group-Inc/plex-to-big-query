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
| Label Design | Unchanged: its own hourly probe, 5 AM-5 PM weekdays, with the push 35 minutes later. Kept as the reference for how fast Plex prod reaches ODBC. |
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
  Of the 82 extractions per environment, 71 have a list. The 11 without one
  are all small status/type lookups with neither column, so they probe by
  count only.
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
bounds that at one day.

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

## The dispatcher (phase 2)

Cloud Scheduler cannot read BigQuery, so a small Cloud Function,
`plex-etl-dispatcher`, does it. It is a Gen 2 function, the same pattern as
`deploy/plex_api_function/`. One Cloud Scheduler job calls it every 5 minutes.
On each call it:

1. Reads `PlexProd.etl_schedule`. Columns: `job_name`, `run_time` (`HH:MM`,
   America/Denver), `mode` (`probe`/`full`), `enabled`, `note`, `updated_by`,
   `updated_at`. There is one row per job per time, staggered a few minutes
   apart so 12 jobs don't hit Plex at once.
2. For each enabled row whose time has passed today, within the last 30
   minutes, and which has no row yet in `PlexProd.etl_dispatch_log` for
   (`job_name`, `scheduled_for`): inserts a dispatch row with DML and starts
   the job with `RUN_MODE` and `DISPATCH_ID` as env overrides. The ETL service
   account can do this since D2 closed on 2026-10-02.
3. Finds dispatch rows whose run ended `failed` or `partial`, or which never
   reported back within the job timeout, and which are not themselves
   follow-ups and have none yet. Once 15 minutes have passed, it dispatches
   exactly one follow-up `probe`.
4. Skips a job that still has a dispatch running.

The job writes its own outcome onto its dispatch row at the end of the run
(`record_dispatch_outcome` in `main.py`), which is what step 3 reads.

**Changing a time** is one statement. No deploy:

```sql
UPDATE `voxdatalake.PlexProd.etl_schedule`
SET run_time = '13:30', updated_by = 'emilio', updated_at = CURRENT_TIMESTAMP()
WHERE job_name = 'plex-etl-sales-orders' AND run_time = '13:00';
```

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
- **Phase 2:** designed (above), not built.
