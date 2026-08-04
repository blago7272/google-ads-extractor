#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  deploy/cloud_run/deploy_pmax_historical_backfill.sh --check
  deploy/cloud_run/deploy_pmax_historical_backfill.sh --provision <image_uri>
  deploy/cloud_run/deploy_pmax_historical_backfill.sh --release <image_uri>

  --check                 Read and validate the inert job configuration only.
  --provision <image_uri> Create the dedicated Cloud Run Job. Refuses to
                          overwrite an existing job.
  --release <image_uri>   Update only the image of the existing history job.

Provisioning or releasing a job does not create the historical transfer and
does not enable the Cloud Scheduler trigger. Those are separate approval gates.
EOF
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
  usage >&2
  exit 2
fi

mode="$1"
image_uri="${2:-}"
if [[ "$mode" == "--help" || "$mode" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "$mode" != "--check" && "$mode" != "--provision" && "$mode" != "--release" ]]; then
  usage >&2
  exit 2
fi
if [[ "$mode" == "--check" && -n "$image_uri" ]]; then
  usage >&2
  exit 2
fi
if [[ "$mode" != "--check" && -z "$image_uri" ]]; then
  usage >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_path="${script_dir}/pmax_historical_backfill.config.json"

if ! command -v jq >/dev/null 2>&1; then
  echo "Required command not found: jq" >&2
  exit 1
fi

project_id="$(jq -er '.project_id' "${config_path}")"
region="$(jq -er '.region' "${config_path}")"
job_name="$(jq -er '.job_name' "${config_path}")"
runtime_service_account="$(jq -er '.runtime_service_account' "${config_path}")"
command="$(jq -er '.container_command' "${config_path}")"
task_timeout="$(jq -er '.task_timeout' "${config_path}")"
max_retries="$(jq -er '.max_retries' "${config_path}")"
tasks="$(jq -er '.tasks' "${config_path}")"
parallelism="$(jq -er '.parallelism' "${config_path}")"
memory="$(jq -er '.memory' "${config_path}")"
cpu="$(jq -er '.cpu' "${config_path}")"
container_args="$(jq -r '.container_args | join(",")' "${config_path}")"

jq -e '
  .job_name == "pmax-historical-backfill" and
  .container_command == "python" and
  .container_args == [
    "scripts/manage_pmax_historical_backfill.py",
    "--apply",
    "--confirm-submit-one-date"
  ] and
  .tasks == 1 and
  .parallelism == 1 and
  .max_retries == 0
' "${config_path}" >/dev/null

if [[ "$mode" == "--check" ]]; then
  echo "Validated inert PMax historical Cloud Run Job configuration: ${job_name}"
  exit 0
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "Required command not found: gcloud" >&2
  exit 1
fi

if [[ "$mode" == "--provision" ]]; then
  if gcloud run jobs describe "$job_name" --project="$project_id" --region="$region" >/dev/null 2>&1; then
    echo "Refusing to overwrite existing Cloud Run Job: ${job_name}" >&2
    exit 1
  fi
  gcloud run jobs deploy "$job_name" \
    --project="$project_id" \
    --region="$region" \
    --image="$image_uri" \
    --service-account="$runtime_service_account" \
    --tasks="$tasks" \
    --parallelism="$parallelism" \
    --max-retries="$max_retries" \
    --task-timeout="$task_timeout" \
    --memory="$memory" \
    --cpu="$cpu" \
    --command="$command" \
    --args="$container_args"
  echo "Provisioned inert PMax historical backfill job: ${job_name}"
  exit 0
fi

gcloud run jobs update "$job_name" \
  --project="$project_id" \
  --region="$region" \
  --image="$image_uri"
echo "Released image to PMax historical backfill job: ${job_name}"
