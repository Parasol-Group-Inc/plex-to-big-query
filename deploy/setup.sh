#!/usr/bin/env bash
# deploy/setup.sh
#
# One-time GCP infrastructure setup for the Plex → BigQuery ETL pipeline.
# Run this once per environment (test / production).
#
# Usage:
#   chmod +x deploy/setup.sh
#   ./deploy/setup.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - Sufficient IAM permissions (Owner or Editor + Secret Manager Admin)
#   - Plex ODBC credentials ready to enter when prompted

set -euo pipefail

# ── Colour output ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Config — edit these before running ───────────────────────────────────────
GCP_PROJECT="vox-nutrition-prod"          # your GCP project ID
GCP_REGION="us-central1"                 # Cloud Run / Scheduler region
BQ_DATASET="plex_dataset"                # BigQuery dataset name
BQ_LOCATION="US"                         # BigQuery dataset location
AR_REPO="plex-pipeline"                  # Artifact Registry repo name
CR_JOB="plex-etl"                        # Cloud Run job name
SCHEDULER_JOB="plex-daily-sync"          # Cloud Scheduler job name
SCHEDULER_CRON="0 2 * * *"              # 2am daily (UTC)
SA_NAME="plex-etl-sa"                    # service account name
IMAGE_TAG="latest"

IMAGE_URL="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${AR_REPO}/etl:${IMAGE_TAG}"
SA_EMAIL="${SA_NAME}@${GCP_PROJECT}.iam.gserviceaccount.com"

# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=================================================="
echo "  Plex → BigQuery ETL — GCP infrastructure setup"
echo "=================================================="
echo "  Project : ${GCP_PROJECT}"
echo "  Region  : ${GCP_REGION}"
echo "  Dataset : ${BQ_DATASET}"
echo "=================================================="
echo ""

read -p "Continue with the above config? (y/N) " -n 1 -r
echo ""
[[ $REPLY =~ ^[Yy]$ ]] || { warn "Aborted."; exit 0; }

# ── 1. Set active project ─────────────────────────────────────────────────────
info "Setting active GCP project..."
gcloud config set project "${GCP_PROJECT}"
success "Project set to ${GCP_PROJECT}"

# ── 2. Enable required APIs ───────────────────────────────────────────────────
info "Enabling required GCP APIs (this may take a minute)..."
gcloud services enable \
    run.googleapis.com \
    cloudscheduler.googleapis.com \
    bigquery.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    cloudbuild.googleapis.com \
    iam.googleapis.com
success "APIs enabled"

# ── 3. Create service account ─────────────────────────────────────────────────
info "Creating service account: ${SA_NAME}..."
if gcloud iam service-accounts describe "${SA_EMAIL}" &>/dev/null; then
    warn "Service account ${SA_EMAIL} already exists — skipping creation"
else
    gcloud iam service-accounts create "${SA_NAME}" \
        --display-name="Plex ETL Service Account" \
        --description="Used by the Plex → BigQuery Cloud Run job"
    success "Service account created: ${SA_EMAIL}"
fi

# ── 4. Grant IAM roles to service account ────────────────────────────────────
info "Granting IAM roles..."

roles=(
    "roles/bigquery.dataEditor"       # write to BQ tables
    "roles/bigquery.jobUser"          # run BQ load jobs
    "roles/secretmanager.secretAccessor"  # read ODBC secrets
    "roles/artifactregistry.reader"   # pull Docker image
    "roles/run.invoker"               # allow Scheduler to trigger Cloud Run
)

for role in "${roles[@]}"; do
    gcloud projects add-iam-policy-binding "${GCP_PROJECT}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${role}" \
        --quiet
    success "Granted ${role}"
done

# ── 5. Create Artifact Registry repository ────────────────────────────────────
info "Creating Artifact Registry repository: ${AR_REPO}..."
if gcloud artifacts repositories describe "${AR_REPO}" \
    --location="${GCP_REGION}" &>/dev/null; then
    warn "Repository ${AR_REPO} already exists — skipping"
else
    gcloud artifacts repositories create "${AR_REPO}" \
        --repository-format=docker \
        --location="${GCP_REGION}" \
        --description="Plex ETL Docker images"
    success "Artifact Registry repository created"
fi

# Authenticate Docker to push images
info "Configuring Docker auth for Artifact Registry..."
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet
success "Docker auth configured"

# ── 6. Create BigQuery dataset ────────────────────────────────────────────────
info "Creating BigQuery dataset: ${BQ_DATASET}..."
if bq ls --project_id="${GCP_PROJECT}" "${BQ_DATASET}" &>/dev/null; then
    warn "Dataset ${BQ_DATASET} already exists — skipping"
else
    bq mk \
        --project_id="${GCP_PROJECT}" \
        --dataset \
        --location="${BQ_LOCATION}" \
        --description="Plex ERP data synced via ODBC" \
        "${GCP_PROJECT}:${BQ_DATASET}"
    success "BigQuery dataset created: ${BQ_DATASET}"
fi

