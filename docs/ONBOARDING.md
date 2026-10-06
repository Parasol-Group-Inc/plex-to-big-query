# Onboarding — your first day on plex-to-big-query

This repo pulls data from **Plex ERP** into **BigQuery** (`voxdatalake`), builds
views on top, and pushes the Label Design queue to **Monday.com**. It runs as
Cloud Run Jobs on a schedule, deployed with Terraform. This page gets you from
nothing to a working machine, and says where everything else is written down.

It takes about an hour. Most of it is waiting for access.

---

## 1. Access to ask for

Ask a project **Owner** (today: Emilio Dominguez or Jennilyn Tockstein) for
the following. Everything in the first table is **read-only**. You can't break
production with it.

| What | Why you need it | How it's granted |
|---|---|---|
| **GitHub:** write access to `Parasol-Group-Inc/plex-to-big-query` | clone, push branches, open PRs | GitHub org admin |
| **Secret Manager:** Secret Accessor on the six secrets `plex-access-token`, `plex-odbc-user`, `plex-odbc-password`, `plex-company-code`, `sendgrid-api-key`, `monday-api-key` | `scripts/dev_setup.sh` builds your `.env` from them | GCP IAM, per secret |
| **Storage:** Object Viewer on `voxdatalake-build-assets` | the licensed Plex ODBC driver. Docker can't build without it | GCP IAM, on the bucket |
| **Storage:** Object Viewer on `voxdatalake-terraform-state` | the tfvars backup and the repo backups | GCP IAM, on the bucket |
| **BigQuery:** Data Viewer + Job User on `voxdatalake` | query the views and raw tables | GCP IAM, project |
| **Cloud Run Viewer + Logs Viewer** on `voxdatalake` | see the jobs, their runs and their logs | GCP IAM, project |
| **Monday:** a seat on the "Plex Import" board | see what the Label Design push creates | Monday admin |
| **Plex test** web login (`vox.test.on.plex.com`) | enter test orders, check the links the push writes | Plex admin |

**Deploying is a separate grant,** given once you know the flow:
- rights to run `terraform apply` and Cloud Build;
- write access to the buckets;
- adding secret versions.

Deploys happen only from the primary folder, through `./scripts/deploy.sh`.

> The secrets are real credentials. Never paste one into chat, a ticket or a
> commit. `.env` is gitignored for that reason.

---

## 2. Install the tools

| Tool | Needed for | Notes |
|---|---|---|
| Git (Git Bash on Windows) | everything | |
| Google Cloud SDK (`gcloud`) | everything | then `gcloud auth login` **and** `gcloud auth application-default login` |
| Python 3.12 + `pip install google-cloud-bigquery` | queries, scripts | the deploy guard runs `python`, not `python3` |
| Docker Desktop, Linux containers | running the ETL locally | |
| Terraform ≥ 1.6 | deploy machine only | |
| GitHub CLI (`gh`) | optional, for PRs | |

---

## 3. Get the code and set up the machine

```bash
git clone https://github.com/Parasol-Group-Inc/plex-to-big-query.git C:/F/Parasol/plex-to-big-query
cd C:/F/Parasol/plex-to-big-query
./scripts/dev_setup.sh --worktrees
```

`dev_setup.sh` checks your tools and login, then:
1. downloads the licensed driver into `driver/`;
2. writes `.env` from Secret Manager, without printing any value;
3. installs the git hooks;
4. creates one folder per project (below).

If a step fails, it names the access you are missing. Add
`--deploy-machine` only on the machine that will deploy; it restores
`terraform/terraform.tfvars` from its bucket backup.

**Health check:** it's safe and read-only. It pulls one Plex test table into a
CSV in `output/`:

```bash
docker compose build && docker compose up    # then: docker compose down
```

---

## 4. Folders and branches: read this before your first edit

One repo, **five folders**, each bound to its own branch (git worktrees):

