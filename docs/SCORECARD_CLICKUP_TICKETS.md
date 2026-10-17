# Vox Scorecard — ClickUp ticket set

One ticket per scorecard element, ready to paste into ClickUp. Written to be
read by whoever picks the ticket up, not just the person who wrote it.

*Generated 2026-10-06 from `docs/SCORECARD_SANDBOX_FINDINGS.md`, the tile list
in `scripts/scorecard_status.ps1`, and a full PlexTest refresh run on
2026-10-05 (all six scorecard pipelines, all views verified created).*

**Row counts below are real** — what each view returned in `voxdatalake.PlexTest`
after that refresh. They tell you what you will actually see on screen when you
build the tile, which is usually the difference between "my chart is broken" and
"the test tenant has two shipment lines in it".

---

## How to read these

| Field | Means |
|---|---|
| **Reads** | The BigQuery view(s) the tile is built on, and its PlexTest row count on 2026-10-05. |
| **Done when** | The acceptance criteria. If you can't tick these, the ticket isn't done. |
| **Watch out** | A trap that has already bitten someone on this exact tile. |
| **Blocked by** | Another ticket, or a person. A blocked tile can still be *built* — it just can't be *trusted* until the blocker clears. |

**Status key:** 🟢 ready to build · 🟡 build it, but a number in it is a
placeholder · 🔴 blocked, needs data or a decision first · ⚪ not a Plex tile.

## Which dataset to build against

Design against **`voxdatalake.ScorecardSandbox`** — it has a full simulated
year under every tile, so charts have a shape to lay out. Validate against
**`voxdatalake.PlexTest`**, which has real but very thin data.

⚠ **The sandbox may need rebuilding before you start — see SC-00.**

---

## Triage summary

| # | Tile | Status | Rows |
|---|---|---|---|
| SC-00 | Rebuild the sandbox snapshot | 🔴 | — |
| **Revenue** | | | |
| SC-01 | MTD / YTD Revenue | 🟢 | 1 |
| SC-02 | Revenue by part group | 🟢 | 1 |
| SC-03 | Revenue detail | 🟢 | 2 |
| SC-04 | % into month and run rate | 🟡 | 1 |
| SC-05 | Revenue goal and % to goal | 🔴 | 1 |
| SC-06 | Shipping daily | 🟢 | 1 |
| SC-07 | Total in Shipping | 🟢 | 1 |
| **Sales** | | | |
| SC-08 | Sales MTD / YTD | 🟢 | 8 |
| SC-09 | Sales by rep | 🟢 | 8 |
| SC-10 | Sales goal and % to goal | 🟡 | 74 |
| SC-11 | Sales detail | 🟢 | 22 |
| SC-12 | Orders pending accounting approval | 🟢 | 2 |
| SC-13 | WIP | 🟢 | 20 |
| SC-14 | Total pipeline | 🔴 | 6 |
| SC-15 | Opportunities and forecast | ⚪ | — |
| **Production** | | | |
| SC-16 | Actual vs goal, all areas | 🟡 | 37 |
| SC-17 | Encapsulating daily | 🔴 | 0 |
| SC-18 | Bottling daily | 🟢 | 1 |
| SC-19 | Labeling daily | 🟢 | 2 |
| **Quality** | | | |
| SC-20 | FPY by area | 🟡 | 3 |
| SC-21 | Reworks (NCs) | 🟢 | 28 |
| SC-22 | NC cost by category | 🟢 | 11 |
| SC-23 | Deviations | 🟢 | 1 |
| SC-24 | Destruction $ / Rework $ | 🔴 | 4 |
| SC-25 | 30-day rolling TAT | 🟡 | 28 |
| **Inventory** | | | |
| SC-26 | Quantity available | 🟢 | 133 |
| SC-27 | Out of stock | 🟢 | 6 |
| SC-28 | Top quantity | 🟢 | 45 |
| SC-29 | Average daily usage | 🟢 | 2 |
| SC-30 | Inventory value | 🔴 | 1 |
| SC-31 | Cycle count accuracy | 🔴 | 0 |
| **Operations** | | | |
| SC-32 | Open caps | 🟢 | 3 |
| SC-33 | Open bottles | 🟢 | 1 |
| SC-34 | Safe days | 🔴 | 1 |

