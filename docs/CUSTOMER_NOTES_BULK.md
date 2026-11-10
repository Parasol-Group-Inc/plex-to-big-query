# Bulk update of customer Notes in Plex (2026-11)

Each customer's **Comments** from `docs/reference/CustomerNotesResults9.csv` (an export with
ID, Name, Email, Phone, Primary Contact, Alt. Email, Comments, Plex Customer Code) is written to
the customer's **Note** in Plex production: Customer Details screen, NOTES section, the
multi-line "Note". The Brief Note and the Contact Information note are left alone.

- Tool: `scripts/plex_customer_notes_bulk.py` (plan, run, verify, log, resume, status).
- Hub: the **Customer notes** tab: every row with a pill ("Note written", "Appended",
  "Pending", or why it was flagged), its own log history, and the run log.
- Files: `etl-manual/customer_note/` in the primary folder (gitignored: customer data):
  `bulk_plan.csv`, `bulk_actions.jsonl`, `BULK_STOPPED.txt` when stopped, and the backups.

> **Done 2026-11-09** (pilot 18:01 UTC, last batch 22:01 UTC): **1,542 notes written** (1,532
> new, 10 appended) in 34 batches, every batch verified through the API. Final check
> 2026-11-10 ~01:00 UTC: a fresh API read of all 4,110 customers matches the plan exactly (each
> target holds its planned note, the appends keep the old note in full, no other customer's note
> changed; customers with a Note 13 → 1,545), and a screen read of 13 sampled customers matched
> 13/13. Two stops, both reviewed and logged: a false alarm at ADRI2 (title parsing, fixed) and
> LUXU1 when the laptop lid closed mid-save (nothing half-written). 0 retries. **Not written,
> for a later decision:** 927 inactive customers, 3 name mismatches, 690 codes not in Plex,
> 1,395 comments with no code (hub tab filters).

**Backups:** everything in `etl-manual/customer_note/` (the customer backups taken before the
update, the plan, the action log, `loop.out`, screenshots) is in
`gs://voxdatalake-terraform-state/plex-to-big-query/backups/customer-notes/2026-11-10T032245Z/customer_note.zip`,
and `scripts/backup_to_bucket.ps1` now zips `etl-manual/` with every run.

