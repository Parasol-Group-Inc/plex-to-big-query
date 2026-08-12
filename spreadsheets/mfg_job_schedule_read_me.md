# MFG Job Schedule — "READ ME" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** 📄 Documentation tab, not data — but its content resolved
  several open questions from other tabs. Notes below, plus a consolidated
  **Open Questions for the Data Architect/Scientist** list at the bottom.

## What it is

Not a data tab — it documents a Google Apps Script automation that runs
this whole spreadsheet system daily at 8:00 PM, moving rows between tabs
and calculating the derived columns (Yield, Success Rating, etc.) that the
other tab-mapping docs had been reverse-engineering from output alone.
Reading it **confirmed or corrected several hypotheses** from those docs.

## Confirmed pipeline architecture

```
Open  →  FG Testing Pending  →  Done YTD  →  TAT Stats & Success
(entry)   (QC release wait)     (completed,     (monthly aggregate —
                                  scored)          likely = "YTD Gate Stats",
                                                    possibly a prior/renamed
                                                    version of it)
```

- **Open** — "Calculates days in WIP, looks up inventory info, and moves
  completed rows to FG Testing Pending."
- **FG Testing Pending** — "Fills in product type, dates, and details
  automatically. Moves finished rows to Done YTD."
- **Done YTD** — "Calculates yield, total days, deviation status, success
  score, and performance by product type." — this is the tab where the
  derived metrics YTD List surfaces (Yield, Days to Mfg, Success Rating)
  actually get calculated, not YTD List itself.
- **TAT Stats & Success** — "Aggregates average turnaround times and
  success metrics by month and product type." This description matches
  "YTD Gate Stats" almost exactly (same aggregation grain, same 3 inputs).
  **Not confirmed whether this is the same tab under an old/internal name,
  or a distinct one** — flagged below as a question for Emilio/the data
  scientist, not assumed.
- `Done 2025` / `2025 List` are the prior-year archives of `Done YTD` /
  `YTD List` — confirmed by the README's "process up to 200 rows per tab,
  keep older tabs archived as needed" note.

## Confirmed: exact Yield formula

"✅ Confirm Ordered (I) and Produced (O) are filled" / "⚠ Ordered qty may
be missing or zero" (for `Yield showing as 0%`) — matched against FG
Testing Pending's real column letters (A=Date entered, ... I=**Capsule
Count**, ... O=**Caps Made**):

**Yield = Caps Made (O) ÷ Capsule Count (I)** — a plain ratio, exactly the
shape guessed at in `mfg_job_schedule_ytd_list.md` from the raw numbers
(values >100%, as low as 43%), now confirmed by the sheet's own
documentation rather than inferred. Both inputs were already flagged
buildable from `Part_v_Job.Quantity` (Capsule Count/Ordered) — "Caps Made"
(Produced) still needs its own Plex source confirmed; likely
`Part_v_Job_Op.Quantity` summed over encapsulation-workcenter operations,
per the existing lead in `plex_production_yield_reference.md`, but this is
the first time we have a confirmed *formula*, not just plausible inputs.

## Confirmed: the row-movement trigger (Open → FG Testing Pending)

"Row not moving to FG Testing Pending: ✅ Column W (FG Pull Date) must be
a valid date; ✅ All Note Dates (AA–AE) must be filled." Matched against FG
Testing Pending's column letters: **W = Date Complete**, **AA–AE = POs
Received, All Raws Sampled & Shipped, Raws Released, Blending Started,
Blending complete** (exact letter-for-letter match against the 36-column
header counted in `mfg_job_schedule_fg_testing_pending.md`). So a row
graduates from Open once all 6 of those dates are filled — a precise,
confirmed business rule, useful if this ever needs replicating as a SQL
filter.

## Revised: "Days to Mfg" is very likely a plain elapsed duration

