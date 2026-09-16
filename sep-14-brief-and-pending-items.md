# Sep 14 brief and pending items

> **⚠ READ THIS SECTION FIRST.** Everything below "## UPDATE — 2026-09-16" is
> the original 2026-09-14 brief, kept for history. Large parts of it are
> **superseded** — the team decided to drop the Google Sheet entirely, which
> is a bigger pivot than anything the original pending-items list
> anticipated. Do not resume work from the original plan without reading the
> update first.

---

## UPDATE — 2026-09-16 (start here)

### The one thing to check first, before anything else

**`terraform plan` shows drift right now**: `label_design_config_prod` needs
updating in place (today's new Part Attribute extractions were added to
`reports/label_design.yaml` but never pushed to prod's GCS object), plus two
harmless metadata-only replacements (`label_design_config_test`,
`label_design_view_sql` — their content-type drifted to
`application/octet-stream` from manual `gcloud storage cp` pushes instead of
`terraform apply`; a replace just re-uploads the same content with the right
metadata, nothing is lost).

**Why this matters more than the usual "prod is stale" note**: the SQL file
at `gs://voxdatalake-report-configs/sql/label_design_view.sql` (shared by
prod and test) was pushed today and now joins against
`raw_Part_v_Attribute` / `raw_Part_v_Part_Attribute`. Test's extraction list
was updated to match — prod's was not. **If the prod job runs before
`terraform apply`, view creation could fail** (the exact "PARTIAL, exit 0,
no view" failure mode this repo has hit before, from a mismatched
config/SQL pair). Run `terraform plan` again on resume; if it still shows
`label_design_config_prod` changing, run `terraform apply` before the next
scheduled prod run (9:30 AM / 1:30 PM Mountain).

### The architecture pivot

The team decided to **drop the Google Sheet entirely** from the Plex →
Monday flow. The two-button Apps Script design described in the original
brief below (Check / Push & Archive, `_PUSH_STATE` ledger, `historical` tab)
is being **retired**, not extended. See `CHANGELOG.md` 2026-09-15/16 entries
for full detail; memory files
`project_label_design_rearchitecture.md` and
`project_label_design_part_attributes.md` carry the same information for
Claude's own recall in a future session.

**New shape, decided but only partly built:**

- **A new standalone service** — Cloud Run Job + Cloud Scheduler, matching
  every other pipeline component here (`plex-etl-<name>` pattern), **not**
  an Apps Script extension. **Not built yet** — this decision has no code
  behind it.
- **A new BigQuery audit table**, replacing the Sheet's role as the visible
  record of what happened. **Not built yet.**
- **Dedupe moves to a hash-based LCR.** The Monday `LCR` column itself will
  hold a SHA-256 hash (first 12 lowercase hex chars) of
  `order_number + customer_part_no`, reusing the existing column rather than
  adding a new one — confirmed safe against all 4,500 real historical LCR
  values (none are lowercase hex). **Decided and documented, not built.**
- **Cutover date 10/19** (Jennilyn). Items already on the board before then
  are grandfathered, never reconciled.
- **Open edge case, not resolved**: the view's 14-day rolling window means an
  order dated just before 10/19 could still appear in BigQuery's output well
  after the cutover, added to Monday the old way (no hash) — the new
  hash-only check wouldn't recognize it and could create a duplicate.
  Recommended fix (fall back to Sales Order + Part# text comparison for any
  row dated before 10/19) is **awaiting confirmation**, not yet built.

### Job Note → Reason Code: RESOLVED and BUILT

Not a number-hunt through free text — **the first character of the Job Note
is the reason code** (1–6), everything after it (one separator character
stripped) is the Memo. An unrecognized first character consumes nothing —
the whole note goes to Memo untouched, no Reason Code set.

Mapping, fully disambiguated against Monday's real Reason Code dropdown
(40+ options, several near-duplicates — see
`label-design/monday_board_catalog.md`):

| Code | Meaning | Monday option index |
|---|---|---|
| 1 | Customer Initiated: Label Edit | `[105]` |
| 2 | Customer Initiated: Label Review | `[0]` |
| 3 | New label design (Vox design) | `[1]` |
| 4 | New label review (Customer design) | `[2]` |
| 5 | Vox Initiated: Label edit/review | `[106]` |
| 6 | 3D Rendering | `[4]` |

**Built**: `label_design_service/reason_code.py` + `test_reason_code.py` —
21/21 checks pass, including a real confirmed example from Emilio:
`"3 Update to current V code. Standard Label."` → *New label design (Vox
design)* + memo `"Update to current V code. Standard Label."`. Checked all
164 real non-blank Monday Memo values from a live board pull — **zero
currently start with a digit**, confirming this is a going-forward
convention with no other real data to validate against yet.

**Not yet wired into any live push** — the push mechanism itself doesn't
exist (see standalone service above).

### Part Attributes: BUILT and VERIFIED against real test data

Plex's model (four tables, none extracted by this pipeline before
2026-09-16): `Part_v_Attribute_Type` → `Part_v_Attribute` → `Part_v_Attribute_Value`
(dropdown options) → `Part_v_Part_Attribute` (`Part_Key` + `Attribute_Key` +
`Value`). Confirmed: **one value per attribute per part** — a need for
several flags at once is handled by Plex's own dropdown carrying pre-defined
COMBINED strings as a single value (`"Prop 65 + Organic"`), passed through
untouched, never parsed.

