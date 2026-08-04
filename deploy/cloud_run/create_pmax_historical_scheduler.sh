#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: deploy/cloud_run/create_pmax_historical_scheduler.sh [--check|--apply]

  --check  Read and validate the intended scheduler contract. No mutation.
  --apply  Create or update the off-peak Cloud Scheduler trigger. Use only
           after the historical transfer and one-date smoke test are accepted.

The trigger invokes a dedicated Cloud Run Job at 02:15 through 07:15 UTC. The
job still exits without a historical submission if the rolling transfer is
PENDING or RUNNING, or if a history run is active in the ledger.
EOF
}

mode="--check"
if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  mode="$1"
fi
if [[ "$mode" == "--help" || "$mode" == "-h" ]]; then
  usage
  exit 0
fi
if [[ "$mode" != "--check" && "$mode" != "--apply" ]]; then
  usage >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_path="${script_dir}/pmax_historical_backfill.config.json"

for command in jq gcloud; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Required command not found: ${command}" >&2
    exit 1
  fi
done

project_id="$(jq -er '.project_id' "${config_path}")"
region="$(jq -er '.region' "${config_path}")"
scheduler_location="$(jq -er '.scheduler_location' "${config_path}")"
job_name="$(jq -er '.job_name' "${config_path}")"
scheduler_name="$(jq -er '.scheduler_name' "${config_path}")"
scheduler_service_account="$(jq -er '.scheduler_service_account' "${config_path}")"
schedule="$(jq -er '.schedule' "${config_path}")"
time_zone="$(jq -er '.time_zone' "${config_path}")"

jq -e '
  .schedule == "15 2-7 * * *" and
  .time_zone == "Etc/UTC" and
  .job_name == "pmax-historical-backfill" and
  .scheduler_name == "pmax-historical-backfill-offpeak"
' "${config_path}" >/dev/null

uri="https://run.googleapis.com/v2/projects/${project_id}/locations/${region}/jobs/${job_name}:run"

job_json="$(gcloud run jobs describe "$job_name" --project="$project_id" --region="$region" --format=json)"
jq -e '
  .template.template.containers[0].command == ["python"] and
  .template.template.containers[0].args == [
    "scripts/manage_pmax_historical_backfill.py",
    "--apply",
    "--confirm-submit-one-date"
  ] and
  .template.template.maxRetries == 0 and
  .template.template.parallelism == 1
' <<<"${job_json}" >/dev/null

if [[ "$mode" == "--check" ]]; then
  echo "Validated PMax historical scheduler target: ${job_name}"
  echo "Planned schedule: ${schedule} (${time_zone})"
  exit 0
fi

common_args=(
  --project="$project_id"
  --location="$scheduler_location"
  --schedule="$schedule"
  --time-zone="$time_zone"
  --uri="$uri"
  --http-method=POST
  --oauth-service-account-email="$scheduler_service_account"
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
  --headers="Content-Type=application/json"
  --message-body="{}"
  --max-retry-attempts=0
  --description="PMax history: one off-peak date only; rolling-state and ledger guarded."
)

if gcloud scheduler jobs describe "$scheduler_name" \
  --project="$project_id" --location="$scheduler_location" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "$scheduler_name" "${common_args[@]}"
  echo "Updated PMax historical scheduler: ${scheduler_name}"
else
  gcloud scheduler jobs create http "$scheduler_name" "${common_args[@]}"
  echo "Created PMax historical scheduler: ${scheduler_name}"
fi
