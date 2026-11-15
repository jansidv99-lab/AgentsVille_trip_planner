# AgentsVille Trip Planner – System Blueprint (template)

> **How to reuse:** keep the 4 headings and the table columns; replace the rows with your project's components.
> Legend: 🧱 build-time · ⚙️ runtime · 🧪 test/eval · ☁️ cloud · 👤 human decision

## 1. Component inventory

| # | Layer | Component | Location | Purpose | Kind |
|---|---|---|---|---|---|
| C01 | Config | Environment & secrets | `.env` / `.env.example`, GitHub vars/secrets, Secret Manager | API key, base URL, `MODEL`, `PROMPT_VERSION`, GCP ids | ⚙️ |
| C02 | Data (course) | Mock APIs + helpers | `project_lib.py` | `Interest` enum, `ChatAgent`, mocked weather + activities (2025-06-10…15) | ⚙️ |
| C03 | Data model | Pydantic models | `models.py` | `VacationInfo` (input), `TravelPlan` (output), `PromptTrace` | ⚙️ |
| C04 | LLM access | Instrumented client | `llm.py` | OpenAI-compatible client; latency, tokens, cost | ⚙️ |
| C05 | Prompts | Versioned templates | `prompts/itinerary/v1..v3.md`, `agents/prompts.py` | `$schema/$weather/$activities` template; selected by `PROMPT_VERSION` (v1 live, sha-pinned) | ⚙️ |
| C06 | Agent | Itinerary agent (Part A) | `agents/itinerary.py` | Builds the prompt from the dates, calls the LLM, parses to `TravelPlan`, records `PromptTrace` | ⚙️ |
| C07 | Agent | ReAct assistant (Part B) | *planned* | THINK → ACT (tool) → OBSERVATION loop for follow-ups | ⚙️ |
| C08 | UI | Streamlit app | `app.py`, `ui/render.py` | Form (name, city, interests, model), results, prompt inspector, Quality tab, 👍/👎 feedback | ⚙️ |
| C09 | CLI | Demo | `planner.py` | One Part A call from the terminal | ⚙️ |
| C10 | Quality | Ground truth | `quality/ground_truth/activity_labels.json`, `quality/labels.py`, `quality/pricing.py` | Approved indoor/outdoor/flex labels; pricing rule | ⚙️ |
| C11 | Quality | Record schema | `quality/schema.py` | `EvalCase`, `EvalRecord`, `GraderResult` (one shape for offline and prod) | ⚙️🧪 |
| C12 | Quality | Graders B0–B3 | `quality/graders/` (`parse`, `grounding`, `constraints`, `relevancy`, `reasoning`) | Deterministic hard/soft/info checks; `task_succeeded()` | ⚙️🧪 |
| C13 | Quality | LLM judge | `quality/graders/judge.py` | Offline-only soft scores; report-only until ≥ 80% calibrated | 🧪 |
| C14 | Tests | Layer A suite | `tests/` + `conftest.py`, `pytest.ini` | Deterministic tests with a fake LLM; mutation tests per grader; Docker/monitoring contracts | 🧪 |
| C15 | Evals | Golden dataset | `evals/datasets/itinerary_golden/` (`v1.0.0.jsonl`, `manifest.json`) | G1–G8 cases, smoke = G1/G2/G5, versioned + approved | 🧪👤 |
| C16 | Evals | Harness | `evals/harness/` (`runner`, `dataset`, `cache`, `report`) | Run cases × repeats, cache replies, grade, write a report | 🧪 |
| C17 | Evals | Baselines + gate | `evals/harness/baseline.py`, `gate.py`, `evals/baselines/*.json` | Accepted snapshots; regression compare; CI gate with a confirm run | 🧪👤 |
| C18 | Evals | Calibration | `evals/harness/calibration.py`, `evals/calibration/` | Judge vs blind human labels | 🧪👤 |
| C19 | Evals | Promote loop | `evals/harness/promote.py` | Prod (BigQuery) → candidates → approved golden cases | 🧪👤 |
| C20 | Observability | Structured events | `observability/events.py` | `llm_run`, `llm_error`, `feedback` JSON lines to stdout | ⚙️ |
| C21 | Observability | BigQuery views | `observability/bigquery/*.sql`, `deploy/observability-setup.sh` | Log sink → dataset `agentsville_observability` → views | ☁️ |
| C22 | Monitoring | Metrics, dashboard, alerts | `deploy/monitoring/` (+ `monitoring-setup.sh`) | 10 log metrics, dashboard, 8 alerts (A1–A7, A9) with runbooks | ☁️ |
| C23 | Packaging | Container | `Dockerfile`, `.dockerignore` | Image with every runtime folder, import check, no `.env` | 🧱 |
| C24 | CI/CD | Workflows | `.github/workflows/ci.yml`, `evals-smoke.yml`, `evals-full.yml`, `deploy.yml` | PR checks, eval gate, manual full eval, deploy to Cloud Run | 🧱☁️ |
| C25 | Cloud | GCP runtime | Cloud Run `agentsville-trip-planner` (asia-south1), Artifact Registry, WIF, `deploy/gcp-setup.sh` | Hosting, keyless auth | ☁️ |
| C26 | Docs | Plans & runbooks | `plan/00…07`, `plan/07-layer-c-monitoring/runbook.md`, `CLAUDE.md`, `README.md` | Decisions, phase plans, operations | 👤 |

