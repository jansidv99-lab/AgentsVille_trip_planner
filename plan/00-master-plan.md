# Master Plan – AgentsVille Trip Planner + AI Quality Assurance Platform

Status: **Approved** – Phases 3, 4, 6 done; Layer B (Phase 5) in progress

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
| 0 | Repo sync + master plan | ✅ done | `plan/00-master-plan.md` | — |
| 1 | Setup (env, deps, repo) | ✅ done | — | — |
| 2 | Part A itinerary agent | ✅ done (prompt tuning driven by Phase 5) | — | 1 |
| 3 | Streamlit UI + prompt inspector | ✅ done | `plan/03-ui/` | 2 |
| 4 | **Layer A** – deterministic tests (minimal) | ✅ done (26 tests) | `plan/04-layer-a-testing/` | 2, 3 |
| 6 | Deploy: Cloud Run + GitHub Actions CI/CD | ✅ done (live) | `plan/06-deploy/` | 4 |
| 5 | **Layer B** – probabilistic evals (slices B0–B5) | in progress | `plan/05-layer-b-evals/` | 4 |
| 7 | **Layer C** – metrics & drift (GCP native, C1–C3) | C1 before B5 | `plan/07-layer-c-monitoring/` | 5, 6 |

Execution order: **4 → 6 → 5 → 7**. The phase numbers are IDs, not the run order.

**Why this order:**
- **Layer A before CI/CD:** CI needs Layer A as the gate that must pass before anything ships.
- **CI/CD before Layer B:** the pipeline only needs Layer A. Deploying early gives Layers B and C a
  real environment to work against.
- **Layer B before Layer C:** Layer C reuses Layer B's graders on live traffic, and its pass rates
  become the baseline that drift is measured against.

```
Phase 4 Layer A ──▶ Phase 6 CI/CD + Deploy ──▶ Phase 5 Layer B ──▶ Phase 7 Layer C
```

Layers B and C interleave at one point: Layer B's last slice (B5, the production feedback loop)
needs Layer C's first slice (C1, structured logging + BigQuery sink):
```
B0 → B1 → B2 → B3 → B4 → C1 → B5 → C2 → C3
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

**Detailed plan: `plan/05-layer-b-evals/00-layer-b-overview.md`.**

Layer B is delivered as **end-to-end scenario slices**. Each slice answers one quality question,
from golden data → graders → harness → thresholds → CI → production signal:

| Slice | Question | Key metric |
|---|---|---|
| B0 – Foundation | Can we run a repeatable experiment? | parse rate; latency, tokens, cost |
| B1 – Hallucination & grounding | Is everything in the plan real? | hallucination rate (0%) |
| B2 – Constraints & goal completion | Are the hard constraints met? | task success rate (100%) |
| B3 – Relevancy & reasoning verification | Is it relevant, and is the reasoning faithful? | interest coverage, answer relevancy (judge), consistency |
| B4 – Consistency & regression gating | Is quality stable, and does a change improve it? | pass^3, v1 vs v2 prompt deltas |
| B5 – Production feedback loop | How does production improve the evals? | 👎 share, online pass rates, promoted cases |

Key decisions:
- Part A only. Tool-use accuracy evals come with the Part B extension.
- Each full run stays within about 50 LLM calls.
- Rule-based ground truth, approved by you.
- Golden datasets versioned in git with a semver manifest.
- `gpt-4.1-mini` judge, calibrated against human labels.
- Smoke evals run on PRs that change prompts or the agent; full runs are manual.
- 👍/👎 feedback in the app.
- Deterministic graders run online on every live request.

## 5. Phase 6 – Deploy: Cloud Run + GitHub Actions

Detailed plan: `plan/06-deploy/01-ci-cd-plan.md`.

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

Split into three slices to match the contract in the Layer B overview:
- **C1 – structured logging + BigQuery sink:** needed by B5.
- **C2 – log-based metrics + dashboard.**
- **C3 – alert policies:** drift against the B4 baselines, cost, errors.

All three reuse Layer B's `EvalRecord` schema and its deterministic graders.

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

- [ ] **Validate-and-repair guardrail (proposed after B4):** after the model replies, code computes the real
  total and runs the hard graders. On a violation, one repair turn lists the exact problems to the model, then
  the result is re-graded. Targets the arithmetic and budget slips that sank v2 and v3. Needs its own plan.
- [ ] **B3 calibration (human labels):** label the 10 items in `evals/calibration/b3_labeling_sheet.md`
  (reply `n: relevancy honest faithful`, e.g. `1: 4 y y`). Then run the agreement report. Until then, all
  LLM-judge metrics are **report-only** and may not gate anything (trust rule: ≥ 80% agreement).
- [ ] Move Layer B from custom pytest evals to an eval framework (e.g. DeepEval or promptfoo)
- [ ] Part B: the ReAct travel assistant, plus its own evals. This adds **tool-use accuracy**
  (right tool, right arguments) and trajectory checks on top of Layer B's B3 reasoning checks
- [ ] Delete the old misnamed private GitHub repo (needs `gh auth refresh -s delete_repo`)
- [ ] Optional: turn on GitHub's "automatically delete head branches"
- [ ] Apply branch protection on `main` (rules approved in `plan/06-deploy/01-ci-cd-plan.md` §4.5)
- [ ] Set the `MODEL` repo variable to a supported model (currently `gpt-4o-mini`, so the app falls back to `gpt-4.1-mini`)
