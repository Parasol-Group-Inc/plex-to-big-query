# Vox Scorecard → Plex/BigQuery Readiness Map

## Goals resolved — 2026-09-04: every "% to Goal" tile is now buildable

The longest-standing gap on this map is closed. Goals were never a Plex
problem — a negotiated target isn't a transaction an ERP records — so the
answer was a maintained table, not a better query.

**`voxdatalake.<dataset>.scorecard_goals`**, created by hand in both datasets.
A Google Sheet is the source of truth; `deploy/goals_sheet_to_bigquery.gs`
pushes it to BigQuery on a trigger. **Not managed by Terraform, not created by
the ETL** — the pipeline only reads it, and the three views below **fail to
create if it is dropped**. Rebuild DDL and full column list:
`docs/reports/scorecard_goals.md`.

| New report | Feeds |
|---|---|
| `revenue_vs_goal_report` | "$4.7M Goal" + "88% to Goal" |
| `sales_vs_goal_report` | "$4.8M Goal" + "103% to Goal", per rep |
| `production_vs_goal_report` | Encap/Bottling/Labeling Actual-vs-Goal bars + "% TO GOAL" |

Long format (one row per metric/month/scope) because the three grains
genuinely differ — revenue is company-wide, sales is per rep, production is per
work centre group. A wide table can't hold that without NULL-padding or three
tables to keep in sync.

**The trap worth knowing: `scope` is an exact string join, and Plex disagrees
with the tile names.** Plex's work centre group is `Encapsulating`; the
scorecard tile says "Encapsulation". A mismatch yields a NULL goal, not an
error — it would read 0% forever with nothing explaining why. All three views
therefore expose `goal_without_sales` / `goal_without_production` so an
unmatched goal row surfaces instead of sitting invisible. Same applies to rep
names, including the literal `(no rep assigned)` bucket.

Verified against seeded placeholder goals, not just dry-run: Bottling
**3,000 of 5,000 (60%)**, Pre-Weigh **429 of 1,000 (43%)**. Built, **not yet
deployed** — needs `terraform apply` plus a job run.

## Build pass — 2026-09-04: everything that wasn't actually blocked

Second build pass after the Sep 1 meeting, this time targeting the rows the
readiness table marked 🎯 BUILDABLE NOW rather than the ones Jennilyn
corrected. **Five new views, zero new extractions** — every one reuses raw
tables this pipeline was already pulling, so nothing here required a new
Plex ODBC call or a live-schema pass.

| New report | Feeds |
|---|---|
| `sales_mtd_by_status_change_report` | Sales MTD detail (status-change grain, rep retained) |
| `sales_mtd_summary_report` | Sales MTD / YTD / % to Goal (actual side), by rep |
| `sales_revenue_run_rate_report` | "94% into month" + MTD Run Rate |
| `pipeline_plex_value_report` | Total Pipeline — **Plex half only** |
| `production_monthly_by_workcenter_group_report` | Production Actual vs. Goal (actual side), all groups |

**Three findings worth keeping, none of which needed new investigation:**

- **Sales MTD was already solved and nobody noticed.** Jennilyn's definition
  — first entry into "Pending Fulfillment," dated by the status change — is
  *exactly* the "Date Approved" calculation `sales_orders_report` has been
  running in production since before this scorecard effort started
  (`MIN(Change_Date)` over `Sales_v_PO_Change` where `PO_Status_Key = 2073`).
  `Sales_v_PO_Change` was already extracted; key 2073 was already confirmed
  live. The whole tile cost one view.
- **Reading her words literally avoided a pointless extraction.** For
  Pipeline she said *"the sales **orders** that have the status quote"* —
  an order status (`Sales_v_PO_Status.Is_Quote`), not `Sales_v_Quote`.
  Building on the Quote module would have meant extracting Plex's automotive
  quote-pricing tables (`Sales_v_Quote_Price` with `Escalation_Year`/`IRR`/
  `NPV`/`EBITDA`, `Sales_v_Quote_Part.Die_Cavity_Count`) that a supplement
  manufacturer almost certainly never populates — checked in the schema
  catalog before writing any SQL, not after.