**Blocker tickets** (owned by people outside this team, each blocks a tile
above): SC-B1 … SC-B14, at the end.

---

# SC-00 — Rebuild the sandbox snapshot before building anything

**Status:** 🔴 Blocked — do this first
**Owner:** Emilio

The sandbox is built from a BigQuery time-travel snapshot, because live
PlexTest's tables stopped joining each other on 2026-09-24. **Time travel only
reaches back 7 days**, so the pinned instant in `build.SNAPSHOT` expired after
2026-09-30 and the copy step will now fail.

**Build:**

1. `python scripts/scorecard_sandbox/snapshot_check.py "<instant>" now` — try
   instants until you find one where every relation joins.
2. Set `build.SNAPSHOT` to it.
3. `python scripts/scorecard_sandbox/build.py` (~7.5 min).

**Done when:** `build.py` completes and the sandbox has a full year under every
tile again.

**Watch out:** `scripts/scorecard_sandbox/proposed_sql/` overrides are **not
deployed** — the sandbox uses them, production runs `reports/sql/`. If a tile
looks right in the sandbox and wrong in PlexTest, check whether an override is
doing the work. When a fix lands in `reports/sql/`, delete its override.

---

# Revenue

## SC-01 — MTD / YTD Revenue

**Status:** 🟢 Ready to build
**Reads:** `sales_revenue_summary_report` — **1 row** (Oct 2026: $4,444.97, 1,350 units)

**Build:** Two scorecard numbers — revenue month-to-date and year-to-date.

**Done when:** MTD matches the current month's `shipping_revenue`; YTD sums all
months in the current year.

**Watch out:** **YTD only covers the months Plex actually holds.** In PlexTest
that is October alone, so YTD and MTD are the same number — that is the data,
not a bug in your formula. Earlier history needs a one-off top-up before YTD
means anything in production.

---

## SC-02 — Revenue by part group

**Status:** 🟢 Ready to build — *newly unblocked*
**Reads:** `sales_revenue_summary_report`, `part_group` column — **1 group ("Capsule")**

**Build:** Revenue broken down by part group.

**Done when:** The chart shows named groups, with no "(no group)" bar carrying
the whole total.

**Watch out:** This tile read **one bar, "(no group)"**, for a long time. It
joined `Part_v_Part_Product_Group`, which has 0 rows in test *and* prod; the
names actually live in `Part_v_Part_Group` (13 groups). The fix needed a new
extraction, and **the 2026-10-05 run is the first time it has been confirmed on
real data** — `part_group` now reads "Capsule". If you ever see "(no group)"
return across the board, suspect `raw_Part_v_Part_Group` went missing, not your
chart.

---

## SC-03 — Revenue detail

**Status:** 🟢 Ready to build
**Reads:** `shipping_revenue_report` — **2 rows**

**Build:** Line-level revenue detail table.

**Done when:** Each shipment line shows with its value, ship date and invoice date.

**Watch out:** The view carries **both** ship date and invoice date, and the
month is grouped by **ship date**. Don't silently switch to invoice date in the
tile — it will disagree with every other revenue tile.

---

## SC-04 — % into month and run rate

**Status:** 🟡 Build it, but see the date bug
**Reads:** `sales_revenue_run_rate_report` — **1 row** (6 of 31 days, projection $22,965.65)

**Build:** "% into month" progress indicator plus the projected month-end revenue.

**Done when:** `pct_into_month` and `run_rate_projection` both render, and the
projection equals revenue ÷ days elapsed × days in month.

**Watch out — two things:**

