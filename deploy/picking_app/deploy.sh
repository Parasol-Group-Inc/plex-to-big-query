#!/usr/bin/env bash
# Build and deploy the picking app to Cloud Run behind IAP (docs/PICKING_STAGING_APP.md "Deploying").
#
#   PLEX_ENV_FOR_APP=test ./deploy/picking_app/deploy.sh   build + deploy (Plex TEST; =prod for production; required)
#   ./deploy/picking_app/deploy.sh --access user:a@x.com  also let a@x.com open it (repeatable;
#                                                        group:team@x.com works too)
#   ./deploy/picking_app/deploy.sh --no-build            redeploy the image of this commit
#
# Run from the primary folder on a clean main (like scripts/deploy.sh). Writes, so Claude runs it
# with CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT=claude-operator@... set.
# Pay per use (request-based billing), scaled to zero, at most one instance. Terraform owns the IAP
# API and PlexOps.picking_move_log.
#
# Found on the first deploy (2026-11-20):
# - claude-operator may deploy the service but NOT set its IAM: run.services.setIamPolicy and the
#   IAP policy are refused. Those steps are printed for an admin (Emilio) to paste instead.
# - The keep-warm scheduler (picking-app-warm, /warm every 10 min in working hours) got HTTP 401 from
#   IAP: Cloud Run's built-in IAP uses a Google-managed OAuth client, which lets people sign in with
#   a browser but not a service account's OIDC token. It needs a custom OAuth client (console) whose
#   ID is the token audience; until then WARM_AUDIENCE is empty and no scheduler is created.
set -euo pipefail
PROJECT=voxdatalake
REGION=us-central1
SERVICE=picking-app
# Runtime identity. Audit 11-23 #8: plex-etl-sa can read every secret and edit all of BigQuery; a dedicated
# picking-app-sa (created by an admin, commands printed below) is used once it exists. PICKING_SA overrides.
if [ -n "${PICKING_SA:-}" ]; then SA=$PICKING_SA
elif gcloud iam service-accounts describe "picking-app-sa@${PROJECT}.iam.gserviceaccount.com" --project="$PROJECT" >/dev/null 2>&1; then
  SA=picking-app-sa@${PROJECT}.iam.gserviceaccount.com
else SA=plex-etl-sa@${PROJECT}.iam.gserviceaccount.com; fi
# Audit 11-23 #14: no default. A plain redeploy used to switch a production service back to TEST silently.
if [ "${PLEX_ENV_FOR_APP:-}" != "test" ] && [ "${PLEX_ENV_FOR_APP:-}" != "prod" ]; then
  echo "Set PLEX_ENV_FOR_APP=test or PLEX_ENV_FOR_APP=prod (live service now: $(gcloud run services describe picking-app \
--project=voxdatalake --region=us-central1 --format='value(metadata.labels.plex-env)' 2>/dev/null || echo unknown))." >&2; exit 2
fi
SESSION_GCS=gs://${PROJECT}-plex-screenshots/picking-app/plex_session_${PLEX_ENV_FOR_APP}.json

build=1; access=()
while [ $# -gt 0 ]; do
  case "$1" in
    --no-build) build=0 ;;
    --access) access+=("$2"); shift ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$(git rev-parse --show-toplevel)"
if [ -n "$(git status --porcelain)" ] || [ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]; then
  echo "Run from a clean main (git status is not clean or not on main)." >&2; exit 1
fi
SHA=$(git rev-parse --short HEAD)
# Audit 11-23 #9: the app writes undo/audit columns that Terraform adds; without them undo finds nothing and the
# detail is dropped silently. Refuse until ./scripts/deploy.sh has applied them.
if ! bq show --format=prettyjson "${PROJECT}:PlexOps.picking_move_log" 2>/dev/null | grep -q '"batch_id"'; then
  echo "PlexOps.picking_move_log has no batch_id column yet: run ./scripts/deploy.sh (Terraform) first." >&2; exit 1
fi
IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/plex-pipeline/${SERVICE}:${SHA}
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')

if [ "$build" = 1 ]; then
  gcloud builds submit --project="$PROJECT" --config deploy/picking_app/cloudbuild.yaml \
    --substitutions=SHORT_SHA="$SHA" .
fi

# A fixed Flask secret keeps people's form tokens and messages valid across restarts (secret picking-app-secret,
# created by an admin, printed below); without it each instance makes its own.
SECRET_KEY_REF=""
if gcloud secrets describe picking-app-secret --project="$PROJECT" >/dev/null 2>&1; then SECRET_KEY_REF=",PICKING_SECRET=picking-app-secret:latest"; fi

gcloud run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" --image="$IMAGE" \
  --service-account="$SA" --no-allow-unauthenticated --iap \
  --cpu=1 --memory=2Gi --concurrency=40 --min-instances=0 --max-instances=1 --timeout=300 \
  --cpu-throttling \
  --set-env-vars="PLEX_ENV=${PLEX_ENV_FOR_APP},PICKING_BQ_LOG=1,PICKING_LOG=/tmp/picking_moves.jsonl,PICKING_SESSION_GCS=${SESSION_GCS},PICKING_IAP_REQUIRED=1" \
  --set-secrets="PLEX_PORTAL_USERNAME=plex-portal-username:latest,PLEX_PORTAL_PASSWORD=plex-portal-password:latest,PLEX_API_KEY=plex-api-consumer-key:latest,PLEX_API_SECRET=plex-api-consumer-secret:latest${SECRET_KEY_REF}" \
  --labels="app=picking,plex-env=${PLEX_ENV_FOR_APP},build=${SHA}"