## 2. Flows

### 2a. Runtime flow (one user request)
```
User ─▶ C08 Streamlit form ─▶ C03 VacationInfo (validated)
   ─▶ C06 ItineraryAgent ── reads C05 prompt (PROMPT_VERSION) + C02 weather/activities
   ─▶ C04 LLM client ─▶ OpenAI-compatible endpoint (C01)
   ◀─ raw reply ─▶ C03 TravelPlan (parse) + PromptTrace
   ─▶ C12 graders (GradingInput.for_request) ─▶ C08 results + Quality tab
   ─▶ C20 llm_run event ─▶ Cloud Logging ─▶ C21 BigQuery ─▶ C22 dashboard/alerts
User 👍/👎 ─▶ C20 feedback event ─▶ same pipeline
```

### 2b. Change lifecycle (from creation to production and back)
| Step | What happens | Components | Gate / owner |
|---|---|---|---|
| 1 Plan | Write `plan/<stage>/<nn>-<topic>.md` | C26 | 👤 review |
| 2 Branch | `git switch main && git pull` → `feature/…` / `fix/…` / `chore/…` / `docs/…` | — | clean `git status` |
| 3 Build | Code with `# Phase X – Step Y` comments; a new prompt goes in a **new** `vN.md` | C02–C13, C20 | 👤 permission |
| 4 Unit test (Layer A) | `pytest` (~2 s, fake LLM); grader mutation tests; Docker/monitoring contracts | C14 | 100% pass |
| 5 Eval (Layer B) | `runner --mode smoke` → `--mode full --prompt-version vN --compare-to v1` (≤ 50 calls); `--judge` optional | C15–C18 | no regression, 0 hallucination |
| 6 Commit + PR | Descriptive PR | C24 `ci.yml` (Layer A + Docker), `evals-smoke.yml` (gate) | 👤 permission; checks green |
| 7 Merge | Into `main` | — | 👤 permission |
| 8 Deploy | `deploy.yml`: Layer A again → image `:<sha>` → Cloud Run → health check | C23–C25 | auto |
| 9 Adopt prompt | `--accept-baseline` via PR; switch `PROMPT_VERSION` | C17, C01 | 👤 decision |
| 10 Monitor | Online graders → events → BigQuery → dashboard/alerts | C12, C20–C22 | alerts A1–A9 |
| 11 Learn | `promote mine` → review → `promote approve` → dataset v1.x → new baseline | C19, C15, C17 | 👤 approval |
| 12 Roll back (if needed) | Cloud Run traffic to the previous revision; `git revert -m 1 <merge>` via PR | C25, C24 | 👤 |

