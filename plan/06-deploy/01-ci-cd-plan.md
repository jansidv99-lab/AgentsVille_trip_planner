# Phase 6 – CI/CD: GitHub Actions + Cloud Run

Status: **Draft – awaiting review**

## 1. Purpose

Automate "test → build → deploy" so that:
- **CI (continuous integration):** every PR runs the Layer A test suite
  (`plan/04-layer-a-testing/01-layer-a-plan.md`) and a Docker build check. A PR can't be merged
  while either is red.
- **CD (continuous deployment):** every merge to `main` re-runs the tests, builds a container image,
  pushes it to Artifact Registry, deploys it to Cloud Run, and smoke-tests the live URL.

```
 PR opened/updated ──▶ ci.yml:  [Layer A tests] + [Docker build]   → required checks
                                         │
 merge to main ─────▶ deploy.yml: [Layer A tests] ─▶ [build + push image :<git-sha>]
                                         ─▶ [gcloud run deploy] ─▶ [smoke test /_stcore/health]
```

Dependency: the Layer A tests (Phase 4, Steps 1–4) must exist first; CI runs them.

## 2. What already exists in GCP (read-only checks)

The project from `GCP_PROJECT_ID` is shared with your other apps (sql-planner, driver-api, …).
`gcloud` is already configured for it.
- **Enabled APIs:** Cloud Run, Artifact Registry, Secret Manager, IAM Credentials, Cloud Build,
  Logging, Monitoring. Nothing new to enable.
- **WIF pool `github-pool`:** each repo has its own provider, restricted with
  `assertion.repository=='jansidv99-lab/<repo>' && assertion.ref=='refs/heads/main'`.
- **Service accounts:** split per app into `*-deployer` and `*-runtime`.

This plan **follows the same pattern** and creates *dedicated* resources, so this app can't
touch the others:

| Resource | Name | Notes |
|---|---|---|
| Artifact Registry repo | `agentsville` (asia-south1, Docker) | images tagged with the git SHA |
| Secret | `agentsville-openai-api-key` | value piped from `.env`, never printed or committed |
| Deployer SA | `agentsville-deployer` | used by GitHub Actions through WIF |
| Runtime SA | `agentsville-runtime` | identity of the running Cloud Run service |
| WIF provider | `github-agentsville` in `github-pool` | condition: this repo **and** `refs/heads/main` |
| Cloud Run service | `agentsville-trip-planner` (asia-south1) | |

### IAM (least privilege)
- `agentsville-deployer`:
  - `roles/run.admin` on the project, to deploy the service and set its access policy
  - `roles/artifactregistry.writer` on the `agentsville` repo only
  - `roles/iam.serviceAccountUser` on `agentsville-runtime` only, so it can deploy "as" the
    runtime SA
  - `roles/iam.workloadIdentityUser` for
    `principalSet://…/github-pool/attribute.repository/jansidv99-lab/AgentsVille_trip_planner`
- `agentsville-runtime`:
  - `roles/secretmanager.secretAccessor` on `agentsville-openai-api-key` only

## 3. New concepts (learning notes)

- **CI vs CD:** CI checks every change *before* merge. CD ships every merged change
  automatically, so `main` always equals what's live.
- **Workload Identity Federation (WIF):** GitHub gives each workflow run a short-lived OIDC token
  that says "I am repo X, branch Y". GCP trusts the token if it matches the provider's condition,
  and hands out temporary credentials for the deployer SA. **No JSON key is stored anywhere.**
  Restricting the provider to `refs/heads/main` means a PR branch can't deploy.
- **Image tagged by git SHA:** each deploy is traceable to an exact commit. Rolling back is just
  redeploying an older tag.
- **Secrets vs variables:** the API key lives in Secret Manager and is mounted into Cloud Run as an
  env var at runtime. Non-secret settings (region, project, model, base URL) are GitHub
  **repository variables**.
- **Streamlit on Cloud Run:**
  - it must listen on `$PORT` (8080) and `0.0.0.0`
  - it keeps each user's state in memory over a websocket, so **session affinity** is turned on,
    keeping a browser on the same instance

## 4. Files to add

### 4.1 `Dockerfile` + `.dockerignore`
- Base `python:3.11-slim`. Install `requirements.txt` with `--no-cache-dir`. Copy only the app
  files (`app.py`, `models.py`, `llm.py`, `project_lib.py`, `agents/`, `ui/`). Run as a
  **non-root** user.
