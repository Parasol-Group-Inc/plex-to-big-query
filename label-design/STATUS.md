# Sep 14 brief and pending items

> **⚠ READ THIS SECTION FIRST.** Everything below "## UPDATE — 2026-09-16" is
> the original 2026-09-14 brief, kept for history. Large parts of it are
> **superseded** — the team decided to drop the Google Sheet entirely, which
> is a bigger pivot than anything the original pending-items list
> anticipated. Do not resume work from the original plan without reading the
> update first.

---

## UPDATE — 2026-09-25: the pivot fix was rolled back in prod, and is restored

The `NULLIF(TRIM(pa.Value), '')` pivot fix and the five new attribute columns
(`80c6431`, "shipped to prod" 2026-09-22) **were live for about an hour.** That
evening a `terraform apply` from `dev-scorecard` rewrote
`sql/label_design_view.sql` in GCS with the old view (2026-09-23 00:18 UTC).
That branch never had the commit. Prod ran the old view from then until
2026-09-25, emitting `''` instead of NULL and no bottle material, California
PDP, Prop 65, trademark or material-classification columns.

- **Fixed by merging `dev-label-design` up to `588fd2b` into `main`** (merge
  `7563821`) and applying from `main`.
- **Checked before the apply:** the view compiles against both datasets, has
  the same row counts as the live one, drops no columns and adds the five
  attribute columns.
- **`2eff172` (push service, test push job, BDM rep fields) is NOT on `main`
  yet.** Its terraform creates a scheduled job that fails until the Monday API
  key secret version exists and an image containing `label_design_service/`
  is built. Merge it once both are in hand; the deploy order is in the
  2026-09-24 section below it on `dev-label-design`.
- **The lesson** is in CLAUDE.md "Known friction": apply only from `main`, and
  read the plan for files you didn't touch.
## UPDATE — 2026-09-24 (later): the push service EXISTS now

