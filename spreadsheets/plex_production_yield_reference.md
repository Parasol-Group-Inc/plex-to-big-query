# Reference: Plex "Production Yield" UI report

Shared reference for four Daily Report spreadsheets (Packaging, Labeling,
Blending, Encap) that `Reports List - Production.csv`'s "Plex Report Equiv"
column flagged as building on this existing Plex UI screen. Per
[[feedback-plex-ui-reports-reference-only]] and the note at the bottom of
[SPREADSHEET_CATALOG.md](SPREADSHEET_CATALOG.md): this is a lead for which
raw ODBC views likely back the business concept, **not** a resolved data
source — the screen itself isn't queryable by this pipeline.

## Verdict (2026-08-11): does it actually solve for them? Mostly no.

Now that the real templates exist (`Packaging Daily Report - Template.csv`,
`Labeling Daily Report - Template.csv`, `Blending Daily Report - Template.csv`,
`Encap Daily Report - Template.csv`), the fit can be checked directly instead
of guessed:

All four templates share the same real shape: **a daily goal-vs-actual
output log per production line/workcenter** — which operator worked, what
time they started/stopped, planned (goal) output vs. actual output that
day, resulting capacity %, plus an attendance roster (Call Outs/OFF).

Production Yield's grain and purpose don't match that:
- It's **per-container/per-serial-number weighing event** (Gross Part
  Weight, Tips Tails Weight, Adjusted Coil Weight, Heat No, Pieces
  Scrapped), not a per-line daily total.
- It has **no Operator, no Start/Stop time, no attendance/Call-Outs
  concept at all** — roughly half of what these Daily Reports track has no
  analog here.
- It DOES have `Production Qty`, `Expected Qty`, `Variance Amount/Percent`,
  filterable by `Workcenter Code` and `Date` — genuinely goal-vs-actual by
  workcenter/date, the one real structural overlap.

**Per-sheet fit, weakest to strongest:**
- **Encap** — worst fit. No weight concept in the template at all (capsule
  counts only); Production Yield is fundamentally weight-centric.
- **Packaging / Labeling** — weak fit. Bottle/label counts, not weights;
  "Tips Tails"/"Coil"/"Heat No" read as raw-material-coil or ingredient
  weigh-out concepts, not finished-good packaging counts.
- **Blending** — weakest-but-most-plausible. The template's "Pre-Weigh
  1/2/3" stations and "Daily Weigh-Out Goal/Total" rows are genuinely a
  weighing workflow, closer to Production Yield's domain — but still
  unconfirmed, and still missing the operator/time-checkpoint half.

**Better lead for the "Actual" output number specifically:** aggregate
`Part_v_Job_Op.Quantity` (or `Part_v_Cell_Production.Quantity`) by
`Complete_Date`/`Production_Date` + `Workcenter_Key` — data this project
already extracts for `mfg_job_schedule_report`/`work_orders_report`. That's
a much closer match to "how much did Line 2 pack today" than a
weighing-event report. Unconfirmed, but a more promising starting point
than Production Yield for any of these four.

- **Module / Report:** Inventory → Inventory Tracking → Production Yield
- **ReportKey / ActionKey:** 5919 / 7346 (confirmed in `mapping/available-reports.csv` row 516)
- **URL pattern:** `https://vox.on.plex.com/VisionPlex/screen?__actionKey=7346`

## Columns visible in the UI (from screenshot, 2026-08-11)

Filters: Date (range), Workcenter Code, From Serial No, Customer Code,
Supplier Code, Part No, From Container Type, From Part No, Heat No, Weigh
Scale Only (checkbox), Variance Only (checkbox).

Result grid: Part No, Part Name, Gross Part Weight, Material, Container
Type, Serial No, Original Weight, Current Gross Weight, Tips Tails Weight,
Adjustment Weight, Adjusted Coil Weight, Pieces Scrapped, Production Qty,
Actual Gross Weight, Gross Weight without Tips/Tails, Gross Weight All
Adjustments, Heat No, Expected Qty, Variance Amount, Variance Percent.

## Plausible Plex ODBC lead (unconfirmed)

`Part_v_Container` (already confirmed live — see
`catalog/plex_part_views_catalog.md` "Confirmed Live" section, and
[mfg_job_schedule.md](mfg_job_schedule.md)'s on-hand-inventory finding) has
`Tare_Weight`, `Gross_Weight`, `Net_Weight`, `Heat_Key`, `Serial_No`, and
`Part_Key` columns directly — a strong naming overlap with this screen's
grid (Gross Part Weight, Current Gross Weight, Heat No, Serial No). **Not
verified** — this is a plausible starting point for whoever maps the 3
Daily Report spreadsheets against real Plex data, not a confirmed join.
"Tips Tails Weight," "Adjusted Coil Weight," "Variance Amount/Percent," and
"Pieces Scrapped" have no obvious `Part_v_Container` analog and would need
their own investigation (weighing/scrap-tracking is a different feature
area than plain container inventory).

## Next step

Each of the 3 spreadsheets below still needs its own actual content (CSV
export or full column list) before a column-by-column mapping can be done —
sharing a reference Plex report doesn't mean the 3 sheets have identical
columns to each other. See each spreadsheet's own stub doc.