- **The WIP ambiguity is now measurable rather than arguable.** Jennilyn gave
  two definitions in one conversation that don't produce the same number.
  `sales_order_value_by_status_report` now carries `is_pending_fulfillment`
  (strict reading is one filter away) and `also_counts_in_pipeline` (marks
  the dollars that double-count against Total Pipeline). She can pick by
  looking at both figures instead of re-deriving the rule from memory.

**Not deployed.** `terraform validate` passes and `fmt` is clean, but the
`gcloud`/`bq` credentials on this machine need an interactive
`gcloud auth login` (see Known friction in `CLAUDE.md`). Nothing here counts
as verified until each view is queried directly — a clean job exit code
doesn't confirm view creation on this project.


## Ground-truth update — 2026-09-01 Emilio/Jennilyn meeting

Everything below this section was written before Emilio and Jennilyn
Tockstein (the data scientist) actually sat down and walked the readiness
map tile by tile. That meeting is transcribed in full in
`meetings-reference/Sep-1/` (an Otter.ai transcript covering the first ~29
minutes, and a full Gemini transcript covering all 42) — read it before
trusting anything below that touches Revenue, WIP, "Total in Shipping,"
Out of Stock, or Pipeline, since several of those turned out to be built
on the wrong assumption. Everything else in this doc (Production, Quality,
Operations, the inventory/valuation views) was never discussed in that
meeting and stands as originally written.

**The core correction:** Revenue, "Total in Shipping," and WIP were all
built against Plex's **Sales module** (`Sales_v_PO`/`Sales_v_Release`
order value). Jennilyn was explicit, more than once, that real revenue has
to come from Plex's **Shipping module** instead: *"the shipping revenue
should just be the units that went out the door, the summed value of the
units that went out the door... the sales one I think will be less
reliable since it will not count in when we close things short or ship
partials."* That module (`Sales_v_Shipper`/`_Line`/`_Status`/`_Container`/
`_AR_Invoice`/`_Line_Release`) had never been extracted by this pipeline
before — found via a full-schema tree search, then live-confirmed the
same session with real data (see `CHANGELOG.md` 2026-09-01 for the
verified numbers: $25,500 real shipped revenue, $115,800 real
ready-to-ship value, $875,475 real WIP across 32 lines).

**Two other real, non-obvious findings from that verification pass:**
- **Plex booleans are not universally `-1 = true`.** `Sales_v_Shipper_Status.Shipped`
  and `Sales_v_PO_Status.Is_Quote`/`Cancelled_Status` all use `1 = true` —
  confirmed by checking real rows, not assumed. The `-1` convention
  confirmed elsewhere in this pipeline (`Part_v_Container.Active`, etc.)
  does not transfer automatically to a table nobody's queried before.
- **Vox's real Out-of-Stock rule** (Part_No `LIKE '33%'`, a real
  `Minimum_Inventory_Quantity` assigned on `Part_v_Part`, negative
  quantity-available, excluding Custom-classified parts) is precise and
  fully buildable from already-extracted or newly-added tables — a much
  better answer than the `inventory_risk_analysis_report.is_at_risk`
  guess this doc originally proposed.

**One tension surfaced, not resolved here:** Jennilyn's Pipeline/Forecast
plan keeps Monday.com permanently — *"it's a blend of the Monday data and
a little bit of the Plex data... Total pipeline will be a sum of the
Monday data plus the quotes and pending sales approval sales orders."*
That's a direct conflict with this project's working assumption that Plex
is replacing Monday outright. Flagging rather than picking a side — this
needs Emilio/Jennilyn to reconcile which plan is current.

See the updated readiness table below (§1, §5) for the corrected
per-tile status, and `docs/reports/` for the 6 affected reports' full
detail (2 rewritten in place, 4 new).

## Build status update — 2026-09-01 (superseded in part, see above)