`label_design_service/push.py` (see its docstring) is built and verified end
to end against PlexTest → `18432111755`, using tracked test data from
`scripts/label_design_test_data.py`. 7 `ZZTEST-LD-` items are on the board
for Ashley; `--delete` removes them. Terraform for a scheduled **test** job is
written and planned (3 to add) but **not applied**. Deploy order: `terraform
apply` → add the secret version → Cloud Build (the new job needs an image that
contains `label_design_service/`; tfvars' `image_url` is stale). Still open:
prod job + prod target board, part-attribute → Monday column mapping,
pre-cutover dedupe fallback, and whether the push should set a starting Design
Status. See CHANGELOG 2026-09-24.

## UPDATE — 2026-09-24: new board for Ashley, with real history on it

**"Plex Import" `18432111755`** (workspace "blank landing page") now holds a
full copy of Design & QA: 59 columns, 16 groups, 183 items, checked cell by
cell. It was made with `scripts/copy_monday_board.py --wipe-target`. Files
(1,071, ~3 GB) were **not** copied. **Jennette's `MONDAY_API_KEY` can write
here**, so this board, not `18430735110`, is the realistic target for the push
service. It's a point-in-time copy; nothing keeps it in sync with Design & QA.
**Re-running the copy script with `--wipe-target` deletes anything added to the
board since, test data included.** See CHANGELOG 2026-09-24.

---

## UPDATE — 2026-09-22 — read the Sep-21 fast follow first

Two decisions from the 2026-09-21 Emilio/Jennilyn call change what gets built,
and one of them partly undoes the attribute work that shipped the same day:
**part attributes stay in Plex and are not going into Monday**, and
**attributes will only be placed on "sevens" (label parts) while our queue
carries "nines" (finished goods)** — so the attribute pivot can never match
unless it hops through the BOM (`93… → 73…`, proven in `PlexProd`). The Monday
write blocker also has a named cause at last: the account holds a **CRM**
licence, not **Work Management**, which is why no permission change ever fixed
it.

Full write-up, with every figure checked against live data:
[`SEP21_FAST_FOLLOW.md`](SEP21_FAST_FOLLOW.md).

---

## UPDATE — 2026-09-21 (start here)

### The Plex attribute catalog doubled — Jennilyn added five more

Read straight from `raw_Part_v_Attribute`, and **identical in PlexProd and
PlexTest**, so this is real production configuration rather than test-tenant
scratch work:

| Key | Name | Assignments |
|---|---|---|
| 2383 | Size | 0 |
| 6537 | Allergen | 14 |
| 6538 | Hazardous | 14 |
| 6770 | Certifications | 0 |
| 7427 | **California PDP** | 0 *(new)* |
| 7428 | **Prop 65 Requirement** | 0 *(new)* |
| 7429 | **Trademark** | 0 *(new)* |
| 7431 | **Bottle Material** | 0 *(new)* |
| 7432 | Printing Material | 0 |
| 7435 | **Material Classification** | 0 *(new)* |

**Attribute keys are not stable.** `Printing Material` moved from `7427` to
`7432`, and `7427` is now `California PDP`. The pivot survived this only
because it joins on `Attribute_Name`, never on `Attribute_Key` — a key-based
pivot would have silently started reporting California PDP as the printing
material. **Keep it name-based**; never cache these keys anywhere.

All ten have `Use_Value_Table = 1` except `Size`, i.e. controlled dropdowns,
which is what the pass-through-untouched design already assumes.

**`Bottle Material` now exists Plex-side.** That resolves the one attribute
mapping there was a confident answer for: Ashley confirmed 2026-09-16 that
Monday's Bottle Material (container — HDPE/PET/Glass) and Plex's Printing
Material (label stock — white BOPP, metallic, laminated) are different
concepts, and Plex now carries both as separate attributes. Monday's
100%-hand-typed Bottle Material column finally has a real source. `Prop 65
Requirement` also now exists, which bears on the pending "Prop 65 → Regulatory"
rename — worth confirming with Jennilyn whether the Plex attribute is meant to
feed that column before she finalises it.

### All values are blank, and they were empty strings, not NULLs

28 assignments (14 parts × Allergen + Hazardous), **every one an empty
string** — verified against live BigQuery, not assumed:

```
Attribute_Key | Attribute_Name | cnt | n_null | n_empty | n_real
         6537 | Allergen       |  14 |      0 |      14 |      0
         6538 | Hazardous      |  14 |      0 |      14 |      0
```

That was a real defect. The pivot selected `pa.Value` raw, so every attribute
column emitted `''` rather than `NULL` — which reads downstream as "filled in,
but blank" and would have let the Monday push service overwrite a hand-entered
value with an empty one. **Fixed**: every branch is now
`NULLIF(TRIM(pa.Value), '')`, confirmed against live BigQuery to return `NULL`.

Also note: the previously documented proof example (`part_allergen = "Yes"` on
`Part_Key 11003458`) is **gone** — that part is no longer in the table at all,
so the test data has been reloaded since 2026-09-16. There is currently no
populated value anywhere to prove the pivot end-to-end against.

### Built this session

- `reports/sql/label_design_view.sql` — pivot rebuilt: `NULLIF(TRIM(...), '')`
  on all branches, and all ten attributes exposed (five new columns:
  `part_bottle_material`, `part_california_pdp`, `part_prop_65_requirement`,
  `part_trademark`, `part_material_classification`). Dry-run validated against
  live BigQuery.
- `docs/reports/label_design_report.md` updated to match.

**Not yet deployed** — needs `terraform apply` (SQL-only change; the view file
is shared, so no prod/test double-edit, unlike `extractions:` lists).

### Known gap

`Part_v_Attribute_Value` — the table holding each dropdown's allowed options —
**is not extracted at all**. Only two of Plex's four attribute tables are in
BigQuery. Fine today, but required the moment you want to validate a value or
pre-populate Monday dropdown options.

---

## UPDATE — 2026-09-16

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

> ⚠ **Superseded 2026-09-21** — `Printing Material` is now key **`7432`**, not
> `7427`; `7427` is now `California PDP`. Prod and test catalogs are identical
> and both hold ten attributes. See the 2026-09-21 update at the top.

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

> ⚠ **Superseded 2026-09-21** — there are now **ten** attributes, not five, and
> `Part_Key 11003458` (the proof example cited just below) no longer exists in
> the table. See the 2026-09-21 update at the top.

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

### 2026-09-16 evening meeting (Emilio/Jennilyn) — decisions and a real blocker root-caused

Full transcript/summary in `meetings-reference/sep-16/`. Directly relevant to
this project:

- **Workspace access granted, but doesn't fix the API blocker.** Jennilyn
  added Emilio to the Voxnutrition workspace and made him a board owner on
  "Plex Import Board," believing that was the cause of earlier access
  issues. Retried `scripts/replicate_board_columns.py` against the real
  board (`18430735110`) on 2026-09-17 — **still 403**, even for Jennette
  Boone's token despite her being `is_admin: true` and a board owner.
  **Root-caused precisely this time**: the API's error payload names the
  actual cause — `role: ms-authorization.basic_roles.account_product.non_member`.
  This is a **Monday seat/license type** (Viewer-tier seat, not a full
  Member seat), a completely different axis from board permissions or
  workspace membership — no amount of board-owner or workspace-member
  changes fixes it. Needs whoever manages Monday billing/seats (not
  necessarily Jennilyn) to upgrade the seat. **Decision: parked, not
  escalated yet** — continuing to build/test against "Tablero nuevo"
  (Emilio's personal dev sandbox, `18430931138`, already fully mirrored)
  instead of blocking further work on this.
- **Prop 65 → renamed "Regulatory," stays a plain TEXT column** (Jennilyn's
  action item, not yet confirmed done). Note: this is a *different* column
  from the existing status-type "Regulatory Status" dropdown already in
  `monday_board_catalog.md` — don't conflate the two.
- **Printing Material**: probably a new column if pushed to Monday at all —
  not finalized, pending an internal team meeting to decide which
  attributes actually get pushed.
- **Bottle size / Label size**: Jennilyn's own read is these probably
  **don't** need a Monday column — a signal against spending more effort
  mapping `part_size` there.
- **Allergens**: still open, same internal-meeting dependency. The
  attributes aren't even fully added to the Part in Plex yet on her side.
- **Strategic pushback, worth weighing before building more attribute
  plumbing**: Jennilyn wants her team to interact with Plex directly
  (unlimited seats, full version history) for label files/attributes
  rather than have everything synced to Monday "because they want to be
  lazy." She's pushing this internally. Could shrink how much
  attribute-to-Monday mapping is actually worth building.
- **New feature idea, well-scoped**: a BigQuery-generated **Part URL**
  column (direct link into the Plex part record) to cut down on manual
  searching — raised in the context of the same Reason Code
  near-duplicate mess already documented (Emilio independently noted ~47
  variants from memory; the real count is 33, see
  `monday_board_catalog.md`). Well received by Jennilyn/Ashley; not
  started.
- **Confirmed next concrete step from the meeting**: once real Plex data is
  flowing into a Plex-mirror board, send it to Jennilyn + Ashley for
  review before deciding on cutover — this is the actual reason the
  board-copy work exists.

**Separate workstream, same meeting** — this call also covered Vox
Scorecard topics (NetSuite/Celigo for revenue+inventory reporting, a
manual-data-app fix, First Pass Yield). That status does **not** live here;
see the Migration Board artifact and `vox_scorecard_sep16_meeting.md` /
`vox_scorecard_manual_data_app.md` in memory instead, per
[[project_two_workstreams]] — not duplicated in this file.

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
