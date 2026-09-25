# Working agreement — how changes get made in this repo

This is a short, practical note for anyone (human or AI assistant) picking up
work in this project, so the *way* changes get made stays consistent even as
who's making them changes.

## Keep patches proportional to the change

Prefer small, surgical edits over large rewrites, even when a bigger rewrite
would be "cleaner." Concretely:

- Touch only the functions/sections a task actually requires. Don't
  re-flow or reformat unrelated code while you're in a file.
- When a change legitimately needs to span many functions (e.g. an
  architecture change like splitting one entry point into two), that's fine
  — but say so up front, and still make each edit as targeted as possible
  rather than regenerating the whole file.
- Before reading a large file end-to-end "just to be safe," check whether a
  targeted `grep`/section read already answers the question.
- Re-run only the smallest test/verification command that actually covers
  the change (e.g. `node deploy/label_design_sync/test_logic.js` rather than
  a full project rebuild) unless there's a specific reason to believe the
  blast radius is wider.

The underlying goal is **token/compute efficiency** as a first-class concern
on this project, not just correctness — a working fix delivered as a giant
diff is a worse outcome here than the same fix delivered as a small one.

## When something needs a human instead of a big automated analysis

If a task would require a large, expensive investigation (e.g. exploring an
unfamiliar codebase area end-to-end, re-deriving state that a person already
knows, or manually reviewing something a human could just glance at and
answer in one line) — **ask first** rather than spending a lot of effort
finding out. A quick clarifying question is almost always cheaper than a
large speculative analysis.

## Branches, folders and locks — `main` is prod, work happens on `dev*`

Rebuilt 2026-09-25. The 2026-09-17 version (branches plus a preflight script
you had to remember) was not enough. In one day, two sessions shared one
working tree, a whole day of Label Design work sat uncommitted on the
scorecard branch, and an apply from `dev-scorecard` rolled back a Label Design
fix in prod without anyone noticing for two days. Each lock below exists
because one of those actually happened.

### One folder per project

| Project | Branch | Folder (git worktree) | VS Code workspace |
|---|---|---|---|
| **Deploy** (merge + deploy only, no edits) | `main` | `C:\F\Parasol\plex-to-big-query` | `main-deploy.code-workspace` |
| Vox Scorecard | `dev-scorecard` | `C:\F\Parasol\ptbq-scorecard` | `scorecard.code-workspace` |
| Scorecard Sandbox | `dev-sandbox` | `C:\F\Parasol\ptbq-sandbox` | `sandbox-scorecard.code-workspace` |
| Label Design | `dev-label-design` | `C:\F\Parasol\ptbq-label-design` | `label-design.code-workspace` |
| Shared tooling | `dev` | `C:\F\Parasol\ptbq-dev` | `dev-shared.code-workspace` |

- **Git refuses to check one branch out in two folders**, so two sessions
  can't share a branch unless one of them switches branches. The pre-commit
  hook catches that case.
- **Each workspace file opens its folder** and colours its title bar. Open
  the workspace for the project you're working on, not the folder.
