# Quality meeting guide — clearing scorecard tiles

Prep for the Quality rep meeting referenced in the 2026-09-16 Emilio/Jennilyn
call (`meetings-reference/sep-16/`). Six Quality-owned questions map directly
to open items on the [Migration Board](https://claude.ai/code/artifact/89e5211a-10c8-4a59-bf3d-c92f188c47a9)
— answering them clears flags #3 and #4 outright, and resolves ambiguity on
three tiles that are technically "ready" but built on an assumption.

## Questions, in priority order

### 1. TAT clock: Problem Date or Entered Date?
- **Where this lives**: `quality_turnaround_time_report` starts the clock at
  `Problem_Date` → `Closed_Date`. This was a code decision, never actually
  put to anyone (Migration Board flag #3).
- **Why it matters**: the existing Performance/Bonus day-count standards
  (Monthly TAT Analysis sheet, keyed by Item Stock Type) were measured
  against *one* of these two dates. If they used `Entered_Date`, our number
  runs consistently larger than theirs — and since this lands right at
  cutover, it will look exactly like performance dropped the day we
  switched systems, when it's really just a different clock start.
- **Ask**: which date did the existing TAT standards use as the clock
  start — when the problem was logged (Entered) or when it actually
  happened (Problem)?

### 2. DPMO — real opportunities-per-unit, or keep the placeholder?
- **Where this lives**: `quality_fpy_by_area_month_report.dpmo_provisional`
  divides by a placeholder of **1 opportunity per unit** — nobody had ever
  defined a real figure (flag #4). With 1, DPMO and defect rate are the
  same number wearing different labels.
- **Why it matters**: feeds **YTD FPY**, the second-heaviest-used data
  source on the whole scorecard — 9 charts.
- **Ask**: is there a real opportunities-per-unit figure per product or
  process? If not, confirm the placeholder is acceptable for now (Sigma is
  deliberately *not* computed from it, specifically to avoid a hand-rolled
  DPMO→Sigma approximation being subtly wrong in cGMP-adjacent reporting).

### 3. Does our First Pass Yield match what Quality means by FPY?
- **Where this lives**: Jennilyn told us she isn't sure Plex has "the FPY
  type stuff" and wants to ask Quality directly. We already compute it —
  `good_qty / total_qty` from `Part_v_Production` (verified: Bottling,
  August 2026, 100% FPY, 3,000 good / 0 rejected) — matching her own
  definition from the call: units produced vs. units with a nonconformance
  recorded in the problem control area.
- **Ask**: confirm this is the right definition, and whether a
  nonconformance should include **Deviations** too, or only standard NC
  records. This is likely a communication gap, not a missing feature — good
  chance to just show them the live number and get a nod.

### 4. Rework $ — which population does Vox actually mean?
- **Where this lives**: "Rework" exists in Plex **two different, unrelated
  ways** — a `Final_Disposition` value on a nonconformance record, and a
  separate container inventory status. These are different populations and
  will not agree with each other. Documented on the Migration Board but
  never resolved.
- **Ask**: when the scorecard says "Rework $," does that mean cost against
  NC records dispositioned Rework, or against containers sitting in Rework
  status? Whichever it is, the other one should probably still get tracked
  somewhere, just not on this tile.

### 5. Deviation $ / Rework $ — is Cost actually populated in practice?
- **Where this lives**: `quality_disposition_cost_report.total_cost` reads
  Plex's own `Cost` field on the nonconformance record. Currently 0 rows —
  no NC records exist yet on the test tenant, not because the field is
  missing.
- **Ask**: when Quality logs a deviation or a rework in Plex, do they
  actually fill in Cost, or does that number live somewhere else today
  (a spreadsheet, an estimate after the fact)? If it's not reliably filled
  in, that's worth knowing before this tile goes live.

### 6. Confirm terminology: destruction = Scrap
- **Where this lives**: settled 2026-09-09 — Plex has no "Destroy" value,
  it calls destruction **Scrap** (`Final_Disposition = 'Scrap'`). Not really
  a question, more a heads-up so nobody's confused later when the tile
  reads "Destruction $" but the underlying Plex value says Scrap.

## Logistics reminder, not a question
Sheldon is creating destruction/deviation/rework test data **Thursday**.
The test tenant resets on its own schedule, so whatever he creates has to be
inspected **the same day** — worth mentioning so the meeting doesn't end
with "let's look at it next week."

## After the meeting
Update the Migration Board (flags #3 and #4, plus the Reworks / Destruction
$ / FPY tile notes) with whatever comes back, redeploying to the same URL —
don't leave answers only in a memory file or this doc.
