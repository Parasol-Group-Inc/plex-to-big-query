#!/usr/bin/env bash
# Wait for a Cloud Build to finish, and fail loudly instead of waiting forever.
#
#   scripts/wait_build.sh <build-id> [max-minutes]
#
# Exit 0 only on SUCCESS. Exit 1 on FAILURE/TIMEOUT/CANCELLED/INTERNAL_ERROR/
# EXPIRED (prints each step's status and the failing step's last error lines).
# Exit 2 if the status cannot be read 3 times in a row (permission, auth, network),
# with the real error, never swallowed. Exit 3 if max-minutes (default 30) passes.
#
# Reads with the active account first. claude-readonly has no Cloud Build role,
# so on PERMISSION_DENIED it switches to reading as claude-operator (a read made
# through the write account, the documented route; see docs/CLAUDE_CODE_IAM.md).
set -uo pipefail

BUILD="${1:?usage: wait_build.sh <build-id> [max-minutes]}"
MAX_MIN="${2:-30}"
PROJECT=voxdatalake
OPERATOR=claude-operator@voxdatalake.iam.gserviceaccount.com
IMP=()

describe() {
  gcloud builds describe "$BUILD" --project="$PROJECT" ${IMP[@]+"${IMP[@]}"} "$@" 2>"$ERR"
}

ERR=$(mktemp)
trap 'rm -f "$ERR"' EXIT
deadline=$(( $(date +%s) + MAX_MIN * 60 ))
fails=0
last=""

while :; do
  if s=$(describe --format='value(status)') && [ -n "$s" ]; then
    fails=0
  elif grep -q PERMISSION_DENIED "$ERR" && [ ${#IMP[@]} -eq 0 ]; then
    echo "$(date +%H:%M:%S) active account cannot read builds; reading as claude-operator"
    IMP=(--impersonate-service-account="$OPERATOR")
    continue
  else
    fails=$((fails + 1))
    echo "$(date +%H:%M:%S) could not read build status ($fails/3): $(grep -v WARNING "$ERR" | tail -1)"
    if [ "$fails" -ge 3 ]; then
      echo "GIVING UP: build status unreadable 3 times in a row" >&2
      exit 2
    fi
    sleep 20
    continue
  fi

  if [ "$s" != "$last" ]; then
    echo "$(date +%H:%M:%S) $BUILD: $s"
    last=$s
  fi
  case "$s" in
    QUEUED|WORKING|PENDING) ;;
    *) break ;;
  esac
  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "TIMED OUT after $MAX_MIN min; build still $s" >&2
    exit 3
  fi
  sleep 20
done

describe --format=json | python3 -c '
import json, sys
for st in json.load(sys.stdin).get("steps", []):
    print("  %-16s %s" % (st.get("id") or st.get("name"), st.get("status", "")))'

if [ "$s" = SUCCESS ]; then
  exit 0
fi

echo "--- last error lines ---"
gcloud builds log "$BUILD" --project="$PROJECT" ${IMP[@]+"${IMP[@]}"} 2>/dev/null \
  | grep -iE 'error|fail|denied|503|unavailable|timeout' | grep -v '■' | tail -15
if gcloud builds log "$BUILD" --project="$PROJECT" ${IMP[@]+"${IMP[@]}"} 2>/dev/null | grep -qE '50[234] (Service Unavailable|Bad Gateway|Gateway Timeout)'; then
  echo "Looks transient (registry 5xx): resubmitting the same commit is safe; no deploy step ran if push failed."
fi
exit 1