### 2c. Build history (how the project evolved)
Setup (C01–C04) → Part A agent + prompt (C05–C06) → UI (C08) → Layer A tests (C14) → CI/CD + Cloud Run (C23–C25) → Layer B: B0 parse/harness → B1 hallucination → B2 constraints → B3 relevancy/judge/calibration → B4 prompt versions, baselines, gate → C1 events/BigQuery → B5 feedback/promote → C2 metrics/dashboard → C3 alerts/runbook → *next:* enforce the gate, Part B ReAct (C07).

## 3. Checklists

### 3a. Before writing code
- [ ] Plan doc written under the right `plan/` stage and reviewed
- [ ] Synced with `main`; branch named `<type>/<topic>`
- [ ] Business rules affected? (group pricing, whole-day weather policy) → stated explicitly in prompt/graders

### 3b. Before opening a PR
- [ ] Phase/step comment on new files, functions and classes
- [ ] `pytest` green; new grader → mutation test asserting **only** it fails
- [ ] New runtime folder → `Dockerfile` COPY + `.dockerignore` `!` (enforced by `test_docker_image.py`)
- [ ] New/renamed event field → metrics updated (`test_monitoring_config.py`); BigQuery-stable fields
- [ ] Prompt change → new `vN.md` (never edit an evaluated version); `$schema/$weather/$activities` only
- [ ] Smoke eval run locally; full eval with `--compare-to v1` for prompt/agent changes (≤ 50 calls)
- [ ] Hallucination = 0; no new hard per-case failures
- [ ] Dataset edited → version bump + manifest + changelog; only 👤-approved cases
- [ ] No secrets, no real traveler names committed; `.env` untouched

### 3c. Before merge / deploy
- [ ] CI green: Layer A tests, Docker build, Smoke eval gate (when triggered)
- [ ] 👤 permission for commit, PR, merge
- [ ] Baseline change only on purpose (`--accept-baseline` in the PR)
- [ ] `PROMPT_VERSION` change decided by 👤 after a full eval

### 3d. After deploy
- [ ] Deploy job: health check green, URL in the job summary
- [ ] Dashboard "AgentsVille – AI quality & ops": task success, hallucination, latency, errors normal
- [ ] No alerts fired (A1 hallucination, A2 drift, A3 weather, A4 errors, A5 latency, A6 feedback, A7 cost, A9 5xx)
- [ ] Weekly: `promote mine --days 7` → review candidates
- [ ] Post-merge cleanup: `git switch main && git pull && git branch -d <branch>`

### 3e. Known gaps (open items)
- [ ] Branch protection on `main` + required smoke gate (currently advisory)
- [ ] Shipped prompt version committed in the repo (currently a repo variable outside the gate)
- [ ] v1 weather-safety weakness (G2/G6/G7) → guardrail or new prompt
- [ ] Judge calibration ≥ 80% before any judge metric gates
- [ ] Part B ReAct assistant (C07)

## 4. Dependencies and usage

### 4a. Dependency map (arrow = "depends on / uses")
```
C08 UI ─────▶ C06 Agent ─▶ C05 Prompts ─▶ C03 Models
  │             │  └──────▶ C04 LLM ─▶ C01 Env
  │             └─────────▶ C02 Mock data
  ├──────────▶ C12 Graders ─▶ C11 Schema, C10 Ground truth, C02, C03
  └──────────▶ C20 Events ─▶ C12 (task_succeeded)
C16 Harness ─▶ C06, C12, C13, C15, cache        C17 Gate/Baseline ─▶ C16, baselines
C19 Promote ─▶ C21 BigQuery ─▶ C20              C22 Monitoring ─▶ C20 event fields
C14 Tests ──▶ everything (fake LLM)             C24 CI/CD ─▶ C14, C17, C23 ─▶ C25
```

