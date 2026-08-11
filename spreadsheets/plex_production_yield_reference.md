# Reference: Plex "Production Yield" UI report

Shared reference for the three Daily Report spreadsheets (Packaging,
Labeling, Blending) that were flagged as building on this existing Plex UI
screen. Per [[feedback-plex-ui-reports-reference-only]] and the note at the
bottom of [SPREADSHEET_CATALOG.md](SPREADSHEET_CATALOG.md): this is a lead
for which raw ODBC views likely back the business concept, **not** a
resolved data source — the screen itself isn't queryable by this pipeline.

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