**Built**: `Part_v_Attribute` + `Part_v_Part_Attribute` added as extractions
to `reports/label_design.yaml` and `reports/test/label_design.yaml` (12
extractions each, counts match). `reports/sql/label_design_view.sql` pivots
them, joined on `Part_Key` (from `Sales_v_PO_Line` directly — Plex's stable
internal key, not the customer-facing part number).

**The first guess was wrong, caught by actually running it, not by a dry
run.** Original pivot guessed attribute names `'Bottle Material'` and
`'Regulatory'` before any real Plex data existed. Once auth was restored and
the job actually ran, it turned out **Jennilyn had already uploaded real
test data** (5 attributes, 28 part assignments) — and neither guessed name
existed. The real five, read directly rather than guessed again:

| Real Plex attribute | Output column |
|---|---|
| Size | `part_size` |
| Allergen | `part_allergen` |
| Hazardous | `part_hazardous` |
| Certifications | `part_certifications` |
| Printing Material | `part_printing_material` |

**Verified against live BigQuery, twice** (wrong names, then corrected
names) — the view recreates successfully both times, and a standalone proof
query confirmed `part_allergen = "Yes"` on `Part_Key 11003458` (the one
value she's actually populated so far) comes through the pivot correctly.

**Still open, not blocking, and the actual next concrete step**: which of
the five real attributes (if any) maps to which *Monday* column. A real
board-usage audit (last-14-days snapshot) found:

| Monday column | Fill rate | What it holds |
|---|---|---|
| Bottle Material | 100% (113/113) | HDPE / PET / Glass — hand-typed every time |
| Label (size) | 4% (4/113) | e.g. `3" x 7.75"` — barely used |
| Regulatory Status | 44% (50/113) | RA Rejected / Pending Customer / RA Approved — **looks like workflow status, not a compliance flag** |
| Prop 65 (plain text) | 0% (0/113) | never used |
| *(nothing found)* | — | no column matches "Allergen" at all |

A message was drafted for **Ashley** (Monday board owner) and **Jennilyn**
(Plex side), asking specifically: does Printing Material feed Bottle
Material or is it a different concept; does Size feed the barely-used Label
field; do Hazardous/Certifications feed Regulatory Status or Prop 65 or
neither; is Allergen brand new. **Not yet confirmed sent or answered** —
pick this up first next session, since it's the one thing genuinely blocking
further Part Attributes work.

### A real bug found and fixed this session, worth remembering

`reports/sql/label_design_view.sql` had an **orphaned `),`** left over from
the 2026-09-15 release-collapse edit — that edit's own dry run never
actually completed (blocked by the `gcloud auth login` wall) and was only
read through by eye afterward, which missed it. Caught this time with a
**local paren-balance check** before building anything on top of it, then
confirmed fixed against live BigQuery. Lesson for next session: **a
"looks right on rereading" is not verification** — either run it live, or at
minimum run a mechanical check (paren balance, etc.) before trusting it.

### Deployment state as of 2026-09-16

- `reports/test/label_design.yaml` + `reports/sql/label_design_view.sql`:
  pushed to GCS manually (`gcloud storage cp`), test job run twice today,
  both successful, view recreated both times, verified with real queries.
- `reports/label_design.yaml` (**prod**): edited and committed to git,
  **not yet pushed to GCS** — see the terraform warning at the very top of
  this doc.
- No code exists yet for the standalone service, the audit table, or the
  hash-based LCR — those are documented decisions only.

### Concrete next steps, in order

1. **Resolve the terraform drift** (see top of this doc) before the next
   scheduled prod run.
2. **Get an answer from Ashley/Jennilyn** on the Part Attributes → Monday
   column mapping (see table above) — this is the one thing blocking
   further Part Attributes work.
3. Confirm the 14-day-window/cutover edge case fix (fall back to text
   comparison for pre-10/19 rows).
4. Start building the standalone service (Cloud Run Job + Scheduler) — the
   Reason Code parser and Part Attribute columns are ready to be consumed by
   it the moment it exists.
5. Build the BigQuery audit table.

---

## Original brief — 2026-09-14 (superseded, kept for history)

> Everything below describes the Sheet-based two-button architecture, which
> has since been replaced by the standalone-service plan above. Several
> "pending decisions" listed here were resolved differently than their
> "recommended default" once real business input came in (see the update
> above) — read them as history, not as an active plan.

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

## Current pending items / unresolved design decisions (historical — see UPDATE above for what actually happened)

These are the concrete decisions that still needed business confirmation as of 2026-09-14.

### 1) Part attribute lookup source

Decision needed:
- use an existing table in BigQuery if one already exists
- or create a small dedicated lookup table keyed by part number

**What actually happened**: neither — Plex's own generic Part Attribute
system (`Part_v_Attribute` / `Part_v_Part_Attribute`) is the source, keyed
on `Part_Key`, not a custom lookup table. See the UPDATE section above.

### 2) Reason code mapping

Decision needed:
- approved controlled catalog only
- or free-text + normalized mapping to standard code

**What actually happened**: first-character-of-Job-Note rule, a 6-code
catalog fully mapped to real Monday option indices. See the UPDATE section
above.

### 3) LCR number generation

Decision needed:
- generate at review time
- or only when the row is pushed to Monday

Recommended default (2026-09-14):
- generate at push time, with idempotency on `dedupe_key` to avoid duplicate LCRs on retry

**What actually happened**: not a generated *sequence* number at all — a
deterministic SHA-256 hash of `order_number + customer_part_no`. Same
idempotency goal, different mechanism. See the UPDATE section above.

### 4) Trigger policy for ETL refreshes

Decision needed:
- source-driven trigger only
- queue-driven trigger only
- hybrid trigger with stale queue fallback
- manual triggers with freshness guard

**Status**: superseded by the standalone-service pivot — this question
belongs to whatever the new service's scan-and-compare logic looks like,
not to an Apps Script trigger policy. Not yet re-decided in the new
architecture.

### 5) "What counts as new work?" rule

Decision needed:
- order number only
- order + item/part
- work order / line item
- date threshold / recency rule

**What actually happened**: order number + customer part number remains the
identity (matches `dedupe_key` in the SQL), but the *mechanism* for checking
"is this already on Monday" moves to a hash comparison rather than a sheet
lookup. See the UPDATE section above.

---

## Key notes from the meeting and current architecture (2026-09-14, historical)

### Working design principle (superseded)

The core architecture described here (review sheet as holding queue, manual
push) has been replaced — see the UPDATE section at the top of this file.

### Important product requirement introduced by Jennilyn

The next layer is not "more automation"; it is reference-data enrichment:
- part attributes from part number — **built and verified, see UPDATE above**
- reason code mapping from job note or review field — **built and verified, see UPDATE above**
- LCR generation with uniqueness and retry-safe behavior — **decided (hash-based), not yet built, see UPDATE above**
