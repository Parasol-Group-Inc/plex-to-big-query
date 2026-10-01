#!/usr/bin/env bash
# Put the six secret VALUES back into Secret Manager from a backup's
# secrets.env (written by scripts/backup_to_bucket.ps1). No copy and paste.
#
#   ./scripts/restore_secrets.sh                      dry run: latest backup, voxdatalake
#   ./scripts/restore_secrets.sh --apply              add the versions
#   ./scripts/restore_secrets.sh --file secrets.env --project NEW-PROJECT --apply
#   ./scripts/restore_secrets.sh --backup 2026-09-30T200803Z --apply
#
# Used by docs/DISASTER_RECOVERY.md step 5, or after a secret version was
# destroyed by mistake. A secret whose current value already matches is
# skipped, so re-running adds nothing. Values are never printed. The secrets
# themselves must exist (Terraform creates them); this only adds versions.
set -euo pipefail

PROJECT=voxdatalake FILE="" BACKUP=latest APPLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --project) PROJECT="$2"; shift ;;
    --file) FILE="$2"; shift ;;
    --backup) BACKUP="$2"; shift ;;
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

tmp=""
cleanup() { [ -n "$tmp" ] && rm -f "$tmp"; }
trap cleanup EXIT
if [ -z "$FILE" ]; then
  tmp="$(mktemp)"; chmod 600 "$tmp"
  src="gs://voxdatalake-terraform-state/plex-to-big-query/backups/$BACKUP/secrets.env"
  gcloud storage cp "$src" "$tmp" >/dev/null 2>&1 || { echo "can't read $src (gcloud auth login? access?)" >&2; exit 1; }
  FILE="$tmp"
  echo "source:  $src"
else
  echo "source:  $FILE"
fi
echo "project: $PROJECT$([ $APPLY = 1 ] || echo '   (DRY RUN: add --apply to write)')"

added=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|\#*) continue ;; esac
  name="${line%%=*}" value="${line#*=}"
  [ -n "$value" ] || { echo "  skip  $name (empty in backup)"; continue; }
  current="$(gcloud secrets versions access latest --secret="$name" --project="$PROJECT" 2>/dev/null || true)"
  if [ "$current" = "$value" ]; then echo "  same  $name"; continue; fi
  if [ $APPLY = 1 ]; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- --project="$PROJECT" >/dev/null
    echo "  added $name"; added=$((added + 1))
  else
    echo "  would add $name ($([ -n "$current" ] && echo 'differs from current' || echo 'no current version'))"
  fi
done < "$FILE"
[ $APPLY = 1 ] && echo "done: $added version(s) added" || true
