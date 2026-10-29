#!/usr/bin/env bash
# ./scripts/deploy.sh, run by Claude Code as the claude-operator service account.
#
# Claude's gcloud identity is claude-readonly (the `claude` configuration), which
# cannot write. claude-readonly may impersonate claude-operator, which can. This
# mints a one-hour access token for claude-operator and hands it to Terraform
# (provider and GCS state backend both read GOOGLE_OAUTH_ACCESS_TOKEN), then runs
# the normal deploy: same preflight, guard, review and typed confirmation.
#
#   ./scripts/deploy_as_claude.sh                      # plan + review, then asks
#   printf '%s\n' <N> | ./scripts/deploy_as_claude.sh  # apply, once a human said go
#
# Humans deploy with ./scripts/deploy.sh as themselves. Details and setup:
# docs/CLAUDE_CODE_IAM.md.
set -euo pipefail
OPERATOR="${CLAUDE_OPERATOR_SA:-claude-operator@voxdatalake.iam.gserviceaccount.com}"

GOOGLE_OAUTH_ACCESS_TOKEN="$(gcloud auth print-access-token --impersonate-service-account="$OPERATOR" 2>/dev/null)" || {
  echo "REFUSING: could not get a token for $OPERATOR." >&2
  echo "Check: gcloud config configurations list (claude = claude-readonly), and that" >&2
  echo "claude-readonly has roles/iam.serviceAccountTokenCreator on $OPERATOR." >&2
  exit 1
}
export GOOGLE_OAUTH_ACCESS_TOKEN
echo "Deploying as $OPERATOR (token valid ~1 h)."
exec "$(dirname "$0")/deploy.sh" "$@"
