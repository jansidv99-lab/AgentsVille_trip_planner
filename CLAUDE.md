# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project goal

An AI-powered trip planner for the fictional destination AgentsVille. The system must:
1. **Understand and interpret** the user's preferences and constraints.
2. **Plan comprehensively:** produce a coherent, day-by-day itinerary tailored to the travelers, not just a list of activities.
3. **Evaluate and enhance:** use tools to evaluate the plan, fetch new information, and refine the schedule.

It is built in two parts:
- **Part A – The Expert Planner (initial itinerary):** from user preferences (destination, duration, interests, budget), prompt the LLM to act as an expert travel planner. The output must be structured JSON that validates against a predefined Pydantic itinerary model. This part relies on prompt design that elicits complex structured output and guides the LLM through planning.
- **Part B – The Resourceful Assistant (ReAct agent):** an "AI Travel Assistant" handles follow-up questions, change requests, and any extra requirements that must be met before the itinerary is final. It runs a ReAct loop:
  - **THINK:** reason about the request in the context of the current itinerary.
  - **ACT:** if a tool can help (e.g. the simulated activities API), emit a structured tool request.
  - **OBSERVATION:** our Python code simulates the tool and feeds the result back.
  - The agent continues reasoning or returns a final answer.

## Workflow rules

1. **Plan first:** before every step, write a detailed plan doc under `plan/` that explains each topic clearly. Keep plans organized by stage:
   ```
   plan/00-master-plan.md        # overall phases, goals, dependencies (AI QA platform, Layers A/B/C)
   plan/01-setup/                # env, dependencies, repo setup
   plan/02-agents/               # LLM / agent logic
   plan/03-ui/                   # Streamlit app
   plan/04-layer-a-testing/      # Layer A – deterministic tests
   plan/05-layer-b-evals/        # Layer B – probabilistic evals
   plan/06-deploy/               # Cloud Run + GitHub Actions CI/CD
   plan/07-layer-c-monitoring/   # Layer C – system metrics & drift (GCP native)
   ```
   Add new stage folders (e.g. `05-testing/`) when ever as needed do not mixup, keeping the numeric prefix.
2. **Review:** ask the user to review each plan doc before implementing it.
3. **Permission:** always ask for permission before making any change to code.
4. **Phased implementation:** start with the master plan, then plan the code phase by phase and step by step, stating each step's purpose and dependencies.
5. **Commits, PRs, merges:** always ask for permission before every commit, pull request, and merge.
6. **Branch naming:** use professional, descriptive names prefixed by type, e.g. `feature/streamlit-itinerary-form`, `fix/llm-timeout-handling`, `bugfix/date-parsing`, `chore/cloudrun-dockerfile`, `docs/master-plan`.
7. **Phase comments in code:** mark which phase/step produced the code, at the top of each new file and on each new function/class, for future reference:
   ```python
   # Phase 2 – Step 3: <purpose of this code>
   ```
8. **Learning-oriented:** this project is a hands-on learning exercise. Go step by step, explain new concepts as they come up, and never build everything in one go.
9. **Sync before new work:** `git switch main && git pull` (the repo is configured with `pull.ff=only` and `fetch.prune=true`), confirm `git status` says "up to date with 'origin/main'", then create the new branch from `main`. After a PR is merged: `git switch main && git pull && git branch -d <merged-branch>`.

## Repository status

GitHub: `jansidv99-lab/AgentsVille_trip_planner` (public; default branch `main`). Part A (itinerary agent), the Streamlit UI, Layer A tests, and CI/CD (GitHub Actions → Cloud Run, `asia-south1`) are merged and live. In progress: Layer B evals, delivered as scenario slices B0–B5 (`plan/05-layer-b-evals/00-layer-b-overview.md`); Layer C follows (C1 is needed before B5).

## Commands

- Install: `pip install -r requirements.txt` (add tests: `pip install -r requirements-dev.txt`)
- Run the app: `streamlit run app.py`
- CLI demo of Part A (makes one LLM call): `python planner.py`
- Layer A tests (no LLM calls, ~2 s): `pytest`
  - one file: `pytest tests/test_models.py`
  - one test: `pytest tests/test_models.py::test_same_day_trip_is_valid`
  - one parametrized case: `pytest "tests/test_models.py::test_invalid_field_is_rejected[zero-budget]"`
  - coverage (optional, needs `pytest-cov`): `pytest --cov=. --cov-report=term-missing`
- Layer B evals (call the LLM, cost credits; excluded from plain `pytest` via `pytest.ini`):
  - smoke via pytest (3 approved smoke cases × 1): `pytest -m eval -s`
  - runner: `python -m evals.harness.runner --mode smoke|full [--repeats N] [--model gpt-4.1-nano] [--prompt-version v1]`
  - re-grade cached replies for free (0 LLM calls): add `--cache replay-only`; force new calls: `--cache refresh`
  - outputs: `evals/results/<UTC>_<mode>/{records.jsonl,report.md,report.json}`; cached replies in `evals/cache/` (both gitignored)
