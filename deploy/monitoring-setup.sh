#!/usr/bin/env bash
# Phase 7 – C2/C3: idempotent Cloud Monitoring setup (safe to re-run; create-or-update everything).
#   - 10 log-based metrics      (deploy/monitoring/metrics/*.yaml)
#   - email notification channel (address from ALERT_EMAIL – never stored in the repo)
#   - dashboard                  (deploy/monitoring/dashboard.json)
#   - 8 alert policies           (deploy/monitoring/alerts/*.yaml, wired to the channel)
#
# Usage (from the repo root):  ALERT_EMAIL=you@example.com bash deploy/monitoring-setup.sh

set -euo pipefail
: "${ALERT_EMAIL:?Set ALERT_EMAIL to the notification address}"

PROJECT_ID="$(python -c "from dotenv import dotenv_values; print((dotenv_values('.env').get('GCP_PROJECT_ID') or '').strip('\`\"\' '))" | tr -d '\r\n')"
CHANNEL_NAME="AgentsVille alerts"
gcloud config set project "${PROJECT_ID}" --quiet >/dev/null 2>&1
step() { echo; echo "==> $*"; }

step "Log-based metrics"
for f in deploy/monitoring/metrics/*.yaml; do
  name="$(basename "${f}" .yaml)"
  if gcloud logging metrics describe "${name}" >/dev/null 2>&1; then
    gcloud logging metrics update "${name}" --config-from-file "${f}" --quiet >/dev/null && echo "updated ${name}"
  else
    gcloud logging metrics create "${name}" --config-from-file "${f}" --quiet >/dev/null && echo "created ${name}"
  fi
done

step "Notification channel '${CHANNEL_NAME}' (email) – via the Monitoring REST API (no gcloud beta needed)"
CHANNEL="$(python deploy/monitoring/monitoring_api.py channel "${PROJECT_ID}" "${CHANNEL_NAME}" "${ALERT_EMAIL}")"
echo "channel: ${CHANNEL}"

step "Dashboard – via the Monitoring REST API"
echo "dashboard: $(python deploy/monitoring/monitoring_api.py dashboard "${PROJECT_ID}")"

step "Alert policies – via the Monitoring REST API"
python deploy/monitoring/monitoring_api.py policies "${PROJECT_ID}" "${CHANNEL}"

echo
echo "✅ Monitoring setup done."
