# Label Design — project hub

A self-contained mini-project riding along inside `plex-to-big-query`: a
Plex → BigQuery → Monday.com queue that replaced a twice-daily manual loop
(download a NetSuite report, paste into a sheet, check for duplicates by
hand, upload to Monday). **Not related to the Vox Nutrition scorecard work**
this repo otherwise tracks — this folder exists so the two don't blend
together.

> **Where it stands (2026-10-22).** Live in prod since the 2026-10-19 cutover.
> - **ETL:** `plex-etl-label-design` probes Plex every 15 minutes, 5:00 AM -
>   5:45 PM Mountain, weekdays, and extracts only when an order, line, release
>   or approval changed.
> - **Push:** a run that extracts starts `plex-etl-label-design-push`
>   (`label_design_service/push.py`). It creates one item per new order line
>   on "Plex Import" (18432111755), deduped by an LCR hash and audited in
>   `label_design_push_log`. A 6:05 PM sweep catches a push that failed.
> - **Repair (2026-10-22):** Ashley moves items on to "Design & QA"
>   (18395121955), and Monday's saved column matching drops some values on
>   the way (Bottle Material). `plex-etl-label-design-repair`
>   (`label_design_service/repair.py`, every 15 min) fills each moved item's
>   blank pushed columns once, from the push log.
> - **Retired:** the Sheet-based Apps Script (`deploy/archive/label_design_sync/`)
>   and the Plex REST API push (`deploy/plex_api_function/ARCHIVED.md`).
>
> For what's built, verified and blocked, read [`STATUS.md`](STATUS.md) first.

This page is a map, not a copy. The working files live where the rest of the
pipeline's conventions expect them (Terraform's GCS paths, the pipeline's
`reports/` layout); nothing was moved here to avoid breaking those.

## Start here

| If you want... | Go to |
|---|---|
| **Current status, what's pending, what's blocked** | [`STATUS.md`](STATUS.md) |
| The plain-English "how do I use it" guide (Sheet-based flow, **retired**) | [`deploy/archive/label_design_sync/TEAM_GUIDE.md`](../deploy/archive/label_design_sync/TEAM_GUIDE.md) |
| What the Monday board's columns mean | [`monday_board_guide.md`](monday_board_guide.md) |
| The board's real column ids + full option lists | [`monday_board_catalog.md`](monday_board_catalog.md) |
| The business-facing report doc | [`docs/reports/label_design_report.md`](../docs/reports/label_design_report.md) |
| The technical design of the Sheet-based Apps Script (**retired**) | [`deploy/archive/label_design_sync/README.md`](../deploy/archive/label_design_sync/README.md) |
| The Plex → Monday push service | [`label_design_service/push.py`](../label_design_service/push.py) docstring |
| The repair job (refills what a board move dropped) | [`label_design_service/repair.py`](../label_design_service/repair.py) docstring |
| Run the ETL on demand (web app) | [`deploy/label_design_trigger/README.md`](../deploy/label_design_trigger/README.md) |
| How to work on this project: its folder, branch, hooks, deploy | [`CONTRIBUTING.md`](../CONTRIBUTING.md): folder `ptbq-label-design`, branch `dev-label-design` |

## How the data flows

```
Plex ERP
  │  (Cloud Run job: plex-etl-label-design, probe every 15 min, 5:00 AM - 5:45 PM MT, weekdays)
  ▼
BigQuery — label_design_report view
  │  (a run that extracts starts the push; 6:05 PM sweep as a safety net)
  ▼
label_design_service/push.py (plex-etl-label-design-push) → Monday "Plex Import" (18432111755)
  │  dedupes by LCR hash; every attempt in label_design_push_log
  ▼  (Ashley moves items by hand)
Monday "Design & QA" (18395121955)
  ▲
  └── label_design_service/repair.py (plex-etl-label-design-repair, every 15 min)
        fills the pushed columns a move left blank, once per item
```

## Where everything actually lives

**Pipeline (BigQuery)**
- [`reports/label_design.yaml`](../reports/label_design.yaml) /
  [`reports/test/label_design.yaml`](../reports/test/label_design.yaml) — prod/test configs
- [`reports/sql/label_design_view.sql`](../reports/sql/label_design_view.sql) — the view SQL
- Terraform resources: search `terraform/main.tf` for `label_design` (job,
  schedulers, GCS objects — added 2026-09-12, see `CHANGELOG.md`)

**Sheet → Monday (Apps Script) — RETIRED 2026-10-02**, archived in
[`deploy/archive/label_design_sync/`](../deploy/archive/label_design_sync/). Kept for the
record only; nothing runs it.
- `Code.gs` — the logic: dedupe, sheet writes, the Monday push
- `Logo.gs` — the Vox wordmark, base64 (Apps Script can't read a repo file)
- `test_logic.js` — its test harness, frozen with the rest
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