1. **Calendar days, not working days.** A month-end projection built on calendar
   days will read optimistically if the remaining days are a weekend.
2. **`days_elapsed` is computed in UTC.** On the 2026-10-05 run it returned
   **6**, because the job completed 00:07 UTC — 18:07 Mountain. After roughly
   6pm Mountain the denominator advances a day early and the projection drops.
   Decide whether to fix this in the view or accept it; same UTC-vs-Mountain
   family as the retry-scheduler issue in `docs/OPEN_ITEMS.md` D2.

---

## SC-05 — Revenue goal and % to goal

**Status:** 🔴 Blocked
**Reads:** `revenue_vs_goal_report` — **1 row**
**Blocked by:** SC-B1 (real revenue target), SC-B2 (the FULL JOIN decision)

**Build:** Revenue against goal, with % to goal.

**Done when:** Every month that has a goal appears, and the goal is a real Vox
target rather than a labelled placeholder.

**Watch out — two separate problems, both live right now:**

1. **The goal is not a revenue goal.** It is a copy of the company-wide *sales*
   goal, seeded 2026-10-02 so the tile would render. Its `goal_note` says so in
   full. 12 months resolve, at $5,230,000 each.
2. **11 of those 12 months are dropped.** The view is built
   `FROM actual LEFT JOIN goal`, and revenue actuals exist only for October, so
   the tile returns one row against twelve goals. A goal month with no revenue
   currently shows *nothing* rather than 0%. Making it a FULL JOIN would match
   how `production_vs_goal_report` already behaves — that's SC-B2.

With today's data the tile reads **0.08% to goal** ($4,445 against $5.23M).
That is arithmetically correct and completely meaningless.

---

## SC-06 — Shipping daily

**Status:** 🟢 Ready to build
**Reads:** `shipping_daily_report` — **1 row**

**Build:** Daily shipping volume.

**Done when:** One point per ship date, over the selected range.

---

## SC-07 — Total in Shipping

**Status:** 🟢 Ready to build
**Reads:** `shipping_pending_revenue_report` — **1 row**

**Build:** Single number — value sitting in Shipping, not yet shipped.

**Watch out:** This is one of the tiles affected by the **"0 rows keeps
yesterday's data"** guard (see SC-B9). When the shipping floor legitimately
empties, the tile keeps showing yesterday's value and nothing says so.

---

# Sales

## SC-08 — Sales MTD / YTD

**Status:** 🟢 Ready to build
**Reads:** `sales_mtd_summary_report` — **8 rows** (Oct 2026)

**Build:** Sales month-to-date and year-to-date totals.

**Done when:** The totals match the sum of order lines for the period.

**Watch out:** The **totals** have always been right on this view; it was the
rep breakdown that was broken. See SC-09.

---

## SC-09 — Sales by rep

**Status:** 🟢 Ready to build — *newly confirmed working*
**Reads:** `sales_mtd_summary_report`, `sales_rep` column — **8 rows, 7 named reps**

**Build:** Sales broken down by sales representative.

**Done when:** Named reps appear with their values; "(no rep assigned)" is a
small minority, not the whole chart.

**Watch out:** Every sale on this tile used to read **"(no rep assigned)"** —
the views read `Sales_v_Order_Salesperson` where `Sort_Order = 1`, a table with
one row in all of test and none in prod. Vox actually records the rep on the
order (`Sales_v_PO.Inside_Sales`) and on the customer
(`Common_v_Customer.Assigned_To`). The fix is deployed and **the 2026-10-05 run
confirms it on real data** — 7 of 8 October rows carry real names (Kami Butcher
$57,340.50, Ashley Quintana $33,378.00, Julianni Pacheco $12,523.84, and four
others). One row is still unassigned, which is a genuine gap in Plex, not the
old bug.

A `sales_rep_source` column tells you which of the three sources each row
resolved from — useful if a rep ever looks wrong.

---

## SC-10 — Sales goal and % to goal

