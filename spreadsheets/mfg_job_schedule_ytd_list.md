# MFG Job Schedule — "YTD List" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** ✅ Built 2026-08-26, unified with Done YTD/Done 2025/2025 List
  into one continuous `mfg_job_schedule_success_metrics_report` (see "Built
  2026-08-26" below). Real data analyzed (108 real rows + a long tail of
  blank placeholder rows). **This tab is the row-level source data behind
  "YTD Gate Stats"** — mapping it reverse-engineered the "Successful"
  formula that Gate Stats' own headers didn't specify.

## What it is

One row per completed blend/batch (not one row per job — see grain note
below): Date, Product, Yield, Product Type (stock/custom), Days to Mfg,
Deviation/NCs? (YES/NO), Success Rating, then a trailing Month column
(`YYYY-MM`) that Gate Stats groups by.

**Grain note:** several Date+Product pairs repeat with *different* Yield
values (e.g. `7/23/2026 Taurine` appears twice — 99.3% and 98.70%;
`6/26/2026 Collagen I,II,III,V,X 1800mg` appears 3 times — 131.63%, 65.27%,
and a third row elsewhere at 100.30%/100.43%/99.31% on other dates). This
lines up with the "# of Blends" column seen on the FG Testing Pending tab
— a job can have multiple blend sub-batches, each yielding independently.
**This tab's grain is one row per blend/batch, not one row per job** —
important for any future SQL: aggregate at the blend/batch level, not
`Part_v_Job`.

**Data-quality note:** the file has ~200 trailing blank rows with only a
`Month = 1899-12` value — the classic spreadsheet artifact for a
date-formatted cell with no real value (Excel/Sheets epoch). Not a data
gap, just noise to filter out (`WHERE Date IS NOT NULL`).

## Major finding — the "Successful" formula, reverse-engineered

`mfg_job_schedule_ytd_gate_stats.md` flagged "how do Yield/Deviations/TAT
combine into pass/fail" as a business rule Emilio would need to define.
Checking real values in this tab against the exact goals stated in Gate
Stats' own headers reveals the formula, validated against ~15+ rows with
zero contradictions:

**`Success Rating = (gates passed) / 3`**, where the 3 gates are:

