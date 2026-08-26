# MFG Job Schedule — "Done 2025" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** ✅ Built 2026-08-26, unified with Done YTD/YTD List/2025 List
  into one continuous view (see "Built 2026-08-26" below — the archiving
  boundary this doc flags as unclear is a non-issue for that build, since
  it doesn't split by year at all). Real data analyzed (~150 rows). Same
  49-column schema as `mfg_job_schedule_done_ytd.md` (confirmed identical,
  including the â¡ï¸ mangled-arrow interval headers) — this is the
  prior-period archive. Pinned down the exact TAT boundary that was still
  open, and surfaced 3 new findings worth flagging to the data scientist.

## What it is

Same 49 columns as Done YTD, letter-for-letter. Covers older jobs — Date
Entered ranges from 11/27/2024 to 10/10/2025, Date Complete/FG Testing
Released ranges into December 2025. Confirms the README's "keep older
tabs archived as needed" note: this is what gets archived once a
period closes.

**Open question, not resolved by this tab:** the exact archiving boundary
between this tab and Done YTD is unclear — some late-2025 completions
appear in *this* tab (Done 2025) while Done YTD's earliest row starts
9/17/2025. Whether the split is by Date Entered, Date Complete, or a
manual cutover point isn't determinable from the data alone. Added as a
new open question.

## Resolved: exact TAT boundary — Total Days ≤84 passes, 85 fails

`mfg_job_schedule_ytd_list.md` and `mfg_job_schedule_done_ytd.md` both
found pass-at-84/fail-at-86 examples but never a row landing exactly on
85. This tab has two, independently:

- `Organic Ashwagandha` (10/31/2024 entry): Yield 95.41% stock (≥95%,
  pass), Deviation = YES (fail), Total Days = **85**, Success Grade =
  33.3% (1/3). Yield is the only other passing gate, so TAT must be the
  failing one → **TAT fails at 85.**
- `Night Time Fat Burn` (7/10/2025 entry): Yield 96.04% custom (≥92%,
  pass), Deviation = NO (pass), Total Days = **85**, Success Grade =
  66.7% (2/3). Yield + Deviation already account for both passing gates
  → **TAT fails at 85 again**, independently.

Combined with the existing 84-passes examples, **the TAT goal is exactly
`Total Days ≤ 84`** — no longer just high-confidence, now confirmed with
zero contradicting rows across ~330 real rows spanning 3 tabs. **Resolves
Open Question #5** in `mfg_job_schedule.md`.

## Reconfirmed: Total Days uses FG Testing Released, immune to bad Date Complete values

Row 1 (`Skin Shield Pro Capsule`) has `Date Complete = 2/13/2024` — a
year typo that predates `Date Entered` (11/27/2024) by 9 months,
physically impossible. Despite that, `Total Days = 97` still matches
exactly: `FG Testing Released (3/4/2025) − Date Entered (11/27/2024) =
97`. Confirms `Total Days` is computed from `FG Testing Released`, not
`Date Complete` — a bad value in the latter doesn't propagate into the
former. Reinforces the formula found in `mfg_job_schedule_done_ytd.md`,
this time under a stress case.

## New finding: reworks are handled inconsistently in stats — by design

One row makes this explicit in its own YYYY-MM cell: instead of a date,
it literally reads **"deleted date so it's not in stats, this is a
rework."** This confirms rework rows are sometimes deliberately excluded
from monthly stats by hand. But `mfg_job_schedule_done_ytd.md` already
found *other* rework rows (negative Total Days) that clearly **are**
included in stats. **There is no single consistent rule for reworks** —
it's a human, case-by-case judgment call, not a formula. Worth surfacing
to the data scientist as a process question, not a data question: should
a future automated version make this decision consistently, and if so,
how?

## New finding: "BR Ready for MFG" has real values, but unclear meaning

Every other tab showed this column blank. Here it has real small integers
(`1`, `2`, `3`) and once a comma-pair (`"2,5"`, quoted in the CSV because
it contains a literal comma). No clear pattern connects these numbers to
`# of Blends` or anything else already mapped. **Don't guess at this** —
added as a new open question rather than a guessed Plex mapping.

## New finding: "Available Inventory" isn't reliably numeric

One row has `Available Inventory = Yes` (literal text) instead of a
number. Reinforces that this column, like the interval columns, needs
type-validation before any automated ingestion — the source sheet mixes
formats freely since a human reads it, not a schema.

## Minor confirmation: Blender/# of Blends = N/A for rework jobs

Rework rows consistently show `Blender = N/A`, `# of Blends = N/A` (e.g.
`Ashwagandha Rework`, `Skin Shield Pro Rework`) — makes sense, a rework
reuses an existing blend rather than running a new one. No new gap, just
context for why those fields are sometimes empty.

## Verdict

No change to buildability — same root blockers as every other calculated
tab (Yield needs real `Job_Op` data, Deviation needs the missing NC-to-job
FK). But this tab closed out Open Question #5 for good and surfaced real
process inconsistencies (rework handling) and 2 new unclear columns worth
asking about directly rather than guessing.

## What's needed next

Same as the other calculated tabs — real `Part_v_Job`/`Part_v_Job_Op`
data to test Yield. Additionally: ask Emilio/the data architect about the
Done YTD/Done 2025 archiving boundary, the "BR Ready for MFG" values, and
whether rework rows should be included in stats consistently.

## Built 2026-08-26

Rework handling **resolved 2026-08-26 (Emilio's call)**: include all
rework rows in stats, never drop them — expose a computed `is_rework`
flag (`Job_Type = 'Rework'` OR negative `total_days`) instead, matching
the "left in with a negative Total Days" behavior this doc found more than
the "deliberately blanked date" behavior. Built into
`mfg_job_schedule_success_metrics_report` — see
`spreadsheets/mfg_job_schedule_ytd_list.md`'s "Built 2026-08-26" section.
The archiving-boundary question above is moot for this build (one
continuous view, no year split). "BR Ready for MFG" remains unbuilt — its
meaning is still genuinely unknown, not guessed at.
