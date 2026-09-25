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
  gitignored and exists only there, and the deploy guard (below) refuses
  anywhere else.
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
cd C:/F/Parasol/ptbq-label-design && git merge main && git push
```

- **A Cloud Build (image) deploy is separate:** `gcloud builds submit`, same
  preflight, as in `docs/OPERATIONS.md` Step 5.
- **After a deploy, check the view, not the exit code** (CLAUDE.md).

**Keep merges to `main` small and frequent.** The `dev*` branches are
long-running and don't merge into each other, so the longer one sits
unmerged, the more it drifts on shared files. Step 4 exists for the same
reason.

## Everything else

See [README.md](./README.md) for the project overview and
`docs/`/`reports-list/`/`spreadsheets/` for where live status actually lives
— read those before re-deriving status from scratch (see the pointers at the
top of those folders / the root README).
