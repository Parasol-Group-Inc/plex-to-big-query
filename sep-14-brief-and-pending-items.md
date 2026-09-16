# Sep 14 brief and pending items

> **⚠ READ THIS SECTION FIRST.** Everything below "## UPDATE — 2026-09-16" is
> the original 2026-09-14 brief, kept for history. Large parts of it are
> **superseded** — the team decided to drop the Google Sheet entirely, which
> is a bigger pivot than anything the original pending-items list
> anticipated. Do not resume work from the original plan without reading the
> update first.

---

## UPDATE — 2026-09-16 (start here)

### Terraform drift — RESOLVED same day, verified in prod

`terraform apply` ran (2 added, 1 changed, 2 destroyed — the destroys were
just content-type metadata fixes on two objects from earlier manual
`gcloud storage cp` pushes, re-uploading the same content). `terraform plan`
immediately after: **"No changes. Your infrastructure matches the
configuration"** across the whole project, not just label_design.

**Then actually verified, not just trusted**: ran `plex-etl-label-design`
(prod, for the first time with the new config) and checked the logs —
`Created/replaced BigQuery view voxdatalake.PlexProd.label_design_report`,
exit 0 for real this time. `label_design_report` in `PlexProd` exists and is
queryable (0 rows — benign, no current order matches the filter, same as
test).

**Bonus finding while checking**: prod's `Part_v_Attribute` has the **same
Attribute_Keys** as test's (`2383` Size, `6537` Allergen, `6538` Hazardous,
`6770` Certifications) — these four are real production Plex configuration,
not test-tenant fabrications. Only `Printing Material` (`7427`) exists in
test so far, not yet promoted to prod.

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
neither; is Allergen brand new.

**Partial answer from Ashley, 2026-09-16 (later)**: Bottle Material (Monday)
holds HDPE/PET/Glass — the bottle's own container material. Printing
Material (Plex) is label stock type — white BOPP, metallic, laminated, etc.
**These are confirmed different concepts** — Printing Material does not feed
Bottle Material, and has no confirmed Monday destination yet. Ashley was
unsure on Size/Allergen/Hazardous/Certifications and tagged Jennilyn for
those — **still awaiting Jennilyn's answer on 4 of the 5 attributes.** Pick
this up first next session if still unanswered.

### A real bug found and fixed this session, worth remembering

`reports/sql/label_design_view.sql` had an **orphaned `),`** left over from
the 2026-09-15 release-collapse edit — that edit's own dry run never
actually completed (blocked by the `gcloud auth login` wall) and was only
read through by eye afterward, which missed it. Caught this time with a
**local paren-balance check** before building anything on top of it, then
confirmed fixed against live BigQuery. Lesson for next session: **a
"looks right on rereading" is not verification** — either run it live, or at
minimum run a mechanical check (paren balance, etc.) before trusting it.

### Deployment state as of 2026-09-16 (end of day)

- **Both prod and test fully in sync and verified.** `terraform apply` ran;
  `terraform plan` confirms zero drift project-wide. Both
  `plex-etl-label-design` and `plex-etl-label-design-test` have been run
  since, and `label_design_report` exists and is queryable in **both**
  `PlexProd` and `PlexTest`.
- No code exists yet for the standalone service, the audit table, or the
  hash-based LCR — those are documented decisions only.

### Concrete next steps, in order

1. ~~Resolve the terraform drift~~ — **done, verified in prod, 2026-09-16.**
   Re-confirmed 2026-09-16 (later): `terraform plan` still shows zero
   project-wide drift.
2. ~~Get an answer from Ashley/Jennilyn~~ — **partially done.** Ashley
   confirmed Printing Material ≠ Bottle Material (different concepts, no
   confirmed Monday destination for Printing Material yet). Still waiting
   on Jennilyn for Size/Allergen/Hazardous/Certifications.
3. Confirm the 14-day-window/cutover edge case fix (fall back to text
   comparison for pre-10/19 rows).
4. Start building the standalone service (Cloud Run Job + Scheduler) — the
   Reason Code parser and Part Attribute columns are ready to be consumed by
   it the moment it exists. **In progress, 2026-09-16 (later):** a test
   board ("Tablero nuevo," `18430931138`, Emilio's personal Monday dev
   sandbox) was built out to structurally mirror prod, specifically so the
   service's Monday-write logic can be tested end-to-end before ever
   touching prod. Full detail in
   `label-design/monday_board_catalog_tablero_nuevo.md`. Real blockers hit
   and resolved along the way:
   - The originally-intended target, "Plex Import Board" (`18430735110`,
     the real Voxnutrition workspace), turned out to be write-restricted
     for the only working API token today (Jennette Boone's personal
     token could read it but not create columns — 403 on every attempt).
     Pivoted to the dev sandbox board instead; **the real target board
     still needs a token with actual write access before the service can
     be tested against it directly**, let alone deployed at it.
   - `.env` had real problems worth knowing about: a duplicate
     `MONDAY_API_KEY` line silently shadowed by env-loader last-value-wins
     behavior, and board-id variables that didn't match
     `monday_board_catalog.md` — both fixed and reconciled against the
     live API, not guessed.
   - Two Monday API bugs found while building the replication script (see
     `CHANGELOG.md` 2026-09-16 (later) and the script's own docstring) —
     worth reading before writing any other Monday column-creation code.
   - The service's Monday write, whenever it's built, should look up
     status-column option indices by label text per-board at runtime, not
     hardcode index numbers — confirmed necessary since even the *option
     set* differs between prod's Reason Code (33 options) and the test
     board's (deliberately only 6).
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
