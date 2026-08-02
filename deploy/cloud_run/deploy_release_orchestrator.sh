#!/usr/bin/env bash
set -euo pipefail

# Deploy the reporting release orchestrator Cloud Run Job.
#
# TWO MODES, deliberately separated:
#
#   release    Image-only update. Preserves env vars, secrets, service account
#              and resource settings. This is the normal path for shipping code.
#
#   provision  Full container spec, including a complete env file. Use ONLY for
#              first-time creation, or a deliberate configuration change.
#
# Why the split: `gcloud run jobs deploy --env-vars-file` REPLACES the entire
# environment block -- gcloud's own docs say "All existing environment variables
# will be removed before the new environment variables are added". Running a full
# provision against the live job with a drifted file silently rewrites its config.
#
# That is not theoretical. This directory's env example shipped with
# RAW_FRESHNESS_MAX_ALLOWED_LAG_DAYS=0 while production runs 3. At 0, every
# account is classified stale -- the Google Ads transfer always lands at least a
# day behind -- so all ten leaf marts inner-join an empty healthy_accounts set and
# rebuild EMPTY. The freshness gate is non-blocking and dbt tests pass vacuously
# on empty tables, so the whole reporting layer would go dark without one error.

usage() {
  cat <<'EOF'
Usage:
  deploy_release_orchestrator.sh release   <project_id> <region> <job_name> <image_uri>
  deploy_release_orchestrator.sh provision <project_id> <region> <job_name> <image_uri> <service_account> <env_file>

Modes:
  release    Ship a new image. Preserves all existing configuration. Use this
             for every normal deploy.
  provision  Create the job, or deliberately rewrite its full configuration.
             Refuses to run against an existing job unless FORCE=1.

Environment overrides (provision only):
  SECRETS    Secret bindings, gcloud --set-secrets syntax.
             Default: TELEGRAM_BOT_TOKEN=telegram-bot-token:latest
             Set to "" to provision with no secrets.
  FORCE=1    Allow provision to overwrite an existing job's configuration.

Examples:
  # normal deploy -- config untouched
  deploy/cloud_run/deploy_release_orchestrator.sh release \
    gads-export-all europe-west1 reporting-release-orchestrator \
    europe-west1-docker.pkg.dev/gads-export-all/reporting/release-orchestrator:COMMIT_SHA

  # first-time provisioning
  deploy/cloud_run/deploy_release_orchestrator.sh provision \
    gads-export-all europe-west1 reporting-release-orchestrator \
    europe-west1-docker.pkg.dev/gads-export-all/reporting/release-orchestrator:COMMIT_SHA \
    dbt-runner@gads-export-all.iam.gserviceaccount.com \
    deploy/cloud_run/release_orchestrator.env.example.yaml
EOF
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

mode="$1"
shift

case "$mode" in
  release)
    if [[ $# -lt 4 ]]; then
      usage
      exit 1
    fi
    project_id="$1"
    region="$2"
    job_name="$3"
    image_uri="$4"

    gcloud run jobs update "$job_name" \
      --project="$project_id" \
      --region="$region" \
      --image="$image_uri"
    ;;

  provision)
    if [[ $# -lt 6 ]]; then
      usage
      exit 1
    fi
    project_id="$1"
    region="$2"
    job_name="$3"
    image_uri="$4"
    service_account="$5"
    env_file="$6"

    if [[ ! -f "$env_file" ]]; then
      echo "ERROR: env file not found: $env_file" >&2
      exit 1
    fi

    if gcloud run jobs describe "$job_name" \
         --project="$project_id" --region="$region" >/dev/null 2>&1; then
      if [[ "${FORCE:-}" != "1" ]]; then
        cat >&2 <<EOF
ERROR: job '$job_name' already exists in ${project_id}/${region}.

Provisioning REPLACES its entire environment block with the contents of
  $env_file
Any variable missing from that file is deleted from the live job.

To ship a new image without touching configuration:
  $0 release $project_id $region $job_name $image_uri

To proceed anyway, first diff the live environment against the file:
  gcloud run jobs describe $job_name --project=$project_id --region=$region \\
    --format='value(spec.template.spec.template.spec.containers[0].env)'

then re-run with FORCE=1.
EOF
        exit 1
      fi
      echo "WARNING: FORCE=1 set -- rewriting the full configuration of existing job '$job_name'." >&2
    fi

    secrets="${SECRETS-TELEGRAM_BOT_TOKEN=telegram-bot-token:latest}"

    deploy_args=(
      "$job_name"
      --project="$project_id"
      --region="$region"
      --image="$image_uri"
      --service-account="$service_account"
      --tasks=1
      --parallelism=1
      --max-retries=0
      --task-timeout=3600s
      --memory=2Gi
      --cpu=1
      --command=python
      --args=scripts/release_orchestrator.py
      --env-vars-file="$env_file"
    )

    # Secrets cannot live in --env-vars-file. Bind them explicitly, or the job is
    # provisioned without them (which would silently disable Telegram alerting).
    if [[ -n "$secrets" ]]; then
      deploy_args+=(--set-secrets="$secrets")
    fi

    gcloud run jobs deploy "${deploy_args[@]}"
    ;;

  *)
    echo "ERROR: unknown mode '$mode' (expected 'release' or 'provision')." >&2
    usage
    exit 1
    ;;
esac