# ── 7. Create sync metadata table ─────────────────────────────────────────────
info "Creating sync metadata table..."
bq mk \
    --project_id="${GCP_PROJECT}" \
    --table \
    --description="Tracks last successful sync per table" \
    "${GCP_PROJECT}:${BQ_DATASET}.sync_metadata" \
    "table_name:STRING,last_sync_at:TIMESTAMP,max_modified_at:TIMESTAMP,rows_written:INTEGER,synced_at:TIMESTAMP" \
    2>/dev/null || warn "sync_metadata table already exists — skipping"
success "Sync metadata table ready"

# ── 8. Create secrets in Secret Manager ───────────────────────────────────────
info "Creating secrets in Secret Manager..."
echo ""
echo "  You will be prompted to enter the Plex ODBC credentials."
echo "  These are stored encrypted in Secret Manager and never"
echo "  written to disk or logged."
echo ""

create_secret() {
    local name=$1
    local prompt=$2
    local is_password=${3:-false}

    if gcloud secrets describe "${name}" &>/dev/null; then
        warn "Secret '${name}' already exists — skipping (update manually if needed)"
    else
        if [ "$is_password" = true ]; then
            read -s -p "  ${prompt}: " value; echo ""
        else
            read -p "  ${prompt}: " value
        fi
        echo -n "${value}" | gcloud secrets create "${name}" \
            --data-file=- \
            --replication-policy="automatic"
        success "Secret created: ${name}"
    fi
}

create_secret "plex-odbc-user"     "Plex ODBC username"
create_secret "plex-odbc-password" "Plex ODBC password" true
create_secret "plex-company-code"  "Plex CompanyCode"

# ── 9. Build and push Docker image ────────────────────────────────────────────
echo ""
info "Building and pushing Docker image..."
echo "  Image: ${IMAGE_URL}"
echo ""

if [ ! -d "driver" ] || [ -z "$(ls -A driver/*.so 2>/dev/null)" ]; then
    error "No .so files found in driver/ — copy the Plex Linux ODBC driver files there first."
fi

docker build -t "${IMAGE_URL}" .
docker push "${IMAGE_URL}"
success "Docker image pushed to Artifact Registry"

# ── 10. Deploy Cloud Run job ──────────────────────────────────────────────────
info "Deploying Cloud Run job: ${CR_JOB}..."
gcloud run jobs create "${CR_JOB}" \
    --image="${IMAGE_URL}" \
    --region="${GCP_REGION}" \
    --service-account="${SA_EMAIL}" \
    --memory=1Gi \
    --cpu=1 \
    --task-timeout=600 \
    --max-retries=3 \
    --set-env-vars="GCP_PROJECT=${GCP_PROJECT},BQ_DATASET=${BQ_DATASET},BQ_TABLE=production_orders,PLEX_DSN=PlexProduction,SECRET_ODBC_USER=plex-odbc-user,SECRET_ODBC_PASSWORD=plex-odbc-password,SECRET_COMPANY_CODE=plex-company-code" \
    2>/dev/null || \
gcloud run jobs update "${CR_JOB}" \
    --image="${IMAGE_URL}" \
    --region="${GCP_REGION}" \
    --service-account="${SA_EMAIL}" \
    --memory=1Gi \
    --cpu=1 \
    --task-timeout=600 \
    --max-retries=3 \
    --set-env-vars="GCP_PROJECT=${GCP_PROJECT},BQ_DATASET=${BQ_DATASET},BQ_TABLE=production_orders,PLEX_DSN=PlexProduction,SECRET_ODBC_USER=plex-odbc-user,SECRET_ODBC_PASSWORD=plex-odbc-password,SECRET_COMPANY_CODE=plex-company-code"
success "Cloud Run job deployed"

# ── 11. Create Cloud Scheduler trigger ───────────────────────────────────────
info "Creating Cloud Scheduler job: ${SCHEDULER_JOB}..."
CR_JOB_URI="https://${GCP_REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${GCP_PROJECT}/jobs/${CR_JOB}:run"

gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
    --location="${GCP_REGION}" \
    --schedule="${SCHEDULER_CRON}" \
    --uri="${CR_JOB_URI}" \
    --message-body="{}" \
    --oauth-service-account-email="${SA_EMAIL}" \
    --time-zone="UTC" \
    --description="Triggers the Plex → BigQuery ETL job daily at 2am UTC" \
    2>/dev/null || warn "Scheduler job already exists — skipping"
success "Cloud Scheduler job created (${SCHEDULER_CRON} UTC)"

# ── 12. Run a test execution ──────────────────────────────────────────────────
echo ""
read -p "Run a test execution now? (y/N) " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    info "Triggering manual Cloud Run job execution..."
    gcloud run jobs execute "${CR_JOB}" \
        --region="${GCP_REGION}" \
        --wait
    success "Test execution complete — check BigQuery for results"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "=================================================="
success "Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Query BigQuery to verify data landed:"
echo "     bq query 'SELECT COUNT(*) FROM \`${GCP_PROJECT}.${BQ_DATASET}.sync_metadata\`'"
echo ""
echo "  2. View job logs:"
echo "     gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=${CR_JOB}' --limit=50"
echo ""
echo "  3. Trigger a manual run anytime:"
echo "     gcloud run jobs execute ${CR_JOB} --region=${GCP_REGION}"
echo "=================================================="