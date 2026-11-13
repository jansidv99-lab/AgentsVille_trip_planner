# Master Plan – AgentsVille Trip Planner + AI Quality Assurance Platform

Status: **Draft – awaiting review**

## 1. Goal

The AgentsVille trip planner (Part A: the itinerary agent and its Streamlit UI) is built. The
project now grows into an **AI Quality Assurance Platform**: three layers of quality checks wrapped
around Part A.

| Layer | Question it answers | Weight |
|---|---|---|
| **A – Deterministic testing** | Does the software work? | minimal |
| **B – Probabilistic evals** | Is the AI producing acceptable outcomes? | **main focus** |
| **C – System metrics & drift monitoring** | Is it sustainable in production? | **main focus** |

Scope decisions:
- **Part A only.** Part B (the ReAct assistant) comes later.
- **Layer B starts as custom pytest-based evals** and moves to an eval framework later (backlog).
- **Layer C is Google Cloud native:** Cloud Logging, log-based metrics, Cloud Monitoring, alerting.

Each phase below gets its own detailed plan in its folder, reviewed before implementation.

## 2. Phases, order, and plan folders

| # | Phase | Status | Plan folder | Depends on |
|---|---|---|---|---|
| 0 | Repo sync + master plan | in review | `plan/00-master-plan.md` | — |
| 1 | Setup (env, deps, repo) | ✅ done | — | — |
| 2 | Part A itinerary agent | ✅ done (prompt tuning driven by Phase 5) | — | 1 |
| 3 | Streamlit UI + prompt inspector | ✅ done | `plan/03-ui/` | 2 |
| 4 | **Layer A** – deterministic tests (minimal) | next | `plan/04-layer-a-testing/` | 2, 3 |
| 5 | **Layer B** – probabilistic evals | | `plan/05-layer-b-evals/` | 4 |
| 6 | Deploy: Cloud Run + GitHub Actions CI/CD | | `plan/06-deploy/` | 4 |
| 7 | **Layer C** – metrics & drift (GCP native) | | `plan/07-layer-c-monitoring/` | 5, 6 |

**Why this order:**
- **Layer A before deploy:** CI needs it as the gate that must pass before anything ships.
- **Layer B before Layer C:** Layer C reuses Layer B's graders on live traffic, and its pass rates
  become the baseline that drift is measured against.
- **Deploy before Layer C:** Cloud Logging and Monitoring need the app running on Cloud Run.

```
Phase 4 Layer A ──▶ Phase 5 Layer B ──┐
       │                              ├──▶ Phase 7 Layer C
       └──────▶ Phase 6 Deploy + CI ──┘
```

## 3. Phase 4 – Layer A: deterministic testing (minimal)

**Purpose:** a fast safety net with no LLM calls and no cost. It runs in CI on every PR.

Most of these checks were already run by hand while building Phase 3. This phase turns them into a
`tests/` suite:
- **`models.py`:** the validation rules (empty name, no interests, departure before arrival).
- **`agents/itinerary.py`:**
  - `trip_dates`
  - `extract_json`
  - `build_system_prompt` includes only the chosen dates
  - `ItineraryAgent` with a fake OpenAI client: the trace is recorded, and bad JSON raises
    `ItineraryParseError`
- **`app.py`:** one Streamlit `AppTest` smoke test with a mocked agent, covering form → itinerary
  → inspector.

**Tooling:** `pytest` in `requirements-dev.txt`. The command is `pytest -m "not eval"`.

## 4. Phase 5 – Layer B: probabilistic evals (focus)

**Purpose:** measure whether itineraries are *good*, not just whether the code runs. The same prompt
gives different answers on different runs, so quality is a **pass rate over repeated runs** on a
fixed dataset, not a single pass/fail.

- **Golden dataset** (`evals/cases/*.json`, about 10 cases):
  - single and multiple travelers
  - tight vs loose budgets
  - storm and rain days (2025-06-12 to 06-14)
  - trips of 1 to 6 days
  - interests with few matching activities
