# MFG Job Schedule — "2025 List" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** ✅ Built 2026-08-26, unified with YTD List/Done YTD/Done 2025
  (see "Built 2026-08-26" below). Real data analyzed (~190 rows). Same
  7-column shape as `mfg_job_schedule_ytd_list.md` (Date, Product, Yield,
  Product Type, Days to Mfg, Deviation/NCs?, Success Rating, Month) — this
  is the prior-year archive counterpart, same relationship as Done
  2025-is-to-Done YTD. Mostly confirmatory, but resolved one real
  ambiguity: what "Date" actually is.

## What it is

Direct sibling of YTD List, same columns, same blend/batch grain (several
Date+Product pairs repeat with different Yield — e.g. two `Night Time Fat
Burn` rows on 10/3/2025, two `Female Enhancement Plus` rows on
10/24/2025). Covers 1/13/2025 through 12/24/2025, matching Done 2025's
range. Same trailing `1899-12` blank-row artifact as YTD List — not new,
just noise to filter.

## Resolved: "Date" = FG Testing Released, not Date Entered or Complete Date

`mfg_job_schedule_ytd_list.md` left the "Date" column as "plausible,
unconfirmed" (guessed at `Job_Op.Complete_Date` or `Job.Completed_Date`).
Cross-matching real rows against `mfg_job_schedule_done_2025.md` resolves
it exactly, twice:

- `B-12 Complex`: this tab shows `Date = 12/24/2025`. The matching Done
  2025 row has `Date Entered = 10/10/2025` and `FG Testing Released =
  12/24/2025` — the List tab's "Date" matches **FG Testing Released**,
  not Date Entered.
- `Prostate`: this tab shows `Date = 10/3/2025, Days to Mfg = 85`. The
  matching Done 2025 row (`7/10/2025` entry) has `FG Testing Released =
  10/3/2025`, `Total Days = 85` — exact match again.

**"Date" is buildable** — it's the same `FG Testing Released` column
already mapped as buildable via `Quality_v_Checksheet`/`_Status` in
`mfg_job_schedule.md`, not a separate open question. Updates
`mfg_job_schedule_ytd_list.md`'s column table.

## Reinforced (not new): TAT boundary, extreme Yield range, blank-Success behavior

- 3 more real rows land on `Days to Mfg = 85` (two `Night Time Fat Burn`,
  one `Prostate` — the same underlying jobs already used in
  `mfg_job_schedule_done_2025.md`, cross-referenced here rather than new
  independent evidence), all still failing the TAT gate. Consistent with
  the already-resolved Open Question #5, not additional new proof.
- `Turmeric w/ Bioperine`: Yield = **161.00%** — even further above 100%
  than the previous max (131.63%), reinforcing Yield is an uncapped
  actual/planned ratio, not a bounded percentage.
- `TK GoGo`: Yield and Success Rating are both **blank** (not a 0% or
  partial score) when the underlying `Caps Made` value is missing —
  confirms Success Rating requires all 3 gate inputs to be valid, matching
  the READ ME's own troubleshooting note ("Confirm Ordered and Produced
  are filled"). Not a new open question, just confirms existing
  understanding.

## Verdict

No change to buildability status — same blockers as YTD List (Yield needs
real `Job_Op` data, Deviation needs the missing NC-to-job FK) — but the
"Date" column moves from an open question to a confirmed, already-mapped
source.

## What's needed next

Same as `mfg_job_schedule_ytd_list.md` and `mfg_job_schedule_done_2025.md`
— real `Part_v_Job`/`Part_v_Job_Op` data to test Yield, and Emilio's
confirmation of the remaining open items in `mfg_job_schedule.md`.

## Built 2026-08-26

See `spreadsheets/mfg_job_schedule_ytd_list.md`'s "Built 2026-08-26"
section — `mfg_job_schedule_success_metrics_report` is one continuous
view covering this tab, YTD List, Done YTD, and Done 2025 together
(confirms this tab's own "Date = FG Testing Released" finding, used
directly as the view's `fg_testing_released_date` column).
