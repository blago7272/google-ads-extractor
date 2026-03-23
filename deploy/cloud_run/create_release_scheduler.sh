#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 7 ]]; then
  cat <<'EOF'
Usage:
  deploy/cloud_run/create_release_scheduler.sh <project_id> <region> <scheduler_location> <job_name> <scheduler_name> <scheduler_service_account> <schedule>

Example:
  deploy/cloud_run/create_release_scheduler.sh \
    gads-export-all \
    europe-west1 \
    europe-west1 \
    reporting-release-orchestrator \
    reporting-release-orchestrator-daily \
    scheduler-invoker@gads-export-all.iam.gserviceaccount.com \
    "30 6 * * *"
EOF
  exit 1
fi

project_id="$1"
region="$2"
scheduler_location="$3"
job_name="$4"
scheduler_name="$5"
scheduler_service_account="$6"
schedule="$7"

uri="https://run.googleapis.com/v2/projects/${project_id}/locations/${region}/jobs/${job_name}:run"

gcloud scheduler jobs create http "$scheduler_name" \
  --project="$project_id" \
  --location="$scheduler_location" \
  --schedule="$schedule" \
  --time-zone="Europe/Sofia" \
  --uri="$uri" \
  --http-method=POST \
  --oauth-service-account-email="$scheduler_service_account" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --headers="Content-Type=application/json" \
  --message-body="{}"