Everything marked 🎯 BUILDABLE NOW below that didn't need a live-schema
guess has now been built, deployed, and verified against `PlexTest`:
`terraform apply` pushed all 6 touched `reports/*.yaml` configs and 9 new
SQL files to GCS (9 added, 12 changed, 0 destroyed), each affected test
Cloud Run job was manually triggered, and every new view was queried
directly per this repo's own house rule of never trusting a clean exit
code alone. See `docs/reports/` for each report's business-facing doc and
`CHANGELOG.md` for the full deploy + bugfix log.

**Interactive artifact for Jennilyn:** every tile on the live scorecard,
mapped to its Plex-native replacement with the real verified numbers below
— [Vox Migration Board](https://claude.ai/code/artifact/89e5211a-10c8-4a59-bf3d-c92f188c47a9).
Gets redeployed to the same link as more views ship or `PlexProd` gets its
own verification pass (this round only covered `PlexTest`).

Two real bugs were caught in the process, not just config drift — see
`CHANGELOG.md` 2026-09-01 for the full story: a naming collision broke
`sales_revenue_summary_report` on first deploy, and a copy-pasted join
pattern was silently dropping every row in `quality_fpy_by_area_month_report`
**and in the 4 already-deployed Daily Reports** the moment real production
data appeared on this tenant — fixed in all 5 files.

Built and verified (9 new `bq_view`s, 0 new Plex extractions — every one
reuses already-extracted, already-confirmed-live raw tables or an
already-deployed report view):

| New report | Replaces / feeds |
|---|---|
| `sales_revenue_summary_report` | MTD/YTD Revenue tiles |
| `sales_order_value_by_status_report` | Revenue in Shipping/WIP, Total in Shipping, Flow's WIP/Ready-to-Ship phases |
| `quality_cost_by_category_report` | Quality_Rework $ Cost, Quality_MatDestr $ Value (see the corrected finding below) |
| `quality_fpy_by_area_month_report` | YTD FPYs (FPY + provisional DPMO; Sigma intentionally not computed) |
| `mfg_job_open_caps_report` | MFG_Job "Open Caps," with the no-status-filter bug fixed |
| `bottling_job_open_report` | Bottling_Job "Open Bottles," same fix |
| `inventory_valuation_total_report` | Flow's "Inventory Val" phase (one total, not split by category) |
| `inventory_avg_daily_usage_report` | Inventory "Avg. Daily" (unverified against real data — see doc) |
| `inventory_top_quantity_report` | `vw_top_overstock`'s "Top Quantity" half only |

**Correction to the earlier pass:** Quality_Rework's `$ Total Cost` and
Quality_MatDestr's `$ Value` were originally flagged as "no Plex path."
That was wrong — `Quality_v_Problem.Cost` exists and is already exposed by
`quality_nonconformance_report`. What's genuinely still open is which live
`Problem_Category` string values mean "Rework" vs. "Material Destruction"
on this tenant — `quality_cost_by_category_report` surfaces the real
values instead of guessing at a literal string match.

**Deferred on purpose, not forgotten:** `vw_top_overstock`'s "Top Value"
ranking (needs a cross-pipeline raw-table dependency this repo hasn't used
before) and the Quotes/Pending-SOs dollar-value extension to the pipeline
funnel (needs `Sales_v_Quote_Part`/`Sales_v_Quote_Price_Cost` columns that
have never been checked live). Both need a live-schema pass before writing
SQL, not just more design work — see §2 and §5 below for the original notes.


Direct answer to the data scientist's question: **of everything feeding the
Vox Nutrition MTD Scorecard today, what's ready right now on the Plex side,
and what could feed it with more work?** Plex is replacing the Monday.com
sync that currently backs part of this scorecard (`voxdatalake.VoxScorecardsLive`,
see §0), so every source is in scope here — nothing is waved off as
"someone else's system" unless it's a category of data Plex genuinely has
no way to produce (an OSHA safety log, a CRM opportunity stage, a
negotiated sales goal — see the ❌ rows below).

Cross-references this repo's own `reports-list/*.md`, `spreadsheets/*.md`,
`reports/*.yaml`, and `reports/sql/*.sql` against the scorecard audit docs
in this folder (`Vox_Scorecard_Data_Catalog.md`, the Data Mapping workbook,
the navigator, the Field Guide). Every SQL-backed claim below was checked
against the actual `.sql` file, not inferred from a report name.

## Readiness key

- ✅ **READY NOW** — a deployed `bq_view` already has this number, in `PlexProd`/`PlexTest` today.
- 🎯 **BUILDABLE NOW** — the exact Plex tables/columns this needs are already extracted and used in a deployed view; getting this tile just needs a new (or extended) view, not new ETL work.
- ⚠️ **NEEDS A DECISION** — the data exists but a business-rule call (a status definition, a formula, a start-date choice) has to be made before the number means the right thing.
- ❓ **UNCONFIRMED SCHEMA** — the Plex table this would need has never been verified live on this tenant.
- ❌ **NO PLEX PATH** — this is not a category of data an ERP extraction produces, regardless of what replaces Monday. Needs a different kind of input (a maintained table, an external log).

## 0. One fact worth keeping in view

Six of the scorecard's sources (`vw_sales`, `vw_pipeline` ×2,
`vw_sales_mtd_vs_goal`, `vw_shipping_daily_snapshot`,
`shipping_revenue_daily`) currently live in `voxdatalake.VoxScorecardsLive`,
fed by a `monday-daily-sync-VoxScorecardsLive` Cloud Scheduler job
(`docs/EMAIL_SCHEDULE.md`) that this repo's Terraform has zero resources
for. That's *why* those sources are being replaced — not a reason to
leave them out of scope. Below, each one gets a real Plex-side answer
alongside everything else.