**Status:** 🟡 Build it, but do not sum the goal column
**Reads:** `sales_vs_goal_report` — **74 rows**
**Blocked by:** SC-B3 (the "Sales Representative" goal)

**Build:** Sales against goal, per rep and company-wide.

**Done when:** Per-rep % to goal renders, and the company-wide % uses the
company row's own goal.

**Watch out — this one has a real trap:** the company-wide goal is **its own row
with `actual = 0`**. Summing `goal_value` across rows double-counts it badly.
Company % to goal = total actual ÷ *that row's* goal, not ÷ the sum.

The view exposes `goal_without_sales` so an unmatched row surfaces instead of
silently reading 0%.

---

## SC-11 — Sales detail

**Status:** 🟢 Ready to build
**Reads:** `sales_mtd_by_status_change_report` — **22 rows**

**Build:** Line-level sales detail table.

**Done when:** Lines render with their rep column populated.

**Watch out:** The lines were always right; the rep column needed the SC-09 fix,
which is now deployed and confirmed.

---

## SC-12 — Orders pending accounting approval

**Status:** 🟢 Ready to build — *newly unblocked*
**Reads:** `sales_orders_pending_accounting_approval_report` — **2 rows**

**Build:** List of orders waiting on accounting approval.

**Done when:** Orders in a Deposit Review status appear.

**Watch out:** This tile was **always empty**, twice. It matched the status name
exactly (`= 'DEPOSIT REVIEW'`), and Plex split that into two statuses —
"Deposit Review (Initiate Payment Request)" and "(Bypass Payment Request)".
Fixed to `LIKE 'DEPOSIT REVIEW%'`. It had already died once before, in the same
way, and was fixed on 2026-09-11. **If Plex renames the status again this tile
goes quietly empty — it does not error.** It is also subject to the
"0 rows keeps yesterday's data" guard (SC-B9).

---

## SC-13 — WIP

**Status:** 🟢 Ready to build
**Reads:** `sales_order_value_by_status_report` — **20 rows**

**Build:** Order value broken down by status.

**Done when:** Each status shows with its total value.

---

## SC-14 — Total pipeline

**Status:** 🔴 Blocked
**Reads:** `pipeline_plex_value_report` — **6 rows**
**Blocked by:** SC-B4 (pipeline stage probabilities)

**Build:** Total sales pipeline value.

**Done when:** The Plex half renders with reps resolved, and the Monday half is
blended in with agreed probabilities.

**Watch out:** This tile is **deliberately a blend** — Plex covers quoted and
later stages, Monday covers pre-quote opportunities. The Plex half works and its
rep column got the SC-09 fix. The Monday half applies stage probabilities
(35/70/80/95%) that exist only as constants in a Monday view and have **no home
on the Plex side**. Don't invent them in Looker.

---

## SC-15 — Opportunities and forecast

**Status:** ⚪ Not a Plex tile — by design
**Reads:** Monday only

**Build:** Nothing on the Plex/BigQuery side. This tile is sourced from Monday
and stays there.

**Done when:** Confirmed with whoever owns the Monday board that it is wired up.
Close this ticket as out of scope for the data pipeline.

---

# Production

## SC-16 — Actual vs goal, all areas

**Status:** 🟡 Build it; the goals are placeholders
**Reads:** `production_vs_goal_report` — **37 rows** (4 for Oct 2026)
**Blocked by:** SC-B5 (real production goals), SC-B6 (does Pre-Weigh have a goal?)

**Build:** Actual production against goal, per work centre group.

**Done when:** Each area shows actual, goal and % to goal, against real targets.

**Watch out — three things:**

1. **The goals are placeholders.** The live board's 100M / 1.5M / 700K were
   seeded for all 12 months of 2026, labelled `PLACEHOLDER, NOT a Vox target`
   in `goal_note`. Against October's real output the percentages are absurd:
   Bottling 750 units against a 1,500,000 goal = 0.05%.