- Budget rule: a full eval run must stay within ~50 LLM calls.

## Testing conventions

- Tests never call the LLM: use the `fake_client` fixture (agent tests) or `patch.object(ItineraryAgent, "get_itinerary", autospec=True, ...)` (UI tests). Shared fixtures live in `tests/conftest.py`.
- The autouse `isolated_env` fixture sets a dummy `OPENAI_API_KEY` and removes `MODEL` / `OPENAI_BASE_URL`, so the local `.env` never affects results.
- Streamlit UI tests use `streamlit.testing.v1.AppTest`, with widgets addressed by their `key` (e.g. `name_0`, `interests_0`).
- Golden datasets (`evals/datasets/<name>/vX.Y.Z.jsonl`) are versioned by `manifest.json` (sha256 with line endings normalized, counts, changelog). Editing a dataset requires a version bump (patch: notes; minor: add cases; major: change expectations). Only `review.status: approved` cases run, and approval is the user's decision.
- New graders are pure functions `grade(inp: GradingInput) -> GraderResult`, decorated with `@grader("B<n>")` and added to `quality/graders/GRADERS`. `GradingInput.for_case(...)` is used offline (golden expectations) and `GradingInput.for_request(...)` in production (expectations derived from the request). Return `not_applicable(...)` (`passed=None`) when a check can't apply. Graders must stay deterministic so the app can run them online (the inspector's "Quality checks" tab does).
- Business rules encoded by graders (decided by the user):
  - **Pricing:** an activity's `price` is a group price; `total_cost` = sum of activity prices.
  - **Weather:** whole-day policy. No `outdoor` activity on any rainy or thunderstorm day; `flex` (indoor rain backup) is allowed. Settings come from the approved `quality/ground_truth/activity_labels.json`.
  - Prompt changes (B4) must state these rules explicitly.
- Every new grader needs a mutation test that breaks the known-good `sample_plan` in one way and asserts **only** that grader fails (see `tests/test_grounding_graders.py`).

## Code layout

- `models.py`: all Pydantic models (`VacationInfo` input, `TravelPlan` output, `PromptTrace`).
- `llm.py`: OpenAI client (wrapped in `InstrumentedClient` for latency/tokens/cost) and default model from `.env`.
- `quality/`: shared by app and evals: `schema.py` (`EvalCase`, `EvalRecord`, the one record shape for offline and prod), `graders/` (`base.py` GradingInput/decorator, `parse.py` B0, `grounding.py` B1 hallucination, `constraints.py` B2 constraints/task success), `labels.py` (approved activity settings), `pricing.py`.
- `evals/`: golden datasets and the harness (`dataset.py`, `cache.py` record/replay, `runner.py`, `report.py`).
- `agents/itinerary.py`: Part A prompt (built from the trip's dates using the mocked APIs) and `ItineraryAgent`, which records a `PromptTrace` on every run.
- `project_lib.py`: course-provided helpers, `Interest` enum, `ChatAgent`, and the mocked weather and activities data (only 2025-06-10 … 2025-06-15 in AgentsVille).
- `app.py` + `ui/render.py`: Streamlit form, results view, and prompt inspector.

## Environment

Copy `.env.example` to `.env` and fill it in (`.env` holds secrets and must stay gitignored). It defines:
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MODEL`: LLM access via an OpenAI-compatible endpoint. `OPENAI_BASE_URL` points at a non-default endpoint, so create the client with `OpenAI(base_url=os.getenv("OPENAI_BASE_URL"))` rather than relying on the SDK default.
- `GCP_PROJECT_ID`, `GCP_PROJECT_NUMBER`: deployment target.

## LLM models

Read the model name from the `MODEL` env var; never hardcode it. If `MODEL` is unset, fall back to `gpt-4.1-mini`. Valid options to experiment with:

| Model | Use for |
|---|---|
| `gpt-4.1` | Strongest; general-purpose reasoning and demanding tasks |
| `gpt-4.1-mini` | **Default.** Fast and affordable; good balance of speed and cost |
| `gpt-4.1-nano` | Fastest and cheapest; lightweight, high-frequency tasks |

## Data models

Use Pydantic for all data models (traveler preferences, the itinerary, tool requests/responses).

## UI

Use Streamlit for the UI.
the UI should have following components - 
  window where traveler enter the name 
  select the city name form the list for now only one city - "AgentsVille"
  select multiple intrests provided in the class - Interest
  select the open ai models to use for the LLM generation
  button to generate the report   

## Deployment and CI/CD

Deploy the app to Google Cloud Run in the project given by `GCP_PROJECT_ID`. Region: TBD (record it here once chosen). Use GitHub Actions as the CI/CD pipeline that builds and deploys to Cloud Run.
