# NetSuite → Plex Report Build Plan

Scope: the 7 reports flagged **High** confidence (exact/near-exact Plex name
match) in [`mapping/netsuite-report-mapping.md`](../mapping/netsuite-report-mapping.md#patterns-worth-noting-for-the-one-by-one-pass)
— #15, #29, #73, #74, #75, #76, #77. Goal: make each available as a
BigQuery table/view via the existing `reports/*.yaml` + `reports/sql/*.sql`
pipeline pattern (see [docs/CHEATSHEET.md § How to Add a New Report](CHEATSHEET.md#how-to-add-a-new-report)).

**Round 1 (2026-08-10): live schema confirmation.** Everything below was
verified with live `SELECT` queries against `vox.test.odbc.plex.com`, run
locally via `docker compose run` against the existing ETL image (see "How
this was confirmed" at the bottom). Round 1 resolved 5 of 6 investigation
items outright — including one (#15's `Change_Key` chain) that first looked
like a dead end and turned out to unlock #73/#74 for free.

**Round 2 (2026-08-10): `main.py` now supports multiple `bq_view`s per
report.** #73 came out of Round 1 with working SQL but no clean way to
deploy it (see its section below for why `extractions: []` was a bad idea).
Rather than add a second, Terraform-untracked scheduled-query mechanism,
`main.py`'s `bq_view` config was extended to accept a list — each view is
validated and created independently, with per-view error isolation so one
bad view doesn't block the others (`bq_view_configs`/`validate_bq_view` in
`main.py`). Fully backward compatible — verified all existing single-view
configs (`sales_orders.yaml`, `work_orders.yaml`, etc.) still parse and
validate unchanged. `reports/inventory_snapshot.yaml` now defines both
`inventory_snapshot_report` and `inventory_valuation_summary_report` from
one extraction run.

**Round 3 (2026-08-10): business questions answered.** The report requester
side answered all four open questions from Round 1/2 (see "Business
decisions — resolved" below). Net effect: #77 and #15/#73/#74 needed no
code change (the built default was confirmed correct). #76 needed a new
open-only view, added as a second `bq_view` entry in `sales_orders.yaml`
(reusing the `bq_view`-list support from Round 2). #75's answer was broader
than the report itself: **Plex's enabled UI reports are reference-only, not
a data source this pipeline can read** — "already covered by a Plex report"
is never a reason to skip building the BigQuery extraction, regardless of
which specific report is in question.

**Round 4 (2026-08-10/11): deployed to GCP.** All 7 reports are now live —
running Cloud Run jobs, on schedule, verified against real production
infrastructure (not just local Docker tests). Sequence, since it matters:
1. `purchasing_open_orders`, `part_obsolescence`, `inventory_activity` — all
   single-`bq_view` reports, compatible with the then-current image — deployed
   immediately via Terraform, triggered via the (then-authenticated) Cloud
   Run Admin API, and verified `succeededCount: 1` on each.
2. The new `main.py` (`bq_view`-list support) was built, pushed to Artifact
   Registry, and deployed to `plex-etl`/`plex-etl-test` via
   `gcloud builds submit --config deploy/cloudbuild.yaml` — its smoke-test
   step (runs `plex-etl-test` automatically) passed.
3. Only once that image was live: `reports/sales_orders.yaml`'s new list-form
   `bq_view` was pushed to GCS (via `terraform apply`), and the
   `inventory_snapshot` Cloud Run jobs + schedulers were created. Triggered
   both `plex-etl-test` and `plex-etl-inventory-snapshot-test` — both
   succeeded, and `sales_orders_open_report` (3 rows) confirmed alongside the
   original `sales_orders_report` (4 rows) from the same real execution.

Mid-deployment hiccup: the `gcloud` CLI session needed an interactive
re-login partway through (separate from the Application Default Credentials
Terraform uses, which stayed valid throughout) — this is why the deploy
happened in the two batches described above rather than one pass.

## Status summary — all deployed

| # | NetSuite Report | Status | Notes |
|---|---|---|---|
| 76 | Vox \| Open Sales Orders | ✅ **Deployed** | `sales_orders_open_report` — second entry in the live `sales_orders.yaml`'s `bq_view` list. Verified: 3 open / 4 total rows from a real Cloud Run execution. |
| 75 | Vox \| Open Purchase Orders | ✅ **Deployed** | `plex-etl-purchasing-open-orders(-test)`, schedule 6/7 AM UTC. Verified: 3 rows, correctly excludes a Cancelled test PO. |
| 77 | VOX \| Products to be discontinued | ✅ **Deployed** | `plex-etl-part-obsolescence(-test)`, schedule 8/9 AM UTC. Verified: runs cleanly (0 matching parts on test tenant currently). |
| 15 | Current Inventory Snapshot | ✅ **Deployed** | `plex-etl-inventory-snapshot(-test)`, schedule 12/1 PM UTC — combined job also produces #73/#74. Verified: runs cleanly end-to-end. |
| 74 | Vox \| Inventory Valuation Summary Transaction | ✅ **Same pipeline as #15** | — |
| 73 | Vox \| Inventory Valuation Summary | ✅ **Deployed** | Second view in the #15 job — `inventory_valuation_summary_report`. |
| 29 | Inventory Activity Detail Usage Per Month | ✅ **Deployed, one open validation item** | `plex-etl-inventory-activity(-test)`, schedule 10/11 AM UTC. Verified: runs cleanly against empty source tables — genealogy-vs-activity mapping still needs a real-data sanity check once `Part_v_Cell_Production`/`Cell_Depletion` have rows (can't be resolved by more querying against empty test tables). |

All prod jobs will run on their own schedule going forward — only the
`-test` variants were manually triggered to verify. See
`docs/NETSUITE_REPORT_BUILD_PLAN.md`'s Terraform for the exact schedule
times, and `docs/CHEATSHEET.md`'s Active Reports table (not yet updated
with these 4 — worth doing as a follow-up).

All 7 of the original High-confidence NetSuite reports have a scaffolded
pipeline and every design question has an answer. **None are deployed** —
no GCS upload, no Terraform Cloud Run job. That's the only thing left (see
"Suggested sequencing").

---

## #76 — Vox | Open Sales Orders → `sales_orders_open_report` — ✅ done

Confirmed: status-based filter, excluding Closed (2074) and Cancelled (2076)
— both confirmed in
[`catalog/plex_catalog_index.md`](../catalog/plex_catalog_index.md#sales_v_po_status--confirmed-status-workflow-vox-nutrition).

Implemented as a **new** view, `sales_orders_open_report`
([`reports/sql/sales_orders_open_view.sql`](../reports/sql/sales_orders_open_view.sql))
— same fields and raw tables as the existing `sales_orders_report`, with
`WHERE po.PO_Status_Key NOT IN (2074, 2076)` added. Not a new extraction:
it's the second entry in `reports/sales_orders.yaml`'s `bq_view` list
(depends on the Round 2 `bq_view`-list support in `main.py`). The original
`sales_orders_report` is untouched — it's a live production report used
for purposes beyond this NetSuite parity effort, so it wasn't repurposed
or filtered in place.

> ⚠ **Deploy-ordering hazard:** `reports/sales_orders.yaml` is the config
> for an **already-deployed, currently-running** production report
> (`plex-etl` / `plex-etl-test` Cloud Run jobs, 2 AM / 3 AM UTC). The
> currently-deployed container image predates the `bq_view`-list change —
> its `main.py` calls `.get()` on `bq_view` assuming a single mapping, which
> **would crash with an `AttributeError` on a list**. Do not push this YAML
> change to `gs://voxdatalake-report-configs/reports/sales_orders.yaml`
> until the new `main.py` is built and deployed to `plex-etl`/`plex-etl-test`
> first. This repo's local copy of the YAML has already been updated in
> anticipation of that deploy — it is safe sitting in git, just not yet safe
> in GCS.

---

## #75 — Vox | Open Purchase Orders → `purchasing_open_orders_report` — ✅ confirmed live

Plex has a literal **Open Purchase Orders** report (Purchasing / Purchase
Orders) — not in `enabled-reports.md` for this tenant, but that only gates
the Plex UI screen, not ODBC view access.

Confirmed live against `vox.test.odbc.plex.com` on 2026-08-10 (3 real test
POs returned):

| View | Role | Confirmed |
|---|---|---|
| `Purchasing_v_PO` | PO header (74 columns) | ✅ `PO_No`, `PO_Date`, `Supplier_No`, `PO_Status_Key`, `PO_Type_Key`, `PO_Key` |
| `Purchasing_v_PO_Status` | Status lookup | ✅ full 7-row workflow captured below |
| `Purchasing_v_PO_Type` | Type lookup | ✅ 156 columns, `PO_Type`/`PO_Type_Key` present |
| `Purchasing_v_Line_Item` | Line items — joins to PO **directly by `PO_Key`** | ✅ no separate "PO_Line" view on this side, unlike Sales |
| `Purchasing_v_Release` | Qty/due-date per line, joins via `Line_Item_Key` — **no `PO_Key` column at all**; its own `Part_Key` was 0/NULL on every row | ✅ join via `Line_Item_Key`; use `Line_Item.Part_Key` for the part |
| `Common_v_Supplier` | Supplier master | ✅ `Supplier_No`, `Name` |

**Confirmed `Purchasing_v_PO_Status` workflow** (live, Vox tenant, full list):

| Key | Label | Cancelled_Status | On_Order | Received |
|---|---|---|---|---|
| 3771 | New | 0 | 0 | 0 |
| 5559 | Pending Approval-NS | 0 | 0 | 0 |
| 3772 | On Order | 0 | 1 | 0 |
| 3773 | Approved | 0 | 0 | 0 |
| 3774 | Cancelled | 1 | 0 | 0 |
| 3775 | Received | 0 | 0 | 1 |
| 5523 | Denied | 1 | 1 | 1 |

No literal "Closed" status on this side. "Open" is defined as
`Cancelled_Status = 0 AND Received = 0`, not by matching status text/keys.

> **Resolved:** the enabled report "Purchase Order Releases Due" replaces
> "Open Purchase Orders" *inside Plex's own UI* — but enabled Plex UI
> reports are reference-only screens, not something this pipeline can read
> or export. "Already covered by a Plex report" doesn't apply here: this
> pipeline exists specifically to get the data into BigQuery, which no
> Plex UI report does regardless of overlap. Build it — confirmed.

Scaffold: [`reports/purchasing_open_orders.yaml`](../reports/purchasing_open_orders.yaml),
[`reports/sql/purchasing_open_orders_view.sql`](../reports/sql/purchasing_open_orders_view.sql).
Ready for a code review + deploy.

---

## #77 — VOX | Products to be discontinued → `part_obsolescence_report` — ✅ confirmed live, simpler than expected

The original plan expected a `Part_Status_Key` FK join from `Part_v_Part` to
`Part_v_Part_Status`. Live query found that's wrong: **querying
`Part_Status_Key` on `Part_v_Part` throws "Column not found."**
`Part_v_Part` carries status as an **inline text column, `Part_Status`**
(same pattern as `Part_v_Workcenter.Workcenter_Type` elsewhere in this repo).

Confirmed full `Part_Status` value list (live, Vox tenant): `''`,
`Initial Setup`, `Pending Approval`, `Active`, `Phase Out`, `Rejected`,
`Obsolete`.

This makes the report **trivial** — single-table filter, no joins:
`WHERE Part_Status IN ('Obsolete', 'Phase Out')`. **Confirmed**: include
both — "products **to be** discontinued" (future tense) covers Plex's
"Phase Out" status as well as fully "Obsolete" parts.

Scaffold: [`reports/part_obsolescence.yaml`](../reports/part_obsolescence.yaml),
[`reports/sql/part_obsolescence_view.sql`](../reports/sql/part_obsolescence_view.sql).
Ready for a code review + deploy.

---

## #15 / #73 / #74 — Inventory Snapshot & Valuation Summary (+ Transaction) — ✅ resolved

These three turned out to share one mechanism, discovered by tracing what
`Change_Key` actually resolves into (see memory / prior pass for why this
looked like a dead end at first).

**Confirmed join chain (live, 2026-08-10, verified returning real matched
rows — not just non-erroring):**

```
Part_v_Snapshot                              (header: Snapshot_Key, Snapshot_Date, Cost_Model_Key — POPULATED, ~hourly)
  → Part_v_Snapshot_Cost_Sub_Type_Breakdown  (pointer: Snapshot_Key, Change_Key — no inline values)
    → Part_v_Cost_Sub_Type_Breakdown_History (resolves Change_Key → Part_Key, Cost_Sub_Type_Key, Cost, Change_Date)
      → Part_v_Part                          (Part_No, Name)
```

Verified with a live join query — 10/10 sample rows returned real matched
`Part_Key`/`Cost` values (e.g. Part_Key 10658236, Cost_Sub_Type_Key 13688,
Cost 25.34722). Note the source column is `Change_key` (lowercase k) on the
History view specifically — confirmed live, easy to typo.

**Semantic caveat — resolved:** this is a **standard-cost snapshot**
(per-part cost-component values from Plex's Advanced Standard Costing
engine — matches "Inventory Snapshots"'s real module placement in Plex), not
a physical on-hand quantity count. **Confirmed with the report requester:**
the cost snapshot is the right data — no need to also source physical
on-hand quantity.

**Also unresolved:** no confirmed label lookup for `Cost_Sub_Type_Key`
(13687/13688/13690/... — no `Part_v_Cost_Sub_Type` view exists under that
name) — exposed as a raw key in both views below.

**Mapping to the three NetSuite reports:**

- **#15 Current Inventory Snapshot** and **#74 Inventory Valuation Summary
  Transaction** are both satisfied by the same detail-level output — one row
  per (snapshot, part, cost sub-type). Scaffold:
  [`reports/inventory_snapshot.yaml`](../reports/inventory_snapshot.yaml),
  [`reports/sql/inventory_snapshot_view.sql`](../reports/sql/inventory_snapshot_view.sql).
- **#73 Inventory Valuation Summary** is a `SUM(Cost)`-per-part rollup of the
  same raw data — [`reports/sql/inventory_valuation_summary_view.sql`](../reports/sql/inventory_valuation_summary_view.sql).
  Giving it its own `reports/*.yaml` with `extractions: []` would have made
  `main.py` log/email a spurious "all extractions returned 0 rows" warning on
  every run (see the `rows_fetched == 0` check in `main.py`) — instead,
  `main.py`'s `bq_view` config was extended to accept a list (Round 2, see
  above), so this view is now the second entry in `inventory_snapshot.yaml`'s
  `bq_view` list, built from the same one extraction run.

---

## #29 — Inventory Activity Detail Usage Per Month → `inventory_activity_report` — ✅ resolved

Plex's **Inventory Activity** UI report is already enabled for this tenant,
but no raw view named `Inventory_Activity` exists — the only match anywhere
is a stored procedure (`Inventory_Activity_Get`, `GlobalAllow: false`, not
usable by this SELECT-only pipeline).

**Round 1** probed three plausible raw transactional views — all confirmed
to exist but each one hop short of `Part_Key` (`Container_Transaction` →
`Container_Track` has no `Part_Key` either; `Inventory_Receipt` and
`Inventory_Shipment` headers have no `Part_Key`; their child `_Container`/
`_Lot` views, checked in the follow-up round, don't carry it either).

**Follow-up round found the real source, live 2026-08-10:**
`Part_v_Cell_Production` and `Part_v_Cell_Depletion` both expose `Part_Key`,
`Quantity`, and `Production_Date` **directly** — no extra join needed.
Production = quantity produced per part per date; Depletion = quantity
consumed/used per part per date (with `Cell_Production_Key` linking back to
what was produced). Aggregating `Cell_Depletion.Quantity` by part and month
maps directly onto "Inventory Activity Detail **Usage Per Month**."

**⚠ Caveat, unresolved:** these views live under Plex's "Advanced Inventory
Traceability — Product Genealogy" feature (the already-enabled reports
"Actual Depletion Including Cells" and "Upstream Traceability" use this same
data) — a genealogy/lot-tracing system, not the "Inventory Activity"
module's own machinery. Aggregating up to part/month plausibly reconstructs
the right numbers, but this is inference from column shape, not a confirmed
1:1 source. Both views were **empty (0 rows)** on the test tenant, so there
was no live sample data to sanity-check actual values against — **confirm
with the report requester that the resulting numbers look right** once real
data exists (test or prod) before treating this as done.

Scaffold: [`reports/inventory_activity.yaml`](../reports/inventory_activity.yaml),
[`reports/sql/inventory_activity_view.sql`](../reports/sql/inventory_activity_view.sql).

---

## Suggested sequencing

1. **Code review the `main.py` change** (Round 2) — the `bq_view` list
   support and its validation/error-isolation. Not yet run against real
   BigQuery this pass (only unit-checked and config-validated locally); the
   first live run against `PlexTest`/`PlexProd` will be its real test.
2. **Deploy the new `main.py` first**, before pushing the updated
   `sales_orders.yaml`/`sales_orders_test.yaml` to GCS — see the
   deploy-ordering hazard called out under #76. The other four new reports
   (#15/#73/#74 combined pipeline, #29, #75, #77) don't have this hazard
   since they're new Cloud Run jobs, not edits to an already-running one —
   but still need Terraform additions (new job + scheduler) per
   [docs/CHEATSHEET.md § How to Add a New Report](CHEATSHEET.md#how-to-add-a-new-report).
3. **Code review all seven** — schema-confirmed and design-confirmed now;
   get a second pair of eyes on the draft SQL before deploying.
4. Once test/prod data exists, spot-check #29's actual output against what
   the report requester expects (see below) — it's the one built entirely
   from empty tables with no live sample to validate against.

## Business decisions — resolved (2026-08-10)

- **#76** — status-based filter (exclude Closed/Cancelled). ✅ Implemented.
- **#75** — build it regardless of the enabled-report overlap; Plex UI
  reports are reference-only, not a data source this pipeline can read.
  ✅ No code change needed, already scaffolded.
- **#77** — include "Phase Out" alongside "Obsolete." ✅ Already the default
  in the scaffold, now confirmed.
- **#15 / #73 / #74** — the standard-cost snapshot is the right data;
  physical on-hand quantity is not needed. ✅ No code change needed.

## Still open — not resolvable by more querying

- **#29** — once real data exists (test or prod), confirm the
  `Cell_Production`/`Cell_Depletion` aggregation actually matches the usage
  numbers the requester expects. Both source views were empty during this
  investigation, so this is the one report built without any live sample to
  validate against.

## How this was confirmed (for anyone repeating this)

Live queries were run locally against `vox.test.odbc.plex.com` using the
existing ETL Docker image (`docker compose build`), with `main.py` imported
as a module (not run as the ETL job) so `cursor.description` could be read
even for empty tables — the packaged legacy single-view mode
(`OUTPUT_MODE=local`, `PLEX_VIEW=...`) skips CSV output entirely on 0 rows,
which hides column names for empty tables. The `main.py` `bq_view`-list
change (Round 2) was verified by importing `main` and calling
`bq_view_configs`/`validate_bq_view`/`load_report_config` directly against
every `reports/*.yaml` in the repo (old and new) — confirming old
single-view configs are unaffected and new list configs validate — plus a
`py_compile` syntax check. It was **not** run against a real BigQuery
dataset this pass (that needs `OUTPUT_MODE=bigquery` and a real GCP project,
out of scope for a local schema-confirmation session). No repo files were
changed by the diagnostic process itself; one-off scripts were used and
deleted afterward.