- **Graders that need no LLM.** They compare against the mock data in `project_lib.py`:

  | Grader | Checks |
  |---|---|
  | Schema validity | The reply parses into `TravelPlan` (parse rate) |
  | No hallucination | Every `activity_id` exists, and its details match `ACTIVITY_CALENDAR` exactly |
  | Coverage | Every trip day has ≥ 1 activity; no overlapping times |
  | Budget | `total_cost` = sum of prices, and ≤ budget; budget utilization % |
  | Personalization | Each traveler's interests are covered by at least one activity |
  | Weather | No outdoor-only activity on days in `INCLIMATE_WEATHER_CONDITIONS` |

- **LLM-as-judge:** a stronger model than the planner returns structured output into a Pydantic
  score model. It does two jobs:
  - scores personalization, coherence, and the quality of the reasons, each 1–5 against a rubric
  - classifies each activity as indoor or outdoor, which the weather grader needs
- **Experiment matrix:** N repetitions per case × model (`gpt-4.1` / `-mini` / `-nano`) × prompt
  version (from the `PROMPT_VERSION` env var).
- **Outputs:**
  - results in JSONL, gitignored
  - a summary report with pass rates, mean judge scores, cost and latency per model/prompt
- **Thresholds**, for example: hard constraints ≥ 95% pass, judge mean ≥ 4. These become the
  **baseline** for Layer C drift alerts.
- **Command:** `pytest -m eval`. Run it manually or nightly, never on every PR, because it costs
  money.
- **Feedback loop:** use the report to tune the Part A prompt. Known issue: it plans about 1
  activity per day and underuses the budget.

## 5. Phase 6 – Deploy: Cloud Run + GitHub Actions

- **Container:**
  - a Dockerfile for the Streamlit app, with images stored in Artifact Registry
  - deployed to Cloud Run in region `asia-south1` (from `REGION` in `.env`)
  - `OPENAI_API_KEY` stored in Secret Manager, not in the image
- **GitHub Actions:**
  - Layer A runs on every PR
  - merging to `main` builds and deploys
  - GCP access uses Workload Identity Federation, so no service-account key is stored in GitHub
- **Docs:** record the region in `CLAUDE.md`.

## 6. Phase 7 – Layer C: system metrics & drift monitoring (focus, GCP native)

- **Structured logging:** one JSON log line per LLM run goes to stdout, and Cloud Run sends it to
  Cloud Logging automatically. Fields:
  - model, prompt version
  - latency, prompt/completion tokens, cost estimate
  - whether the reply parsed
  - online scores from the Layer B graders that need no LLM. They're cheap, so they run on every
    live response.
- **Log-based metrics** in Cloud Monitoring: latency distribution, tokens, cost, parse-failure rate,
  constraint-violation rate. Cloud Run's built-in metrics add requests, errors, instances and
  memory.
- **Dashboard and alerting policies:** p95 latency, error rate, daily cost, spikes in violation
  rate.
- **Drift detection:**

  | Drift type | Signal | How |
  |---|---|---|
  | Output drift | Online grader scores trending down | Log-based metrics + alert |
  | Input drift | Users' interests, budgets, and trip lengths shifting from the baseline | Log sink → BigQuery queries |
  | Model / prompt drift | Golden-set scores falling below the Phase 5 baseline | Cloud Scheduler → nightly Cloud Run Job re-runs the Layer B evals and logs scores as metrics |

## 7. Backlog / to-do

- [ ] Move Layer B from custom pytest evals to an eval framework (e.g. DeepEval or promptfoo)
- [ ] Part B: the ReAct travel assistant, plus its own evals
- [ ] Delete the old misnamed private GitHub repo (needs `gh auth refresh -s delete_repo`)
- [ ] Optional: turn on GitHub's "automatically delete head branches"