### 4b. Dependency table
| Component | Depends on | Used by | Breaks if… |
|---|---|---|---|
| C03 Models | pydantic | C06, C08, C11, C12, C20 | a field is renamed → parse fails, graders/events break |
| C05 Prompts | C03 schema, C02 data | C06, C16 (cache key = prompt hash) | v1 edited → sha pin test fails; cache invalid |
| C06 Agent | C04, C05, C02, C03 | C08, C09, C16 | — |
| C10 Ground truth | 👤 approval | C12 `weather_safety`, relevancy | labels wrong → false pass/fail |
| C12 Graders | C10, C11, C02, C03 | C08 (online), C16 (offline), C20 | non-deterministic → can't run online |
| C15 Dataset | C11 `EvalCase`, 👤 approval | C16, C17 | edited without a version bump → manifest test fails |
| C17 Baselines | C16 output, dataset@version + model + prompt + mode | C24 smoke gate | missing baseline → gate exit 2 |
| C20 Events | C12, C03 | C21, C22, C19 | field renamed → metrics/views silently empty (contract test) |
| C22 Monitoring | C20 fields, C21 | 👤 on-call | metric references an undefined field → contract test fails |
| C23 Docker | all runtime folders | C24, C25 | folder missing → import check fails |
| C24 CI/CD | C14, C17, C23, GitHub secrets/vars, WIF | C25 | secret/var missing → eval or deploy job fails |

## 5. Golden cases, graders and evaluation metrics

> Sources: `evals/datasets/itinerary_golden/v1.0.0.jsonl` (8 cases, all 👤-approved on 2026-11-13), graders in `quality/graders/`, metrics in `evals/harness/report.py` + `baseline.py`. Numbers come from the accepted **v1 full baseline** (`evals/baselines/itinerary_golden@1.0.0__gpt-4.1-mini__v1__full.json`, 8 cases × 3 repeats).

### 5a. Golden cases G1–G8

| Case | Smoke | Trip (travelers · dates · budget) | Scenario under test | Expectations stored in the case | Focus graders ★ |
|---|---|---|---|---|---|
| **G1** | ✅ | Yuri + Hiro · 06-10→06-12 · 130 | Regression anchor (the original sample trip); 06-12 thunderstorm | max_cost 130; 06-12 safe ids `-12-1`, `-12-3`; uncoverable: theatre | all hard graders, `weather_safety` |
| **G2** | ✅ | Mara (hiking, gardening, dancing) · 06-12→06-14 · 100 | Weather safety: storm + 2 rainy days; her favourite interests are only offered outdoors | max_cost 100; safe ids per day (`-12-1/-12-3`, `-13-0`, `-14-3`) | `weather_safety` |
| **G3** | | Ana (art, music) · 06-10→06-11 · 30 | Exact budget edge: the only valid plan costs 15 + 15 | max_cost 30 | `budget_within_limit`, `cost_arithmetic`, `day_coverage` |
| **G4** | | Leo (tennis) · 06-15 · 50 | Single day, one obvious best match | max_cost 50; must include `event-2025-06-15-3` | `must_include`, `interest_coverage` |
| **G5** | ✅ | Kai (theatre) · 06-10→06-11 · 60 | Hallucination trap: no activity offers theatre | max_cost 60; uncoverable: theatre | B1 grounding, `reason_grounding`, `uncoverable_interest_mentions` |
| **G6** | | Yuri + Hiro + Sam · 06-10→06-15 · 200 | Scale: 6 days, 3 travelers, mixed weather | max_cost 200; safe ids for 06-12/13/14; uncoverable: theatre | all, especially `weather_safety`, `no_time_overlaps`, `cost_arithmetic` |
| **G7** | | Rin (hiking) + Tom (movies) · 06-12 · 40 | Conflicting interests in a thunderstorm | max_cost 40; safe ids `-12-1/-12-3`; uncoverable: hiking | `weather_safety`, `interest_coverage` |
| **G8** | | Yuri + Hiro · 06-10→06-11 · 500 | Generous budget: does the planner use it? | max_cost 500; uncoverable: theatre | `plan_shape` (activities/day, utilization) |

Every case uses `min_activities_per_day = 1`. The `allowed_activity_ids_by_date` lists are **documentation for reviewers**. `weather_safety` itself decides using the approved labels in `quality/ground_truth/activity_labels.json` plus the forecast, so it behaves the same way in production.

### 5b. Grader catalog (what each grader checks and which metric it feeds)

**Grader categories**

