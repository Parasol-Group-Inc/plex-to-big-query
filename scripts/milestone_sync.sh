#!/usr/bin/env bash
# Milestone sync (2026-11-12, Emilio: "make sure the commit fires a task to update all angles of
# documentation and backups"). Started in the background by .githooks/post-merge whenever the
# PRIMARY folder's main moves (git pull after a merged PR); safe to run by hand any time.
#
#   1. Backups: a git bundle of every branch (keeps the newest 10) and dated BigQuery copies of
#      the small ops tables people or Claude change by hand (once per day).
#   2. Documentation check: lists what a milestone must have touched (CHANGELOG for deployable
#      files; docs, hub tab sources) and writes a to-do for the next Claude session / you.
#   3. Log: one line per run in ~/plex-monitor/milestones.log; details in milestones/<sha>.md.
#
# Never deploys, merges, emails or changes Plex/Monday. BigQuery copies go through claude-operator
# impersonation when that works and are skipped (logged) when it does not.
set -uo pipefail
REPO="$(git rev-parse --show-toplevel)"
OUT="${PLEX_MONITOR_DIR:-$HOME/plex-monitor}"
BACK="$OUT/backups"; MS="$OUT/milestones"
mkdir -p "$BACK" "$MS"
cd "$REPO"
SHA="$(git rev-parse --short HEAD)"; TODAY="$(date +%Y%m%d)"; NOW="$(date '+%Y-%m-%d %H:%M %Z')"
PREV="${1:-$(git rev-parse --short 'HEAD@{1}' 2>/dev/null || git rev-parse --short HEAD~1)}"
NOTE="$MS/$SHA.md"
log() { echo "$*" >> "$NOTE"; }
: > "$NOTE"
log "# Milestone $SHA ($NOW)"; log ""; log "Range: $PREV..$SHA"; log ""

# 1a. git bundle, newest 10 kept
B="$BACK/plex-to-big-query_${TODAY}_${SHA}.bundle"
if git bundle create "$B" --all >/dev/null 2>&1 && git bundle verify "$B" >/dev/null 2>&1; then
  log "- Backup: git bundle $(basename "$B") ($(du -h "$B" | cut -f1)), verified"
else
  log "- Backup: git bundle FAILED"
fi
ls -1t "$BACK"/plex-to-big-query_*.bundle 2>/dev/null | tail -n +11 | xargs -r rm -f

# 1b. dated BigQuery copies of hand-edited ops tables, once a day
for t in PlexOps.etl_schedule PlexProd.manual_data_access; do   # tables only; views (live_source, data_freshness) are in Terraform
  dst="Backups.${t/./__}_${TODAY}"
  if bq show "voxdatalake:$dst" >/dev/null 2>&1; then
    log "- Backup: $dst already taken today"
  elif CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT=claude-operator@voxdatalake.iam.gserviceaccount.com \
       bq cp -f "voxdatalake:$t" "voxdatalake:$dst" >/dev/null 2>&1; then
    log "- Backup: $dst"
  else
    log "- Backup: $dst SKIPPED (no BigQuery write access from this shell)"
  fi
done

# 2. documentation check for the range
CHANGED="$(git diff --name-only "$PREV" "$SHA" 2>/dev/null)"
log ""; log "## Changed files"; echo "$CHANGED" | sed 's/^/- /' >> "$NOTE"
todo=()
echo "$CHANGED" | grep -qx CHANGELOG.md || \
  { echo "$CHANGED" | grep -Eq '^(main\.py|watchdog\.py|email_utils\.py|plex_api_lag\.py|scripts/screen_recon\.py|deploy/|terraform/|reports/)' \
    && todo+=("CHANGELOG.md has no entry for deployable changes in this range"); }
echo "$CHANGED" | grep -Eq '^(reports/|terraform/|deploy/|main\.py|watchdog\.py)' && \
  todo+=("Deploy: Cloud Build for code (main.py, watchdog.py, scripts/screen_recon.py, deploy/cloudbuild.yaml) and ./scripts/deploy.sh for terraform/ and reports/")
todo+=("Hub: python scripts/hub/snapshot_data.py && python scripts/hub/build_hub.py (machine-local tabs come from tab_store), then publish docs/hub/index_live.html")
todo+=("Work log: add a row; daily scan rebuilds the Record page (scripts/build_record.py) and conversation page")
echo "$CHANGED" | grep -Eq '^(terraform/|deploy/|scripts/deploy)' && todo+=("docs/DISASTER_RECOVERY.md and docs/ONBOARDING.md: still true after these infra changes?")
log ""; log "## To do"
for t in "${todo[@]}"; do log "- [ ] $t"; done
echo "$NOW  $PREV..$SHA  $(echo "$CHANGED" | grep -c .) files  todo=${#todo[@]}  $NOTE" >> "$OUT/milestones.log"
echo "milestone_sync: $NOTE"