2. **`scope` is an exact string match, and Plex disagrees with the board.** The
   work centre group is **`Encapsulating`**; the scorecard tile says
   "Encapsulation". A mismatch yields a NULL goal, not an error, so it reads 0%
   forever. The `goal_without_production` / `production_without_goal` flags exist
   to surface this — put them somewhere visible.
3. **Pre-Weigh is producing with no goal at all.** 250 units in October,
   `production_without_goal = true`. It was never in the seeded set. See SC-B6.

---

## SC-17 — Encapsulating daily

**Status:** 🔴 Blocked — no data
**Reads:** `encap_daily_report` — **0 rows**

**Build:** Daily encapsulating output, scrap and operator.

**Done when:** Daily bars render for Encapsulating.

**Watch out:** **The view is not broken — Encapsulating has produced 0 units in
any month in PlexTest.** `production_vs_goal_report` confirms it with
`goal_without_production = true`. There *are* 3 open cap jobs (1,542,000 caps),
they just have no completed output. You cannot build or validate this tile
against PlexTest; use the sandbox, and re-check against PlexTest once the test
tenant has encapsulating production.

Also: **the employee column will be blank.** `Personnel_v_Employee.Common_Name`
is empty for all 132 employees in the tenant.

---

## SC-18 — Bottling daily

**Status:** 🟢 Ready to build
**Reads:** `packaging_daily_report` — **1 row** (750 units, 1 day with production)

**Build:** Daily bottling output and scrap.

**Done when:** Daily bars render with output and scrap.

**Watch out:** **Scrap read 0 everywhere** until recently — the views counted
scrap at `Rejected = -1`, an assumed convention, while real Plex writes `1`.
Now `Rejected != 0`, which holds either way. October's scrap is genuinely 0.0,
so don't treat a zero as proof the fix works; the one real rejected record in
the tenant is a Bottling Line 1 entry from 2026-09-24. Employee column blank,
as SC-17.

---

## SC-19 — Labeling daily

**Status:** 🟢 Ready to build
**Reads:** `labeling_daily_report` — **2 rows** (3,100 units across 2 work centres)

**Build:** Daily labeling output and scrap.

**Done when:** Daily bars render with output and scrap.

**Watch out:** Same scrap-convention and blank-employee notes as SC-18.

---

# Quality

## SC-20 — FPY by area

**Status:** 🟡 Build it; DPMO is a placeholder
**Reads:** `quality_fpy_by_area_month_report` — **3 rows**
**Blocked by:** SC-B7 (DPMO opportunities per unit)

**Build:** First-pass yield by area and month, plus DPMO.

**Done when:** FPY renders per area, and DPMO uses a real opportunities-per-unit
figure.

**Watch out:** **FPY is trustworthy; DPMO is not.** FPY is good ÷ total, so it
survived the scrap-convention bug. Rejected quantity and DPMO both read 0 under
that bug and are only now correct. DPMO additionally assumes **1 opportunity per
unit** as a hard-coded placeholder — the real figure has to come from Quality.

---

## SC-21 — Reworks (NCs)

**Status:** 🟢 Ready to build
**Reads:** `quality_nonconformance_report` — **28 rows**

**Build:** Nonconformance / rework counts.

**Done when:** NCs render by period.

---

## SC-22 — NC cost by category

**Status:** 🟢 Ready to build
**Reads:** `quality_cost_by_category_report` — **11 rows**

**Build:** NC cost broken down by category.

**Done when:** Categories render with their costs.

**Watch out:** Costs here inherit the same problem as SC-24 — Quality types
amounts into the NC description instead of Plex's Cost field, so real cost
figures are frequently 0.00.

---

## SC-23 — Deviations

**Status:** 🟢 Ready to build
**Reads:** `quality_deviation_report` — **1 row**

**Build:** Deviations, with their linked NC.

**Done when:** Deviations render by `deviation_month`, with the NC column
populated where a link exists.

