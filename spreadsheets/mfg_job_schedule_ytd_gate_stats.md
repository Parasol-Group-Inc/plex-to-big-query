# MFG Job Schedule — "YTD Gate Stats" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** 🔍 Mapped — column structure analyzed, **not buildable yet**:
  blocked on 2 pre-existing gaps + 1 new gap + 1 business-rule definition
  that can't be inferred from the sheet alone

## What it is

Not a job-level row report like the "Open" tab — this is a **monthly
aggregate rollup**, two tables side by side, one row per calendar month
(2026-01 through 2026-12, most of the year still blank/zero):

**Table 1 — "Success (Yield, Deviations/NCs, TAT) Frequency":** Month,
Total # Jobs, # Jobs Successful / Not Successful / % Successful (goal
75%+), then the same three columns split by **Stock** and **Custom** job
type.

**Table 2 — "Yield and Deviations by Product Type" / "TAT by product
type":** Stock/Custom Avg Yield (goals 95%+/92%+), # Stock/Custom Jobs
with Deviation/NCs, Stock/Custom Jobs Avg TAT (days), Count of Stock/Custom
Jobs within Goal.

The tab's own title is explicit about its formula's three inputs — a job's
success is a function of **Yield**, **Deviations/NCs**, and **TAT**. It
does not say how the three combine (all must pass? any one fail = not
successful? weighted?) — that composite logic is a business rule only
Emilio can define, not something inferable from column headers.

## Findings — what blocks building this

This tab is a **downstream aggregate of the "Open" tab's own job-level
data**, so it inherits every unresolved gap from `mfg_job_schedule.md`,
plus adds new ones:

| Input needed | Status | Detail |
|---|---|---|
| Total # Jobs per month | ✅ Buildable | `Part_v_Job` grouped by month — but which date defines "the month" (Add_Date vs. `Job_Op.Start_Date` vs `.Complete_Date`) is ambiguous from the sheet alone; needs Emilio's confirmation once real data exists |
| Stock vs. Custom job classification | 🔍 **Corrected 2026-08-11 — real lead found, partially validated, deployment held** | First pass wrongly called this a dead end (see history below). Mapping the "FG Testing Pending" tab turned up the real join: `Part_v_Job.Job_Type_Key` → `Part_v_Job_Type` (4 configured types: `Stock`/`Service`/`Pre-Production`/`Rework`, no literal "Custom") and `Part_v_Job_Distribution.Release_Key` (populated = tied to a customer order = custom; null = stock). Both added to `mfg_job_schedule_view.sql` (committed `6c3b1c7`, **not yet deployed** — Emilio wants to batch-deploy after all tabs are mapped). Local BigQuery test partially validated the first lead already: 2 leftover job records resolved `job_type = 'Stock'`. `Job_Distribution` is still empty on the test tenant — second lead untested. See `spreadsheets/mfg_job_schedule_fg_testing_pending.md` and `catalog/plex_part_views_catalog.md`. |
| Yield (Stock Avg / Custom Avg) | ⏳ Inherited gap, still unconfirmed | Same lead flagged in `mfg_job_schedule.md`/`plex_production_yield_reference.md`: `Job_Op.Quantity` (actual) vs. `Job.Quantity` (planned). **`Part_v_Job` still has 0 rows on the test tenant as of 2026-08-11** — re-confirmed live — so this can't be tested until real production data exists on either tenant. |
| # Stock/Custom Jobs with Deviation/NCs | ⏳ Inherited gap, still unconfirmed | Same "NC-to-job correlation" gap already flagged in `mfg_job_schedule.md`: `Quality_v_Problem` has no `Job_Key`/`Job_Op_Key` FK — linking an NC to a specific job (and by extension, to that job's month/Stock-or-Custom bucket) needs a part+date match, not a join key. This blocks the second column depending on it. |
| TAT (Stock/Custom Avg, days) | 🔍 Plausible, needs definition + real data | Worth explicitly distinguishing from the "Days in WIP"/"Days Left" columns on the Open tab, which are flagged **manual-only** there (hand-updated while a job is still in progress). This TAT is a **historical rollup over completed jobs**, plausibly `Job_Op.Complete_Date − Start_Date`, or possibly the broader `Job.Complete_Date − Add_Date` if "TAT" means order-entry-to-done rather than shop-floor time. Which date pair is correct is Emilio's call, not guessable — and either way, `Job_Op` has no completed rows on the test tenant yet to validate against. |
| "Successful" composite definition | 🔍 **Reverse-engineered 2026-08-11, needs Emilio's yes/no** | Mapping the "YTD List" tab (the row-level data behind this one) found a formula that matches ~15+ real rows with zero contradictions: `Success Rating = (gates passed) / 3`, gates = Yield ≥ goal (95%/92%), Deviation/NCs = NO, Days to Mfg ≤ ~84. See `mfg_job_schedule_ytd_list.md`. Still open: what makes a job "Successful" (binary) in *this* tab's Table 1 — `= 100%` on that fractional score, or some lower threshold. |
| Goal thresholds (75%, 95%, 92%) | Not a gap | Once the above metrics exist, these are just comparison constants, not something to source from Plex. |

## Verdict

**Not buildable today.** Only "Total # Jobs per month" is independently
buildable right now — everything else in this tab either has no confirmed
Plex source (Stock/Custom classification), is blocked by a gap already
flagged in the parent tab (NC-to-job correlation), or needs real
(non-empty) production data that doesn't exist on the test tenant yet
(Yield, TAT). The "Successful" business rule that looked undefinable is
now a reverse-engineered hypothesis pending Emilio's confirmation, not an
open-ended gap — see `mfg_job_schedule_ytd_list.md`.

This tab is a good forcing function for prioritizing 2 things once real
production data lands: (1) validating the Stock/Custom leads above
(`Job_Type_Key`/`Job_Distribution.Release_Key`) against real jobs — the
"FG Testing Pending" tab shows this is a hand-typed column today, so even
a partial match would let it stop being manual — and (2) confirming the
Yield calculation against real `Job_Op` activity, since that same gap now
blocks two downstream reports, not one.

## What's needed next

1. Real job data to test the Stock/Custom leads, and Emilio's definition
   of "Successful" (composite pass/fail logic across Yield/Deviations/TAT)
   — the latter can't come from data at all, only from Emilio.
2. Real (non-empty) `Part_v_Job`/`Part_v_Job_Op` data on either tenant, to
   test the Yield and TAT reconstructions.
3. Once both are resolved, this becomes a `GROUP BY month` aggregate query
   over `mfg_job_schedule_report` + `quality_nonconformance_report` output
   — no new extraction needed, same reuse pattern as the rest of this
   spreadsheet.
