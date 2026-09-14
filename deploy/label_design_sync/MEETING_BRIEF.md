# Label Design Sync — Meeting Brief

## Purpose

This brief captures the current working flow, the decisions still open, the recommended long-term architecture, and the improvements we should discuss with the team before making the next change.

---

## 1) What is currently working

### Current architecture

The current design is intentionally split into two separate steps, documented in [deploy/label_design_sync/README.md](README.md):

1. Check for new orders
   - Reads the refreshed Plex data from BigQuery.
   - Deduplicates against rows already present on the Google Sheet.
   - Appends only new orders to the `MONDAY` tab.
   - Does not push anything to Monday.com.
   - Runs automatically on a schedule and can also be run manually.

2. Push to Monday & Archive
   - Reads the current `MONDAY` sheet state, including reviewer-entered fields.
   - Creates one Monday item per row.
   - Appends successfully pushed rows to `historical`.
   - Removes the row from `MONDAY` only after the push is confirmed.
   - This step is manual by design.

### What the team already has

The current pattern is working as intended for a review queue:

- The ETL refreshes the source data.
- The sheet acts as a reviewable holding queue.
- The Monday board is not populated until someone explicitly pushes approved rows.
- The system includes safeguards to reduce data loss risk:
  - lock service to avoid concurrent writes
  - write-ahead ledger for push state
  - idempotent archive logic
  - row-tracking to avoid silent duplicate or missing records

### Why this is good

This design protects the human review step.

It prevents the old failure mode where a raw BigQuery snapshot was sent directly to Monday before the team had a chance to fill in:
- Reason Code
- Label
- Bottle Material
- Prop 65
- LCR

The current system keeps those review fields in the loop before anything reaches Monday.

---

## 2) What is currently being treated as a design decision

The main architectural choice is not whether the system works; it is whether the Apps Script check should act as a trigger for downstream work or as a summary-only notification.

### Current behavior

The check flow is intentionally a cheap summary, not an ETL trigger.

This means:
- if there are no new rows, the Apps Script still reports status
- it does not force the pipeline to run again
- it avoids paying for unnecessary Cloud Run executions when there is no new queue value

### Why this is a reasonable direction

This is the right cost-conscious choice when:
- the queue is often empty
- the ETL uses paid infrastructure
- Monday is not the system of record
- the review sheet is a downstream worklist, not a trigger source

### Team decision still open

The real question is: should the decision to run the ETL be based on:

- source data change detection only
- `MONDAY` tab queue fill only
- a hybrid of both
- or a manual trigger plus stale-queue safety

That is the key design conversation.

---

## 3) What needs team decisions

These are the decisions the team should address in the meeting.

### Decision A — What is the real trigger source?

Choose one of the following:

1. Source-driven trigger
   - run whenever new orders appear in Plex / BigQuery
2. Queue-driven trigger
   - run when the `MONDAY` tab is non-empty
3. Hybrid trigger
   - run when source has new rows OR queue is stale
4. Manual trigger with stale safety
   - no automated ETL except for maintenance checks

### Decision B — What counts as “new work”?

The system must define the exact record of a new order.

We need to decide:
- order number
- line item key
- work order key
- date threshold
- whether a row is “new” only once or reappears after a review

### Decision C — What is the freshness policy?

If the queue is empty, do we still refresh data:
- every day
- only during active business hours
- only if queue was stale for more than N hours
- only on demand

### Decision D — What should happen when the queue is empty?

Options:
- skip processing silently
- send a no-new-orders summary
- log a quiet health check
- trigger a maintenance verification run only for stale data

### Decision E — What is the team’s tolerance for false positives vs false negatives?

- false positive: runs with no new work
- false negative: misses work that should have reached the queue

In cost-sensitive work, false positives are cheaper but must be bounded.

---

## 4) Ideal architecture for the next iteration

The most robust long-term design is a hybrid model.

### Recommended pattern

Use the source data as the primary trigger, and the review sheet as the downstream worklist.

#### Step 1 — Source gate

At the ETL or scheduler level, check whether there are new meaningful order keys since the last successful run.

#### Step 2 — Queue freshness guard

If no new source rows are found, do not trigger an expensive run unless:
- the queue is stale beyond an agreed threshold
- a manual override is requested
- a known backlog requires re-checking

#### Step 3 — Review queue remains human-controlled

The `MONDAY` tab remains the review queue, and manual push remains separate from the check step.

#### Step 4 — Summary only when empty

When no new work is detected, send a lightweight summary email instead of running a full ETL cycle.

This gives the team a clean message:
- no new orders found
- nothing pushed to Monday
- the queue is healthy
- no extra cost incurred

### Why this is the ideal state

It preserves the current architectural strength:
- source-of-truth = data layer
- queue = review layer
- push = intentional human action