| Folder | Branch | Use it for |
|---|---|---|
| `plex-to-big-query` | `main` | merging and deploying. **Never edit here.** |
| `ptbq-scorecard` | `dev-scorecard` | Vox Scorecard |
| `ptbq-sandbox` | `dev-sandbox` | Scorecard Sandbox |
| `ptbq-label-design` | `dev-label-design` | Label Design |
| `ptbq-dev` | `dev` | shared tooling: `main.py`, Terraform, hooks, scripts |

**The branches hold different files.** Work sits on a project branch until it
is merged into `main`. On 2026-09-30, for example, `dev-scorecard` had 4
commits `main` didn't have and was 21 behind it: 16 files differed. The same
`reports/sql/…` file can say different things in two folders.
- **`main` is the truth** for what's deployed.
- **See how far a branch is from `main`:**
  `git fetch && git diff --stat origin/main origin/dev-scorecard`.
- **Never `git switch`** a folder onto another branch; the hooks refuse the
  commit. Open the folder of the project you're working on.
- **Gitignored files aren't shared between folders.** That includes `.env`,
  `driver/` and `terraform.tfvars`. Copy `.env` into a folder if you run the
  ETL there. tfvars lives in the primary folder only.
- **Other machines:** Emilio also works from a Mac. Always `git fetch` before
  starting, because the branch on GitHub can be ahead of your folder.

---

## 5. How a change goes live

```
edit in the project folder ─► commit (hooks check it) ─► PR into main ─► ./scripts/deploy.sh ─► verify in BigQuery
```

- **Every behaviour change** gets a `CHANGELOG.md` entry in the same commit
  (the hook enforces it for `reports/` and `terraform/`).
- **Every report change** also updates its business-facing doc in
  `docs/reports/`.
- **A report has two configs,** `reports/<name>.yaml` and
  `reports/test/<name>.yaml`. Change both (a hook checks they list the same
  number of extractions).
- **A green job run is not proof.** Query the view itself afterwards.
- **Code in the image** (`main.py`, `label_design_service/`) needs a Cloud
  Build after the deploy (`docs/OPERATIONS.md`).

Every lock and its override: [CONTRIBUTING.md](../CONTRIBUTING.md). Every
command on one page: [docs/CHEATSHEET.md](CHEATSHEET.md).

---

## 6. Where the state of things is written down

| File | What it holds |
|---|---|
| [docs/OPEN_ITEMS.md](OPEN_ITEMS.md) | every open item, owner and next step. **Read first.** |
| [CHANGELOG.md](../CHANGELOG.md) | every change, newest first, dated |
| [label-design/STATUS.md](../label-design/STATUS.md) | Label Design, newest update first |
| [docs/reports/REPORT_CATALOG.md](reports/REPORT_CATALOG.md) | one business doc per deployed view |
| [reports-list/](../reports-list/) and [spreadsheets/](../spreadsheets/) | company reports mapped to Plex |
| [docs/DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) | what is backed up where, and how to rebuild |
| [CLAUDE.md](../CLAUDE.md) | the hard-won rules, written for Claude Code but true for everyone |

---

## 7. Known friction (so you don't lose an afternoon)

- **"Reauthentication failed … cannot prompt"** from `gcloud`: an org policy
  expires your login. Run `gcloud auth login` in your own terminal; it can't
  be scripted.
- **`bq` fails with "python3.12: command not found"** in Git Bash on Windows.
  Use the Python client (`google.cloud.bigquery`) instead.
- **`git push` 403** while `gh auth status` looks fine: a GitHub org setting,
  not your config. Ask an org admin.
- **PowerShell `.ps1` files** must be saved as UTF-8 **with** BOM, or Windows
  PowerShell 5.1 misreads them.
- **Plex test is wiped nightly.** Test orders you enter are gone the next day.

## 8. Never

- `gcloud storage cp` into the prod `reports/` or `sql/` paths: that is how
  prod once drifted from `main`.
- `terraform apply` directly, or from any folder but the primary one. Use
  `./scripts/deploy.sh`.
- `git commit --no-verify`, or an override variable nobody asked for.
- Commit `.env`, `terraform.tfvars`, `driver/`, `zipfiles/` or a customer
  export.