- **Claude Code sessions** work in their project's folder. All folders share
  one memory directory (they're linked).
- **Terraform deploys from the primary folder only.** `terraform.tfvars` is
  gitignored, and the deploy guard (below) refuses anywhere else.
- **Deploying from another machine** (done 2026-09-25 from a Mac, while the
  usual primary folder was on Windows). The primary folder is simply a plain
  clone on `main`:
  1. Restore the variables from the bucket copy. It holds only Secret
     Manager names, never secret values:
     `gcloud storage cp gs://voxdatalake-terraform-state/plex-to-big-query/terraform.tfvars.backup terraform/terraform.tfvars`
  2. **Check it isn't stale before trusting it.** Its date is on
     `gcloud storage ls -l`. If someone has edited tfvars since then, the
     plan shows changes you didn't make. Anything beyond your own change
     means stop and get the current file.
  3. `gcloud auth application-default login`. Terraform uses these
     credentials, not the ones from `gcloud auth login`.
  4. The guard runs `python`, not `python3`. With Homebrew, put
     `/opt/homebrew/opt/python@3.14/libexec/bin` on `PATH`.
  5. A first `terraform init` on a new OS adds that platform's checksums to
     `.terraform.lock.hcl`, and the guard then refuses a dirty tree. Commit
     it through a branch and PR like any other change.
  6. If you change tfvars, re-upload it to the same path. The bucket is
     versioned, so older copies stay recoverable.
- **New machine / fresh clone:**
  ```bash
  git worktree add ../ptbq-scorecard dev-scorecard
  ```
  and the same for each project, then run `scripts/install_hooks.sh` once.

Which files belong to which project is defined **once**, in
`.githooks/hooks.py` (`LABEL_DESIGN`, `SCORECARD`). Everything else is
shared: the ETL engine, the `reports/sql` both projects use, `terraform/`,
`CHANGELOG.md` and general docs. Shared files may be committed from any
branch.

### The locks

| Lock | Where | Blocks | Override (one command, printed) |
|---|---|---|---|
| Folder ↔ branch | pre-commit | committing in a project folder that has another branch checked out | `ALLOW_WRONG_FOLDER=1` |
| `main` takes merges only | pre-commit | a non-merge commit on `main` | `ALLOW_MAIN_COMMIT=1` |
| Own project only | pre-commit | Label Design files on a scorecard branch or the reverse; one commit mixing projects | `ALLOW_CROSS_PROJECT=1` |
| Changelog with deployables | pre-commit | `reports/` or `terraform/` changes without `CHANGELOG.md` in the same commit | `ALLOW_NO_CHANGELOG=1` |
| Prod/test YAML pair | pre-commit | the two YAMLs of a pipeline listing different numbers of `plex_view:` | `ALLOW_YAML_MISMATCH=1` |
| Only `main` goes to `main` | pre-push | `git push origin dev-x:main`; non-fast-forward pushes to `main` | `ALLOW_MAIN_PUSH=1` |
| **Deploy guard** | inside Terraform | any `plan`/`apply` not in the primary folder, on `main`, clean, and equal to `origin/main` | `TF_GUARD_OVERRIDE="why"` — read-only plans only |
| **Reviewed deploy** | `scripts/deploy.sh` | applying anything but the plan you just read; destroys pass unremarked | — (type the change count to confirm) |

- **Install the hooks once per clone:** `scripts/install_hooks.sh`. It sets
  `core.hooksPath`, which covers every worktree.
- **`--no-verify` skips the hooks without a trace. Don't.** Use the named
  override instead, so the reason is visible.

### The flow: change → main → deploy

```bash
# 1. Work in the project's folder, on its branch
cd C:/F/Parasol/ptbq-label-design          # (open label-design.code-workspace)
git pull                                   # stay current
# ...edit, then commit with its CHANGELOG entry...
git push origin dev-label-design

# 2. Into main, by PR (reviewable) or by a local merge in the primary folder
gh pr create --base main --head dev-label-design --title "..." --body "..."
#   ...or: cd C:/F/Parasol/plex-to-big-query && git pull && git merge --no-ff dev-label-design && git push origin main

# 3. Deploy, from the primary folder only
cd C:/F/Parasol/plex-to-big-query && git pull
./scripts/deploy.sh                        # preflight, guard, plan, review, confirm, apply, tag

# 4. Re-sync every dev branch with what is live
cd C:/F/Parasol/ptbq-label-design && git merge main && git push origin HEAD
```

- **A Cloud Build (image) deploy is separate:** `gcloud builds submit`, same
  preflight, as in `docs/OPERATIONS.md` Step 5.
- **After a deploy, check the view, not the exit code** (CLAUDE.md).

**Keep merges to `main` small and frequent.** The `dev*` branches are
long-running and don't merge into each other, so the longer one sits
unmerged, the more it drifts on shared files. Step 4 exists for the same
reason.

## Commits

- **One change, one commit.** A milestone that builds, runs or reads right
  on its own is the unit. Several milestones in a day is normal.
- **Message:** `type(scope): what changed, in plain words`. Then a body
  saying *why*, and what was verified, with numbers where there are any.
  - **Types in use:** `feat`, `fix`, `docs`, `chore`, `refactor`.
  - **Scopes** name the project or area: `label-design`, `scorecard`,
    `sandbox`, `views`, `quality`, `dev`, `deploy`.
  - Commits written with Claude end with its `Co-Authored-By:` trailer.
- **Stage by explicit path, never `git add -A` / `git add .`.** Another
  session, or you in another window, may have files in progress in the same
  folder. That's how a day of Label Design work nearly went out under a
  scorecard commit. `git status` before every commit.
- **Anything that deploys gets a `CHANGELOG.md` entry in the same commit.**
  That's `reports/`, `terraform/`, and the Python the image runs. The hook
  enforces it for `reports/` and `terraform/`.
  - **Where the entry goes:** at the top, newest first, headed
    `## YYYY-MM-DD (project) - what happened`.
  - **What it says:** what was wrong, what changed, and how it was verified.
- **A change to a report's YAML or SQL** also updates its business doc in
  `docs/reports/` (the catalog has the template), and the status line in the
  `reports-list/` / `spreadsheets/` file that tracks it.
- **Prod and test YAML change together.** `reports/<p>.yaml` and
  `reports/test/<p>.yaml` are both hand-kept, and the hook compares their
  `plex_view:` counts.

## Pull requests

`main` receives work in two ways; both end in a merge commit on `main`.

| Use | When |
|---|---|
| **PR** (`gh pr create --base main --head <branch>`) | Anything someone else should see before it's live, and anything touching `terraform/` or `main.py`. The PR page is the review record. |
| **Local merge** (in the primary folder: `git merge --no-ff <branch>`, then `git push origin main`) | Docs-only or already-reviewed changes, when you're the only reviewer. |

```bash
# from the project's folder, after committing
git push origin dev-label-design
gh pr create --base main --head dev-label-design \
  --title "Label Design: run the sync on demand" \
  --body "What / why / how verified. Terraform changes: none (or: list them)."
gh pr view --web                 # review
gh pr merge --merge              # a merge commit, not squash: keeps the per-milestone history
```

- **Always say in the PR body whether it changes Terraform.**
  `deploy.sh` will show the same list; they should match.
- **Never push a dev branch into `main`** (`git push origin dev-x:main`). The
  pre-push hook blocks it.
- **`main` never takes force-pushes.**

## When branches conflict

These files conflict routinely. Each has one right resolution:

| File | Resolution |
|---|---|
| `CHANGELOG.md` | Keep **both** sides' entries, **newest date first**. For the same day, order by when the work happened. Check no heading appears twice. |
| `label-design/STATUS.md`, other status files | Same: keep both `## UPDATE` sections, newest first. |
| `terraform/main.tf` | Usually auto-merges (different resources). If not, keep both resources. Then run a read-only plan from the primary folder after merging; it must show only what the PR says. |
| `reports/sql/*.sql` | A real conflict: two projects changed one view. Resolve by hand, then dry-run the SQL against PlexTest (`SELECT COUNT(*) FROM (<sql>)`) before committing. |

## Kinds of deploy

| What | How | Guard |
|---|---|---|
| Report YAML/SQL, Cloud Run jobs, schedulers, IAM: **anything in `terraform/`** | `./scripts/deploy.sh` from the primary folder | Terraform deploy guard + plan review + typed confirmation. Tagged `deploy/<UTC>`. |
| **Container image** (`main.py`, `email_utils.py`, `Dockerfile`, `label_design_service/`) | `./scripts/deploy_preflight.sh`, then `gcloud builds submit --config deploy/cloudbuild.yaml --project=voxdatalake --substitutions=SHORT_SHA=$(git rev-parse --short HEAD) .` | Preflight only; nothing inside Cloud Build checks the branch. Run it from the primary folder. |
| **Apps Script** (`deploy/manual_data_app/`, `deploy/label_design_sync/`, `deploy/label_design_trigger/`) | Paste from the repo into the Apps Script editor, then Deploy → Manage deployments → **New version** | None. The repo copy is the record; paste from `main`. Saving in the editor does not update a live web app. |
| **Hand-kept BigQuery tables** (`scorecard_goals*`, `turnaround_standards`, `safety_incidents`) | The manual-data app, or DDL in `docs/reports/` | None. Never `CREATE OR REPLACE` them: they hold people's entries. |

**Quick iteration** on a view is not a deploy:
- **For SQL:** dry-run the query against PlexTest, or rebuild it in the
  ScorecardSandbox.
- **For a YAML:** copy it into the `test/` path only, and run only the
  `-test` job.
- **SQL objects in GCS are shared by prod and test,** so a copied SQL file
  changes prod's next run too. Every iteration still lands through a branch,
  `main` and `deploy.sh`, or the next deploy silently reverts it.

## After a deploy: verify, then re-sync

1. **Run the `-test` job** of each pipeline you changed:
   `gcloud run jobs execute plex-etl-<pipeline>-test --region=us-central1 --wait`.
2. **In the logs,** check `Report '<name>' loaded: N extraction(s)` against
   `grep -c 'plex_view:' reports/test/<pipeline>.yaml`.
3. **Query the view itself.** Exit code 0 does not mean the view was created
   (CLAUDE.md, "Verifying a report deploy actually worked").
4. **Prod picks up the change on its next scheduled run.** Check the prod
   view's `modified` time afterwards. Don't fire prod jobs to hurry it: they
   email the team.
5. **Re-sync every dev branch** so none drifts from what is live:
   ```bash
   for d in ptbq-scorecard ptbq-sandbox ptbq-label-design ptbq-dev; do
     (cd ../$d && git merge --no-edit main && git push origin HEAD)
   done
   ```

## Rolling back

**Revert, don't reset.** On the project's branch, `git revert <commit>`, then
PR or merge, then `deploy.sh`. The `deploy/<UTC>` tags show what was live
when:
- `git tag -l 'deploy/*'` lists every deploy;
- `git diff deploy/<a> deploy/<b> -- reports/` shows what changed between two.

`main`'s history is never rewritten. It is the record of what prod ran.

## The workspace files

| File | Opens | Title bar | Hides |
|---|---|---|---|
| `scorecard.code-workspace` | `ptbq-scorecard` | green | Label Design and Sandbox folders |
| `sandbox-scorecard.code-workspace` | `ptbq-sandbox` | amber | Label Design folders, manual-data app |
| `label-design.code-workspace` | `ptbq-label-design` | purple | Scorecard and Sandbox folders |
| `dev-shared.code-workspace` | `ptbq-dev` | slate | nothing |
| `main-deploy.code-workspace` | the primary folder | **red**: deploy only | nothing |

- **Open a workspace file, not the folder.** It sets the title, the colour,
  the hidden folders, and git branch protection on `main`.
- **Hidden isn't protected.** Hidden files are still there. The hooks, not
  the explorer, stop cross-project commits.
- **Every folder has a copy of every workspace file**, and they all resolve
  to the same five sibling folders.

## Working with Claude Code sessions

- **One session per folder.** Start it in the folder of the project you want
  worked on, via the workspace or `cd`.
- **A user-level hook warns every session.** It runs on every prompt and
  after every shell command, and flags: another session in the same folder;
  another session on the same branch; the session's own branch having
  changed. It lives at `~/.claude/hooks/session_branch_guard.py`, registered
  in `~/.claude/settings.json`. The session stops and asks.
- **Memory is shared.** Every folder's memory directory is linked to the
  primary folder's, so a session anywhere sees the same notes.
- **Claude's own limits:** it can't `terraform apply` or push to GitHub on
  this machine (the permission classifier blocks both). It prepares the
  deploy, and you run `deploy.sh` and `git push`.
- **Parallel subagents** each own disjoint files, and one session reviews and
  commits. That's how the 2026-09-24/25 sandbox and doc work was done.

## What the locks don't catch

- **Deploys outside Terraform.** Apps Script pastes, Cloud Build from a dev
  folder, `bq` DDL, and `gcloud storage cp` into prod paths. Follow the
  table above.
- **Silent data gaps.** The ETL keeps yesterday's rows when Plex returns 0
  (see `main.py` `write_to_bigquery`), so an empty tile and a stale tile can
  both look fine. `docs/SCORECARD_SANDBOX_FINDINGS.md` has the details.
- **Two humans on one branch in two clones.** Git worktrees prevent it on
  one machine only. Pull before you start; push when you stop.

## Everything else

See [README.md](./README.md) for the project overview, and
[docs/CHEATSHEET.md](docs/CHEATSHEET.md) for every command on one page. Live
status lives in `reports-list/`, `spreadsheets/`, `label-design/STATUS.md` and
the Migration Board. Read those before re-deriving status from scratch.
