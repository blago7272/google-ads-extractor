#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/deploy_pmax_rolling_refresh.sh [--check|--apply|--seed-current-window]

  --check                Read and validate the isolated PMax transfer identity.
                           No mutation.
  --apply                Enable its daily schedule and 30-day BigQuery Data
                           Transfer refresh window, then verify the result.
  --seed-current-window  Submit one immediate backfill for only the active
                           [today-30, today-1] rolling window. Requires the
                           contracted schedule and refresh window to be live.

The script only accepts the explicitly contracted PMax transfer. It never
changes the shared gads_raw transfer or any transfer in blissful-land-485813-e2.
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
if [[ "$mode" != "--check" && "$mode" != "--apply" && "$mode" != "--seed-current-window" ]]; then
  usage >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config_path="${script_dir}/pmax_rolling_refresh.config.json"

for command in bq jq; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command not found: ${command}" >&2
    exit 1
  fi
done

project_id="$(jq -er '.project_id' "${config_path}")"
transfer_project_number="$(jq -er '.transfer_project_number' "${config_path}")"
transfer_config="$(jq -er '.transfer_config' "${config_path}")"
data_source="$(jq -er '.data_source' "${config_path}")"
destination_dataset="$(jq -er '.destination_dataset' "${config_path}")"
display_name="$(jq -er '.display_name' "${config_path}")"
schedule="$(jq -er '.schedule' "${config_path}")"
refresh_window_days="$(jq -er '.refresh_window_days' "${config_path}")"

if [[ "$transfer_config" != "projects/${transfer_project_number}/locations/europe/transferConfigs/"* ]]; then
  echo "Refusing an unexpected transfer resource outside ${project_id}/europe." >&2
  exit 1
fi
if [[ "$destination_dataset" != "gads_pmax_creative_test" ]]; then
  echo "Refusing an unexpected destination dataset: ${destination_dataset}" >&2
  exit 1
fi
if [[ "$refresh_window_days" -ne 30 ]]; then
  echo "The PMax rolling refresh must use exactly 30 days." >&2
  exit 1
fi

transfer_json="$(bq show --transfer_config --format=prettyjson "${transfer_config}")"
jq -e \
  --arg transfer_config "${transfer_config}" \
  --arg data_source "${data_source}" \
  --arg destination_dataset "${destination_dataset}" \
  --arg display_name "${display_name}" \
  '
    .name == $transfer_config and
    .dataSourceId == $data_source and
    .destinationDatasetId == $destination_dataset and
    .displayName == $display_name
  ' <<<"${transfer_json}" >/dev/null

current_schedule="$(jq -r '.schedule // "<disabled>"' <<<"${transfer_json}")"
current_refresh_window="$(jq -r '.dataRefreshWindowDays // 0' <<<"${transfer_json}")"
echo "Validated isolated PMax transfer: ${transfer_config}"
echo "Current schedule: ${current_schedule}"
echo "Current refresh window: ${current_refresh_window} days"

if [[ "$mode" == "--check" ]]; then
  exit 0
fi

if [[ "$mode" == "--apply" ]]; then
  bq update \
    --transfer_config \
    --schedule="${schedule}" \
    --refresh_window_days="${refresh_window_days}" \
    "${transfer_config}"

  updated_json="$(bq show --transfer_config --format=prettyjson "${transfer_config}")"
  jq -e \
    --arg schedule "${schedule}" \
    --argjson refresh_window_days "${refresh_window_days}" \
    '
      .schedule == $schedule and
      .dataRefreshWindowDays == $refresh_window_days and
      (.nextRunTime != null)
    ' <<<"${updated_json}" >/dev/null

  echo "Enabled ${schedule} (${refresh_window_days}-day refresh window) on ${transfer_config}."
  exit 0
fi

if [[ "${current_schedule}" != "${schedule}" || "${current_refresh_window}" != "${refresh_window_days}" ]]; then
  echo "Refusing to seed before the contracted schedule and refresh window are live." >&2
  exit 1
fi

read -r start_time end_time < <(python3 - <<'PY'
from datetime import datetime, timedelta, timezone

end_date = datetime.now(timezone.utc).date()
start_date = end_date - timedelta(days=30)
print(f"{start_date.isoformat()}T00:00:00Z {end_date.isoformat()}T00:00:00Z")
PY
)

echo "Submitting initial rolling-window seed: [${start_time}, ${end_time})"
bq mk \
  --transfer_run \
  --start_time="${start_time}" \
  --end_time="${end_time}" \
  "${transfer_config}"
echo "Seed submitted. Monitor the transfer runs before beginning historical work."