## 1. Revenue & Sales — more is ready than the original audit assumed

The original pass treated all revenue tiles as "Plex has no dollar column,
route to NetSuite." That's true for the *raw* `Sales_v_PO`/`Sales_v_PO_Line`
tables in isolation, but **`sales_orders_report`, `sales_orders_open_report`,
`sales_orders_pending_approval_report`, and `sales_revenue_by_rep_report` —
all four already deployed on `reports/sales_orders.yaml` — already compute
and expose a per-order dollar value.** Two fields, confirmed in
`reports/sql/sales_orders_view.sql`:

- `price_total` = `Part_v_Customer_Part_Price` (base tier) × `Sales_v_Release.Quantity`, per line — the computed proxy already used for `sales_orders_over_10k_report`.
- `order_total` = `Sales_v_PO.Master_Price` — a real field on the PO header, but flagged "where populated" in the over-10k report's own header comment, i.e. sparsely populated on this tenant. Treat `price_total` as the primary figure, `order_total` as a cross-check, not the other way around.

Neither includes tax or freight. That's the one caveat to carry into every
row below, not a reason to discard the whole approach.

| Scorecard tile / source | Status | Plex path |
|---|---|---|
| **MTD Revenue $** (Rev_MTD) | ✅ REBUILT + VERIFIED 2026-09-01 | **Corrected per the Jennilyn meeting** — now `sales_revenue_summary_report`, rolled up from the new `shipping_revenue_report` (`Sales_v_Shipper_Line.Quantity × Price`, shipped units only), not Sales-module order value. Verified real: September 2026, $25,500 shipping revenue, 17,000 units. |
| **YTD $ / vw_sales** | ✅ REBUILT + VERIFIED 2026-09-01 | Same `sales_revenue_summary_report` — sum across months instead of filtering to one. Only September has real data so far. |
| **Sales MTD vs. Goal / vw_sales_mtd_vs_goal** | ✅ REBUILT (actual side, shipping-sourced now) / ❌ NO PLEX PATH (goal side) | `sales_revenue_summary_report`'s `shipping_revenue` is the actual half. The `goal` half is a negotiated target — see the Goal row below. |
| **Revenue in Shipping / Total in Shipping** (Operational Health) | ✅ NEW + VERIFIED 2026-09-01 | **Corrected per the Jennilyn meeting** — a distinct concept from WIP, not the same view. New `shipping_pending_revenue_report`: ready-but-unshipped `Sales_v_Shipper_Line` quantity, falling back to the customer price list when Plex hasn't finalized a shipment price yet (decided 2026-09-01). Verified real: $115,800 ready value on 20,000 ready units (would be $0 without the price fallback — Shipper_Line.Price is 0 pre-shipment on this tenant). |
| **WIP** (Operational Health) | ✅ REBUILT + VERIFIED 2026-09-01 | **Corrected per the Jennilyn meeting** — `sales_order_value_by_status_report` no longer uses `Job_Status` at all: "we don't need the production status... if the order line isn't a quote, isn't cancelled, and isn't shipped, it's WIP." Verified real: 32 lines across 15 orders, $875,475 total — a far richer number than the Job_Status version ever produced. |
| **vw_pipeline — "NS Quotes" stage** | ✅ READY (status) / 🎯 BUILDABLE (value) | `sales_quotes_open_report` is deployed today for status/count. It has **no dollar field** — `Sales_v_Quote` itself doesn't carry one, but `Sales_v_Quote_Part`/`Sales_v_Quote_Price_Cost` do (already identified in `reports-list/sales.md`'s discount research) — extending the view to join those in is a bounded, scoped task, not a new investigation. |
| **vw_pipeline — "NS Pending SOs" stage** | ✅ READY | `sales_orders_pending_approval_report` — confirmed (via its own SQL header) to be the exact same field set as `sales_orders_report`, including `price_total`/`order_total`, just filtered to status key 2585. Nothing left to build here. |
| **vw_pipeline — "Opportunities" / "Forecast" stages** | ❌ NO PLEX PATH — **and per the 2026-09-01 meeting, not meant to be replaced** | Pre-quote CRM concepts; Plex tracks quotes and orders, not opportunities. Jennilyn's own plan: *"it's a blend of the Monday data and a little bit of the Plex data... Total pipeline will be a sum of the Monday data plus the quotes and pending sales approval sales orders."* This directly conflicts with this project's working assumption that Plex replaces Monday outright — flagged, not resolved. Needs Emilio/Jennilyn to confirm which plan stands. |
| **Vox_Looker_DB - Revenue** (transaction detail: Account, Date, Document Number, Period, Amount) | ✅ REPLACED 2026-09-01 | Superseded by `shipping_revenue_report` (§ above) — shipment-line grain, sorted by invoice date, with customer/part/part-group detail. Direct swap, correctly sourced now. |
| **Shipping daily metrics** (packages/cartons shipped, orders shipped, daily revenue — new ask from the 2026-09-01 meeting, not on the original dashboard) | ✅ NEW + VERIFIED 2026-09-01 | New `shipping_daily_report`. Verified real: 2026-09-01, 17 packages, 1 order, $25,500 shipped. |
| **MTD Run Rate** | 🎯 BUILDABLE NOW | Pure date math once MTD Revenue exists (`MTD Revenue ÷ days elapsed × days in month`) — no new data. |
| **Goal $ / % to rev goal's denominator / Production_Goals / every "Goal" field on the scorecard** | ❌ NO PLEX PATH | A negotiated S&OP target isn't a transactional record an ERP produces — this is true with or without Monday in the picture. Needs a small maintained table (owner, month, value, last-updated columns), which the scorecard's own Field Guide already recommends. Once that table exists, `% to Goal` is a trivial `SAFE_DIVIDE` against the actuals above. |
| **"Inventory Balance"** (Rev_MTD field) | ❓ UNCONFIRMED MEANING | The original sheet never made clear what this represents — flag for the report owner before scoping a Plex source; don't guess. |