**Credentials it needs** (in `.env`, never in git): `PLEX_PORTAL_USERNAME` /
`PLEX_PORTAL_PASSWORD` for the screen (added to the Mac's `.env` on 2026-11-09) and
`PLEX_API_CONSUMER_KEY` / `PLEX_API_CONSUMER_SECRET` for the API reads.

## Contents

- [Which Note field](#which-note-field)
- [Why the screen and not the API](#why-the-screen-and-not-the-api)
- [The rules](#the-rules)
- [Backup](#backup)
- [Four checks](#four-checks)
- [Running it](#running-it)
- [When it stops](#when-it-stops)
- [Undoing a write](#undoing-a-write)

## Which Note field

The Customer Details screen has three note fields:

| On the screen | Screen field | BigQuery (ODBC) | REST API | In use (prod, 2026-11-09) |
|---|---|---|---|---|
| NOTES › **Note** (multi-line) | `Note` | not exported | `note` | 13 customers, mostly shipping instructions |
| NOTES › Brief Note (one line) | `GridNote` | `Grid_Note` | — | 0 |
| CONTACT INFORMATION › Note | `ContactNote` | `Contact_Note` | — | 1 (a web address) |

This update writes only the first.

## Why the screen and not the API

`PUT /mdm/v1/customers/{id}` with `note` on a test-tenant customer with no note (AEREL,
2026-11-09) returned 200 and stamped the record modified, but the note stayed empty. Reads of
`note` work, so the API is used for the backup and the per-batch verification, and the screen for
the writes. `scripts/plex_customer_note.py` is the one-customer version (first used on 101 Via
Imports, `PLACEHOLDER`).

## The rules

Decided by Emilio on 2026-11-09:

| Category | Rule | Written? |
|---|---|---|
| `write` | code and name identical to Plex, Active, Plex Note empty | yes: Note = comment |
| `append` | same, but the Note already has text | yes: Note = old note + new line + comment (nothing removed); flagged |
| `flag-inactive` | matched exactly, customer Inactive | not for now |
| `flag-name-mismatch` | code matches, name in the file not identical (HOME3 "Winona, Inc." vs "Homera Health"; APLBR and USNU3 have no name in the file) | no |
| `flag-not-in-plex` | the code is not a Plex customer code | no |
| `flag-no-code` | comment but no Plex code | no |
| `flag-no-customer-no` | customer newer than the ODBC copy, no Customer No for the screen | no |

The plan of 2026-11-09: 1,532 `write`, 10 `append`, 927 `flag-inactive`, 3
`flag-name-mismatch`, 690 `flag-not-in-plex`, 1,395 `flag-no-code` (4,557 rows with a comment).
Plain writes go first, appends last.

## Backup

`plan` saves every production customer as the API returns it (all fields, including `note`) to
`customers_backup_prod_<UTC>.json` before anything else, and the plan keeps each customer's
note as it was (`before_note`). The Brief Note and Contact note are in BigQuery
(`PlexProd.raw_Common_v_Customer`), and nothing here writes them.

## Four checks

1. **Claude's plan** from the CSV and the API backup.
2. **An independent Sonnet agent** built its own plan from the same two files without seeing the
   first: identical on all 3,162 rows that have a code (customer, note text, action).
3. **A different source:** Plex's ODBC customer table in BigQuery agrees on every code, name and
   status, and gives the Customer No the screen needs. The final `bulk_plan.csv` was compared
   row for row with the Sonnet plan again: 0 differences.
4. **During the run:**
   - before each write, the screen's Name and Customer Code fields must equal the planned customer and the Note on screen must
     equal the backed-up note (if someone changed it since, the run stops);
   - after Apply, the screen is reloaded and the saved Note must equal the planned text;
   - after each batch, `verify` reads every customer through the API: each written customer holds
     its planned note, and no other customer's note differs from the backup;
   - Claude reviews the batch (log, verification, a sample on screen) and records the review with
     `log` before the next batch starts. A batch must be verified before the next one can run.

## Running it

From the primary folder's checkout of the script, on the Mac, with Playwright installed and
`PLEX_PORTAL_USERNAME` / `PLEX_PORTAL_PASSWORD` and `PLEX_API_CONSUMER_KEY` /
`PLEX_API_CONSUMER_SECRET` in `.env`:

```bash
python scripts/plex_customer_notes_bulk.py status
python scripts/plex_customer_notes_bulk.py run --batch-size 5     # the pilot
python scripts/plex_customer_notes_bulk.py verify
python scripts/plex_customer_notes_bulk.py log --actor claude --event review "batch 1: ..."
python scripts/plex_customer_notes_bulk.py run --batch-size 50    # then repeat run / verify / review
```

**Standalone (how the rest ran, from 2026-11-09):** `loop --batch-size 50` runs batch after
batch, each followed by the API `verify`, until done or stopped, with no one watching:

```bash
nohup caffeinate -ims python -u scripts/plex_customer_notes_bulk.py loop --batch-size 50 \
  >> etl-manual/customer_note/loop.out 2>&1 < /dev/null & disown
```

A transient error (timeout, dropped session) is retried up to 3 times per customer with a fresh
login, 15-45 s apart, and API reads 4 times; a guard that trips (wrong customer, changed note,
Plex error, wrong read-back, a note changed elsewhere) stops at once. Emilio chose to skip the
per-batch Claude review for the rest (to save tokens); Claude verifies everything against the
backup at the end. Progress: `status`, `loop.out`, or the hub tab once it is re-published.

It takes the same Plex web lock as the screen task and the export, so only one runs at a time.
After each reviewed batch the hub tab is re-injected into the published hub.

## When it stops

Anything unexpected writes `BULK_STOPPED.txt` (when, why, the customer) and an `abort` line in
the log, and exits with code 3:
- the screen shows a different customer than planned;
- the Note on screen differs from the backup (someone edited it since the plan);
- Plex shows an error after Apply, or the reloaded Note is not the planned text;
- the API verification finds a written customer without its note, or any other customer's note
  changed;
- any unexpected error (timeout, page change).

`run` refuses while the file exists. After the reason is understood and fixed:
`resume --reason "<why it is safe>"`, which logs the reason and clears the stop. A customer
already holding its planned note is logged `already-set` and skipped, so a re-run after a stop is
safe.

## Undoing a write

The plan has each customer's previous note (`before_note`, empty for `write` rows). To undo one,
set it back with `scripts/plex_customer_note.py <CustomerNo> --set "<before_note>" --overwrite`,
or clear it on the screen.
