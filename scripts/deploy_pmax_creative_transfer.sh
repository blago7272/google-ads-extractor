#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--apply" ]]; then
  echo "Dry run only. Re-run with --apply to create or update the isolated manual-only PMax creative transfer."
  exit 0
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_path="${script_dir}/pmax_creative_transfer.config.json"

for command in bq jq; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command not found: ${command}" >&2
    exit 1
  fi
done

project_id="$(jq -r '.project_id' "${config_path}")"
location="$(jq -r '.location' "${config_path}")"
transfer_location="$(jq -r '.transfer_location' "${config_path}")"
target_dataset="$(jq -r '.target_dataset' "${config_path}")"
display_name="$(jq -r '.display_name' "${config_path}")"
data_source="$(jq -r '.data_source' "${config_path}")"
params="$(jq -c '{
  customer_id,
  custom_report_table_names: [.custom_reports[].table_name],
  custom_report_queries: [.custom_reports[].gaql]
}' "${config_path}")"

if bq show --project_id="${project_id}" "${project_id}:${target_dataset}" >/dev/null 2>&1; then
  echo "Dataset already exists: ${project_id}:${target_dataset}"
else
  bq --location="${location}" mk --dataset "${project_id}:${target_dataset}"
fi

existing_config="$(bq ls --transfer_config --project_id="${project_id}" --transfer_location="${transfer_location}" --format=prettyjson \
  | jq -r --arg name "${display_name}" '.[] | select(.displayName == $name) | .name')"

if [[ -n "${existing_config}" ]]; then
  bq update --transfer_config \
    --params="${params}" \
    --no_auto_scheduling \
    "${existing_config}"
  echo "Transfer configuration updated with automatic scheduling disabled: ${existing_config}"
  exit 0
fi

bq mk --transfer_config \
  --project_id="${project_id}" \
  --target_dataset="${target_dataset}" \
  --display_name="${display_name}" \
  --data_source="${data_source}" \
  --params="${params}" \
  --no_auto_scheduling
