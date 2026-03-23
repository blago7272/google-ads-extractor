#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 6 ]]; then
  cat <<'EOF'
Usage:
  deploy/cloud_run/deploy_release_orchestrator.sh <project_id> <region> <job_name> <image_uri> <service_account> <env_file>

Example:
  deploy/cloud_run/deploy_release_orchestrator.sh \
    gads-export-all \
    europe-west1 \
    reporting-release-orchestrator \
    europe-west1-docker.pkg.dev/gads-export-all/reporting/release-orchestrator:COMMIT_SHA \
    dbt-runner@gads-export-all.iam.gserviceaccount.com \
    deploy/cloud_run/release_orchestrator.env.example.yaml
EOF
  exit 1
fi

project_id="$1"
region="$2"
job_name="$3"
image_uri="$4"
service_account="$5"
env_file="$6"

gcloud run jobs deploy "$job_name" \
  --project="$project_id" \
  --region="$region" \
  --image="$image_uri" \
  --service-account="$service_account" \
  --tasks=1 \
  --parallelism=1 \
  --max-retries=0 \
  --task-timeout=3600s \
  --memory=2Gi \
  --cpu=1 \
  --command=python \
  --args=scripts/release_orchestrator.py \
  --env-vars-file="$env_file"
