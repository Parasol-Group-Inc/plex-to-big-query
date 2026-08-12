# MFG Job Schedule — "Done YTD" tab

- **Parent spreadsheet:** [MFG Job Schedule](mfg_job_schedule.md) (see its
  "Tabs in this spreadsheet" tracker)
- **Status:** 🔍 Mapped — real data analyzed (~110 real rows). **This is
  the actual master table** where Yield/Total Days/Deviation/Success Grade
  get calculated — YTD List is a slimmed extract of it. Confirmed 2 of the
  4 open questions from `mfg_job_schedule_read_me.md` with exact,
  reproducible formula matches; no guessing needed this round.

## What it is

Same 36 columns as `mfg_job_schedule_fg_testing_pending.md` (confirmed
identical letter-for-letter, A through AJ), plus 13 new columns appended
at the end — the calculated fields the READ ME described "Done YTD"
computing:

`AK=Yield %, AL=Total Days, AM=Deviation, AN=Success Grade` (matches the
README's "Success (AN)" reference exactly), then 8 interval columns
(`AO`–`AV`: Entered→POs Received, POs Recvd→All Raws Sampled&Shipped,
Raws Shipped→Raws Released, Raws Released→Blending Started, Blending
Started→Blending complete, Blending Complete→Encap Started, Encap
Started→FG Complete, FG Complete→FG Testing Released), then `AW=YYYY-MM`
— matching the README's "Column AW in Done YTD must contain YYYY-MM
format" exactly.

## Confirmed: "Total Days" = FG Testing Released − Date Entered (exact match, no rounding)

`mfg_job_schedule_ytd_list.md` flagged 2 negative "Days to Mfg" values as
unexplained. Cross-matching `Total Days` in this tab against real dates
resolves this **exactly**, twice:

- `Female Enhancement Plus` (5/15/2026 entry, 7/24/2026 complete):
  FG Testing Released = 7/27/2026. `7/27/2026 − 5/15/2026 = 73 days` —
  matches `Total Days = 73` exactly, and matches YTD List's `Days to Mfg
  = 73` for the same job (`7/27/2026, Female Enhancement Plus, 99.4%,
  stock, 73, NO, 100.0%`). **Confirms YTD List's "Days to Mfg" and Done
  YTD's "Total Days" are the same metric.**
- The two negative outliers are now fully explained, not data-entry
  mistakes: `Female Enhancement` (3/19/2026 entry) has FG Testing
  Released = 2/27/2026 — `2/27/2026 − 3/19/2026 = −20 days`, exact match
  to `Total Days = −20`. The Notes column explains why: "Encapsulating
  the remaining 2 blends from the previous run" — this row's FG Testing
  Released date is inherited from an **earlier, already-tested run**; the
  new row's Date Entered is later than that inherited release date. A
  similar rework row ("01/26 - Rework") produces `Total Days = −4` the
  same way. **Negative Total Days is a legitimate rework/partial-batch
  signature, not bad data** — revises `mfg_job_schedule_ytd_list.md`'s
  "reframe the metric" note into a confirmed, understood behavior.

**Resolves Open Question #3** in `mfg_job_schedule.md`.

## Confirmed again: Yield % = Caps Made ÷ Capsule Count

Spot-checked against this tab's real numbers: `Capsule Count = 2,945,234`,
`Caps Made = 2,772,255` → `2772255 / 2945234 = 94.128%` — matches
`Yield % = 94.13%` exactly (rounding only). Same formula as found in the
READ ME tab, now independently confirmed against a different row.

## Reinforced: TAT gate boundary is ≤84 days

Two more real examples, independent of the ones in
`mfg_job_schedule_ytd_list.md`:

- `Total Days = 84`, Yield 99.15% (stock, pass), Deviation NO (pass),
  Success Grade = **100.0%** (3/3) → TAT passes at 84.
- `Total Days = 86`, Yield 99.04% (stock, pass), Deviation NO (pass),
  Success Grade = **66.7%** (2/3) → TAT fails at 86.

Same boundary as before (pass 84 / fail 86) confirmed a second time in a
different dataset. Still no row across ~220 total real rows (both tabs
combined) lands exactly on 85 — high confidence the goal is "≤84 days"
(12 weeks), but the literal boundary value is still not 100% pinned.

## New finding: Custom/Stock still tracks Customer 1:1

Every row with `Customer = Warehouse` is `stock`; every row with a real
company name (`Lux Global`, `Nutricost Manufacturing, LLC`, `Argo Brands`,
etc.) is `custom`. Consistent with the "manual SKU-column convention"
finding in the READ ME doc — reinforces it, doesn't change it.

## New finding: real "MG Per Cap" values now visible

Unlike FG Testing Pending (mostly blank), this tab has real values —
`622 mg`, `725 mg`, etc. Doesn't resolve the standing gap (still needs a
`Part_v_BOM` unit-conversion source, not built), but gives real target
values to validate against once that reconstruction is attempted.

## New finding: interval columns are free once dates exist, but fragile to typos

The 8 interval columns (`AO`–`AV`) are pure date subtraction over columns
already flagged buildable (POs Received, Raws Released, Blending
Started/complete, Encap Started, FG Complete, FG Testing Released) — no
new gap, they fall out automatically once those dates are populated.

**Data-quality risk worth flagging:** several rows have obviously-wrong
interval values in the millions (`1095785`, `-1095722`, `-664727`,
`664750`) traced to year typos in manually-entered dates (e.g. `6/17/0206`
instead of `6/17/2026`, `5/22/5026` instead of `5/22/2026`). A future
build computing these intervals in SQL should sanity-bound them (e.g.
reject/flag any interval outside a few hundred days) rather than trusting
raw date subtraction — the source sheet clearly doesn't do this itself.

## Verdict

Still not independently buildable (same root blockers: Yield needs real
`Job_Op` data, Deviation needs the missing NC-to-job FK), but this tab
closed out the most important open question cleanly — "Total Days" now
has an exact, reproducible formula with the negative-value mystery fully
explained, not just a hypothesis.

## What's needed next

Same as `mfg_job_schedule_ytd_list.md` — real `Part_v_Job`/`Part_v_Job_Op`
data to test Yield, and Emilio's confirmation of the job-level
"Successful" threshold and the exact TAT boundary (84 vs 85).
