#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_pmax_historical_transfer.sh [--check|--apply]

  --check  Read the planned historical-transfer identity. It does not create a
           dataset, a transfer configuration, a schedule, or a transfer run.
  --apply  Create or update the separate manual-only historical transfer. It
           requires explicit operator approval and an interactive Google Ads
           consent flow when BigQuery requests one.

The script never changes the rolling gads_pmax_creative_test transfer, gads_raw,
or any resource in blissful-land-485813-e2.
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

for command in bq jq; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command not found: ${command}" >&2
    exit 1
  fi
done

project_id="$(jq -er '.project_id' "${config_path}")"
location="$(jq -er '.location' "${config_path}")"
transfer_location="$(jq -er '.transfer_location' "${config_path}")"
target_dataset="$(jq -er '.target_dataset' "${config_path}")"
display_name="$(jq -er '.display_name' "${config_path}")"
data_source="$(jq -er '.data_source' "${config_path}")"
auto_scheduling="$(jq -er '.auto_scheduling' "${config_path}")"
params="$(jq -c '{
  customer_id,
  custom_report_table_names: [.custom_reports[].table_name],
  custom_report_queries: [.custom_reports[].gaql]
}' "${config_path}")"

if [[ "${target_dataset}" != "gads_pmax_creative_history" ]]; then
  echo "Refusing an unexpected destination dataset: ${target_dataset}" >&2
  exit 1
fi
if [[ "${auto_scheduling}" != "false" ]]; then
  echo "Historical transfer must remain manual-only." >&2
  exit 1
fi

existing_config="$(bq ls --transfer_config --project_id="${project_id}" --transfer_location="${transfer_location}" --format=prettyjson \
  | jq -r --arg name "${display_name}" '.[] | select(.displayName == $name) | .name')"

if [[ "${mode}" == "--check" ]]; then
  if [[ -z "${existing_config}" ]]; then
    echo "Historical transfer is not deployed. --check made no changes."
  else
    existing_json="$(bq show --transfer_config --format=prettyjson "${existing_config}")"
    jq -e \
      --arg data_source "${data_source}" \
      --arg target_dataset "${target_dataset}" \
      --arg display_name "${display_name}" \
      '
        .dataSourceId == $data_source and
        .destinationDatasetId == $target_dataset and
        .displayName == $display_name and
        (.schedule == null or .schedule == "")
      ' <<<"${existing_json}" >/dev/null
    echo "Validated manual-only historical transfer: ${existing_config}"
  fi
  exit 0
fi

if bq show --project_id="${project_id}" "${project_id}:${target_dataset}" >/dev/null 2>&1; then
  echo "Dataset already exists: ${project_id}:${target_dataset}"
else
  bq --location="${location}" mk --dataset "${project_id}:${target_dataset}"
fi

if [[ -n "${existing_config}" ]]; then
  bq update --transfer_config \
    --params="${params}" \
    --no_auto_scheduling \
    "${existing_config}"
  echo "Historical transfer updated with automatic scheduling disabled: ${existing_config}"
else
  bq mk --transfer_config \
    --project_id="${project_id}" \
    --target_dataset="${target_dataset}" \
    --display_name="${display_name}" \
    --data_source="${data_source}" \
    --params="${params}" \
    --no_auto_scheduling
fi
