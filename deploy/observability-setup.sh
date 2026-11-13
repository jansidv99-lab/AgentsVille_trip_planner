#!/usr/bin/env bash
# Phase 7 – C1 Step 3: one-time setup of the observability pipeline (idempotent – safe to re-run).
#   Cloud Run stdout (JSON events) ──log sink──▶ BigQuery dataset agentsville_observability ──▶ views
#
# - Dataset in the app's region; a log sink filtered to THIS service's app events; least-privilege write
#   access for the sink's writer identity on THIS dataset only (not project-wide).
# - Views are created only once the sink's table exists (it appears with the first live event), so re-run
#   this script after the first itinerary is generated on the live app.
#
# Usage (from the repo root):  bash deploy/observability-setup.sh

set -euo pipefail

env_value() {  # same helper as gcp-setup.sh: read .env without quotes/backticks/CR
  python -c "import sys; from dotenv import dotenv_values; sys.stdout.write((dotenv_values('.env').get('$1') or '').strip('\`\"\' \r\n'))" | tr -d '\r\n'
}

PROJECT_ID="$(env_value GCP_PROJECT_ID)"
REGION="$(env_value REGION)"
DATASET="agentsville_observability"
SINK="agentsville-llm-events"
SERVICE="agentsville-trip-planner"
TABLE="run_googleapis_com_stdout"
FILTER="resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${SERVICE}\" AND jsonPayload.app=\"agentsville\""

step() { echo; echo "==> $*"; }

step "BigQuery dataset ${DATASET} (${REGION})"
bq --project_id "${PROJECT_ID}" show --dataset "${PROJECT_ID}:${DATASET}" >/dev/null 2>&1 \
  || bq --project_id "${PROJECT_ID}" --location "${REGION}" mk --dataset \
       --description "AgentsVille LLM run + feedback events (Layer C1 / B5)" "${PROJECT_ID}:${DATASET}"

step "Log sink ${SINK}"
if ! gcloud logging sinks describe "${SINK}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud logging sinks create "${SINK}" "bigquery.googleapis.com/projects/${PROJECT_ID}/datasets/${DATASET}" \
    --project "${PROJECT_ID}" --log-filter "${FILTER}" --use-partitioned-tables --quiet
fi
WRITER="$(gcloud logging sinks describe "${SINK}" --project "${PROJECT_ID}" --format='value(writerIdentity)')"
echo "sink writer identity: ${WRITER}"

step "IAM: sink writer may write to ${DATASET} only"
tmp="$(mktemp)"
bq --project_id "${PROJECT_ID}" show --format=prettyjson "${PROJECT_ID}:${DATASET}" > "${tmp}"
python - "${tmp}" "${WRITER#serviceAccount:}" <<'PY'
import json, sys
path, email = sys.argv[1], sys.argv[2]
ds = json.load(open(path))
entry = {"role": "WRITER", "userByEmail": email}
if entry not in ds.get("access", []):
    ds.setdefault("access", []).append(entry)
    json.dump(ds, open(path, "w"))
    print("added WRITER access for", email)
else:
    print("access already present")
PY
bq --project_id "${PROJECT_ID}" update --source "${tmp}" "${PROJECT_ID}:${DATASET}" >/dev/null
rm -f "${tmp}"

step "Views (need the sink table, created by the first live event)"
if bq --project_id "${PROJECT_ID}" show "${PROJECT_ID}:${DATASET}.${TABLE}" >/dev/null 2>&1; then
  for view in llm_runs feedback runs_with_feedback daily_quality input_profile; do  # order matters (dependencies)
    sql="$(sed -e "s/\${PROJECT}/${PROJECT_ID}/g" -e "s/\${DATASET}/${DATASET}/g" "observability/bigquery/${view}.sql")"
    bq --project_id "${PROJECT_ID}" rm -f -t "${PROJECT_ID}:${DATASET}.${view}" >/dev/null 2>&1 || true
    bq --project_id "${PROJECT_ID}" mk --use_legacy_sql=false --view "${sql}" "${PROJECT_ID}:${DATASET}.${view}" >/dev/null
    echo "view ${view} ✓"
  done
else
  echo "Table ${TABLE} doesn't exist yet – generate one itinerary on the live app, wait ~1–2 min, then re-run."
fi

echo
echo "✅ Observability setup done."