- Start command:
  `streamlit run app.py --server.port=${PORT:-8080} --server.address=0.0.0.0 --server.headless=true`
- `.dockerignore` excludes `.env` (**critical**), `.git`, `tests/`, `plan/`, `__pycache__/`, and
  `*.md`, so secrets and dev files never end up in the image.

### 4.2 `.github/workflows/ci.yml`
- **Triggers:** `pull_request` to `main`, `workflow_dispatch`.
- **Job `Layer A tests`:** checkout → `setup-python` 3.11 with pip cache → `pip install -r requirements-dev.txt`
  → `pytest`. No secrets are needed, because the tests use a fake client and a dummy key.
- **Job `Docker build`:** `docker build .` without pushing, to catch a broken Dockerfile before
  merge.
- `permissions: contents: read`, the minimum.

### 4.3 `.github/workflows/deploy.yml`
- **Triggers:** `push` to `main` (i.e. a merged PR), `workflow_dispatch`.
- **`concurrency: deploy-production`**, so two deploys never run at once.
- **Job `Deploy gate – Layer A tests`:** the same Layer A run, a second safety net on the merged code.
- **Job `deploy`** (`needs:` the gate job; `permissions: id-token: write, contents: read`):
  1. `google-github-actions/auth@v2` with `workload_identity_provider` + `service_account` from
     repo variables
  2. `google-github-actions/setup-gcloud@v2`
  3. `gcloud auth configure-docker asia-south1-docker.pkg.dev`
  4. Build and push `asia-south1-docker.pkg.dev/<project>/agentsville/trip-planner:<github.sha>`
  5. `gcloud run deploy agentsville-trip-planner`, with:
     - `--image …:<sha>` `--region asia-south1`
     - `--service-account agentsville-runtime@…`
     - `--set-secrets OPENAI_API_KEY=agentsville-openai-api-key:latest`
     - `--set-env-vars OPENAI_BASE_URL=…,MODEL=…,PROMPT_VERSION=…`
     - `--session-affinity` `--min-instances 0` `--max-instances 2` (caps cost)
     - `--cpu 1 --memory 512Mi` `--timeout 300` (an LLM call takes 20–60 s)
     - `--allow-unauthenticated` (public, decision Q1)
  6. **Smoke test:** `curl` the service URL `/_stcore/health`, expect `ok` (retry for up to ~60 s)
  7. Write the service URL and image tag to the job summary

### 4.4 `deploy/gcp-setup.sh` (one-time, run locally)
Idempotent `gcloud` commands (re-running is safe) that create everything in §2 and set the GitHub
repo variables with `gh variable set`:
- `GCP_PROJECT_ID`, `GCP_REGION`
- `WIF_PROVIDER`, `DEPLOYER_SA`, `RUNTIME_SA`
- `OPENAI_BASE_URL`, `MODEL`, `PROMPT_VERSION`

The secret value is piped from `.env` straight into `gcloud secrets versions add --data-file=-`
and never echoed. **I'll ask before running it**, because it creates billable cloud resources.

### 4.5 Branch protection on `main`

**What it is:** GitHub rules on the `main` branch that GitHub itself enforces. Since every merge to
`main` now deploys to production, protection makes sure **only tested, reviewed-by-PR code can
reach `main`**, and therefore production. It's free on public repos.

**Proposed rules** (tuned for a solo developer):

