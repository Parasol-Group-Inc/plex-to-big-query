#!/usr/bin/env bash
# Refuses to let a deploy proceed unless you're on `main` with a clean
# working tree. Run this before `terraform apply` and before
# `gcloud builds submit` (see docs/OPERATIONS.md) -- neither of those
# commands cares what branch you're on or whether you have local edits;
# they deploy exactly whatever's on disk right now. This script is the
# only thing standing between "I was iterating on dev-label-design" and
# "that iteration just went to prod."
#
#   ./scripts/deploy_preflight.sh
#
# Exits 0 (silent) if safe to proceed. Exits 1 with an explanation otherwise.
set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD)"
if [ "$branch" != "main" ]; then
  echo "REFUSING TO DEPLOY: current branch is '$branch', not 'main'." >&2
  echo "terraform apply / gcloud builds submit deploy whatever's on disk" >&2
  echo "right now, regardless of branch -- switch to main first:" >&2
  echo "    git checkout main" >&2
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "REFUSING TO DEPLOY: working tree on main is not clean." >&2
  echo "Commit or stash local changes first -- an uncommitted edit would" >&2
  echo "deploy without ever being recorded in git history." >&2
  git status --short >&2
  exit 1
fi

local_head="$(git rev-parse HEAD)"
remote_head="$(git rev-parse origin/main 2>/dev/null || echo "")"
if [ -n "$remote_head" ] && [ "$local_head" != "$remote_head" ]; then
  echo "WARNING: local main ($local_head) differs from origin/main ($remote_head)." >&2
  echo "Not blocking -- but confirm this is intentional (e.g. not-yet-pushed" >&2
  echo "local commits) before deploying, so main on GitHub stays the record" >&2
  echo "of what's actually in prod." >&2
fi

echo "OK: on main, clean tree -- safe to deploy."
