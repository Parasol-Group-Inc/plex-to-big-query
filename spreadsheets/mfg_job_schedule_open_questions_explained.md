# MFG Job Schedule — Open Questions, Explained

**Where the list lives:** [mfg_job_schedule.md](mfg_job_schedule.md), in
the "❓ Open Questions for the Data Architect/Scientist" section near the
top. That's the working list — this document is a plain-language guide to
what's actually in it, for bringing to that conversation without having
to first decode the jargon.

## First, a small glossary

A handful of terms show up over and over. Once these click, most of the
open questions read as plain English.

- **Plex** — the manufacturing ERP system (like a company-wide database +
  UI for tracking production). Everything this pipeline pulls comes from
  Plex via a database connection (ODBC).
- **Job** — one production run of a product (e.g. "make 500,000 capsules
  of Magnesium Complex"). Comparable to an "order" record in a normal app.
- **Job Operation ("Job_Op")** — one *step* within a job (blend the
  powder, then encapsulate it, then inspect it). Comparable to line items
  under an order — one job can have several operations.
- **Yield** — actual amount produced ÷ amount planned, as a percentage.
  100% = made exactly what was planned; 110% = made more than planned;
  80% = came in short.
- **TAT / "Total Days"** — turnaround time: how many days a job took from
  start to finish.
- **Deviation / NC ("Non-Conformance")** — a quality problem got logged
  against a job (something didn't meet spec). "Deviation = NO" means no
  issues.
- **Foreign key (FK)** — a database term for "a column that points at a
  specific row in another table," like a hyperlink between two
  spreadsheets. If table A has no FK into table B, there's no clean,
  reliable way to say "this row in A belongs to that row in B" — you'd
  have to guess by matching other fields (like matching on product name +
  date), which is fuzzy and can get it wrong.
- **Stock vs. Custom** — whether a production run was for general
  inventory ("stock," goes to a warehouse bucket) or for one specific
  customer's order ("custom").
- **Reorder Point / Avg Daily** — standard inventory-planning terms.
  Reorder Point is the stock level that should trigger "order more now."
  Avg Daily is how fast a product typically gets used up, in units/day —
  needed to turn a raw quantity into "how many days of supply is this."
- **Confirmed vs. speculative** — "confirmed" means checked against real
  data or a real config and proven correct. "Speculative"/"unconfirmed"
  means it's a good, checked lead — not a wild guess — but not yet proven
  with real numbers.

## The one blocker worth leading with

Before the numbered list: there's a gap that isn't formally numbered in
`mfg_job_schedule.md` but blocks more than anything else — **Deviation/NC
has no foreign key to a job.** The table that records quality problems
(`Quality_v_Problem`) links to a *part* and a *date*, not to a specific
job. So Plex has no clean, reliable way to say "this quality issue
belongs to that production run." Since "Deviation = NO" is one of the
three ingredients in the Success Rating formula (see Q4 below), **this
alone blocks fully automating Success Rating from Plex, no matter what
else gets resolved.** Worth raising explicitly — the fix isn't more data,
it's a person deciding on a matching rule (e.g. "same part number within
±3 days of the job" is a reasonable rule, but it's a judgment call, not
something obviously correct).

## The numbered list, in plain language

Grouped by theme rather than in list order, since a few of these are
really the same underlying question asked from different tabs.

### Group 1 — What exactly counts as "a successful job"?

- **Q1 — Is "TAT Stats & Success" the same tab as "YTD Gate Stats"?**
  The automation's own description names a tab we haven't actually seen
  a CSV for. Might just be an old name for a tab already reviewed, or a
  genuinely separate tab. Quick to answer, low stakes.
- **Q4 — What makes a job "Successful" (yes/no), not just a percentage?**
  We know the *percentage* formula (yield passed + no deviation + on-time
  = each worth a third). What's still unclear: does a job need a perfect
  100% to count as "Successful" in the monthly rollup, or does 2-out-of-3
  count too? This is a business decision, not something derivable from
  data.

### Group 2 — Where do some numbers actually come from?

- **Q2 — Does the Yield formula hold for jobs with no encapsulation
  step?** The formula (`amount made ÷ amount planned`) is confirmed for
  capsule products. Some jobs are just a powder blend with no
  encapsulation step — does the same formula still make sense there, or
  is "amount made" measured differently for a pure blend?
- **Q8 — Where does "Blender" (a batch size like `2000L`) come from?**
  Checked the obvious Plex table, wrong columns. Might be somewhere else
  in Plex, might be a purely manual field. Low priority, cosmetic.
- **Q13 — Where do "Avg Daily" (usage rate) and "Reorder Point" actually
  come from?** These drive the whole "how many days of inventory do we
  have left" calculation. Checked every plausible Plex table and none of
  them have it — this is very likely calculated somewhere else entirely
  (could be NetSuite, could be a manual historical average someone
  maintains in the sheet). Worth asking directly rather than guessing
  further — this is the single most valuable one to get an answer on,
  since it unlocks "Days Left" everywhere it shows up.
- **Q14 — Is "Current QTY Available" just "Quantity On Hand" minus
  something reserved/committed?** Checked the obvious Plex table for
  "committed/reserved" quantities — it exists, but doesn't have the right
  columns to compute this directly. Needs someone who knows the
  inventory process to confirm.

### Group 3 — Business process / policy calls (not data questions at all)

- **Q6 — Is it even worth automating Stock vs. Custom?** Today, someone
  just types "stock" or "custom" into a cell by hand. We found 2
  plausible Plex fields that *might* replicate that by-hand judgment
  automatically — but they're unproven, and replacing a human judgment
  call with an automated guess is a decision, not just an engineering
  task. Worth discussing whether it's even desired.
- **Q11 — Should "rework" jobs count in the monthly stats?** Right now,
  the sheet handles reworks inconsistently — sometimes someone manually
  deletes the date so it's excluded from stats, other times it's left in
  and skews the numbers (very short or even negative turnaround times).
  Neither is "wrong," but it's not a consistent rule either. This is a
  policy question for whoever owns these stats.
- **Q12 — What does "BR Ready for MFG" mean?** A column with small
  numbers (1, 2, 3, and once "2,5") that doesn't match any other known
  field. Nobody's guessed at what it represents — needs someone who
  actually uses the sheet to explain it.

### Group 4 — Bookkeeping / definitions (lower priority)

- **Q7 — How should the 95%/92%/84-day goals be stored if this gets
  automated?** These numbers can change over time (the sheet says so
  explicitly — "you can change the success table any time, it won't
  apply retroactively"). If this ever gets built for real, do we need to
  track *which* goal was active when each job was scored, or is "always
  use today's goal" good enough?
- **Q9 — Should we guard against typo dates blowing up calculations?**
  A few real rows have a mistyped year (like `0206` instead of `2026`),
  which turns a date-math calculation into a nonsense number in the
  millions. The spreadsheet doesn't protect against this either — just
  flagging it as something a real build should handle, not urgent.
- **Q10 — What's the actual cutoff between "Done YTD" and "Done 2025"?**
  These look like a current-year bucket and an archived-prior-year
  bucket, but the exact rule for when a job moves from one to the other
  isn't obvious from the data. Cosmetic, not blocking anything.

## What this means for the conversation

If time with the data architect/scientist is limited, the highest-value
things to get through are: the **Deviation/NC matching rule** (blocks
Success Rating outright), **Q13** (unlocks the inventory "days left"
metric everywhere it appears), and **Q4** (defines what "Successful"
even means for the monthly rollup). Everything else is either lower
priority or a quick factual answer.
