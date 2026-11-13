# Phase 5 – Layer B: Probabilistic Evals (overview)

Status: **Approved** – B0 detailed plan next (`01-b0-foundation.md`)

## Context

Layers A (deterministic tests) and CI/CD are live. Layer B is the core of the AI QA platform: it
measures whether Part A's **LLM output is acceptable**, not just whether the code runs. Instead of
building pieces at random, Layer B is delivered as **end-to-end scenario slices**. Each slice
answers one quality question, from golden data → graders → harness run → thresholds → CI →
production signal (Layer C).

The slices map onto four competencies:
- evaluation harnesses: hallucination rate, answer relevancy
- agentic / reasoning validation
- versioned golden datasets
- observability and feedback loops

### Decisions from the grilling round
| Topic | Decision |
|---|---|
| Scope | **Part A only.** Tool-use accuracy waits for the Part B extension. Reasoning verification and goal completion are evaluated on Part A's chain-of-thought (`ANALYSIS`) and its final plan |
| Budget | A full eval run uses **≤ ~50 LLM calls**; the smoke run about 3–5. Responses are cached so graders can be re-run for free |
| Ground truth | Rule-based expectations per case, plus a human-reviewed indoor/outdoor label for each activity. **You approve every case** |
| Datasets | Git JSONL + semver manifest (content hash, changelog). Production candidates arrive via BigQuery (Layer C) and are promoted after review |
| CI | Smoke eval on PRs that touch `agents/`, `prompts/` or `models.py`, blocking on hard-constraint regressions. Full run is manual (`workflow_dispatch`) |
| Feedback | 👍/👎 + optional comment in the live app, linked by `trace_id` |
| Judge | `gpt-4.1-mini` at temperature 0 with structured output, **calibrated against your labels**. Set via `JUDGE_MODEL`, so it can be swapped later |
| Online eval | Deterministic graders on **every** live run (free); no judge in production |

### Facts from the code and mock data that shape the design
- **`theatre` is never offered** by any activity, yet the sample traveler Hiro lists it. That makes
  it a natural hallucination trap.
- **06-13 and 06-14 are rainy with only one indoor activity each:**
  - 06-13: `event-2025-06-13-0`
  - 06-14: `event-2025-06-14-3`

  That gives a precise, deterministic expectation for weather safety. 06-12 (thunderstorm) has one
  indoor activity (`-12-3`) and one "moves indoors if it rains" activity (`-12-1`). The labels need
  three values: `indoor`, `outdoor`, `flex`.
- **Daily minimum price is 15,** so the cheapest valid plan for N days costs 15·N. Budget-edge
  cases can be exact.
- **`project_lib.do_chat_completion` returns only the text:** no token usage, no latency. Cost and
  latency metrics need a thin **instrumented client wrapper** (`llm.py`); `project_lib.py` stays
  untouched.
- **Existing building blocks to reuse:**
  - `PromptTrace` (`models.py`)
  - `ItineraryAgent.get_itinerary` / `last_trace` (`agents/itinerary.py`)
  - `call_activities_api_mocked`, `call_weather_api_mocked`, `ACTIVITY_CALENDAR`,
    `WEATHER_FORECAST` (`project_lib.py`)
  - `FakeOpenAIClient` (`tests/conftest.py`)
  - the `eval` marker (`pytest.ini`)
  - the CI workflows (`.github/workflows/`)
- **Known quality gap to fix with evidence:** the current prompt plans about 1 activity per day and
  underuses the budget. B4 turns this into an eval-driven prompt v2.

## Architecture (shared by offline evals and production)

```
quality/                      # imported by BOTH the app (online) and the eval harness (offline)
  schema.py                   # EvalCase, Expectations, GraderResult, EvalRecord (one record shape everywhere)
  graders/grounding.py        # B1 – hallucination
  graders/constraints.py      # B2 – hard constraints / goal completion
  graders/relevancy.py        # B3 – interest coverage, reason grounding (deterministic)
  graders/reasoning.py        # B3 – ANALYSIS structure + reasoning↔output consistency
  graders/judge.py            # B3 – LLM-as-judge (offline only)
  ground_truth/activity_labels.json   # human-reviewed indoor/outdoor/flex per activity
evals/
  datasets/itinerary_golden/v1.0.0.jsonl + manifest.json
  harness/runner.py           # cases × repeats × model × prompt version → EvalRecords
  harness/cache.py            # record/replay of raw LLM replies (free re-grading)
  harness/report.py           # Markdown/JSON summary, baseline comparison
  baselines/                  # accepted metric baselines per dataset version
  results/                    # gitignored run outputs
  test_evals.py               # pytest -m eval entry points (smoke / full)
prompts/itinerary/v1.md, v2.md  # versioned prompts, selected by PROMPT_VERSION (B4)
```

**Key design rule:** `EvalRecord` is the single record shape for both offline runs and production
logs. Layer C's log-based metrics, BigQuery table and dashboards therefore work for both without
translation.

## Scenario slices (execution order)

