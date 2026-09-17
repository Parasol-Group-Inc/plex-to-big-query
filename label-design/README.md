# Label Design — project hub

A self-contained mini-project riding along inside `plex-to-big-query`: a
Plex → BigQuery → Monday.com queue that replaced a twice-daily manual loop
(download a NetSuite report, paste into a sheet, check for duplicates by
hand, upload to Monday). **Not related to the Vox Nutrition scorecard work**
this repo otherwise tracks — this folder exists so the two don't blend
together.

> **Mid-pivot as of 2026-09-16**: the Google Sheet is being dropped from this
> flow entirely, replaced by a standalone service comparing BigQuery directly
> against the Monday board. **For the actual current status — what's built,
> what's verified, what's still blocked — see
> [`STATUS.md`](STATUS.md)
> first, before anything else on this page.** Most of this README still
> describes the Sheet-based flow and hasn't been rewritten for the new
> architecture yet.

This page is a map, not a copy. The working files live where the rest of the
pipeline's conventions expect them (Terraform's GCS paths, the pipeline's
`reports/` layout); nothing was moved here to avoid breaking those.

## Start here

| If you want... | Go to |
|---|---|
| **Current status, what's pending, what's blocked** | [`STATUS.md`](STATUS.md) |
| The plain-English "how do I use it" guide (Sheet-based flow, being retired) | [`deploy/label_design_sync/TEAM_GUIDE.md`](../deploy/label_design_sync/TEAM_GUIDE.md) |
| What the Monday board's columns mean | [`monday_board_guide.md`](monday_board_guide.md) |
| The board's real column ids + full option lists | [`monday_board_catalog.md`](monday_board_catalog.md) |
| The business-facing report doc | [`docs/reports/label_design_report.md`](../docs/reports/label_design_report.md) |
| The technical design of the Apps Script | [`deploy/label_design_sync/README.md`](../deploy/label_design_sync/README.md) |

## How the data flows

```
Plex ERP
  │  (Cloud Run job: plex-etl-label-design, 09:30 / 13:30 Mountain, every day)
  ▼
BigQuery — label_design_report view
  │  (Apps Script: reads BigQuery, dedupes, writes new rows)
  ▼
Google Sheet — MONDAY tab (reviewable) / historical tab (append-only archive)
  │  (Apps Script: pushes to Monday, only once a person has reviewed)
  ▼
Monday.com — "Design & QA" board (18395121955)
```

## Where everything actually lives

**Pipeline (BigQuery)**
- [`reports/label_design.yaml`](../reports/label_design.yaml) /
  [`reports/test/label_design.yaml`](../reports/test/label_design.yaml) — prod/test configs
- [`reports/sql/label_design_view.sql`](../reports/sql/label_design_view.sql) — the view SQL
- Terraform resources: search `terraform/main.tf` for `label_design` (job,
  schedulers, GCS objects — added 2026-09-12, see `CHANGELOG.md`)

**Sheet → Monday (Apps Script)** — all in [`deploy/label_design_sync/`](../deploy/label_design_sync/)
- `Code.gs` — the logic: dedupe, sheet writes, the Monday push
- `Logo.gs` — the Vox wordmark, base64 (Apps Script can't read a repo file)
- `test_logic.js` — `node deploy/label_design_sync/test_logic.js`, run after
  any change to the sheet-column mapping or the dedupe keys
- `README.md` — technical design/reference
- `TEAM_GUIDE.md` — plain-English, for the team
- `MEETING_BRIEF.md` — open decisions and the recommended longer-term shape
- `REFERENCE_DATA.md` — the config-driven enrichment layer's settings

**Monday board**
- [`monday_board_catalog.md`](monday_board_catalog.md) — technical: every
  column's real id, type, and full option list
- [`monday_board_guide.md`](monday_board_guide.md) — plain-language: what the
  board tracks and what each stage means
- Board: https://voxnutrition-company.monday.com/boards/18395121955

**Source sheet**
- https://docs.google.com/spreadsheets/d/1sGMt4xHrtTyDKAbUPXH2cE94OUEsamoFOldBDDvfF0w/edit
- The `MONDAY` tab's real header row is committed at
  [`assets/Copy of Design in Monday- NEW - MONDAY.csv`](../assets/Copy%20of%20Design%20in%20Monday-%20NEW%20-%20MONDAY.csv)
  (header only — this is what `SHEET_MAP` in `Code.gs` is built from).
  The `historical` tab's full export is **gitignored** — it's a live customer
  list (real names/emails/order history); it's backed up to the state bucket
  instead. See the note at the top of `.gitignore` for how to fetch it back.

**History** — search `CHANGELOG.md` for `Label Design` / `label_design` for
the full build history: the original 2026-09-11 build, the 2026-09-12
infrastructure fixes (the job/scheduler had never existed), and the SQL fixes
found once the view was actually built for the first time.

## Known open decisions

These block finishing the Monday push and are recorded in more detail in
`monday_board_catalog.md` and `MEETING_BRIEF.md`:

- **Two "Sales Rep" columns** on the board (a fixed-name dropdown vs. a real
  people-assignment column) — which is the source of truth?
- **Two phone columns** (`Phone`, numeric vs. `Phone Number`, text) — which
  one the pipeline should write formatted phone strings to.
- **`Label SKU` is the item's own name**, not a separate column — so a
  created Monday item's title should be the SKU, not `customer — part`.
