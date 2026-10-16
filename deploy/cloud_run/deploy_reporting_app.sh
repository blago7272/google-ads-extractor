#!/usr/bin/env bash
set -euo pipefail

# Deploy the reporting web app to Cloud Run (stage + prod).
#
# Usage:
#   deploy/cloud_run/deploy_reporting_app.sh <commit_sha>
#
# commit_sha is required. The image is built from a clean export of that
# commit (git archive), never from the working tree: `gcloud builds submit`
# uploads whatever directory it is given, so building from the checkout
# would ship uncommitted local changes under the commit's tag.
#
# Steps:
#   1. Build the image via Cloud Build from a clean export of the commit
#   2. Update stage Cloud Run service
#   3. Update prod Cloud Run service
#   4. Verify the prod revision and /healthz

PROJECT_ID="gads-export-all"
REGION="europe-west1"
REPO="europe-west1-docker.pkg.dev/${PROJECT_ID}/reporting/reporting-app"
STAGE_SERVICE="reporting-app-stage"
PROD_SERVICE="reporting-app-prod"
PROD_URL="https://reporting.idconsult.bg/healthz"

if [[ $# -lt 1 || -z "${1}" ]]; then
  echo "Usage: $0 <commit_sha>" >&2
  echo "A commit is required; the image is built from that commit, not the working tree." >&2
  exit 1
fi

repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

if ! full_sha="$(git -C "${repo_root}" rev-parse --verify --quiet "${1}^{commit}")"; then
  echo "ERROR: '${1}' is not a commit in ${repo_root} (fetch first?)" >&2
  exit 1
fi
commit_sha="$(git -C "${repo_root}" rev-parse --short "${full_sha}")"
image="${REPO}:${commit_sha}"

build_dir="$(mktemp -d "${TMPDIR:-/tmp}/reporting-app-build.XXXXXX")"
trap 'rm -rf "${build_dir}"' EXIT

echo "=== Deploying reporting app ==="
echo "  Commit:  ${commit_sha} (${full_sha})"
echo "  Image:   ${image}"
echo "  Source:  clean export in ${build_dir}"
echo ""

echo "--- Step 1: Build image via Cloud Build ---"
git -C "${repo_root}" archive --format=tar "${full_sha}" | tar -x -C "${build_dir}"
gcloud builds submit "${build_dir}" \
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
