#!/usr/bin/env bash
# Phase 6 – Step 3: one-time Google Cloud + GitHub setup for the CD workflow (deploy.yml).
#
# Creates dedicated "agentsville-*" resources (never touches the other apps in the project):
#   Artifact Registry repo, Secret Manager secret, deployer + runtime service accounts,
#   least-privilege IAM bindings, a WIF provider limited to this repo on main,
#   and the GitHub repository variables the workflow reads.
#
# Idempotent: every step checks whether the resource exists first, so re-running is safe.
# Reads settings from .env (via python-dotenv). The API key is piped straight into
# Secret Manager and is never printed.
#
# Usage (from the repo root):  bash deploy/gcp-setup.sh

set -euo pipefail

# ---------------------------------------------------------------------------
# Phase 6 – Step 3: configuration
# ---------------------------------------------------------------------------
env_value() {  # read one value from .env, stripping quotes/backticks
  # sys.stdout.write (not print) so Windows doesn't append "\r\n"; tr removes any stray CR/LF.
  python -c "import sys; from dotenv import dotenv_values; sys.stdout.write((dotenv_values('.env').get('$1') or '').strip('\`\"\' \r\n'))" | tr -d '\r\n'
}

PROJECT_ID="$(env_value GCP_PROJECT_ID)"
PROJECT_NUMBER="$(env_value GCP_PROJECT_NUMBER)"
REGION="$(env_value REGION)"
OPENAI_BASE_URL="$(env_value OPENAI_BASE_URL)"
MODEL="$(env_value MODEL)"
PROMPT_VERSION="$(env_value PROMPT_VERSION)"

GITHUB_REPO="jansidv99-lab/AgentsVille_trip_planner"
POOL="github-pool"
PROVIDER="github-agentsville"
AR_REPO="agentsville"
SECRET="agentsville-openai-api-key"
DEPLOYER="agentsville-deployer"
RUNTIME="agentsville-runtime"
DEPLOYER_SA="${DEPLOYER}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="${RUNTIME}@${PROJECT_ID}.iam.gserviceaccount.com"
POOL_ID="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}"
WIF_PROVIDER="${POOL_ID}/providers/${PROVIDER}"

for v in PROJECT_ID PROJECT_NUMBER REGION; do
  [[ -n "${!v}" ]] || { echo "Missing ${v} in .env"; exit 1; }
done

gcloud config set project "${PROJECT_ID}" --quiet >/dev/null
step() { echo; echo "==> $*"; }

# ---------------------------------------------------------------------------
# Phase 6 – Step 3: Artifact Registry repository (holds the app images)
# ---------------------------------------------------------------------------
step "Artifact Registry repo ${AR_REPO} (${REGION})"
gcloud artifacts repositories describe "${AR_REPO}" --location "${REGION}" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "${AR_REPO}" --location "${REGION}" \
       --repository-format docker --description "AgentsVille trip planner images"

# ---------------------------------------------------------------------------
# Phase 6 – Step 3: secret with the OpenAI API key (value piped from .env, never echoed)
# ---------------------------------------------------------------------------
step "Secret ${SECRET}"
gcloud secrets describe "${SECRET}" >/dev/null 2>&1 \
  || gcloud secrets create "${SECRET}" --replication-policy automatic
if [[ -z "$(gcloud secrets versions list "${SECRET}" --filter='state=ENABLED' --format='value(name)' --limit 1)" ]]; then
  env_value OPENAI_API_KEY | gcloud secrets versions add "${SECRET}" --data-file=- >/dev/null
  echo "Added the API key as the first secret version."
else
  echo "Secret already has an enabled version (to rotate: add a new version manually)."
fi

