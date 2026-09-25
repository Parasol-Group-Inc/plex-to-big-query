#!/usr/bin/env bash
# The ONE way to deploy config/SQL/infra:  ./scripts/deploy.sh
#
#   1. preflight          — on main, clean tree (scripts/deploy_preflight.sh)
#   2. up to date         — fetch; HEAD must equal origin/main
#   3. plan to a file     — the Terraform deploy guard runs inside the plan too
#   4. review             — scripts/plan_review.py separates real content changes
#                           from line-ending noise and flags destroys
#   5. confirm            — type the number of content changes to proceed
#   6. apply THAT plan    — exactly what was reviewed, nothing re-planned
#   7. tag                — deploy/<UTC timestamp> on the deployed commit, pushed,
#                           so "what was live when?" is answerable from git
#
# It deploys Terraform-managed things only. A Cloud Build (image) deploy is
# separate: gcloud builds submit ... (docs/OPERATIONS.md), after the same
# preflight.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

./scripts/deploy_preflight.sh
git fetch -q origin main
if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
  echo "REFUSING: local main $(git rev-parse --short HEAD) != origin/main $(git rev-parse --short origin/main)." >&2
  echo "Push or pull first — GitHub's main must be the record of what is deployed." >&2
  exit 1
fi

cd terraform
# Remove the plan files however this script ends — Ctrl+C at the prompt
# included. Left behind, they make the tree dirty and the deploy guard then
# refuses every later plan (happened 2026-09-25).
trap 'rm -f deploy.tfplan deploy.plan.json' EXIT
terraform plan -var-file=terraform.tfvars -out=deploy.tfplan -no-color | tail -3
terraform show -json deploy.tfplan > deploy.plan.json
set +e
python ../scripts/plan_review.py deploy.plan.json
review=$?
set -e
content=$(python - <<'PY'
import json
p = json.load(open("deploy.plan.json"))
print(sum(1 for r in p.get("resource_changes", []) if r["change"]["actions"] not in (["no-op"], ["read"])))
PY
)
if [ "$content" = "0" ]; then
  echo "Nothing to deploy."; exit 0
fi
[ "$review" = "2" ] && echo -e "\n⚠ This plan DESTROYS or REPLACES resources. Read them above before confirming."

echo
read -r -p "Type the total number of resource changes ($content) to apply exactly this plan: " answer
if [ "$answer" != "$content" ]; then
  echo "Not confirmed — nothing applied."; exit 1
fi

terraform apply deploy.tfplan

tag="deploy/$(date -u +%Y-%m-%dT%H%MZ)"
git tag -a "$tag" -m "terraform apply of $(git rev-parse --short HEAD) — $content resource change(s)"
git push -q origin "$tag" && echo "tagged and pushed $tag"