| Category | Question it answers | Slice | Code |
|---|---|---|---|
| **Format** | Is the reply machine-readable? | B0 | `quality/graders/parse.py` |
| **Grounding (hallucination)** | Are all facts real and copied correctly? | B1 | `quality/graders/grounding.py` |
| **Constraints (business rules)** | Does the plan obey budget, cost, coverage, time and weather rules? | B2 | `quality/graders/constraints.py` |
| **Relevancy** | Does the plan fit the travelers' interests? | B3 | `quality/graders/relevancy.py` |
| **Reasoning** | Is the ANALYSIS well formed and does it explain every choice? | B3 | `quality/graders/reasoning.py` |
| **LLM judge** | How good is the plan, as judged by a second model? (offline only) | B3 | `quality/graders/judge.py` |

Each grader also has a **type**: *deterministic* (pure Python, same input → same verdict, safe to run online in prod) or *model-based* (LLM judge, costs calls, offline only).

| Grader | Category | Type | Slice | Severity | Checks | Feeds metric(s) |
|---|---|---|---|---|---|---|
| `parse` | Format | deterministic | B0 | hard | The reply parses into a `TravelPlan` | parse pass rate, task success |
| `activity_exists` | Grounding | deterministic | B1 | hard | Every activity id exists in the mocked API | hallucination rate, task success |
| `activity_details_match` | Grounding | deterministic | B1 | hard | Name, price, time etc. equal the API record | hallucination rate, task success |
| `activity_on_its_date` | Grounding | deterministic | B1 | hard | The activity is scheduled on the date it really happens | hallucination rate, task success |
| `weather_matches_forecast` | Grounding | deterministic | B1 | hard | The stated weather equals the forecast | hallucination rate, task success |
| `plan_matches_request` | Grounding | deterministic | B1 | hard | Travelers, destination, dates and budget are copied correctly | hallucination rate, task success |
| `description_verbatim` | Grounding | deterministic | B1 | soft | The description is copied word for word | report only |
| `uncoverable_interest_mentions` | Grounding | deterministic | B1 | info | Reasons that mention an interest no activity offers | report only (count) |
| `budget_within_limit` | Constraints | deterministic | B2 | hard | Real spend ≤ max_cost (the budget) | task success |
| `cost_arithmetic` | Constraints | deterministic | B2 | hard | `total_cost` = sum of activity prices (group price) | task success |
| `day_coverage` | Constraints | deterministic | B2 | hard | Every trip day has ≥ 1 activity | task success |
| `no_time_overlaps` | Constraints | deterministic | B2 | hard | No overlapping activities on a day | task success |
| `weather_safety` | Constraints | deterministic | B2 | hard | No `outdoor` activity on a rainy or thunderstorm day (`flex` allowed) | task success, weather-violation count |
| `plan_shape` | Constraints | deterministic | B2 | info | Activities per day, budget utilization | report only |
| `interest_coverage` | Relevancy | deterministic | B3 | soft | Share of coverable interests that are served | report only (mean coverage) |
| `must_include` | Relevancy | deterministic | B3 | soft | Required activity ids are present | report only |
| `reason_grounding` | Relevancy | deterministic (keyword heuristic) | B3 | soft | Reasons don't claim interests the activity lacks | report only |
| `analysis_structure` | Reasoning | deterministic | B3 | soft | The ANALYSIS section is well formed | report only |
| `reasoning_covers_choices` | Reasoning | deterministic | B3 | soft | Every final activity is discussed in the ANALYSIS | report only |
| `judge_relevancy`, `judge_coherence`, `judge_reasons_honest`, `judge_reasoning_faithful` | LLM judge | model-based | B3 | soft | Second model scores relevancy/coherence (1–5) and honesty/faithfulness (yes/no) (offline only, `--judge`) | report only until ≥ 80% calibrated |

### 5c. Which graders apply to which case

All deterministic graders **run on every case**: offline through `GradingInput.for_case`, in production through `for_request`. A grader returns *not applicable* (shown as –, and excluded from its pass rate) when the case gives it nothing to check.

Legend: ● gives a verdict (pass/fail) · ★ the case was designed to stress this grader · ○ info only (no pass/fail) · – not applicable

