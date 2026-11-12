#!/usr/bin/env python3
"""The "New developer" tab of the Plex Data Hub (2026-11-12): static text taken from docs/ONBOARDING.md.
No BigQuery at render time. build_hub.py injects it like budget_tab.py; keep it and the doc in step.
"""
from __future__ import annotations

import html
import re
import sys

START, END = "<!--onboard-tab-start-->", "<!--onboard-tab-end-->"
NAV = '["platform", "Schedules & probe", ""]'
STATS = '  $("#q").disabled = '
KEY, LABEL = "onboarding", "New developer"

TITLE = "Your first day on plex-to-big-query"
LEDE = ("Plex ERP to BigQuery ETL on Cloud Run, deployed with Terraform. About an hour, mostly waiting for access. "
        "Full text: docs/ONBOARDING.md. Reviewed 2026-11-12.")


def SECTIONS():
    return [
        ("Day 1 setup", ul([
            "Ask an Owner for read access: GitHub, the six secrets, build-assets and terraform-state buckets, BigQuery, Cloud Run and Logs, Monday board, Plex test login.",
            "Install git, gcloud (login and application-default login), Python 3.12 (a `python` on PATH), Docker, Terraform on the deploy machine only.",
            "Clone, then run ./scripts/dev_setup.sh --worktrees: driver, .env from Secret Manager, git hooks, project folders.",
            "Health check: docker compose build && docker compose up (read-only; writes a CSV to output/). Apple Silicon: DOCKER_DEFAULT_PLATFORM=linux/amd64.",
            "Your own terminal must run gcloud as you: ~/.config/gcloud/active_config must say default, not claude.",
        ])),
        ("Folders and branches", tbl(["Folder", "Branch", "Use"], [
            ("plex-to-big-query", "main", "merging and deploying. Never edit here."),
            ("ptbq-scorecard", "dev-scorecard", "Vox Scorecard"),
            ("ptbq-sandbox", "dev-sandbox", "Scorecard Sandbox"),
            ("ptbq-label-design", "dev-label-design", "Label Design"),
            ("ptbq-part-lot", "dev-part-lot", "Part Lot Attributes and inheritance"),
            ("ptbq-dev", "dev", "shared tooling: main.py, Terraform, hooks, scripts"),
        ]) + "<p class=\"lede\">Branches hold different files; main is the truth. Never git switch a folder onto another branch. .env, driver/ and terraform.tfvars are gitignored and not shared between folders.</p>"),
        ("How a change goes live", code([
            "edit in project folder -> commit (hooks check) -> PR into main -> ./scripts/deploy.sh -> verify in BigQuery",
        ]) + ul([
            "Every behaviour change gets a CHANGELOG.md entry in the same commit, and its docs/reports/ doc.",
            "A report has two configs (reports/<name>.yaml and reports/test/<name>.yaml): change both.",
            "A green job run is not proof: query the view.",
            "Prod run times are rows in PlexOps.etl_schedule (change with SQL). The dispatcher is a Cloud Function deployed with gcloud (command in terraform/main.tf).",
            "Image code (main.py, label_design_service/) needs a Cloud Build after the deploy.",
            "Check drift: terraform plan -var-file=terraform.tfvars from the primary folder on clean main; fix with deploy.sh.",
        ])),
        ("Where status lives", tbl(["File", "What it holds"], [
            ("docs/OPEN_ITEMS.md", "every open item, owner, next step. Read first."),
            ("CHANGELOG.md", "every change, newest first"),
            ("docs/OPERATIONS.md", "runbooks: watchdog, probe, backups, batch emails"),
            ("docs/reports/REPORT_CATALOG.md", "one business doc per deployed view"),
            ("reports-list/ and spreadsheets/", "company reports mapped to Plex"),
            ("docs/DISASTER_RECOVERY.md", "what is backed up where, how to rebuild"),
            ("CLAUDE.md", "the hard-won rules"),
        ])),
        ("The rules", ul([
            "Never git commit --no-verify, and never use an override variable nobody asked for.",
            "Deploy only with ./scripts/deploy.sh from the primary folder. Never a bare terraform apply.",
            "Never gcloud storage cp into the prod reports/ or sql/ paths.",
            "Never commit .env, terraform.tfvars, driver/, zipfiles/ or a customer export.",
            "Never paste a secret into chat, a ticket or a commit.",
            "Stage by explicit path, never git add -A.",
        ])),
        ("First tasks", ul([
            "Read OPEN_ITEMS.md and the top three CHANGELOG entries.",
            "Run the health check and read one job's log in Cloud Run.",
            "Query one view in BigQuery.",
            "Read DISASTER_RECOVERY.md.",
            "Make a doc-only change on dev, open a PR, watch the hooks. Do not deploy yet.",
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