**Watch out:** The linked NC **never showed** — the view joined the classic
`Quality_v_Problem`, which is permanently empty, instead of
`Quality_v_Problem_2`, where Vox's NCs actually live. Fixed and deployed. The NC
column will **still look blank on PlexTest, correctly**: the one real link
belongs to a deviation that has since been deleted from Plex, and today's only
deviation has no NC linked. Validate this one in the sandbox, where 49 of 151
deviations carry an NC.

The view gained `deviation_month` (by add date) so the tile doesn't have to pick
between the two candidate dates.

---

## SC-24 — Destruction $ / Rework $

**Status:** 🔴 Blocked
**Reads:** `quality_disposition_cost_report` — **4 rows**
**Blocked by:** SC-B8 (Quality to use Plex's Cost field)

**Build:** Money lost to destruction and to rework.

**Done when:** The amounts come from Plex's Cost field and the missing-cost flag
is near zero.

**Watch out:** **This tile works in the sandbox only because costs are modelled
there.** On real records `Cost` is 0.00, because Quality types the amount into
the NC *description* instead. The view's missing-cost flag now counts NULL-or-0
on Scrap/Rework records so the gap is visible — surface that flag on the tile,
or the number reads as "we destroyed $0 this month".

Blanks are now split into open / closed-no-material / closed-disposition-missing
rather than lumped into "(not yet dispositioned)".

---

## SC-25 — 30-day rolling TAT

**Status:** 🟡 Build it; the standards are placeholders
**Reads:** `quality_turnaround_time_report` — **28 rows**
**Blocked by:** SC-B10 (real TAT standards and grouping)

**Build:** 30-day rolling turnaround time against the Performance and Bonus
standards.

**Done when:** Met/missed is judged against real Vox standards on the right
grouping.

**Watch out:** **The clock was calendar days against work-day standards.** Fixed
— the view now carries work-day columns for both clocks and met/missed uses
them. **Mon–Fri only; there is no holiday table**, so a week with a holiday
reads slightly optimistic. The standards themselves are still placeholders in
both datasets, and all 28 records currently match a placeholder standard rather
than reading "none set" — so the tile will look healthy and mean nothing until
SC-B10 closes.

---

# Inventory

## SC-26 — Quantity available

**Status:** 🟢 Ready to build
**Reads:** `inventory_available_to_sell_report` — **133 rows**

**Build:** Quantity available to sell (on-hand less demand).

**Done when:** Parts render with available quantity.

---

## SC-27 — Out of stock

**Status:** 🟢 Ready to build
**Reads:** `inventory_out_of_stock_report` — **6 rows**

**Build:** Parts that are out of stock.

**Done when:** Out-of-stock parts list correctly.

**Watch out:** **One part number can appear twice**, because it has two
`Part_Key`s. Decide whether to dedupe in the tile or show both — but don't be
surprised by it.

---

## SC-28 — Top quantity

**Status:** 🟢 Ready to build
**Reads:** `inventory_top_quantity_report` — **45 rows**

**Build:** Highest-quantity parts on hand.

**Done when:** Parts rank by quantity.

**Watch out:** **Quantity only — not value.** Don't let this be read as "our
biggest inventory"; that is SC-30.

---

## SC-29 — Average daily usage

**Status:** 🟢 Ready to build
**Reads:** `inventory_avg_daily_usage_report` — **2 rows**

**Build:** Average daily usage per part.

**Done when:** Usage renders per part, with its unit shown.

**Watch out — do not sum this across parts.** It is per part, **in each part's
own unit**, so a total adds capsules to bottles. The view deliberately converts
nothing; use the `unit` column as a filter.

The current month used to divide by all its days and so read low; it now divides
by days elapsed through today. `days_in_period` and `is_month_in_progress` are
exposed so the tile can say which it is.

---

## SC-30 — Inventory value

**Status:** 🔴 Blocked — no trend, and $0 in PlexTest
**Reads:** `inventory_valuation_total_report` — **1 row**
**Blocked by:** SC-B11 (month-end on-hand source)

**Build:** Total inventory value, ideally with a trend.

**Done when:** A current value renders and, if a trend is wanted, month-end
points exist to plot.

**Watch out — three things:**

1. **It used to read about $77 for the entire building.** It summed per-unit
   standard costs with no quantity. Now it is on-hand × per-unit cost at the
   snapshot: $2.76M in the sandbox.
2. **In PlexTest it is $0.** Only 5 parts are costed and none of them are on
   hand; 57 on-hand parts are uncosted. The `uncosted_on_hand_part_count` column
   shows this — put it on the tile.
3. **There is no trend and cannot be one yet.** `Part_v_Snapshot` holds cost but
   **no quantity**, so earlier snapshots give a NULL value, not old stock at old
   costs. A trend needs month-end on-hand captured somewhere. The interim answer
   for this number is NetSuite anyway.

---

## SC-31 — Cycle count accuracy

**Status:** 🔴 Blocked — source data has no dates
**Reads:** `part_cycle_count_report` — **0 rows**
**Blocked by:** SC-B12 (Warehouse to record count dates)

**Build:** Per-location cycle count accuracy by month.

**Done when:** Months with counts show an accuracy percentage, and months
without counts show "no counts" rather than 0%.

**Watch out — the tile is empty for a reason nobody had identified:**
`raw_Part_v_Cycle_Inventory` holds **17 records, and all 17 have a NULL
`Cycle_Inventory_Date`**. The view's only filter is `IS NOT NULL`, so everything
drops. This is **not** the "counting is lumpy, some months have none" case the
view was designed around — the counts exist, they just carry no date.

Three further things for when it does populate:

- **Accuracy is a per-location hit rate**, deliberately not quantity-weighted —
  that is Vox's own definition, confirmed 2026-09-11.
  `accuracy_pct_qty_weighted` sits beside it unused; the two diverging means
  misses are concentrated in big locations.
- **`locations_counted = 0` must be checked before showing a percentage at all.**
  A month with no counts is normal and must not read as 0% accurate.
- There are **no location names** — `Location` is an integer and no location
  master is extracted.

---

# Operations

## SC-32 — Open caps

**Status:** 🟢 Ready to build
**Reads:** `mfg_job_open_caps_report` — **3 rows**

**Build:** Open encapsulating jobs and their quantities.

**Done when:** Open cap jobs render with quantities.

**Watch out:** This filtered on `Name LIKE 'Encapsulation%'` and so **missed
"Schedule Encapsulation"**, which is where the real open jobs sit — not an empty
pseudo-centre. Now filtered by `Workcenter_Group = 'Encapsulating'`, matching
how Open bottles already worked. PlexTest went **200,000 → 1,542,000 open caps**
on that fix. Subject to the "0 rows keeps yesterday's data" guard (SC-B9).

---

## SC-33 — Open bottles

**Status:** 🟢 Ready to build
**Reads:** `bottling_job_open_report` — **1 row**

**Build:** Open bottling jobs and their quantities.

**Done when:** Open bottling jobs render with quantities.

**Watch out:** Subject to the "0 rows keeps yesterday's data" guard (SC-B9).

---

## SC-34 — Safe days

**Status:** 🔴 Blocked — needs building, and the data is questionable
**Reads:** `safety_incidents` (table, not a view) — **1 row**
**Blocked by:** SC-B13 (who logs incidents)

**Build:** **No view computes Safe Days — Looker has to.** Days since the latest
incident date: today − `MAX(incident_date)`.

**Done when:** The tile computes safe days in Looker from the table's latest
date.

**Watch out — two things:**

1. **An empty log reads as a clean record.** Nobody has been named as the person
   who logs incidents, so a long "safe days" streak may mean nothing was
   recorded rather than nothing happened. Caveat the tile.
2. **The one row in PlexTest is dated 2026-10-02, not the 7/23 recordable** the
   open-items list describes. That would make Safe Days read ~4, not ~75.
   **Confirm whether that row is a real incident or an app test entry before
   anyone reads this tile.**

---

# Blocker tickets

These are not tiles. Each is a decision or a piece of data owned by someone
outside this team, and each blocks at least one tile above.

| # | Blocker | Owner | Blocks | What's needed |
|---|---|---|---|---|
| SC-B1 | **Revenue goal is a copy of the sales goal** | Jennilyn | SC-05 | Confirm whether a separate revenue target exists. Enter real figures in the Manual Data app's Revenue tab — they override the placeholder automatically. |
| SC-B2 | **`revenue_vs_goal_report` drops goal months with no revenue** | Decision (team) | SC-05 | Decide whether a goal month with no revenue should read 0%. That means changing `LEFT JOIN` to `FULL JOIN`, matching `production_vs_goal_report`. |
| SC-B3 | **A goal scoped "Sales Representative"** matches no person | Jennilyn | SC-10 | Reassign it to a real rep or delete it. |
| SC-B4 | **Pipeline stage probabilities (35/70/80/95%)** have no Plex-side home | Jennilyn | SC-14 | Decide where these live. |
| SC-B5 | **Production goals are placeholders** | Jennilyn | SC-16 | Enter real monthly goals for Encapsulating, Bottling and Labeling in the app's Production tab. |
| SC-B6 | **Pre-Weigh is producing with no goal** | Jennilyn | SC-16 | Does Pre-Weigh have a goal? Do any other areas? Found in the 2026-10-05 data: 250 units in October, flagged `production_without_goal`. |
| SC-B7 | **DPMO opportunities per unit is hard-coded to 1** | Quality | SC-20 | Supply the real figure. |
| SC-B8 | **Destruction $ / Rework $ typed into NC descriptions** | Quality | SC-24, SC-22 | Use Plex's Cost field so `Cost` stops being 0.00. |
| SC-B9 | **A table that goes to 0 rows keeps yesterday's data** | Decision (team) | SC-07, SC-12, SC-32, SC-33 | Deliberate guard against transient ODBC failures, but the ETL can't tell a failure from a genuinely empty result, so an emptied tile silently shows stale rows. Keep the guard but mark staleness — e.g. a `last_nonempty_at` column or a line in the run email. |
| SC-B10 | **TAT standards are placeholders, and the grouping is unknown** | Jennilyn / Quality | SC-25 | Supply real Performance/Bonus day counts, and say which grouping applies — the old sheet's bottle types, or Plex's stock types. Edit `turnaround_standards` in BigQuery. |
| SC-B11 | **Inventory value has no month-end trend** | Decision (team) | SC-30 | `Part_v_Snapshot` has no quantity column. Either store a daily on-hand copy or find a Plex inventory-history source. The interim answer is NetSuite. |
| SC-B12 | **All 17 cycle-count records have a NULL count date** | Warehouse | SC-31 | Record `Cycle_Inventory_Date` when counting, or identify where the date is actually stored. |
| SC-B13 | **Nobody is named as the person who logs safety incidents** | Jennilyn | SC-34 | Name the owner. Also confirm whether the 2026-10-02 row in PlexTest is real. |
| SC-B14 | **Lab TAT target ("within goal") has no home** | Jennilyn | — | Decide where it lives. |

---

## Two more that aren't tiles but will bite you

- **The PlexTest tenant's master data changes between days.** On 2026-09-24 it
  went from 182 customers and 2,120 priced customer parts to 24 customers and
  312 unpriced ones. **Test numbers from different days are not comparable**, and
  a tile that "broke" overnight may just be the tenant changing under you.
- **Prod and test are separate hand-maintained configs.** Any change to an
  `extractions:` or `bq_view:` list must be made in **both**
  `reports/<pipeline>.yaml` and `reports/test/<pipeline>.yaml`. Editing only one
  and running the other job looks like a successful deploy and is not.