## 2. Production — the single biggest win, zero new work

| Scorecard tile / source | Status | Plex path |
|---|---|---|
| **Production_Daily** (21 charts — highest usage in the whole report) | ✅ READY NOW | `encap_daily_report`, `blending_daily_report`, `labeling_daily_report`, `packaging_daily_report` — all deployed, `PlexProd`+`PlexTest`. Still 0 rows on this tenant (confirmed benign — no job has logged real production yet); confirm real rows exist before cutover so the new tiles don't look broken for an unrelated reason. |
| **Production_Goals** (Blending/Bottling/Encap/Labeling targets) | ❌ NO PLEX PATH | Same as every other Goal field above — a planning input, not an extraction. |

## 3. Quality

| Scorecard tile / source | Status | Plex path |
|---|---|---|
| **Quality_Deviation** | ✅ READY NOW | `quality_deviation_report`. Direct swap, richer than the sheet (adds Job/Part/Workcenter correlation). |
| **YTD FPYs** (9 charts — 2nd-highest usage) | ✅ BUILT, not yet deployed | `quality_fpy_by_area_month_report` (`reports/work_orders.yaml`) — FPY computed directly from `Part_v_Production`, no assumption needed. DPMO uses a documented `Opportunities_Per_Unit = 1` placeholder (decided 2026-09-01, trivial to change once Quality defines a real figure). **Sigma deliberately not computed** — a DPMO→Sigma conversion needs a proper statistical lookup, and a hand-rolled approximation risked being subtly wrong in cGMP-adjacent reporting; left out rather than guessed. |
| **Weekly/Monthly TAT Analysis** (Operations tab) | ⚠️ NEEDS A DECISION | `quality_turnaround_time_report` (`Closed_Date − Problem_Date` per NC) is deployed and close in spirit, but **not the same grain** — the sheet's `Item Stock Type`/`Performance Standard`/`Bonus Standard` fields describe a per-stock-type benchmark this view doesn't carry at all. Also open: whether `Problem_Date` or `Entered_Date` is the right TAT start (flagged in the SQL file itself). |
| **Quality_FGTAT / Quality_RawTAT** (Quality tab — do not confuse with the TAT Analysis sheets above; different grain, different tables) | 🎯 BUILDABLE NOW | `Quality_v_Checksheet`/Sample Plan (already extracted) covers lab-result turnaround on raw materials and finished goods. Not yet built as its own view. |
| **Quality_Rework** — status/count | ✅ READY NOW | `quality_nonconformance_report`'s `is_rework` flag. |
| **Quality_Rework** — `$ Total Cost` / **Quality_MatDestr** — `$ Value` | ✅ BUILT, not yet deployed (correction to the earlier pass) | `Quality_v_Problem.Cost` exists and is already exposed by `quality_nonconformance_report` — this was wrongly flagged "no Plex path" originally. `quality_cost_by_category_report` (`reports/quality_nonconformance.yaml`) rolls Cost up by `Problem_Category` + month without guessing which live string values mean "Rework"/"Material Destruction" — that mapping is the one remaining step, done by eyeballing real data once queryable. |