And it removes unnecessary spend without making the system fragile.

---

## 5) Improvements the flow would need

These are the improvements worth discussing after the architecture is agreed.

### Improvement 1 — A simple “new order since last run” checkpoint

Introduce a lightweight metadata table or last-run marker that records:
- last successful ETL timestamp
- last seen order key or max order date
- whether the queue was empty

This removes guesswork from trigger logic.

### Improvement 2 — Clear queue freshness rules

Define stale thresholds explicitly, such as:
- no new orders for 24 hours
- queue still open but no activity for 3 business days
- manual override allowed outside normal hours

### Improvement 3 — Better summary content

The summary should state:
- rows reviewed
- rows added to `MONDAY`
- rows skipped as duplicates
- queue age
- last successful trigger time
- whether the run was cost-saving and skipped by rule

### Improvement 4 — Explicit operational ownership

Define who owns:
- ETL schedule
- review queue hygiene
- stale backlog follow-ups
- manual override requests

### Improvement 5 — Decision log / audit trail

Every run should record why it was triggered or skipped.

This makes the process explainable during meetings and easier to debug later.

---

## 6) Suggested meeting framing

Use this framing in the team discussion:

> “The current architecture is already intentionally designed to avoid pushing raw data directly to Monday without review. The remaining decision is not whether the process should be reviewed, but how we decide when it is worth running the source refresh and when it is better to skip cost and send a summary only.”

This keeps the conversation on the real design question instead of re-litigating the safety controls that already work.

---

## 7) Questions to ask the team

1. Is the Monday tab a review queue or a real trigger source?
2. Do we want the ETL to run only when new source orders exist, or should it still refresh on a regular time window for freshness?
3. What is the acceptable threshold for a no-new-orders run to be considered “safe to skip”?
4. Should the system log skipped runs as health checks or only send a summary when a real change is detected?
5. Should we keep the current “summary-only when empty” rule as the default, with manual override for exceptions?
6. What should be the exact definition of “new order” for deduping and trigger logic?

### New requirements surfaced by Jennilyn

These are not just implementation tweaks; they are additional schema and product decisions.

#### 1) Part attributes from the part number

The idea is to pull part attributes onto the review queue using the part number as the key, so the team can use attributes like allergens or regulatory flags (for example Prop 65) without retyping them manually.

This is technically feasible, but it needs a clear data contract:
- a part attribute table keyed by part number
- a many-to-many or flattened representation if a part has multiple attributes
- a rule for which values are considered required versus optional
- a decision on whether the attributes are shown on the sheet only, or also stored in BigQuery for downstream use

This is a strong fit for a lookup/enrichment layer, not for ad hoc string parsing in the Apps Script.

#### 2) Job note to Monday “Reason Code” mapping

This is a controlled catalog problem.

The requirement is effectively: the job note field can contain a short free-text value, and the system should map it to the correct Monday reason code. The team wants the import into Monday to carry the correct standardized reason code, not just a raw note.

That implies:
- a source-of-truth `reason_code` mapping table or lookup list
- normalization rules for short one-word values or abbreviations
- a decision on whether only approved codes are accepted, or whether free text is allowed and transformed later
- a business owner for the catalog so it does not drift over time

This should be treated as a reference-data design problem, not a raw spreadsheet formatting problem.

#### 3) Auto-generated LCR number

This is a very plausible workflow enhancement, but it raises the question of when and where the number should be generated.

Key considerations:
- format: 14-character alphanumeric, or another agreed pattern
- uniqueness: must be guaranteed across rows and retries
- idempotency: a row should not get a new LCR number if the push restarts or retries
- lifecycle: generate when the row is created, when it is reviewed, or only when it is pushed to Monday

This is a product / operational decision as much as a software one, especially if the number has compliance or audit significance.

### Decision implications for the meeting

These three asks imply a more complete downstream design:
- part attribute enrichment as a lookup layer
- reason code catalog and normalization rules
- LCR generation + uniqueness policy

This means the next architecture step is not just “improve the trigger,” it is also “design the reference data and enrichment model behind the review queue.”

---

## 8) Recommended default position

If the team wants a practical default, this is the recommendation:

- Keep the current split design.
- Keep the Apps Script check as a summary-only gate.
- Use source-based new-order detection for the ETL trigger.
- Add a stale-queue safety rule so the system does not silently go cold.
- Keep manual override available for operational exceptions.

This is the best balance of cost, reliability, and human review.

---

## 9) Bottom line

The system is structurally sound. The main work now is not rebuilding the flow; it is deciding the trigger policy and freshness rules that make the system efficient and predictable.

The strongest version of the design is:

- source-driven refresh when new work exists
- summary-only behavior when nothing new is detected
- stale-queue recovery as an exception path
- manual human review remains the gating mechanism before Monday receives anything