# ---------------------------------------------------------------------------
# Phase 6 – Step 3: service accounts (deployer = GitHub Actions, runtime = the running app)
# ---------------------------------------------------------------------------
for sa in "${DEPLOYER}:AgentsVille GitHub Actions deployer" "${RUNTIME}:AgentsVille Cloud Run runtime"; do
  name="${sa%%:*}"; display="${sa#*:}"
  step "Service account ${name}"
  gcloud iam service-accounts describe "${name}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 \
    || gcloud iam service-accounts create "${name}" --display-name "${display}"
done

# ---------------------------------------------------------------------------
# Phase 6 – Step 3: least-privilege IAM (add-iam-policy-binding is idempotent)
# ---------------------------------------------------------------------------
step "IAM: deployer can deploy Cloud Run services"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member "serviceAccount:${DEPLOYER_SA}" --role roles/run.admin --condition=None --quiet >/dev/null

step "IAM: deployer can push images to ${AR_REPO} only"
gcloud artifacts repositories add-iam-policy-binding "${AR_REPO}" --location "${REGION}" \
  --member "serviceAccount:${DEPLOYER_SA}" --role roles/artifactregistry.writer --quiet >/dev/null

step "IAM: deployer can deploy *as* the runtime SA only"
gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}" \
  --member "serviceAccount:${DEPLOYER_SA}" --role roles/iam.serviceAccountUser --quiet >/dev/null

step "IAM: runtime SA can read ${SECRET} only"
gcloud secrets add-iam-policy-binding "${SECRET}" \
  --member "serviceAccount:${RUNTIME_SA}" --role roles/secretmanager.secretAccessor --quiet >/dev/null

# ---------------------------------------------------------------------------
# Phase 6 – Step 3: Workload Identity Federation (GitHub OIDC → deployer SA, this repo + main only)
# ---------------------------------------------------------------------------
step "WIF provider ${PROVIDER} in ${POOL}"
gcloud iam workload-identity-pools providers describe "${PROVIDER}" \
    --workload-identity-pool "${POOL}" --location global >/dev/null 2>&1 \
  || gcloud iam workload-identity-pools providers create-oidc "${PROVIDER}" \
       --workload-identity-pool "${POOL}" --location global \
       --display-name "AgentsVille trip planner" \
       --issuer-uri "https://token.actions.githubusercontent.com" \
       --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
       --attribute-condition "assertion.repository=='${GITHUB_REPO}' && assertion.ref=='refs/heads/main'"

step "IAM: GitHub workflows from ${GITHUB_REPO} may impersonate the deployer SA"
gcloud iam service-accounts add-iam-policy-binding "${DEPLOYER_SA}" \
  --member "principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/${GITHUB_REPO}" \
  --role roles/iam.workloadIdentityUser --quiet >/dev/null

# ---------------------------------------------------------------------------
# Phase 6 – Step 3: GitHub repository variables (non-secret settings read by deploy.yml)
# ---------------------------------------------------------------------------
step "GitHub repository variables"
gh variable set GCP_PROJECT_ID  --repo "${GITHUB_REPO}" --body "${PROJECT_ID}"
gh variable set GCP_REGION      --repo "${GITHUB_REPO}" --body "${REGION}"
gh variable set WIF_PROVIDER    --repo "${GITHUB_REPO}" --body "${WIF_PROVIDER}"
gh variable set DEPLOYER_SA     --repo "${GITHUB_REPO}" --body "${DEPLOYER_SA}"
gh variable set RUNTIME_SA      --repo "${GITHUB_REPO}" --body "${RUNTIME_SA}"
gh variable set OPENAI_BASE_URL --repo "${GITHUB_REPO}" --body "${OPENAI_BASE_URL}"
gh variable set MODEL           --repo "${GITHUB_REPO}" --body "${MODEL:-gpt-4.1-mini}"
gh variable set PROMPT_VERSION  --repo "${GITHUB_REPO}" --body "${PROMPT_VERSION:-V1}"

echo
echo "✅ Setup complete. Merging to main will now deploy ${GITHUB_REPO} to Cloud Run in ${REGION}."