1. **Yield ≥ goal** — 95%+ for `stock`, 92%+ for `custom` (the exact
   thresholds Gate Stats' headers already state)
2. **Deviation/NCs? = NO**
3. **Days to Mfg ≤ ~84** (a clean 12-week boundary) — pass observed at 84
   days (`Ultra Test`, 3/2/2026 → 100.0%), fail observed at 86 days
   (`Platinum Turmeric`, 1/13/2026 → 66.7% despite yield 99.04% and NC=NO)

Example checks (all consistent, no exceptions found in the sample):

| Row | Yield vs. goal | NC | Days to Mfg | Gates passed | Success Rating |
|---|---|---|---|---|---|
| `5/28/2026 Menopause` 87.93% stock, YES, 111 | fail (<95) | fail | fail (>84) | 0/3 | 0.0% ✅ |
| `6/4/2026 Ultra Test` 99.23% stock, YES, 64 | pass | fail | pass | 2/3 | 66.7% ✅ |
| `6/26/2026 Neuro Plus...` 99.06% stock, NO, 93 | pass | pass | fail | 2/3 | 66.7% ✅ |
| `7/16/2026 Max Detox` 100.40% stock, NO, 79 | pass | pass | pass | 3/3 | 100.0% ✅ |
| `10/23/2025 USDA Organic BeetRoot` 43.11% custom, YES, 101 | fail (<92) | fail | fail | 0/3 | 0.0% ✅ |

**Not yet confirmed:** the exact Days-to-Mfg boundary (84 vs 85 vs some
other cutoff — no row in this sample lands on 85), and what the **job-level
"Successful" flag** in Gate Stats' Table 1 (`# Jobs Successful`) actually
requires — this row-level Success Rating is fractional (0/33.3/66.7/100%),
so Gate Stats' binary "Successful" could mean `= 100%` (all 3 gates) or
`≥ some threshold` (e.g. 66.7%+). Needs Emilio's confirmation, not a guess.

**Resolved 2026-08-11 (see `mfg_job_schedule_done_ytd.md`):** "Days to
Mfg" = `FG Testing Released − Date Entered`, confirmed by exact match
against Done YTD's `Total Days` column for the same jobs (`Female
Enhancement Plus`, 73 days, exact). The 2 negative values are **not** bad
data or a signed due-date metric — they're rework/partial-batch rows
where the FG Testing Released date is inherited from an earlier run that
predates the new row's Date Entered. Confirmed with 2 independent exact
matches, not inferred.

## Findings — column-by-column

| Column | Status | Detail |
|---|---|---|
| Date | ✅ **Resolved 2026-08-11** | Confirmed = `FG Testing Released` by exact cross-match against `mfg_job_schedule_done_2025.md` (2 independent matches). Already buildable via `Quality_v_Checksheet`/`_Status`, same source as the Open tab's "FG Testing Released" column. See `mfg_job_schedule_2025_list.md`. |
| Product | ✅ Buildable | `Part_v_Part.Name` |
| Yield | ⏳ Inherited gap | Same reconstruction lead as `mfg_job_schedule_ytd_gate_stats.md`: actual (`Job_Op.Quantity`) ÷ planned (`Job.Quantity`). Real values here (>100%, as low as 43%) are strong behavioral confirmation the formula is a straightforward ratio, not a bounded percentage — but `Part_v_Job_Op` is still empty on the test tenant, so it's unconfirmed against live data. |
| Product Type (stock/custom) | 🔍 Same open lead | Confirms (again) this is a per-batch manual label matching "Custom or Stock" on other tabs. See the `Job_Type_Key`/`Job_Distribution.Release_Key` leads in `catalog/plex_part_views_catalog.md` — committed and deployed live (2026-08-11), still unvalidated against real distribution data. |
| Days to Mfg | ⏳ Gap, formula partially reverse-engineered | See "Major finding" above — behaves like a TAT gate with a ~84-day goal, but the exact source date pair is unconfirmed. |
| Deviation/NCs? | ⏳ Inherited gap | Same standing NC-to-job correlation gap (`Quality_v_Problem` has no `Job_Key`/`Job_Op_Key`). |
| Success Rating | 🔍 Derived, not a Plex field | Computable once Yield/Deviation/TAT are resolved — see formula above. Not sourced from Plex directly, calculated from the other 3. |
| Month (trailing column) | ✅ Buildable once Date is resolved | `FORMAT_DATE('%Y-%m', date)` — confirms the "group by month" plan for Gate Stats was the right grain. |

## Verdict

**Still not buildable** — same root blockers as Gate Stats (Yield and NC
correlation both need real data / a missing FK), but this tab meaningfully
de-risked the "Successful" business-rule gap: what looked like an
undefined judgment call is very likely a specific, discoverable 3-gate
formula. Worth presenting the reverse-engineered formula to Emilio for a
yes/no rather than treating it as unknowable.

## What's needed next

1. Confirm with Emilio: (a) is `Success Rating = gates passed / 3` right,
   (b) what date pair makes up "Days to Mfg", (c) what threshold makes a
   job "Successful" in Gate Stats' Table 1.
2. Real (non-empty) `Part_v_Job`/`Part_v_Job_Op` data, to test Yield and
   the Days-to-Mfg date pair once known.
3. Once resolved, `Success Rating`/`Month` become computed columns over
   the same `mfg_job_schedule_report` + `quality_nonconformance_report`
   data — still no new extraction needed.

## Built 2026-08-26

Deployed as `mfg_job_schedule_success_metrics_report` — ONE continuous
view (no separate current-year/archive split, see
`spreadsheets/mfg_job_schedule_done_2025.md`'s archiving-boundary note)
covering this tab plus Done YTD/Done 2025/2025 List at once, since all 4
are the same underlying per-job calculated-metrics concept. Implements
`Success Rating = (Yield + Deviation + TAT gates passed) / 3` exactly as
reverse-engineered here, using the date pair confirmed in
`mfg_job_schedule_done_ytd.md` (`FG Testing Released − Date Entered`).

**Deviation** now comes from a real join (`Quality_v_Deviation_Job`, same
source as `quality_deviation_report`), not left as a gap — still carries
that report's own "unconfirmed whether every Problem/NC gets a linked
Deviation" caveat.

**Yield's "Caps Made" is a generalization**, not a literal match: sums
`Part_v_Production` across ALL of a job's operations (not just
Encapsulation), so Blending-only jobs get a Yield instead of a hard NULL
— Emilio's Q2 (does the formula hold for Blending-only jobs) is still
open, unvalidated either way, since no job with real completed production
existed to check against at build time.

**Verified live against `PlexTest`**: 25 real rows (this tenant's jobs, all
added 2026-08-26). Job 4 already shows a real partial yield
(429/2000 = 21.5%) from actual logged production — the first real,
non-zero Yield calculation this spreadsheet's build effort has seen. No
job has an FG Testing Released date yet, so `total_days`/`month`/the TAT
gate are still NULL across the board — expected, not broken.
