#!/usr/bin/env bash
# One-time, per clone: point git at the versioned hooks in .githooks/.
# core.hooksPath lives in the shared repo config, so it covers every worktree
# (main, ptbq-scorecard, ptbq-sandbox, ptbq-label-design, ptbq-dev) at once.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
echo "hooks installed: $(git config --get core.hooksPath)  (pre-commit, pre-push — see .githooks/hooks.py)"
