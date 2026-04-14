#!/usr/bin/env bash
set -euo pipefail

# Deploy the reporting web app to Cloud Run (stage + prod).
#
# Usage:
#   deploy/cloud_run/deploy_reporting_app.sh [commit_sha]
#
# If commit_sha is omitted, uses the current HEAD.
#
# Steps:
#   1. Build the image via Cloud Build
#   2. Update stage Cloud Run service
#   3. Update prod Cloud Run service
#   4. Verify the prod revision and /healthz

PROJECT_ID="gads-export-all"
REGION="europe-west1"
REPO="europe-west1-docker.pkg.dev/${PROJECT_ID}/reporting/reporting-app"
STAGE_SERVICE="reporting-app-stage"
PROD_SERVICE="reporting-app-prod"
PROD_URL="https://reporting.idconsult.bg/healthz"

commit_sha="${1:-$(git rev-parse --short HEAD)}"
image="${REPO}:${commit_sha}"

echo "=== Deploying reporting app ==="
echo "  Commit:  ${commit_sha}"
echo "  Image:   ${image}"
echo ""

echo "--- Step 1: Build image via Cloud Build ---"
gcloud builds submit \
  --project="${PROJECT_ID}" \
  --tag="${image}"

echo ""
echo "--- Step 2: Update stage service ---"
gcloud run services update "${STAGE_SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${image}"

echo ""
echo "--- Step 3: Update prod service ---"
gcloud run services update "${PROD_SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${image}"

echo ""
echo "--- Step 4: Verify prod ---"
gcloud run services describe "${PROD_SERVICE}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format='value(status.latestReadyRevisionName,spec.template.spec.containers[0].image)'

echo ""
echo "--- Step 5: Health check ---"
http_code=$(curl -s -o /dev/null -w "%{http_code}" "${PROD_URL}" || true)
if [[ "${http_code}" == "200" ]]; then
  echo "Health check passed (HTTP ${http_code})"
else
  echo "WARNING: Health check returned HTTP ${http_code}"
fi

echo ""
echo "=== Deploy complete ==="
