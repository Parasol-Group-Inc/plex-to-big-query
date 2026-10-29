#!/usr/bin/env bash
# After `gh pr create`, merge the new PR as the account that owns that org:
# Parasol-Group-Inc repos -> emiliodparasol, anything else -> emiliodom.
# Uses a per-command GH_TOKEN, so the globally active gh account never changes.
# No jq on this machine, so the hook payload is parsed with python.
set -uo pipefail
PR_REF=$(python -c '
import json, re, sys
d = json.load(sys.stdin)
if "gh pr create" not in (d.get("tool_input") or {}).get("command", ""):
    sys.exit(0)
m = re.search(r"https://github\.com/[^/\s]+/[^/\s]+/pull/[0-9]+", json.dumps(d.get("tool_response", "")))
print(m.group(0) if m else "")
')
[[ -z "$PR_REF" ]] && exit 0
OWNER=$(echo "$PR_REF" | cut -d/ -f4)
PR_NUM=${PR_REF##*/}
case "$OWNER" in
  Parasol-Group-Inc) GH_USER=emiliodparasol; FLAGS="--merge" ;;
  *)                 GH_USER=emiliodom;      FLAGS="--merge --admin" ;;
esac
TOKEN=$(gh auth token --user "$GH_USER" 2>/dev/null)
if [[ -n "$TOKEN" ]] && GH_TOKEN="$TOKEN" gh pr merge "$PR_REF" $FLAGS >/dev/null 2>&1; then
  echo "{\"systemMessage\":\"✅ PR #${PR_NUM} auto-merged as ${GH_USER}\"}"
else
  echo "{\"systemMessage\":\"⚠️ PR #${PR_NUM} merge failed as ${GH_USER}\"}"
fi