Each slice gets its own plan doc in `plan/05-layer-b-evals/` (review, then implement, per CLAUDE.md),
its own branch, and its own PR.

### B0 – Foundation: harness, golden dataset v1.0.0, record/replay
**Question:** can we run a repeatable experiment and get comparable numbers?
- **Schemas** (`quality/schema.py`):
  - `EvalCase` (id, scenario tags, `VacationInfo`, `Expectations`, review status)
  - `GraderResult` (name, passed, score, details)
  - `EvalRecord` (trace_id, case_id, dataset@version, prompt_version, model, repeat, latency,
    tokens, cost, grader results)
- **Instrumented client** in `llm.py`: measures latency and reads `response.usage`; values are added
  to `PromptTrace`.
- **Golden dataset v1.0.0**, 8 cases. I draft them; you approve each:

  | id | Trip | Targets |
  |---|---|---|
  | G1 | Yuri + Hiro, 06-10..12, budget 130 (current sample) | baseline |
  | G2 | 06-12..14 storm stretch | weather safety; expects `-13-0` and `-14-3` |
  | G3 | 06-10..11, budget **30** | exact budget edge (15 + 15) |
  | G4 | 1 traveler, 06-15 only, tennis | single day; expects `event-2025-06-15-3` |
  | G5 | traveler interested **only in theatre** | hallucination trap: nothing matches; must not invent |
  | G6 | 3 travelers, 06-10..15, budget 200 | scale and coverage |
  | G7 | hiking vs movies travelers, 06-12 thunderstorm | conflicting interests + weather |
  | G8 | 06-10..11, budget 500 | budget utilization / activities per day (soft) |
- **Harness:**
  - run modes: `smoke` (G1, G2, G5 × 1 repeat = 3 calls) and `full` (8 × 3 repeats = 24 planner
    calls + 8 judge calls ≈ 32, within budget)
  - **cache:** keyed by case, dataset version, prompt version, model and repeat
  - **report:** a Markdown table plus JSON
- **Concepts:** experiment design, record/replay, why repeats matter (non-determinism).

### B1 – Hallucination & grounding
**Question:** is everything in the plan real?
- **Graders** (deterministic, against `ACTIVITY_CALENDAR` / `WEATHER_FORECAST`):
  - each `activity_id` exists
  - its name, times, location, price and interests match exactly
  - each day's weather equals the forecast
  - days fall inside the trip, with no invented dates
- **Metrics:** hallucination rate (plans with ≥ 1 fabricated or mismatched field), plus a per-field
  breakdown. **Threshold: 0%.**
- **Key case:** G5 (theatre). Any "theatre" activity is a hallucination.
- **Production signal (→ Layer C):** runs on every live response; logs `grounding.passed` and
  `hallucinated_fields`.
- **Concepts:** grounded vs ungrounded generation; ground-truth lookups vs fuzzy matching.

### B2 – Constraint compliance & goal completion
**Question:** does the plan satisfy the traveler's hard constraints?
- **Graders:**
  - total ≤ budget, and `total_cost` = sum of prices
  - every trip day covered, with ≥ 1 activity per day
  - no overlapping times
  - **weather safety:** no `outdoor` activity on rainy or thunderstorm days, using the reviewed
    `activity_labels.json`; `flex` is allowed
- **Metrics:**
  - per-constraint pass rate
  - **task success rate:** all hard constraints pass, which is goal completion for Part A
  - **threshold:** 100% on approved cases (hard gate)
- **Human step:** you review the 24 indoor/outdoor/flex labels once. They become ground truth.
- **Production signal (→ Layer C):** `constraints.passed`, plus a list of violations per live run.

### B3 – Relevancy & reasoning verification
**Question:** is the plan relevant to these travelers, and is its step-by-step reasoning faithful
to the output?
- **Deterministic checks:**
  - interest coverage per traveler
  - reason grounding: each `reasons_for_recommendation` mentions an interest the activity really
    has
  - ANALYSIS structure: the 5 required steps are present
  - reasoning↔output consistency:
    - the budget total stated in ANALYSIS equals `total_cost`
    - the weather stated for each day matches the data
- **LLM judge** (`gpt-4.1-mini`, temperature 0, Pydantic `JudgeScore`):
  - `relevancy` 1–5 and `coherence` 1–5, each with a rubric
  - `reasoning_faithful` yes/no, with quoted evidence
  - **answer relevancy** = mean relevancy, normalized to 0–1
- **Calibration:**
  - you hand-score 8–10 outputs
  - we report judge-vs-human agreement (exact and ±1)
  - a judge metric is used as a gate only if agreement is ≥ 80%; otherwise it's report-only
  - same-family bias (the judge and the planner are both 4.1-mini) is documented and measured,
    not ignored
- **Production:** the deterministic coverage and consistency checks run online; the judge stays
  **offline only**.
- **Concepts:**
  - LLM-as-judge and why it needs rubrics and calibration
  - faithfulness vs plausibility
  - the explicit note that tool-use accuracy comes with Part B

