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

## Branches — `main` is prod, work happens on `dev*`

Added 2026-09-17 for clearer per-project tracking (Label Design vs Vox
Scorecard commit history had been blending together on `main`):

- **`main`** — the only branch anything should ever be deployed from.
  Nothing enforces this automatically (`terraform apply` and
  `gcloud builds submit` both deploy whatever's on local disk, regardless
  of branch — see `docs/OPERATIONS.md` Step 5) — that's why
  `scripts/deploy_preflight.sh` exists. **Run it before every deploy.**
- **`dev`** — shared pipeline fixes not specific to either project
  (`main.py`, `Dockerfile`, `requirements.txt`, `terraform/main.tf`
  structure itself, cross-cutting `docs/`).
- **`dev-label-design`** — Label Design work (`label-design/`,
  `label_design_service/`, `reports/label_design*.yaml`,
  `deploy/label_design_sync/`). Status: `label-design/STATUS.md`.
- **`dev-scorecard`** — Vox Scorecard work (`score-card-reference/`,
  `deploy/manual_data_app/`, the scorecard-facing report YAMLs/views).
  Status: the Migration Board artifact (see memory `reference_vox_migration_board`).

**Keep merges to `main` small and frequent, not batched.** These three
`dev*` branches are long-running by design (they don't merge into each
other, and nobody's deleting them after one task) — the risk that creates
is drift on shared files between branches. Merging often keeps that drift
small; a branch sitting unmerged for weeks while shared files change
elsewhere is how a "quick fix" becomes a conflict-resolution afternoon.

## Everything else

See [README.md](./README.md) for the project overview and
`docs/`/`reports-list/`/`spreadsheets/` for where live status actually lives
— read those before re-deriving status from scratch (see the pointers at the
top of those folders / the root README).
