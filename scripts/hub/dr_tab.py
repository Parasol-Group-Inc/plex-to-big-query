#!/usr/bin/env python3
"""The "Disaster recovery" tab of the Plex Data Hub (2026-11-12): static text taken from docs/DISASTER_RECOVERY.md.
No BigQuery at render time. build_hub.py injects it like budget_tab.py; keep it and the doc in step.
"""
from __future__ import annotations

import html
import re
import sys

START, END = "<!--dr-tab-start-->", "<!--dr-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "dr", "Disaster recovery"

TITLE = "If something breaks: where the backup is and how to restore"
LEDE = ("Two cases: a table or file is damaged (minutes to fix), or the whole GCP project is gone (a working day). "
        "Full text and commands: docs/DISASTER_RECOVERY.md. Reviewed 2026-11-12.")


def SECTIONS():
    return [
        ("What can break and where the copy is", tbl(["What went wrong", "Where the copy is", "How to restore"], [
            ("A table or view deleted or overwritten", "BigQuery time travel, 7 days, automatic", "bq cp voxdatalake:PlexProd.<t>@<ms-epoch> voxdatalake:PlexProd.<t>_restored"),
            ("A BigQuery-only table damaged (etl_schedule, probe_log, msl_demand_daily, scorecard_goals_app, VoxScorecardsLive)", "Backups dataset: <Dataset>__<table>_<YYYYMMDD>; weekly, kept 90 days (VoxScorecardsLive 11-11 copies never expire)", "bq cp -f voxdatalake:Backups.<name> voxdatalake:<Dataset>.<table>_restored, compare, then swap"),
            ("A raw table or report view is wrong", "Plex and git", "Re-run the job; views are rebuilt from reports/sql/"),
            ("Terraform state damaged", "gs://voxdatalake-terraform-state, versioned (471 versions on 11-12)", "gcloud storage ls -a on the bucket, copy the good generation back, terraform init"),
            ("Code lost", "GitHub, and git bundles in ~/plex-monitor/backups/ on Emilio's Mac", "git clone <bundle> restore-dir"),
            ("Dispatcher stopped", "deploy/etl_dispatcher/ and PlexOps.etl_schedule", "Redeploy with the gcloud functions deploy command in terraform/main.tf"),
            ("A prod run time is wrong", "PlexOps.etl_schedule (days column since 11-12); Backups.PlexOps__etl_schedule_20261112", "Change it with SQL, not Terraform"),
            ("A laptop is lost", "scripts/backup_to_bucket.ps1 copy; dev_setup.sh", "dev_setup.sh rebuilds .env and driver/"),
        ])),
        ("Commands", code([
            "bq ls --max_results=500 voxdatalake:Backups",
            "bq cp -f voxdatalake:Backups.PlexOps__etl_schedule_20261112 voxdatalake:PlexOps.etl_schedule_restored",
            "gcloud storage ls -a gs://voxdatalake-terraform-state/plex-to-big-query/",
            "./scripts/restore_secrets.sh --project NEW-PROJECT-ID --apply",
        ]) + "<p class=\"lede\">Restores are writes: Claude Code does them only as claude-operator, a person with their own login.</p>"),
        ("How much could we lose, and for how long (plain words)", ul([
            "Anything the ETL reloads: at most until the next run.",
            "BigQuery-only tables: minutes inside the 7-day time-travel window, otherwise up to a week (weekly snapshot).",
            "One table back: about 15 minutes. The whole project from nothing: a working day, mostly waiting on Plex support if the driver licence is lost.",
        ])),
        ("The whole project is gone (Scenario B)", ul([
            "Create the project, state bucket (versioned) and build-assets bucket; restore driver and licence.",
            "Edit the backend bucket in terraform/main.tf, commit and push to main, then terraform init and ./scripts/deploy.sh.",
            "Restore the six secret values with scripts/restore_secrets.sh from secrets.env.",
            "Build and push the image tagged with the commit SHA; set image_url; deploy again.",
            "Deploy the dispatcher with gcloud before the schedulers hit it, then load PlexOps.etl_schedule from seed_schedule.sql or the latest backup.",
            "Run every test job (15) and query each view: exit 0 does not prove a view exists.",
        ])),
        ("Known gaps", ul([
            "Backups, state bucket and secrets all live in voxdatalake: they cover mistakes, not loss of the project. Git is the only outside copy.",
            "No off-GCP copy of the driver licence or secret values yet; a second Owner must exist (Emilio Dominguez and Jennilyn Tockstein today).",
            "The hourly Windows/Mac monitors are not infrastructure: losing a laptop stops no production job.",
        ])),
        ("Who to call", ul([
            "Project Owners: Emilio Dominguez, Jennilyn Tockstein.",
            "Plex support for the ODBC driver licence; SendGrid and Monday admins for their keys.",
        ])),
    ]


def esc(s) -> str:
    return html.escape(str(s))


def table(head, rows, num_cols=()):
    h = "".join(f'<th{" class=num" if i in num_cols else ""}>{esc(x)}</th>' for i, x in enumerate(head))
    b = "".join("<tr>" + "".join(f'<td{" class=num" if i in num_cols else ""}>{c}</td>' for i, c in enumerate(r)) + "</tr>"
                for r in rows)
    return f'<div class="tbl-wrap"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'


def tbl(head, rows):
    return table(head, [tuple(esc(x) for x in r) for r in rows])


def ul(items):
    return '<ul class="plain">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def code(lines):
    return '<pre class="code"><code>' + esc("\n".join(lines)) + "</code></pre>"


def render_tab() -> str:
    body = "".join(f'<div class="block"><h2>{esc(t)}</h2>{h}</div>' for t, h in SECTIONS())
    return f"""{START}<section id="s-{KEY}" data-tab="{KEY}" hidden><div class="ref">
<div class="block"><h2>{esc(TITLE)}</h2><p class="lede">{esc(LEDE)}</p></div>
{body}
</div></section>{END}"""


def inject(page: str, tab: str) -> str:
    if START in page:
        page = re.sub(re.escape(START) + ".*?" + re.escape(END) + "\n?", lambda m: "", page, flags=re.S)
        page = page.replace(f', ["{KEY}", "{LABEL}", ""]', "").replace(f'  if (k === "{KEY}") $("#stats").hidden = true;\n', "")
    anchor = '  <section id="s-history"'
    for needle in (anchor, NAV, STATS):
        if page.count(needle) != 1:
            sys.exit(f"hub page changed shape: expected exactly one {needle!r}, found {page.count(needle)}")
    page = page.replace(anchor, tab + "\n" + anchor)
    page = page.replace(NAV, NAV + f', ["{KEY}", "{LABEL}", ""]')
    page = page.replace(STATS, f'  if (k === "{KEY}") $("#stats").hidden = true;\n' + STATS)
    return page


def add(live: str) -> str:
    return inject(live, render_tab())


if __name__ == "__main__":
    sys.exit(__doc__)
