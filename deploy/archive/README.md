# deploy/archive

Last reviewed: 2026-10-02

Deployed code kept for the record, not for use. Each folder here ran in
production once and has been replaced. Read it for *why* something is the way
it is; don't paste it into an Apps Script editor, don't deploy it, and don't
update it to match the present. Every file carries a banner saying when it was
archived and where the live version of its subject now lives.

| Folder | Archived | Why | Live information instead |
|---|---|---|---|
| [label_design_sync/](label_design_sync/) | 2026-10-02 | The Sheet → Monday Apps Script, replaced by the push service | `label_design_service/push.py`, `label-design/STATUS.md` |

**Archiving deployed code is not the same as switching it off.** An Apps Script
project lives in Google, not in this repo, so moving the source here stops
nothing. Confirm the deployed project's triggers are gone *before* archiving —
this repo has precedent for getting that wrong, in
`deploy/goals_sheet_to_bigquery.gs`, whose trigger kept truncating a BigQuery
table for weeks after the file was deleted (CLAUDE.md, "Goals").

For `label_design_sync` that check came back clean: its only scheduled
functions were `checkForNewOrdersAuto` (sheet refresh — it never touched
Monday.com; the push was menu-only) and `sendDailySummary`, and no summary
email has reached the recipient list since the changeover.

**Archiving a folder:** `git mv` it here (history follows), put the banner
under each document's title, add a row above, fix the links that pointed at the
old path, and check for scripts that *write into* the folder — the logo
generator wrote `label_design_sync/Logo.gs` and had to lose that half.