### B4 – Consistency, regression gating & eval-driven improvement
**Question:** is quality stable across runs, and does a change actually improve it?
- **Consistency:**
  - pass^k (a case counts only if all k = 3 repeats pass)
  - the spread of scores across repeats
- **Prompt versioning:**
  - extract the current prompt to `prompts/itinerary/v1.md`; `PROMPT_VERSION` selects the version
  - write **v2** aimed at the known gap (more activities per day, better budget use, coverage of
    every traveler's interests)
  - compare v1 and v2 on the same dataset version; the report shows the deltas
- **Baselines:** `evals/baselines/itinerary_golden@1.0.0.json` stores accepted metrics. A run is
  compared to the baseline, and any regression on a hard metric fails.
- **CI:**
  - new `evals-smoke.yml`: PRs with path filters (`agents/**`, `prompts/**`, `models.py`,
    `quality/**`) run 3 calls with the API key from a GitHub secret, and block on regressions
  - `evals-full.yml`: manual (`workflow_dispatch`); uploads the report as an artifact
- **Model comparison** (`gpt-4.1` / `-mini` / `-nano`) is opt-in; it costs about 3× the default run.
- **Concepts:** regression testing for LLMs, baselines, the smoke vs full trade-off, eval-driven
  development.

### B5 – Production feedback loop & dataset lifecycle (the Layer B ↔ Layer C bridge)
**Question:** how does production traffic make the evals better?
- **Tracing:**
  - every live request gets a `trace_id` (UUID), carried on `PromptTrace` and `EvalRecord`
  - the app emits one structured JSON log line per run: online grader results, latency, tokens,
    cost, model, prompt_version, dataset of origin = `prod`
- **Feedback UI:** 👍/👎 plus an optional comment under the itinerary. It logs a `feedback` event
  with the same `trace_id`.
- **Candidate mining:**
  - `evals/harness/promote.py` queries BigQuery for runs with 👎 or failed online graders
  - it drafts `EvalCase` candidates (`review_status: draft`)
  - after your review, approved cases go into **dataset v1.1.0**, with a manifest changelog entry
- **Drift signals defined here** (Layer C alerts on them):
  - online pass rates vs the B4 baseline
  - share of 👎
  - shift in the input distribution: interests, budget, trip length
- **Concepts:** online vs offline evaluation, trace correlation, the data flywheel, dataset
  versioning across dev and prod.

## Contract with Layer C

| Layer B provides | Layer C uses it for | Needed before |
|---|---|---|
| `EvalRecord` schema (B0) | Log format, BigQuery table schema, dashboard fields | C1 |
| Instrumented latency, tokens and cost (B0) | Latency, token and cost metrics; daily cost alert | C1 |
| Online grounding + constraint graders (B1, B2) | Log-based metrics: hallucination rate, violation rate; alerts | C2 |
| Baselines (B4) | Drift thresholds (alert when online pass rate < baseline − margin) | C3 |
| Eval harness CLI (B0, B4) | Optional scheduled golden re-run (Cloud Run Job) for provider-side model drift | C3 (optional) |

| Layer C provides | Layer B uses it for | Needed by |
|---|---|---|
| **C1:** structured logging on Cloud Run + **log sink → BigQuery** | Querying production traces and feedback | **B5** |
| C2: log-based metrics, dashboard | Watching online grader rates | after B2 |
| C3: alert policies (drift, cost, errors) | Closing the loop on regressions in production | after B4 |

**Sequencing:**
```
B0 → B1 → B2 → B3 → B4 → [C1 logging + BigQuery sink] → B5 → C2 → C3
```
C1 is the only Layer C piece Layer B must wait for. It's small: a log sink and a dataset, no
dashboards.

## Metrics catalogue (initial thresholds; B4 makes them baselines)
| Metric | Type | Slice | Threshold |
|---|---|---|---|
| parse rate | hard | B0 | 100% |
| hallucination rate | hard | B1 | 0% |
| task success (all hard constraints) | hard | B2 | 100% on approved cases |
| weather safety | hard | B2 | 100% |
| interest coverage | soft | B3 | ≥ 80% of travelers covered |
| reasoning↔output consistency | soft | B3 | ≥ 90% |
| answer relevancy (judge) | soft | B3 | ≥ 0.75, gated only if calibrated |
| activities per day, budget utilization | soft | B4 | report; v2 must improve over v1 |
| pass^3 | soft | B4 | report; tracked over time |
| p95 latency, cost per run | ops | B0 → C | report; alerting in C |

## How each slice is delivered

For every slice B0–B5:
1. Write `plan/05-layer-b-evals/0N-<slice>.md` (detailed steps, files, tests). Review it.
2. Implement it on its own branch (e.g. `feature/layer-b-b1-hallucination`). Layer A tests
   cover the new graders with fixed fake outputs (no LLM).
3. Run the eval (smoke first, then full, within the ~50-call budget). Record the report.
4. Open a PR with the report summary; merge with your permission.

