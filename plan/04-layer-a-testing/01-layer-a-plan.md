# Phase 4 – Layer A: Deterministic Testing (minimal)

Status: **Draft – awaiting review**

## 1. Purpose

Layer A answers **"does the software work?"** It checks the code *around* the LLM: models,
prompt building, response parsing, error handling, and the UI flow. It never calls the LLM.

Properties:
- **Deterministic:** the same code always gives the same result, so a failure means a real bug.
- **Fast and free:** the whole suite runs in seconds and costs nothing.
- **CI gate:** runs on every PR. It's wired into GitHub Actions in Phase 6.

It is deliberately **minimal**: one focused test per behavior that matters, not exhaustive
coverage. Judging the *quality* of the LLM's itineraries is Layer B's job (Phase 5).

**No production code changes are needed.** Everything can be tested through the existing
functions, with a fake OpenAI client and `unittest.mock`.

## 2. What is tested

| File | Covers | Tests (≈) |
|---|---|---|
| `tests/test_models.py` | `VacationInfo` / `Traveler` validation; `sample_plan.json` still matches `TravelPlan` | 8 |
| `tests/test_llm.py` | `get_default_model` fallback; `get_client` needs a key | 4 |
| `tests/test_itinerary_agent.py` | `trip_dates`, `extract_json`, `build_system_prompt`, `ItineraryAgent` success + parse error | 7 |
| `tests/test_app.py` | Streamlit `AppTest`: validation errors, happy path, parse-error path | 3 |

About 22 tests in total, running in under 10 seconds.

### 2.1 `test_models.py`
- The sample trip in `planner.py` (`VACATION_INFO_DICT`) validates.
- **Parametrized** invalid cases, each must raise `ValidationError` at the right field:
  - empty name
  - no interests
  - unknown interest (`"skydiving"`)
  - age 121
  - budget 0
  - no travelers
  - departure before arrival
- A same-day trip (arrival = departure) is valid.
- `sample_plan.json` validates as `TravelPlan`, so the fixture can't silently go stale when the
  models change.

### 2.2 `test_llm.py`
- `get_default_model()`:
  - `MODEL` unset → `gpt-4.1-mini`
  - `MODEL=gpt-4.1-nano` → nano
  - `MODEL=gpt-5` (unknown) → falls back to `gpt-4.1-mini`
- `get_client()`:
  - raises `RuntimeError` when `OPENAI_API_KEY` is missing
  - returns a client using `OPENAI_BASE_URL` when it's set (creating a client makes no network
    call)

### 2.3 `test_itinerary_agent.py`
- `trip_dates`: includes both ends (06-10 → 06-12 gives 3 dates); a single-day trip gives 1 date.
- `extract_json`: works with a ```` ```json ```` fence and with bare JSON.
- `build_system_prompt` for 06-13 → 06-14:
  - contains `event-2025-06-13-*` but not `event-2025-06-10-1`
  - contains that range's weather and the `TravelPlan` schema
- `ItineraryAgent.get_itinerary` with a **fake client** that returns `sample_plan.json` inside a
  fence:
  - returns a `TravelPlan`
  - `last_trace` holds the model, system prompt, user prompt (with the traveler names), raw
    response and plan
  - the fake client received the chosen model and exactly 2 messages (system + user)
- Fake client returns `"sorry, no JSON"`:
  - raises `ItineraryParseError`
  - `err.trace.raw_response` is the reply, and `err.trace.travel_plan is None`

### 2.4 `test_app.py` (Streamlit `AppTest`)
- **Empty form → Generate:** shows the validation errors (name, interests), and the agent is
  **not** called.
- **Happy path:** `ItineraryAgent.get_itinerary` is patched to return the sample plan and a trace.
  The page shows the itinerary header, the cost metric `108 / 130`, and the inspector's 4 tabs.
- **Parse error:** the patched agent raises `ItineraryParseError`. The page shows the error and
  the inspector, but no itinerary.

## 3. Shared fixtures (`tests/conftest.py`)

| Fixture | Provides |
|---|---|
| `isolated_env` (autouse) | Sets `OPENAI_API_KEY=test-key`, removes `OPENAI_BASE_URL` and `MODEL`. Tests never use your real `.env` values and behave the same locally and in CI |
| `vacation_info` | `VacationInfo` built from `planner.VACATION_INFO_DICT` |
| `sample_plan` | `TravelPlan` loaded from `sample_plan.json` |
| `fake_client(reply)` | Factory for a stand-in OpenAI client whose `chat.completions.create(**kwargs)` records its arguments and returns `reply` |

## 4. New concepts (learning notes)

- **Test doubles:** a *fake* is a small working stand-in (our fake client). A *mock* or *patch*
  (`unittest.mock.patch.object`) temporarily replaces a real method and records how it was called.
  Both let us test agent code without the network.
- **Fixtures:** pytest builds shared test inputs and passes them to any test that names them as
  a parameter. `autouse=True` applies a fixture to every test.
- **`monkeypatch`:** pytest's tool for setting or removing environment variables for one test and
  restoring them afterwards. It's how we isolate tests from `.env`.
- **Parametrize:** `@pytest.mark.parametrize` runs one test body over many inputs, which suits
  the list of invalid trips.
- **Markers:** `@pytest.mark.eval` will tag the Layer B tests. They're excluded by default, so a
  plain `pytest` stays free and fast.
- **Streamlit `AppTest`:** runs `app.py` headlessly, so tests can type into widgets, click
  buttons, and read what was rendered.

## 5. Tooling and configuration

- **`requirements-dev.txt`:** `-r requirements.txt` plus `pytest==9.0.3`, the version already
  installed.
- **`pytest.ini`:**
  ```ini
  [pytest]
  testpaths = tests
  pythonpath = .
  addopts = -m "not eval"
  markers =
      eval: Layer B probabilistic evals (call the LLM, cost money)
  ```
  Layer B will run `pytest -m eval`. When `-m` is given twice, the last one wins.
- **Commands**, to be added to the CLAUDE.md "Commands" section:
  - all Layer A tests: `pytest`
  - one file: `pytest tests/test_models.py`
  - one test: `pytest tests/test_models.py::test_same_day_trip_is_valid`
  - optional coverage report (`pytest-cov` is already installed):
    `pytest --cov=. --cov-report=term-missing`

## 6. Implementation steps

Branch: `feature/layer-a-deterministic-tests`, created from an up-to-date `main` (workflow rule 9).
Each file starts with `# Phase 4 – Step N: …`.

| Step | Purpose | Depends on | Files |
|---|---|---|---|
| 1 | Tooling + shared fixtures | — | `requirements-dev.txt`, `pytest.ini`, `tests/conftest.py` |
| 2 | Model and config tests | 1 | `tests/test_models.py`, `tests/test_llm.py` |
| 3 | Agent tests with the fake client | 1 | `tests/test_itinerary_agent.py` |
| 4 | UI tests with `AppTest` | 1 | `tests/test_app.py` |
| 5 | Document the commands | 2–4 | `CLAUDE.md` |

After each step, run `pytest`; it must pass and run no LLM calls. Commit after each step, with
your permission.

## 7. Done when

- `pytest` passes locally in under 10 seconds with **no network access needed**. To prove it,
  run once with `OPENAI_BASE_URL=http://127.0.0.1:9`, an unreachable address, so any real call
  would fail.
- Every behavior in §2 has a test.
- The CLAUDE.md commands are updated.
- Out of scope: the CI workflow (Phase 6), quality evals (Phase 5), coverage targets.
