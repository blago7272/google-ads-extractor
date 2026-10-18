#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/create_monitoring_alert_policies.sh [--check|--apply] [options]

  --check                    Print the policies this script manages and whether each
                             already exists. No mutation. (default)
  --apply                    Create the email notification channel if needed, then
                             create each policy, or update it in place if a policy
                             with the same display name exists.

Options:
  --email ADDRESS            Where alerts go. Required for --apply (or ALERT_EMAIL).
  --include-still-excluded   Also manage the low-urgency "still excluded" policy. It
                             fires on every run while any account is excluded from the
                             marts, so it is off by default.

Policies (project gads-export-all, job reporting-release-orchestrator):

  1. Reporting release: execution failed
     Metric run.googleapis.com/job/completed_execution_count, result=failed. Catches
     every failed run, including a container killed by OOM or timeout that never
     logs release_failed.
  2. Reporting release: account newly excluded from marts
     Log event skipped_accounts_alert (ERROR), from docs/skipped_accounts_alerting.md.
  3. Reporting release: accounts still excluded from marts   (--include-still-excluded)
     Log event skipped_accounts_still_excluded (WARNING), same doc.

The ops Telegram chat gets failure and drop-out messages from the job itself; these
policies are the independent channel.
EOF
}

PROJECT_ID="gads-export-all"
JOB_NAME="reporting-release-orchestrator"
CHANNEL_DISPLAY_NAME="Reporting pipeline alerts (email)"
POLICY_PREFIX="Reporting release:"

mode="--check"
email="${ALERT_EMAIL:-}"
include_still_excluded=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check|--apply) mode="$1" ;;
    --email) email="${2:-}"; shift ;;
    --include-still-excluded) include_still_excluded=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

for command in gcloud jq; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Required command not found: ${command}" >&2
    exit 1
  fi
done

if [[ "$mode" == "--apply" && -z "$email" ]]; then
  echo "--apply needs --email ADDRESS (or ALERT_EMAIL)." >&2
  exit 2
fi

work_dir="$(mktemp -d "${TMPDIR:-/tmp}/monitoring-policies.XXXXXX")"
trap 'rm -rf "${work_dir}"' EXIT

job_logs='resource.type="cloud_run_job" AND resource.labels.job_name="'"${JOB_NAME}"'"'

# write_policy FILE DISPLAY_NAME SEVERITY CONDITION_JSON ALERT_STRATEGY_JSON DOC
write_policy() {
  jq -n \
    --arg display_name "$2" \
    --arg severity "$3" \
    --argjson condition "$4" \
    --argjson strategy "$5" \
    --arg doc "$6" \
    '{
      displayName: $display_name,
      severity: $severity,
      combiner: "OR",
      enabled: true,
      conditions: [$condition],
      alertStrategy: $strategy,
      documentation: {content: $doc, mimeType: "text/markdown"}
    }' > "$1"
}

write_policy "${work_dir}/1-execution-failed.json" \
  "${POLICY_PREFIX} execution failed" "CRITICAL" \
  "$(jq -n --arg job "${JOB_NAME}" '{
      displayName: "A reporting-release-orchestrator execution failed",
      conditionThreshold: {
        filter: ("resource.type = \"cloud_run_job\" AND resource.labels.job_name = \"" + $job + "\" AND metric.type = \"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result = \"failed\""),
        aggregations: [{alignmentPeriod: "300s", perSeriesAligner: "ALIGN_SUM", crossSeriesReducer: "REDUCE_SUM"}],
        comparison: "COMPARISON_GT",
        thresholdValue: 0,
        duration: "0s",
        trigger: {count: 1},
        evaluationMissingData: "EVALUATION_MISSING_DATA_INACTIVE"
      }
    }')" \
  '{"autoClose": "86400s"}' \
  "The daily Google Ads reporting release failed, so the marts were not (fully) rebuilt. The ops Telegram chat has the failing step and error unless the container was killed (OOM or timeout). Logs: Cloud Run job ${JOB_NAME}, event release_failed."

