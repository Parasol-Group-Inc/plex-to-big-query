#!/usr/bin/env bash
# Build and deploy the picking app to Cloud Run behind IAP (docs/PICKING_STAGING_APP.md "Deploying").
#
#   ./deploy/picking_app/deploy.sh                       build + deploy (Plex TEST)
#   ./deploy/picking_app/deploy.sh --access user:a@x.com  also let a@x.com open it (repeatable;
#                                                        group:team@x.com works too)
#   ./deploy/picking_app/deploy.sh --no-build            redeploy the image of this commit
#
# Run from the primary folder on a clean main (like scripts/deploy.sh). Writes, so Claude runs it
# with CLOUDSDK_AUTH_IMPERSONATE_SERVICE_ACCOUNT=claude-operator@... set.
# Pay per use (request-based billing), scaled to zero, at most one instance; the scheduler
# picking-app-warm calls /warm every 10 min on weekdays 6:00-17:50 Mountain so the Plex session
# and the default job-set list stay warm. Terraform owns the IAP API and PlexOps.picking_move_log.
set -euo pipefail
PROJECT=voxdatalake
REGION=us-central1
SERVICE=picking-app
SA=plex-etl-sa@${PROJECT}.iam.gserviceaccount.com
PLEX_ENV_FOR_APP=${PLEX_ENV_FOR_APP:-test}
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
IMAGE=${REGION}-docker.pkg.dev/${PROJECT}/plex-pipeline/${SERVICE}:${SHA}
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')

if [ "$build" = 1 ]; then
  gcloud builds submit --project="$PROJECT" --config deploy/picking_app/cloudbuild.yaml \
    --substitutions=SHORT_SHA="$SHA" .
fi

gcloud run deploy "$SERVICE" --project="$PROJECT" --region="$REGION" --image="$IMAGE" \
  --service-account="$SA" --no-allow-unauthenticated --iap \
  --cpu=1 --memory=2Gi --concurrency=8 --min-instances=0 --max-instances=1 --timeout=300 \
  --cpu-throttling \
  --set-env-vars="PLEX_ENV=${PLEX_ENV_FOR_APP},PICKING_BQ_LOG=1,PICKING_LOG=/tmp/picking_moves.jsonl,PICKING_SESSION_GCS=${SESSION_GCS}" \
  --set-secrets="PLEX_PORTAL_USERNAME=plex-portal-username:latest,PLEX_PORTAL_PASSWORD=plex-portal-password:latest,PLEX_API_KEY=plex-api-consumer-key:latest,PLEX_API_SECRET=plex-api-consumer-secret:latest" \
  --labels="app=picking,plex-env=${PLEX_ENV_FOR_APP},build=${SHA}"

# IAP calls the service as its own service agent.
gcloud run services add-iam-policy-binding "$SERVICE" --project="$PROJECT" --region="$REGION" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" --role=roles/run.invoker >/dev/null

# Who may open it, and the keep-warm caller.
for m in "${access[@]}" "serviceAccount:${SA}"; do
  gcloud iap web add-iam-policy-binding --project="$PROJECT" --resource-type=cloud-run --service="$SERVICE" \
    --region="$REGION" --member="$m" --role=roles/iap.httpsResourceAccessor >/dev/null
done

URL=$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" --format='value(status.url)')
WARM=(--project="$PROJECT" --location="$REGION" --schedule="*/10 6-17 * * 1-5" --time-zone="America/Denver"
      --uri="${URL}/warm" --http-method=GET --oidc-service-account-email="$SA" --oidc-token-audience="$URL"
      --attempt-deadline=120s --description="Keeps picking-app's Plex session and job-set list warm in working hours (docs/PICKING_STAGING_APP.md)")
if gcloud scheduler jobs describe picking-app-warm --project="$PROJECT" --location="$REGION" >/dev/null 2>&1; then
  gcloud scheduler jobs update http picking-app-warm "${WARM[@]}" >/dev/null
else
  gcloud scheduler jobs create http picking-app-warm "${WARM[@]}" >/dev/null
fi
echo "picking-app ${SHA} deployed: ${URL} (Plex ${PLEX_ENV_FOR_APP}); keep-warm picking-app-warm"