## 4. Operations / Jobs

| Scorecard tile / source | Status | Plex path |
|---|---|---|
| **MFG_Job** (Open Caps) | ✅ BUILT, not yet deployed | `mfg_job_open_caps_report` (`reports/work_orders.yaml`) — decided 2026-09-01: "open" = inverse of Completed/Cancelled/Hold status flags, matching the pattern already used by `labeling_open_work_orders_report`/`printing_open_work_orders_report`. Fixes the no-status-filter bug the scorecard's own audit flagged on the original tile. |
| **Bottling_Job** (Open Bottles) | ✅ BUILT, not yet deployed | `bottling_job_open_report` — same fix, same decision, `Workcenter_Group = 'Bottling'` instead of Encapsulation. |

## 5. Inventory & Safety

| Scorecard tile / source | Status | Plex path |
|---|---|---|
| **Inventory — Current Qty, On Order** | ✅ READY NOW | `part_on_hand_inventory_report` + `purchasing_open_orders_report`, already combined once in `mfg_job_schedule_inventory_availability_report`. |
| **OOS (Out of Stock)** | ✅ NEW — built + logic verified 2026-09-01 | **Corrected per the Jennilyn meeting** — this repo's earlier guess (`inventory_risk_analysis_report.is_at_risk`, 90-day-no-activity) was a different concept entirely. Real rule, given directly: `Part_No LIKE '33%'` AND `Part_v_Part.Minimum_Inventory_Quantity > 0` (a literal 0 doesn't count as "assigned," decided 2026-09-01) AND quantity-available (on-hand − allocated) `< 0`, excluding parts whose `Part_v_Part_Product_Type` indicates Custom. New `inventory_out_of_stock_report`. 0 rows today — `Sales_v_Release_Allocation` (needed for "allocated") is genuinely empty on this tenant, not a bug. |
| **Inventory — Avg. Daily (consumption rate)** | ✅ BUILT, unverified against real data | `inventory_avg_daily_usage_report` (`reports/inventory_activity.yaml`) — divides `inventory_activity_report`'s monthly `depleted_quantity` by days-in-month. This is a stronger lead than earlier notes in this repo suggested ("no confirmed source" was written about a narrower reorder-point/MSL concept, not this simpler daily-average ask). Caveat: `Part_v_Cell_Production`/`Part_v_Cell_Depletion` were confirmed **empty** on this tenant when the underlying view was built — schema-confirmed, not value-validated yet. |
| **vw_top_overstock** (ranked list) | ✅ BUILT (quantity only), not yet deployed | `inventory_top_quantity_report` (`reports/part_on_hand_inventory.yaml`) — `RANK()` over `part_on_hand_inventory_report` by on-hand quantity. The "Top Value" half is deliberately deferred: it needs a $ figure from a *different* pipeline's raw tables (`inventory_snapshot`'s cost tables), a cross-pipeline raw-table dependency this repo hasn't used before — held back rather than shipped with an untested pattern. |
| **Vox_Looker_DB - Flow, Quotes phase** | ✅ READY NOW | `sales_quotes_open_report`. |
| **Vox_Looker_DB - Flow, Pending SOs phase** | ✅ READY NOW | `sales_orders_pending_approval_report`. |
| **Vox_Looker_DB - Flow, WIP phase** | ✅ REBUILT + VERIFIED 2026-09-01 | `sales_order_value_by_status_report` (§1, corrected per the Jennilyn meeting — no more Job_Status). $875,475 real WIP value verified. |
| **Vox_Looker_DB - Flow, Ready to Ship phase** | ✅ NEW + VERIFIED 2026-09-01 | Now `shipping_pending_revenue_report` (§1) instead — Jennilyn described this as a distinct Shipper-module concept, not a flag on the WIP view. $115,800 real ready value verified. |
| **Vox_Looker_DB - Flow, Inventory Val phase** | ✅ BUILT (total only), not yet deployed | `inventory_valuation_total_report` (`reports/inventory_snapshot.yaml`) — one grand total per snapshot date, on top of the already-deployed `inventory_valuation_summary_report`. Splitting that total into WIP-vs-Finished-Goods-vs-Raw specifically is still blocked: `Cost_Sub_Type_Key` has no label lookup anywhere (`inventory_snapshot_view.sql`'s own comment says so) — fine if "Inventory Val" just means one total figure, not fine if it needs to be broken out by category. |
| **Cycle count - Dashboard** | ❓ UNCONFIRMED SCHEMA | `Cycle_Count`/`Cycle_Count_Line` are ❓ estimated-only in `catalog/plex_warehouse_views_catalog.md` — never even tree-confirmed. Needs a live schema check before this goes on anyone's "buildable" list. |
| **Safety (Last OSHA / Safe Days)** | ❌ NO PLEX PATH | OSHA recordable-incident tracking. No safety-incident object exists anywhere in this project's Plex schema catalogs, and none will appear regardless of what replaces Monday — this needs its own system of record. |

## 6. Recommended build order

Items 1–6 below are **done** (SQL + YAML + Terraform staged 2026-09-01, see
the build status banner at the top) — what's left is deployment and the
items that still need a live-schema pass or a business decision.

1. ~~Wire the 4 Daily Reports to Production_Daily's 21 charts.~~ Already deployed and live, predates this migration effort.
2. ~~Wire `quality_deviation_report`, `quality_nonconformance_report`'s rework flag, and the Inventory on-hand/on-order pair.~~ Already deployed, predates this effort.
3. ~~Build the MTD/YTD revenue rollup.~~ **Built** — `sales_revenue_summary_report`.
4. ~~Build the WIP / Ready-to-Ship / Total-in-Shipping $ views.~~ **Built** — `sales_order_value_by_status_report`.
5. ~~Decide the "open" status definition for MFG_Job/Bottling_Job.~~ **Decided and built** — `mfg_job_open_caps_report`/`bottling_job_open_report`.
6. ~~Build YTD FPY.~~ **Built** — `quality_fpy_by_area_month_report` (FPY + provisional DPMO; Sigma intentionally omitted, see §3).
7. **Deploy.** Run `terraform apply` to push the 6 updated `reports/*.yaml`/`test/*.yaml` configs and 9 new SQL files to GCS, then trigger (or wait for the next scheduled run of) the `sales_orders`, `work_orders`, `quality_nonconformance`, `inventory_activity`, `inventory_snapshot`, and `part_on_hand_inventory` pipelines. Verify each new view directly with `bq query`, per this repo's own house rule — a clean job exit code doesn't confirm view creation succeeded.
8. **Live-schema pass, then build:** the Quotes/Pending-SOs pipeline-funnel dollar value (needs `Sales_v_Quote_Part`/`Sales_v_Quote_Price_Cost` columns, never checked live), `vw_top_overstock`'s "Top Value" ranking (needs the cross-pipeline raw-table dependency question resolved first), and Quality_FGTAT/RawTAT (needs `Quality_v_Checksheet`/Sample Plan schema confirmed for this exact use).
9. **Re-verify `inventory_activity_report`/`inventory_avg_daily_usage_report` against real (non-empty) `Part_v_Cell_Production`/`Part_v_Cell_Depletion` data** once this tenant has some.
10. **Once `quality_cost_by_category_report` is queryable, map its real `Problem_Category` values** to "Rework"/"Material Destruction" and add a thin filtered view over it for each.
11. **Leave Goal figures, CRM Opportunities/Forecast, Safety, and Cycle Count off this migration's punch list** — none of them become Plex-buildable no matter what replaces Monday; they need a maintained table, a different data source, or a live schema check, respectively. See the note below on lighter-weight ways to capture some of these anyway.

## 7. On the ❌ NO PLEX PATH items — a Sheet/Form can still feed BigQuery

None of Goal figures, CRM Opportunities/Forecast, or Safety become
Plex-extractable — that's a category mismatch, not a missing view. But
"not from Plex" doesn't mean "stuck in Looker Studio's fragile Sheets
connector" either. The same pattern this repo already uses for other
non-ERP inputs works here: a Google Form (for one-at-a-time entries like a
new monthly Goal or an OSHA incident) or a small, deliberately-structured
Google Sheet (real header row, one value type per column — unlike the
current `Vox_Looker_DB - Safety`/`Cycle count` sheets' scrambled-header
problem) feeding BigQuery via Sheets-to-BigQuery sync or a simple scheduled
load, same as this pipeline already loads Plex data on a schedule. That
gets these values into the same `voxdatalake` project as everything else
here — with an audit trail (who entered it, when) that a hardcoded number
or a manually-copied cell never had — without pretending they're Plex data.
Worth scoping as a small, separate project once the Plex-native pieces
above are deployed; flagged here rather than built, since it's a Sheets/
Forms + BigQuery task, not a Plex ODBC one.
