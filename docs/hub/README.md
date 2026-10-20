# Plex Data Hub

`index.html` is one self-contained page over the whole pipeline: every report
view, raw table and pipeline as a card, plus schedules, the probe and
dispatcher logic (Mermaid), Cloud Run jobs, datasets, deploy guards, recent
changes and open items. Clicking a card opens:

- **Report:** overview and lineage (Plex view → raw table → upstream view → report → readers), the Plex SQL Developer query, the BigQuery SQL and the business doc.
- **Raw table:** extraction settings (filter, probe columns), column list from the schema catalog, the reports that read it, and an aliased `SELECT TOP 100` for Plex.
- **Pipeline:** jobs, prod/test YAML count check, views, tables and the prod YAML.
- **Scorecard tile** (Scorecard tab): the question it answers, today's source and its audit verdict, the replacing view(s) linked to their report modals, raw tables, the Field Manual's "why it is built this way" and "watch out", and the view's Plex and BigQuery SQL. Report modals link back to the tiles that read them.

The Scorecard tab also carries the open decisions, the manual-data forms and hand-edited tables, vocabulary traps, "what might not be true", both glossaries (scorecard terms and Plex field names) and recent scorecard changes. It merges two artifacts that stay where they are: the Vox Migration Board (shared with Jennilyn, still published from `scripts/board/`) and the Scorecard Field Manual.

Published as an artifact: https://claude.ai/artifact/UYTn9LfVwgZe9MLgBAVeAt
(private to its owner until shared from the page's Share menu).

## Regenerate

```bash
python scripts/hub/build_hub.py
```

Run it after any change to `reports/*.yaml`, `reports/sql/`, `reports/plex_sql/`
or `docs/reports/`, commit the new `index.html`, and republish the artifact.
Edit the page in `scripts/hub/template.html`, never `index.html`.

| Input | What it gives the page |
|---|---|
| `reports/*.yaml`, `reports/test/*.yaml` | pipelines, extractions, `bq_view` lists, prod/test count check |
| `reports/sql/*.sql` | BigQuery SQL; `raw_*` and `{dataset}.<view>` references build the lineage |
| `reports/plex_sql/*.sql` | Plex SQL Developer equivalents and their header (`confidence`, `plex_views`, `notes`) |
| `docs/reports/*.md` | status line and business doc |
| `catalog/full_schema_catalog.csv` | columns and types of each Plex view |
| `docs/hub/platform.json` | jobs, schedules, probe, functions, ops tables, Mermaid, changelog, open items, traps |
| `scripts/board/board_data.py` | scorecard tiles, open decisions, forms, glossary, recent changes: imported, so the hub and the Migration Board never disagree |
| `docs/hub/field_manual.json` | per-tile teardowns (matched to tiles by view name), traps, risks, the 93-term Plex glossary |

`field_manual.json` is a one-time snapshot of the Field Manual artifact
(https://claude.ai/code/artifact/2e629322-e24f-4402-87bd-77217143011a), which has
no generator in the repo. Edit the JSON when a teardown changes. The board's
content is owned by the scorecard project: change it on `dev-scorecard`, not here.
A tile whose view no pipeline creates shows a red "view not built" pill, and the
build prints it.

`platform.json` is hand-curated, compiled from CLAUDE.md, CHANGELOG.md,
`docs/PROBE_BUILD_PLAN.md`, `docs/OPEN_ITEMS.md` and `terraform/main.tf` on
2026-10-20. It does not update itself: refresh it when schedules, jobs or the
probe change. Values that come from the gitignored `terraform.tfvars` (the
scheduler time zone, the Sales Orders test cron) are taken from the docs.

## Plex SQL equivalents

Every table is aliased (`FROM Sales_v_PO AS po`), as Plex SQL Developer
requires even for single-table queries. A report view that reads another
report view has the upstream logic inlined as CTEs, so each file runs on its
own. None has been run in Plex yet: see D12 in `docs/OPEN_ITEMS.md`.
