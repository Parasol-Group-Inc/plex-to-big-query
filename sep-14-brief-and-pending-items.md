# Sep 14 brief and pending items

## Current project status

### Label Design project status

- Current architecture is working and intentionally split into two steps:
  1. Check for new orders
     - reads the refreshed Plex/BigQuery queue
     - deduplicates against the sheet + historical archive
     - appends only fresh rows to the `MONDAY` tab
     - does not push to Monday.com
  2. Push to Monday & Archive
     - reads the current `MONDAY` tab including team review fields
     - pushes one Monday item per row
     - appends rows to `historical`
     - deletes rows from `MONDAY` only after archive success
     - manual only, no automatic trigger

- Safety model is already implemented and working:
  - `LockService` serializes check/push entry points
  - `_PUSH_STATE` ledger is the commit point for a successful Monday item
  - `historical` is append-only and protected by `assertNotHistory_()`
  - dedupe logic is keyed by order + label SKU and includes quarantine alarm logic when the key rule appears to break

- Current state of the codebase:
  - committed milestone: `62fab36` — `feat: add review-field enrichment helpers`
  - verified with: `node deploy/label_design_sync/test_logic.js`
  - result: `ALL CHECKS PASSED`

### Repository-level context

- This repo remains a working Plex -> BigQuery ETL + reporting pipeline.
- The relevant live decision from the team is not whether the queue architecture works; it is which data-source and business rules drive the downstream review queue and Monday actions.

---

## What is complete

### Already implemented and stabilized

- split check vs push flow
- manual push workflow with ledger safety
- reviewable sheet queue before Monday push
- dedupe against archive + queue
- email summaries and run logging
- guardrails against silent queue corruption
- enhancement layer for reason-code normalization, part-attribute enrichment, and LCR generation

### Last verified command

```bash
cd /Users/parasol/plex-to-big-query && node deploy/label_design_sync/test_logic.js
```

Expected outcome:

```text
ALL CHECKS PASSED
```

---

## Current pending items / unresolved design decisions

These are the concrete decisions that still need business confirmation before deepening implementation.

### 1) Part attribute lookup source

Decision needed:
- use an existing table in BigQuery if one already exists
- or create a small dedicated lookup table keyed by part number

Recommended default:
- small lookup / enrichment table keyed by `customer_part_no`
- optional multiple attributes flattened or stored in JSON-ish normalized rows depending on source shape

Why this is pending:
- it changes the contract for how attribute values should be pulled into the review queue and Monday row
- it affects whether the attributes are only shown on the sheet or also used downstream in BigQuery

### 2) Reason code mapping

Decision needed:
- approved controlled catalog only
- or free-text + normalized mapping to standard code

Recommended default:
- controlled catalog with normalization layer for common short forms/abbreviations

Why this is pending:
- If free text is allowed, the system must standardize it before Monday import.
- If the catalog is controlled, the team must confirm the allowed codes and ownership of the list.

### 3) LCR number generation

Decision needed:
- generate at review time
- or only when the row is pushed to Monday

Recommended default:
- generate at push time, with idempotency on `dedupe_key` to avoid duplicate LCRs on retry

Why this is pending:
- uniqueness and idempotency are operational requirements, not just implementation details
- if this has compliance or audit significance, the lifecycle must be agreed

### 4) Trigger policy for ETL refreshes

Decision needed:
- source-driven trigger only
- queue-driven trigger only
- hybrid trigger with stale queue fallback
- manual triggers with freshness guard

Recommended default:
- source-driven refresh as primary trigger
- summary-only / no-op when no new orders are found
- stale-queue fallback when the queue has gone quiet too long

Why this is pending:
- this is the cost-vs-coverage tradeoff for when the ETL should run

### 5) “What counts as new work?” rule

Decision needed:
- order number only
- order + item/part
- work order / line item
- date threshold / recency rule

Recommended default:
- use order + label SKU as the dedupe key, matching current design

Why this is pending:
- the definition of “new” directly affects whether duplicate or reopened rows are treated as new work or existing work

---

## Recommended next implementation path

Use the following exact next steps to keep momentum without broad speculative work.

### Milestone 1: finalize source-of-truth contracts

- confirm part attribute source/table contract
- confirm reason code catalog and normalization rules
- confirm LCR lifecycle / generation timing

### Milestone 2: keep code minimal and config-driven

- encode the attribute map and reason map in script properties or small lookup tables
- keep the current manual review process intact
- avoid changing the queue architecture while the business rules are still uncertain

### Milestone 3: implement stale-queue trigger policy

- add a lightweight last-success / last-seen marker
- add decision logic to skip empty runs with a summary email
- add stale backup trigger if queue activity is older than the agreed threshold

### Milestone 4: production hardening

- add audit trail for trigger skip vs trigger run decisions
- add a clear summary payload for no-new-order runs
- add operational ownership / escalation notes

---

## Key notes from the meeting and current architecture

### Working design principle

The core architecture is correct:
- the review sheet is a holding queue
- Monday is not populated until the team manually pushes approved rows
- source data is refreshed independently of Monday writes
- check and push are intentionally decoupled

### Important product requirement introduced by Jennilyn

The next layer is not “more automation”; it is reference-data enrichment:
- part attributes from part number
- reason code mapping from job note or review field
- LCR generation with uniqueness and retry-safe behavior

This is now the active design layer behind the queue, not just nice-to-have formatting.

---

## Commands to run next session

### Verify the current logic

```bash
cd /Users/parasol/plex-to-big-query && node deploy/label_design_sync/test_logic.js
```

### Check repo state

```bash
cd /Users/parasol/plex-to-big-query && git status --short
```

### Commit a follow-up work item

```bash
git add .
git commit -m "<milestone message>"
```

### Push current branch

```bash
git push origin main
```

---

## Decision summary

The current state is:
- architecture is working
- safety model is done
- next work is about reference data and trigger decision policy
- the recommended default is: keep the review queue split, add summary-only no-op behavior when empty, and use source fresh data as the trigger basis

This is the best state for the next session to pick up without redoing analysis.
