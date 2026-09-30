#!/usr/bin/env bash
# One command from a fresh clone to a machine that can run the ETL locally:
#
#   ./scripts/dev_setup.sh                 driver + .env + git hooks
#   ./scripts/dev_setup.sh --worktrees     ... plus one folder per project branch
#   ./scripts/dev_setup.sh --deploy-machine ... plus terraform.tfvars (primary folder only)
#
# It needs read access to the project's secrets and buckets. That is granted by
# a project Owner (docs/ONBOARDING.md, "Access to ask for"); without it the
# script stops at the first step it can't do and says which one.
#
# It never prints a secret value, and never overwrites an existing .env or
# terraform.tfvars unless you pass --force.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

PROJECT="${GCP_PROJECT:-voxdatalake}"
WORKTREES=0 DEPLOY=0 FORCE=0
for a in "$@"; do
  case "$a" in
    --worktrees) WORKTREES=1 ;;
    --deploy-machine) DEPLOY=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

ok()   { printf '  \033[32mok\033[0m    %s\n' "$*"; }
skip() { printf '  skip  %s\n' "$*"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$*" >&2; exit 1; }

echo "1. Tools"
for t in git gcloud python; do command -v "$t" >/dev/null || fail "$t is not on PATH (docs/ONBOARDING.md, step 1)"; done
ok "git, gcloud, python"
command -v docker >/dev/null && ok "docker" || skip "docker not found: needed only to run the ETL locally"
command -v terraform >/dev/null && ok "terraform" || skip "terraform not found: needed only on a deploy machine"

echo "2. Google login"
gcloud auth print-access-token >/dev/null 2>&1 || fail "run 'gcloud auth login' (the org policy expires it; it can't be scripted)"
ok "gcloud: $(gcloud config get-value account 2>/dev/null)"
if gcloud auth application-default print-access-token >/dev/null 2>&1; then ok "application-default credentials (Python, Terraform)"
else skip "no application-default credentials: run 'gcloud auth application-default login' for Python/Terraform"; fi

echo "3. Plex ODBC driver (licensed, gitignored)"
if [ -f driver/lib64/ivoa27.so ] && [ "$FORCE" = 0 ]; then
  skip "driver/ already present"
else
  mkdir -p driver
  gcloud storage cp -r "gs://${PROJECT}-build-assets/plex-odbc-driver/*" driver/ >/dev/null \
    || fail "can't read gs://${PROJECT}-build-assets: ask an Owner for storage.objectViewer on it"
  [ -f driver/lib64/ivoa27.so ] || fail "driver downloaded but driver/lib64/ivoa27.so is missing"
  ok "driver/ downloaded"
fi

echo "4. .env (local credentials, gitignored)"
secret() {  # value of a secret, or empty + a warning; never echoed
  gcloud secrets versions access latest --secret="$1" --project="$PROJECT" 2>/dev/null \
    || { echo "  warn  can't read secret '$1'" >&2; printf ''; }
}
if [ -f .env ] && [ "$FORCE" = 0 ]; then
  skip ".env already exists (use --force to rebuild it)"
else
  umask 077
  {
    echo "# Written by scripts/dev_setup.sh on $(date -u +%Y-%m-%dT%H:%MZ). Gitignored; never commit or paste it."
    echo "# Values come from Secret Manager in ${PROJECT}. Targets the Plex TEST tenant."
    echo "PLEX_ACCESS_TOKEN=$(secret plex-access-token)"
    # The ODBC user is not a secret: it's plex_odbc_user in terraform.tfvars.
    # The plex-odbc-user secret is an empty placeholder (username/password
    # auth, never used), so read it from the tfvars backup.
    echo "PLEX_ODBC_USER=$(gcloud storage cat "gs://${PROJECT}-terraform-state/plex-to-big-query/terraform.tfvars.backup" 2>/dev/null \
      | sed -n 's/^[[:space:]]*plex_odbc_user[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)"
    echo "PLEX_HOST=vox.test.odbc.plex.com"
    echo "PLEX_PORT=19995"
    echo "PLEX_SERVER_DATASOURCE=ReportDataSource"
    echo "BQ_TABLE=local_test"
    echo "# Monday: Jennette Boone's token, the only one that can write to the boards."
    echo "MONDAY_API_KEY=$(secret monday-api-key)"
  } > .env
  grep -q '^PLEX_ACCESS_TOKEN=.' .env || fail ".env written but the Plex token is empty: ask for secretAccessor on plex-access-token"
  grep -q '^PLEX_ODBC_USER=.' .env || echo "  warn  PLEX_ODBC_USER is empty: can't read the tfvars backup (objectViewer on ${PROJECT}-terraform-state)" >&2
  ok ".env written ($(grep -c '=.' .env) values filled; nothing printed)"
fi

echo "5. Git hooks"
./scripts/install_hooks.sh >/dev/null && ok "hooks installed (.githooks)"

if [ "$WORKTREES" = 1 ]; then
  echo "6. One folder per project branch (README, 'Folders and branches')"
  parent="$(dirname "$(pwd)")"
  for pair in ptbq-scorecard:dev-scorecard ptbq-sandbox:dev-sandbox ptbq-label-design:dev-label-design ptbq-dev:dev; do
    dir="$parent/${pair%%:*}" branch="${pair##*:}"
    if [ -d "$dir" ]; then skip "$dir exists"
    else git fetch -q origin "$branch" && git worktree add -q "$dir" "$branch" && ok "$dir -> $branch"; fi
  done
  skip "copy .env into each folder that runs the ETL (it is gitignored, so worktrees don't share it)"
fi

if [ "$DEPLOY" = 1 ]; then
  echo "7. terraform.tfvars (deploy machine only)"
  if [ -f terraform/terraform.tfvars ] && [ "$FORCE" = 0 ]; then
    skip "terraform/terraform.tfvars already exists"
  else
    src="gs://${PROJECT}-terraform-state/plex-to-big-query/terraform.tfvars.backup"
    gcloud storage cp "$src" terraform/terraform.tfvars >/dev/null || fail "can't read $src"
    ok "terraform.tfvars restored. Check its date against 'gcloud storage ls -l $src' (CONTRIBUTING.md)"
  fi
fi

echo
echo "Done. Health check: docker compose build && docker compose up   (then: docker compose down)"