| Grader | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 |
|---|---|---|---|---|---|---|---|---|
| `parse` | ★ | ● | ● | ● | ● | ● | ● | ● |
| B1 hard grounding (5 graders) | ● | ● | ● | ● | ★ | ● | ● | ● |
| `description_verbatim` | ● | ● | ● | ● | ● | ● | ● | ● |
| `uncoverable_interest_mentions` | ○ | – | – | – | ★○ | ○ | ○ | ○ |
| `budget_within_limit` | ● | ● | ★ | ● | ● | ● | ● | ● |
| `cost_arithmetic` | ● | ● | ★ | ● | ● | ★ | ● | ● |
| `day_coverage` | ● | ● | ★ | ● | ● | ★ | ● | ● |
| `no_time_overlaps` | ● | ● | ● | ● | ● | ★ | ● | ● |
| `weather_safety` | ★ | ★ | ● | ● | ● | ★ | ★ | ● |
| `plan_shape` | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ★○ |
| `interest_coverage` | ● | ● | ● | ★ | – (only theatre) | ● | ★ | ● |
| `must_include` | – | – | – | ★ | – | – | – | – |
| `reason_grounding` | ● | ● | ● | ● | ★ | ● | ● | ● |
| `analysis_structure`, `reasoning_covers_choices` | ● | ● | ● | ● | ● | ● | ● | ● |
| LLM judge (offline, optional) | ● | ● | ● | ● | ● | ● | ● | ● |

### 5d. Evaluation metrics

| Metric | Formula | Target | Gates? |
|---|---|---|---|
| **Task success rate** | runs with parse ✔ + no hallucination + every hard B2 constraint ✔, ÷ all runs (`task_succeeded`) | ≥ baseline (goal 100%) | ✅ |
| **Hallucination rate** | parsed runs where any hard B1 grader fails ÷ parsed runs | **0%** always | ✅ (any value > 0 fails) |
| **Pass rate per hard grader** | passed ÷ runs with a verdict (N/A excluded) | ≥ baseline | ✅ |
| **New per-case hard failure** | a hard grader fails on a case where it never failed in the baseline (confirmed by a re-run in CI) | none | ✅ |
| Pass rate per soft grader | same formula | — | ❌ report only |
| pass^k / pass@k | per case: all k repeats succeed / at least one succeeds; flaky = pass@k but not pass^k | — | ❌ report only |
| Interest coverage (mean) | mean share of coverable interests served | — | ❌ |
| Plan shape | activities per day; budget utilization = spend ÷ budget | — | ❌ (target of G8 / prompt v2) |
| Latency mean/p95, tokens, cost | from `InstrumentedClient` | a full run stays within ~50 calls | ❌ (alerts A5/A7 in prod) |
| Judge metrics | relevancy/coherence ≥ 4; honest/faithful = true | needs ≥ 80% human agreement first | ❌ until calibrated |

### 5e. Current v1 results per case (full baseline, 3 repeats each)

| Case | Task success | Reliable (pass^3) | Hard failures seen |
|---|---|---|---|
| G1 | 33% | ❌ (flaky) | `parse`, `cost_arithmetic` |
| G2 | 0% | ❌ | `weather_safety` |
| G3 | 100% | ✅ | — |
| G4 | 100% | ✅ | — |
| G5 | 100% | ✅ | — |
| G6 | 33% | ❌ (flaky) | `cost_arithmetic`, `weather_safety` |
| G7 | 0% | ❌ | `weather_safety` |
| G8 | 100% | ✅ | — |
| **Overall** | **58.3%** | pass^3 50% · pass@3 75% | hallucination **0%**; weather_safety 65%, cost_arithmetic 91%, parse 96% |

Smoke baseline (G1, G2, G5 × 1): task success 66.7%, hallucination 0%, and only G2 fails (`weather_safety`). **The main v1 weakness is weather safety (G2, G6, G7).**

### 5f. Metrics explained with examples

All examples use the v1 full baseline: 8 cases × 3 repeats = **24 runs**.

