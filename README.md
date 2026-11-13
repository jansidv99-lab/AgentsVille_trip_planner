# AgentsVille Trip Planner

An AI-powered trip planner for the fictional city of **AgentsVille**, wrapped in an
**AI Quality Assurance platform**: deterministic tests, probabilistic LLM evals, and production
monitoring on Google Cloud.

Give it your travelers, their interests, dates, and budget. An LLM acting as an expert travel
planner returns a day-by-day itinerary as structured JSON, validated against a Pydantic model and
grounded in (mocked) weather and activity APIs.

> Built as a hands-on learning project (Udacity). Each phase was planned in `plan/` and reviewed
> before it was implemented.

---

## Contents

- [Features](#features)
- [Architecture](#architecture)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Quality assurance](#quality-assurance)
  - [Layer A – deterministic tests](#layer-a--deterministic-tests)
  - [Layer B – probabilistic evals](#layer-b--probabilistic-evals)
  - [Layer C – monitoring & alerting](#layer-c--monitoring--alerting)
- [Deployment (CI/CD)](#deployment-cicd)
- [Prompt versions](#prompt-versions)
- [Business rules](#business-rules)
- [Roadmap](#roadmap)

---

## Features

- **Part A – The Expert Planner.** Turns traveler preferences into a coherent, day-by-day
  itinerary. The prompt contains only the weather and activities for the chosen dates, and the
  reply must validate against the `TravelPlan` Pydantic model.
- **Streamlit UI.** Enter traveler names, pick the city (AgentsVille), choose interests from the
  `Interest` enum, select the OpenAI model, and generate the plan.
- **Prompt inspector.** Shows the exact system prompt, the raw LLM reply, latency, tokens, cost,
  and live **quality checks** (the same graders the eval harness uses).
- **Feedback.** 👍/👎 with an optional comment, linked to each run by `trace_id`.
- **AI QA platform.** Three layers of checks around the planner (see
  [Quality assurance](#quality-assurance)).

> The mocked APIs in `project_lib.py` only have data for **2025-06-10 to 2025-06-15**, so trips
> must fall inside that window.

## Architecture

```
            ┌──────────────────────────── Streamlit app (app.py, ui/render.py) ─────────────┐
 traveler → │  form → VacationInfo ──▶ ItineraryAgent ──▶ LLM (OpenAI-compatible endpoint)  │
            │                          │   prompt = prompts/itinerary/vN.md                 │
            │                          │          + mocked weather + activities             │
            │                          ▼                                                    │
            │                     TravelPlan (Pydantic) ──▶ quality/graders (online, free)   │
            └──────────────────────────┬─────────────────────────────────────────────────────┘
                                       │ one JSON event per run (observability/events.py)
                                       ▼
          Cloud Logging ──▶ log-based metrics ──▶ dashboard + alert policies   (Layer C)
                │
                └──▶ BigQuery sink ──▶ promote.py ──▶ golden dataset candidates (Layer B)

  Offline: evals/harness/runner.py ── golden dataset ──▶ same quality/graders ──▶ report + gate
```

The `quality/` package is shared by the app (online checks on every run) and the eval harness
(offline runs on the golden dataset), so production and evals grade results the same way.

## Quick start

Requirements: Python 3.11, an OpenAI-compatible API key.

```bash
git clone https://github.com/jansidv99-lab/AgentsVille_trip_planner.git
cd AgentsVille_trip_planner

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt    # app
pip install -r requirements-dev.txt  # + tests

cp .env.example .env               # then fill in OPENAI_API_KEY etc.

streamlit run app.py               # open http://localhost:8501
```

CLI demo of Part A (one LLM call, prints the plan):

```bash
python planner.py
```

## Configuration

All settings come from environment variables (`.env` locally, never committed).

| Variable | Purpose | Default |
|---|---|---|
| `OPENAI_API_KEY` | API key for the LLM endpoint | — (required) |
| `OPENAI_BASE_URL` | OpenAI-compatible endpoint | SDK default |
| `MODEL` | Model used for generation | `gpt-4.1-mini` |
| `PROMPT_VERSION` | Itinerary prompt (`prompts/itinerary/v<N>.md`) | `v1` |
| `JUDGE_MODEL` | Offline LLM judge (evals only) | `gpt-4.1-mini` |
| `GCP_PROJECT_ID`, `GCP_PROJECT_NUMBER` | Deployment target | — |

Supported models:

| Model | Use for |
|---|---|
| `gpt-4.1` | Strongest; demanding reasoning |
| `gpt-4.1-mini` | **Default** – good balance of speed and cost |
| `gpt-4.1-nano` | Fastest and cheapest |

## Project layout

```
app.py                 Streamlit entry point
ui/render.py           Results view, prompt inspector, feedback
planner.py             CLI demo of Part A
models.py              Pydantic models: VacationInfo (input), TravelPlan (output), PromptTrace
llm.py                 OpenAI client + InstrumentedClient (latency, tokens, cost)
agents/itinerary.py    Prompt builder and ItineraryAgent
prompts/itinerary/     Versioned prompt templates (v1 live; v2, v3 rejected by the gate)
project_lib.py         Course helpers, Interest enum, mocked weather & activities data
quality/               Graders, schema, pricing, approved activity labels (shared app + evals)
evals/                 Golden datasets, harness (runner, cache, report, gate, promote), baselines
observability/         Structured JSON events + BigQuery views
deploy/                GCP setup, observability and monitoring config-as-code
tests/                 Layer A test suite (no LLM calls)
plan/                  Phase-by-phase design docs (start with plan/00-master-plan.md)
.github/workflows/     CI, deploy, eval smoke gate, manual full eval
```

## Quality assurance

| Layer | Question it answers | Where |
|---|---|---|
| **A – Deterministic tests** | Does the software work? | `tests/` |
| **B – Probabilistic evals** | Is the AI producing acceptable outcomes? | `quality/`, `evals/` |
| **C – Metrics & drift monitoring** | Is it healthy in production? | `observability/`, `deploy/monitoring/` |

### Layer A – deterministic tests

Fast (~2 s), free, and never call the LLM (a fake client and mocked agent are used instead).

```bash
pytest                                   # whole suite
pytest tests/test_models.py              # one file
pytest tests/test_models.py::test_same_day_trip_is_valid   # one test
pytest --cov=. --cov-report=term-missing # coverage (needs pytest-cov)
```

Covers model validation, prompt building, JSON extraction, the agent trace, the Streamlit UI
(`AppTest`), the graders (with mutation tests), the eval harness, observability events, the
monitoring config contract, and the Docker image contents.

### Layer B – probabilistic evals

Evals call the real LLM, so they cost credits and are excluded from plain `pytest`.

**Graders** are pure, deterministic functions over a plan:

| Slice | Checks |
|---|---|
| B0 | The reply parses and validates against `TravelPlan` |
| B1 | Hallucination – every activity, date, and price exists in the mocked data |
| B2 | Constraints / task success – budget, dates, weather safety, interests |
| B3 | Relevancy and reasoning (deterministic) + an offline LLM judge (report-only until calibrated) |
| B4 | Regression gating – compare a prompt version with the accepted baseline |
| B5 | Feedback loop – production runs are mined from BigQuery into reviewed golden cases |

**Golden dataset:** `evals/datasets/itinerary_golden/` – versioned JSONL with a semver
`manifest.json` (sha256, counts, changelog). Only cases with `review.status: approved` run.

**Running evals:**

```bash
pytest -m eval -s                                          # smoke (3 cases)
python -m evals.harness.runner --mode smoke                # smoke via the runner
python -m evals.harness.runner --mode full --repeats 1     # full run (≤ ~50 LLM calls)
python -m evals.harness.runner --mode full --cache replay-only   # re-grade cached replies, 0 calls
python -m evals.harness.runner --mode full --judge         # add the offline LLM judge
python -m evals.harness.runner --mode full --prompt-version v3 --compare-to v1
python -m evals.harness.gate                               # CI smoke gate
```

Results go to `evals/results/<UTC>_<mode>/` (`records.jsonl`, `report.md`, `report.json`);
replies are cached in `evals/cache/`. Both are gitignored.

**Production → golden data:**

```bash
python -m evals.harness.promote mine --days 7               # BigQuery → candidates (drafts)
python -m evals.harness.promote approve P1 --reviewer <name> # after human review
```

Traveler names are replaced with synthetic ones before anything is committed.

### Layer C – monitoring & alerting

- **C1 – structured logging.** The app writes one JSON line per event to stdout (`llm_run`,
  `llm_error`, `feedback`). Cloud Run → Cloud Logging → sink → BigQuery dataset
  `agentsville_observability`. Set up with `bash deploy/observability-setup.sh` (idempotent).
- **C2 – metrics & dashboard.** 10 log-based metrics and the dashboard
  **“AgentsVille – AI quality & ops”** (`deploy/monitoring/`).
- **C3 – alerting.** 8 alert policies, each with a runbook in its documentation:

| Alert | Fires when |
|---|---|
| A1 Hallucination | any hallucination in 1 h |
| A2 Task-success drift | > 60% failures in 6 h (≥ 5 runs) |
| A3 Weather spike | > 50% weather failures in 6 h (≥ 5 runs) |
| A4 LLM errors | ≥ 3 errors in 10 min |
| A5 Slow | p95 latency > 60 s over 30 min |
| A6 Unhappy users | 👎 > 50% in 24 h (≥ 5 ratings) |
| A7 Cost guard | > 60 runs per hour |
| A9 5xx | server errors on Cloud Run |

```bash
ALERT_EMAIL=<address> bash deploy/monitoring-setup.sh       # apply (idempotent)
python deploy/monitoring/fire_synthetic_event.py <project>  # synthetic alert test
```

## Deployment (CI/CD)

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | every PR to `main` | Layer A tests + Docker build, secret check, health check |
| `evals-smoke.yml` | PRs touching prompts / agents / models / quality / evals | LLM smoke gate (blocks on confirmed regressions or any hallucination) |
| `deploy.yml` | push to `main` | Re-test, build image tagged with the commit SHA, deploy to Cloud Run, smoke test |
| `evals-full.yml` | manual | Full eval run |

- Hosted on **Google Cloud Run** (`asia-south1`), image in Artifact Registry.
- GitHub authenticates with **Workload Identity Federation** – no service-account JSON keys.
- One-time GCP setup: `bash deploy/gcp-setup.sh`.

Run the container locally:

```bash
docker build -t agentsville .
docker run -p 8080:8080 --env-file .env agentsville   # http://localhost:8080
```

## Prompt versions

Prompts live in `prompts/itinerary/v<N>.md` (`string.Template` with exactly `$schema`,
`$weather`, `$activities`) and are selected with `PROMPT_VERSION`.

- **v1 is live.** v2 and v3 were evaluated and rejected by the regression gate.
- v1 is sha256-pinned in `tests/test_prompts.py`, because eval cache keys hash the prompt.
- Once a version has been evaluated, add a new version instead of editing it.
- Accept a new baseline only on purpose (`--accept-baseline`), committed via PR.

## Business rules

The graders encode these rules:

- **Pricing:** an activity's `price` is a group price; `total_cost` is the sum of activity prices
  and must stay within the budget.
- **Weather:** no `outdoor` activity on a rainy or thunderstorm day. `flex` activities (with an
  indoor rain backup) are allowed. Activity settings come from the human-approved
  `quality/ground_truth/activity_labels.json`.

## Roadmap

- **Part B – The Resourceful Assistant:** a ReAct agent (THINK → ACT → OBSERVATION) that answers
  follow-up questions and change requests using tool calls against the simulated activities API.
- Calibrate the LLM judge against human labels (≥ 80% agreement) before it may gate.
- Move the custom eval harness onto an eval framework.

See `plan/00-master-plan.md` for the full phase plan and status.