write_policy "${work_dir}/2-newly-excluded.json" \
  "${POLICY_PREFIX} account newly excluded from marts" "ERROR" \
  "$(jq -n --arg filter "${job_logs}"' AND jsonPayload.event="skipped_accounts_alert" AND severity="ERROR"' '{
      displayName: "skipped_accounts_alert logged",
      conditionMatchedLog: {filter: $filter}
    }')" \
  '{"notificationRateLimit": {"period": "3600s"}, "autoClose": "604800s"}' \
  "An account that was in reporting yesterday has stale raw data and is now excluded from every mart. See docs/skipped_accounts_alerting.md. Fixing it usually means re-authorising the account in the Google Ads Data Transfer."

if [[ "$include_still_excluded" == true ]]; then
  write_policy "${work_dir}/3-still-excluded.json" \
    "${POLICY_PREFIX} accounts still excluded from marts" "WARNING" \
    "$(jq -n --arg filter "${job_logs}"' AND jsonPayload.event="skipped_accounts_still_excluded"' '{
        displayName: "skipped_accounts_still_excluded logged",
        conditionMatchedLog: {filter: $filter}
      }')" \
    '{"notificationRateLimit": {"period": "86400s"}, "autoClose": "604800s"}' \
    "Standing reminder: one or more accounts are still excluded from the marts. Re-emitted on every run. See docs/skipped_accounts_alerting.md."
fi

existing_policies="$(gcloud monitoring policies list --project="${PROJECT_ID}" --format=json)"

policy_name_for() {
  jq -r --arg name "$1" '[.[] | select(.displayName == $name) | .name] | first // empty' <<<"${existing_policies}"
}

echo "Project: ${PROJECT_ID}  Mode: ${mode}"
for file in "${work_dir}"/*.json; do
  display_name="$(jq -r '.displayName' "${file}")"
  existing="$(policy_name_for "${display_name}")"
  echo ""
  echo "== ${display_name} -> $([[ -n "$existing" ]] && echo "exists (${existing})" || echo "not created")"
  if [[ "$mode" == "--check" ]]; then
    jq . "${file}"
  fi
done

if [[ "$mode" == "--check" ]]; then
  echo ""
  echo "No changes made. Re-run with --apply --email ADDRESS to create or update."
  exit 0
fi

# Notification channel: reuse ours by display name, else create it.
channels="$(gcloud beta monitoring channels list --project="${PROJECT_ID}" --format=json)"
channel="$(jq -r --arg name "${CHANNEL_DISPLAY_NAME}" --arg email "${email}" \
  '[.[] | select(.displayName == $name and .labels.email_address == $email) | .name] | first // empty' <<<"${channels}")"
if [[ -z "$channel" ]]; then
  channel="$(gcloud beta monitoring channels create \
    --project="${PROJECT_ID}" \
    --display-name="${CHANNEL_DISPLAY_NAME}" \
    --type=email \
    --channel-labels="email_address=${email}" \
    --format='value(name)')"
  echo "Created notification channel ${channel}"
else
  echo "Using notification channel ${channel}"
fi

for file in "${work_dir}"/*.json; do
  jq --arg channel "${channel}" '.notificationChannels = [$channel]' "${file}" > "${file}.final"
  display_name="$(jq -r '.displayName' "${file}")"
  existing="$(policy_name_for "${display_name}")"
  if [[ -n "$existing" ]]; then
    gcloud monitoring policies update "${existing}" --project="${PROJECT_ID}" --policy-from-file="${file}.final" >/dev/null
    echo "Updated: ${display_name}"
  else
    gcloud monitoring policies create --project="${PROJECT_ID}" --policy-from-file="${file}.final" >/dev/null
    echo "Created: ${display_name}"
  fi
done

echo ""
echo "Done. Policies now:"
gcloud monitoring policies list --project="${PROJECT_ID}" \
  --filter="displayName:\"${POLICY_PREFIX}\"" \
  --format='table(displayName,enabled,severity,notificationChannels.len():label=CHANNELS)'