`mfg_job_schedule_ytd_list.md` flagged 2 negative values (−20, −4) as
possible evidence "Days to Mfg" was a signed, due-date-relative metric
rather than a simple duration. The README complicates that: "Success
Rating not calculated: ✅ Check that Start Date (A) and Test Complete Date
(AH) are both valid dates" — **A = Date entered**, **AH = FG Testing
Released** (again, exact letter match). Since Success Rating's timeliness
gate is almost certainly built from these same two dates, **"Days to Mfg"
is most likely just `AH − A`, a plain elapsed count that should never be
negative under normal use.** The 2 negative rows in the real YTD List data
are more likely data-entry mistakes (a job's Date Entered was backdated or
mis-typed after the fact) than a deliberate sign convention. Revising
downward from "reframe the metric" to "flag those 2 rows as bad data" —
worth confirming with Emilio, not asserted as fact.

## New finding: Custom/Stock is a manual sheet convention, not a system field

"Changes from old manufacturing job schedule: Custom products must be
noted in the SKU col." This confirms — straight from the sheet's own
documentation — that **Custom vs. Stock classification is currently a
human data-entry convention**, not derived from Plex or any other system.
This matters for the `Job_Type_Key`/`Job_Distribution.Release_Key` leads
already added to `mfg_job_schedule_view.sql`: they're a plausible
**replacement** for this manual convention if validated against real
data, but they are **not** currently what drives the sheet — don't treat
a future match as "reproducing the existing source," it would be
introducing a new, independent source that happens to agree (or not).

## New finding: goal thresholds are editable, and not retroactive

"You may change the success table at any time - just note it doesn't
apply retroactively." The 95%/92%/84-day goals reverse-engineered in
`mfg_job_schedule_ytd_list.md` are **not fixed constants** — they're a
business-editable lookup table, and historical rows keep whatever goal
was active when they were scored. **Implication for any future build:**
don't hardcode these thresholds as SQL literals without a way to version
them — a small goals-lookup table (goal value + effective date range)
would be closer to how the sheet actually behaves, if this ever gets
built. Flagged for the data architect conversation, not built.

## Not data-relevant (sheet hygiene, no Plex implication)

"All font must be black," "Don't delete or add columns; hide them
instead," "Avoid dragging formulas," "NO COMMENTS MOVE" — internal Google
Sheets maintenance conventions. Noted for completeness, no action.

## Parking lot (future column requests, not yet in the sheet)

Two pending requests logged in the README's own "Issues/Errors" section
— neither exists in the sheet yet, nothing to map today:
- "Add column for picking start and complete" (Nick, Operations)
- "Add column for barrel tags" (Elibeth Arrieta, Quality) — if/when added,
  this plausibly maps to `Part_v_Container`/`Part_v_Lot` tracking, worth
  revisiting once the column actually exists.

---

## ❓ Open Questions for the Data Architect/Scientist

Consolidated from this tab and all others mapped so far — carried forward
in `mfg_job_schedule.md`'s tracker as the running list to bring to that
conversation:

1. **Is "TAT Stats & Success" the same tab as "YTD Gate Stats"** under a
   different/older name, or a genuinely separate tab we haven't seen yet?
2. **Confirm the Yield formula**: `Caps Made (O) ÷ Capsule Count (I)` —
   is "Caps Made" always from encapsulation operations, or does a
   Blending-only job (no encap step) compute Yield differently?
3. **Confirm "Days to Mfg" = FG Testing Released (AH) − Date Entered (A)**
   — and whether the 2 negative values seen in real YTD List data
   (`Female Enhancement` −20, `Neuro Plus...` −4) are known bad rows.
4. **Confirm the "Successful" job-level threshold** in Gate Stats' Table 1
   — does it require a perfect 3/3 (100%) Success Rating, or some lower
   bar (e.g. 2/3, 66.7%+)?
5. **Confirm the exact TAT goal boundary** — evidence points to ≤84 days
   (12 weeks), pass observed at 84, fail at 86; no row lands on 85 to pin
   it exactly.
6. **Is Custom/Stock worth automating from Plex at all**, given it's
   currently a manual SKU-column convention? The `Job_Type_Key`/
   `Job_Distribution.Release_Key` leads are unvalidated against real data
   and would be a new source, not a reproduction of the existing one.
7. **How should goal thresholds (95%/92%/84-day) be stored** if this ever
   gets built in BigQuery, given they're editable and explicitly
   non-retroactive in the source sheet?