**Two terms used throughout**
- **Run** = one LLM reply for one case (e.g. G1 repeat #2). A full eval has 24 runs; smoke has 3.
- **Verdict** = a grader's result for one run: ✔ pass, ✘ fail, or **N/A** (nothing to check). **N/A results are left out of the count.**

#### 1. Task success rate (gates)
**Question:** "Is this itinerary actually usable?" A run succeeds only if **all** of these are true: (1) it parsed into a `TravelPlan`, (2) no hard B1 grader failed (no hallucination), (3) every hard B2 constraint passed (budget, cost sum, every day covered, no overlaps, weather safe).

```
task success rate = successful runs ÷ all runs
```

Example: one G2 run

| Check | Result |
|---|---|
| parse | ✔ |
| all 5 grounding checks | ✔ |
| budget 45 ≤ 100 | ✔ |
| total_cost = sum of prices | ✔ |
| every day has an activity | ✔ |
| no overlaps | ✔ |
| weather_safety: outdoor `event-2025-06-12-0` on the thunderstorm day | **✘** |

One failure is enough to fail the whole run, so this run is **not** a success. That's intentional: a plan that sends a traveler outdoors in a storm is unusable.

Full baseline calculation:

| Case | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 |
|---|---|---|---|---|---|---|---|---|
| successful runs out of 3 | 1 | 0 | 3 | 3 | 3 | 1 | 0 | 3 |

1 + 0 + 3 + 3 + 3 + 1 + 0 + 3 = **14**, so 14 ÷ 24 = **58.3%**

#### 2. Hallucination rate (gates; must be 0%)
**Question:** "Did the model make up or change any fact?"

```
hallucination rate = parsed runs where ANY hard B1 grader failed ÷ parsed runs
```

Only **parsed** runs count, because a reply that didn't parse has no plan to inspect.

Examples that would count as a hallucination:

| What the model wrote | Real data | Grader that fails |
|---|---|---|
| `event-2025-06-10-9` | that id doesn't exist | `activity_exists` |
| price 20 | API says 25 | `activity_details_match` |
| a 06-11 event placed on 06-10 | wrong date | `activity_on_its_date` |
| "sunny" on 06-12 | forecast: thunderstorm | `weather_matches_forecast` |
| budget 150 | user entered 130 | `plan_matches_request` |
| G5: "Shakespeare Night" (theatre) | no such event | `activity_exists` |

- **Full baseline:** 23 parsed runs (one G1 run didn't parse), 0 with a hallucination → 0 ÷ 23 = **0%**.
- **Gate rule:** a single hallucinated run, e.g. 1 ÷ 23 = 4.3%, fails the gate, even if the baseline also had one.
- **Not a hallucination:** in G5 the model wrote "close to theatre interest" about an art event. The event is real and its details are correct, so the B1 hard checks pass. The wording is flagged by `reason_grounding`, which is soft and report-only.

#### 3. Pass rate per grader (gates for hard graders)
**Question:** "How often does this one check pass?" It shows **which rule** is causing failures.

```
pass rate = runs that passed ÷ runs with a verdict (N/A excluded)
```

| Grader | Calculation | Pass rate | Why |
|---|---|---|---|
| `parse` | 23 ÷ **24** | 95.8% | one G1 reply wasn't valid JSON |
| `cost_arithmetic` | 21 ÷ **23** | 91.3% | the unparsed run is N/A; G1 and G6 each had a total ≠ sum of prices once |
| `weather_safety` | 15 ÷ 23 | 65.2% | G2 ×3, G7 ×3 and G6 ×2 put outdoor activities on bad-weather days |
| `must_include` | 3 ÷ **3** | 100% | only G4 has a must-include expectation; the other 21 runs are N/A |

The divisor changes from row to row. Excluding N/A results stops `must_include` from looking like 3 ÷ 24 = 12.5% just because most cases don't test it. Task success shows **that** runs failed; per-grader pass rates show **why**. Here, `weather_safety` at 65% is clearly the main problem in v1.

#### 4. New per-case hard failure (gates)
**Question:** "Did a case start failing a rule it used to pass?" Averages can hide changes. Imagine a new prompt v4:

| | Baseline v1 | v4 |
|---|---|---|
| G2 weather_safety | ✘ | ✔ (fixed) |
| G3 budget_within_limit | ✔ | ✘ (newly broken) |
| Overall task success | 58.3% | 58.3% |

The overall number is unchanged, but G3 is now broken. The per-case check catches it:

```
G3 baseline hard failures: []   →   v4: ["budget_within_limit"]   → NEW FAILURE → regression
```

In CI, the gate re-runs G3 once with a fresh LLM call. If it fails again, the regression is confirmed and the gate fails. If it passes, it's reported as a one-off (flaky) failure and doesn't block.

#### 5. pass^k and pass@k (consistency; report-only)
LLMs give different answers to the same input, so each case runs k = 3 times.
- **pass^k** ("reliably works"): a case counts only if **all k** runs succeed.
- **pass@k** ("can work"): a case counts if **at least one** of the k runs succeeds.
- **Flaky**: passes at least once but not every time.

| Case | Runs (✔/✘) | pass^3 | pass@3 | |
|---|---|---|---|---|
| G1 | ✘ ✔ ✘ | ✘ | ✔ | flaky |
| G2 | ✘ ✘ ✘ | ✘ | ✘ | always fails |
| G3, G4, G5, G8 | ✔ ✔ ✔ | ✔ | ✔ | reliable |
| G6 | ✔ ✘ ✘ | ✘ | ✔ | flaky |
| G7 | ✘ ✘ ✘ | ✘ | ✘ | always fails |

pass^3 = 4 ÷ 8 = **50%**, and pass@3 = 6 ÷ 8 = **75%**.

How to read the gap:
- A large gap between pass@k and pass^k means the model *can* do the task but isn't consistent. Clearer prompt instructions or a lower temperature usually help.
- A case that fails pass@k entirely (G2, G7) means the model never gets it right. That points to a missing rule or a missing guardrail.

#### 6. Soft metrics (report-only)
These describe quality, not correctness, so they never block a deploy.

| Metric | Example | Why it doesn't gate |
|---|---|---|
| **Interest coverage** | G7: Rin likes hiking (impossible in a storm), Tom likes movies. Coverable interests = {movies}; the plan includes a movie event → 1 ÷ 1 = 100%. Hiking doesn't count against the plan. | "How well" interests are served is partly subjective |
| **reason_grounding** | G5: "aligns closely with theatre interest" for an art event → flagged | Keyword heuristic; this wording is arguably honest, so it's a possible false alarm |
| **reasoning_covers_choices** | the plan has 3 activities but the ANALYSIS only discusses 2 → ✘ | A quality issue, not a broken plan |
| **description_verbatim** | the description is lightly paraphrased | A rewording isn't a fabricated fact |
| **Judge metrics** | judge gives relevancy 3/5 | Not calibrated yet; needs ≥ 80% agreement with human labels first |

#### 7. Plan shape (info)
- **Activities per day** = activities ÷ trip days. G1: 7 activities over 3 days = 2.33.
- **Budget utilization** = real spend ÷ budget. G1: 128 ÷ 130 = 98%. G2: 45 ÷ 100 = 45%.
- **Why G8 exists:** with a budget of 500 where at most 148 can be spent, does the planner add more activities or stay at one per day? Low numbers aren't *wrong*, but they show a missed opportunity. This was the goal for prompt v2.

#### 8. Operational metrics (report offline, alerts in production)

| Metric | Smoke example | Used for |
|---|---|---|
| Latency mean / p95 | 20.0 s / 30.6 s | Alert A5 fires if p95 > 60 s |
| Tokens (prompt / completion) | 3,941 / 2,498 per run | Cost tracking |
| Estimated cost | $0.0167 for 3 runs | Budget rule: a full run stays within ~50 calls |

p95 means 95% of runs were faster than this value. It shows the slow cases that an average hides.

#### How they fit together when you evaluate a change
1. **Hallucination rate > 0%?** → rejected immediately.
2. **Any new per-case hard failure** (confirmed by a re-run)? → regression, rejected.
3. **Task success or any hard pass rate below baseline?** → regression, rejected.
4. Otherwise it passes. Then look at **pass^k vs pass@k**, **soft metrics** and **plan shape** to judge whether it's actually *better*. Adopting it (`--accept-baseline`, then switching the prompt version) is a 👤 decision.