URL=https://${SERVICE}-${PROJECT_NUMBER}.${REGION}.run.app

# IAP calls the service as its own service agent; people (and the ping) need IAP access.
# claude-operator cannot set these: try, and print the command for an admin when refused.
admin=()
try() { "$@" >/dev/null 2>&1 || admin+=("$*"); }
try gcloud run services add-iam-policy-binding "$SERVICE" --project="$PROJECT" --region="$REGION" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" --role=roles/run.invoker
for m in ${access[@]+"${access[@]}"}; do
  try gcloud iap web add-iam-policy-binding --project="$PROJECT" --resource-type=cloud-run --service="$SERVICE" \
    --region="$REGION" --member="$m" --role=roles/iap.httpsResourceAccessor
done

# Keep-warm ping: only with a custom IAP OAuth client (WARM_AUDIENCE = its client ID); see above.
if [ -n "${WARM_AUDIENCE:-}" ]; then
  try gcloud iap web add-iam-policy-binding --project="$PROJECT" --resource-type=cloud-run --service="$SERVICE" \
    --region="$REGION" --member="serviceAccount:${SA}" --role=roles/iap.httpsResourceAccessor
  WARM=(--project="$PROJECT" --location="$REGION" --schedule="*/10 6-17 * * 1-5" --time-zone="America/Denver"
        --uri="${URL}/warm" --http-method=GET --oidc-service-account-email="$SA" --oidc-token-audience="$WARM_AUDIENCE"
        --attempt-deadline=120s --description="Keeps picking-app's Plex session and job-set list warm in working hours (docs/PICKING_STAGING_APP.md)")
  if gcloud scheduler jobs describe picking-app-warm --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs update http picking-app-warm "${WARM[@]}" >/dev/null
  else
    gcloud scheduler jobs create http picking-app-warm "${WARM[@]}" >/dev/null
  fi
fi

# Audit 11-23 #8, #15, #24: least privilege, session expiry, and no IAP access for the ETL account. Printed until done.
if [ "$SA" = "plex-etl-sa@${PROJECT}.iam.gserviceaccount.com" ]; then
  B=gs://${PROJECT}-plex-screenshots
  admin+=("gcloud iam service-accounts create picking-app-sa --project=$PROJECT --display-name='Picking app (Cloud Run)'")
  for s in plex-portal-username plex-portal-password plex-api-consumer-key plex-api-consumer-secret picking-app-secret; do
    admin+=("gcloud secrets add-iam-policy-binding $s --project=$PROJECT --member=serviceAccount:picking-app-sa@${PROJECT}.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor")
  done
  admin+=("bq add-iam-policy-binding --member=serviceAccount:picking-app-sa@${PROJECT}.iam.gserviceaccount.com --role=roles/bigquery.dataEditor ${PROJECT}:PlexOps.picking_move_log")
  admin+=("gcloud projects add-iam-policy-binding $PROJECT --member=serviceAccount:picking-app-sa@${PROJECT}.iam.gserviceaccount.com --role=roles/bigquery.jobUser")
  admin+=("gcloud storage buckets add-iam-policy-binding $B --member=serviceAccount:picking-app-sa@${PROJECT}.iam.gserviceaccount.com --role=roles/storage.objectAdmin --condition='expression=resource.name.startsWith(\"projects/_/buckets/${PROJECT}-plex-screenshots/objects/picking-app/\"),title=picking-app-prefix'")
  admin+=("gcloud iam service-accounts add-iam-policy-binding picking-app-sa@${PROJECT}.iam.gserviceaccount.com --project=$PROJECT --member=serviceAccount:claude-operator@${PROJECT}.iam.gserviceaccount.com --role=roles/iam.serviceAccountUser")
fi
if ! gcloud secrets describe picking-app-secret --project="$PROJECT" >/dev/null 2>&1; then
  admin+=("python3 -c 'import secrets; print(secrets.token_hex(32))' | gcloud secrets create picking-app-secret --project=$PROJECT --data-file=-")
fi
if [ -z "${WARM_AUDIENCE:-}" ]; then
  try gcloud iap web remove-iam-policy-binding --project="$PROJECT" --resource-type=cloud-run --service="$SERVICE" \
    --region="$REGION" --member="serviceAccount:plex-etl-sa@${PROJECT}.iam.gserviceaccount.com" --role=roles/iap.httpsResourceAccessor
fi

echo "picking-app ${SHA} deployed: ${URL} (Plex ${PLEX_ENV_FOR_APP}, runs as ${SA})"
if [ ${#admin[@]} -gt 0 ]; then
  echo
  echo "These need an admin (paste in your own terminal):"
  printf '%s\n' "${admin[@]}"
fi