| Rule | Setting | Why |
|---|---|---|
| Require a pull request before merging | on | No direct `git push` to `main`; every change goes through a PR, so CI runs on it |
| Required approvals | **0** | GitHub doesn't let you approve your own PR, so requiring 1 would block every merge. Raise it when collaborators join |
| Require status checks to pass | `Layer A tests`, `Docker build` (from `ci.yml`) | A red test or a broken Dockerfile can't be merged, so it can't be deployed |
| Require branches to be up to date before merging | on | The checks must have run against the *latest* `main`, so two PRs that each pass alone can't break `main` together. Cost: a "Update branch" click when `main` moved |
| Block force pushes | on | Published history on `main` can't be rewritten (the cleanup we did earlier was a one-off) |
| Block branch deletion | on | `main` can't be deleted by accident |
| Apply rules to administrators | on | You're the admin; without this you could bypass every rule. Turning it on builds the habit. For an emergency, temporarily disable it (below) |
| Require linear history | off | We merge PRs with merge commits (like PR #1); linear history would forbid that |
| Require signed commits / conversation resolution | off | Extra friction with little value for a solo learning project |

**How it changes your daily workflow:**
- `git push origin main` is rejected. Push a branch, open a PR, wait for the green checks, then
  merge on GitHub.
- The PR page shows the two checks. The merge button stays disabled until both pass.
- After merging: `git switch main && git pull` (workflow rule 9), and `deploy.yml` deploys.
- GitHub Actions deploying isn't affected: the deploy workflow reads `main`, it doesn't push to it.

**Job names:** status checks are matched by job *name*, so the CI jobs get unique, readable names:
`Layer A tests` and `Docker build`. The deploy workflow's gate job is named `Deploy gate – Layer A
tests`, so it can't be confused with the PR check.

**When to turn it on:** a check can only be selected as required *after it has run once*, so
protection is enabled in Step 5, after the first green CI run.

**How it's applied** (one `gh api` call, shown to you before running):
```
gh api -X PUT repos/jansidv99-lab/AgentsVille_trip_planner/branches/main/protection --input - <<'EOF'
{
  "required_status_checks": { "strict": true, "contexts": ["Layer A tests", "Docker build"] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0 },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false
}
EOF
```
- **Inspect:** `gh api repos/jansidv99-lab/AgentsVille_trip_planner/branches/main/protection`
- **Emergency off and back on:** `gh api -X DELETE …/branches/main/protection`, then re-run the PUT.
- You can also view and edit the same rules in the GitHub UI: Settings → Branches.

## 5. Implementation steps

Branch: `feature/layer-a-tests-and-ci-cd`, the same branch as the Layer A tests (your
decision), so Layer A and CI/CD ship in one PR. Each new file starts with a `# Phase 6 – Step N: …` comment (YAML and shell support `#`).

| Step | Purpose | Depends on | Files / actions |
|---|---|---|---|
| 1 | Container: build and run locally with `docker run -p 8080:8080 --env-file .env` | — | `Dockerfile`, `.dockerignore` |
| 2 | CI workflow; open a PR and watch it go green | Layer A tests | `.github/workflows/ci.yml` |
| 3 | One-time GCP + GitHub setup (with your permission) | 1 | `deploy/gcp-setup.sh` |
| 4 | CD workflow; merge → watch it deploy → open the URL | 2, 3 | `.github/workflows/deploy.yml` |
| 5 | Branch protection; record the region, URL, and commands in CLAUDE.md | 4 | repo settings, `CLAUDE.md` |

Later phases extend this pipeline:
- **Layer B (Phase 5):** a nightly / manual `evals.yml` workflow that runs `pytest -m eval` with
  the API key.
- **Layer C (Phase 7):** monitoring config, deployed the same way.

## 6. Decisions

- **Q1 – Access: public.** Deploy with `--allow-unauthenticated` and `--max-instances 2` to limit
  cost. Layer C adds a budget alert.
- **Q2 – Branch protection: approved** with the rules in §4.5 (enabled in Step 5).
- **Q3 – Resources: dedicated `agentsville-*`,** as listed in §2.

## 7. Notes found during research

- `.env` has `` REGION=`asia-south1` `` with **backticks**. python-dotenv keeps them as part of the
  value. Change it to `REGION=asia-south1`. The workflows read the region from a GitHub variable,
  so CI/CD isn't affected.
- `OPENAI_BASE_URL` points at the Vocareum endpoint, so the deployed app keeps working only while
  that key is valid.

## 8. Updates to the master plan

`plan/00-master-plan.md` changes the order to **Phase 4 (Layer A) → Phase 6 (CI/CD) → Phase 5
(Layer B) → Phase 7 (Layer C)**. CI/CD only needs the Layer A tests, and deploying early gives
Layer B and Layer C a real environment to work against.

## 9. Done when

- A PR shows green `Layer A tests` and `Docker build` checks, and a deliberately broken test turns it red.
- Merging to `main` deploys automatically. The job summary shows the URL, `/_stcore/health`
  returns `ok`, and a real itinerary can be generated on the live app.
- No JSON keys or secrets exist in GitHub, the image, or the repo
  (`docker run --rm <image> ls -a /app` shows no `.env`).
