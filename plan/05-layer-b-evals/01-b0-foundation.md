# Layer B – B0 Foundation: harness, golden dataset v1.0.0, record/replay

Status: **Draft – awaiting review** (including approval of the 8 golden cases in §3)

Parent plan: `00-layer-b-overview.md`

## 1. Question this slice answers

**"Can we run a repeatable experiment on the itinerary agent and get comparable numbers?"**

B0 builds everything the later slices plug into:
- the schemas
- a versioned golden dataset
- an instrumented LLM client that captures latency, tokens and cost
- a runner with record/replay caching
- a report

Its only quality grader is **parse rate**. Hallucination (B1), constraints (B2) and relevancy (B3)
add graders to this same harness.

**Budget for B0:** one real **smoke** run of 3 LLM calls. Everything else is tested free with the
fake client.

## 2. Schemas (`quality/schema.py`)

One record shape is used everywhere: offline runs now, production logs later (Layer C, C1). Fields
are typed with Pydantic.

### 2.1 `Expectations`: per-case ground truth (rule-based, human-approved)
| Field | Type | Meaning | Used by |
|---|---|---|---|
| `max_cost` | int | Budget ceiling (normally `= vacation_info.budget`) | B2 |
| `min_activities_per_day` | int = 1 | Every trip day must have at least this many | B2 |
| `allowed_activity_ids_by_date` | `dict[date, list[str]] \| None` | Exhaustive allow-list for days where the right answer is precise (e.g. rainy days with a single indoor option) | B2 |
| `must_include_activity_ids` | `list[str]` | Strong relevancy expectation (soft) | B3 |
| `uncoverable_interests` | `list[Interest]` | Interests no activity on the trip dates can satisfy (e.g. `theatre`). Not penalized by coverage, but **inventing** coverage is a hallucination | B1, B3 |
| `notes` | str | Why the case exists, in plain words | humans |

### 2.2 `EvalCase`: one golden dataset row (a line in the JSONL file)
| Field | Type |
|---|---|
| `case_id` | str (`G1`…) |
| `title` | str |
| `tags` | list of `grounding / constraints / weather / budget / relevancy / scale / utilization` |
| `smoke` | bool (part of the 3-call smoke subset) |
| `vacation_info` | `VacationInfo` (existing model) |
| `expectations` | `Expectations` |
| `review` | `{status: draft \| approved, reviewer, reviewed_on}`. **The harness runs approved cases only** |

### 2.3 `GraderResult`
`grader` (name), `severity` (`hard / soft / info`), `passed` (bool or None), `score` (0–1 or
None), `details` (dict, e.g. which field was hallucinated).

### 2.4 `EvalRecord`: one LLM run, graded
| Field | Notes |
|---|---|
| `schema_version` | `"1"` |
| `trace_id` | UUID, the same id `PromptTrace` carries (B5 correlates feedback with it) |
| `timestamp` | UTC |
| `source` | `offline` or `prod` |
| `case_id`, `dataset` | e.g. `G2`, `itinerary_golden@1.0.0` (None in prod) |
| `prompt_version`, `model`, `repeat` | the experiment coordinates |
| `latency_ms`, `prompt_tokens`, `completion_tokens`, `cost_usd` | from the instrumented client (§4) |
| `parsed`, `error` | did the reply become a `TravelPlan` |
| `grader_results` | list of `GraderResult` |
| `cache_key`, `git_sha` | reproducibility |

## 3. Golden dataset v1.0.0: the 8 cases (please review each one)

File: `evals/datasets/itinerary_golden/v1.0.0.jsonl`. All cases start as `review.status: draft`.
They're facts from the mock data, checked against `ACTIVITY_CALENDAR` / `WEATHER_FORECAST`.

| id | Travelers (age; interests) | Dates | Budget | Weather | Why it exists | Key expectations |
|---|---|---|---|---|---|---|
| **G1** ⚡ | Yuri (30; tennis, cooking, comedy, technology), Hiro (25; reading, music, theatre, art) | 06-10 → 06-12 | 130 | clear, partly cloudy, **thunderstorm** | The current sample: baseline and regression anchor | max 130; ≥1/day; 06-12 only `-12-1` (flex) or `-12-3` (indoor); `theatre` uncoverable |
| **G2** ⚡ | Mara (34; hiking, gardening, dancing) | 06-12 → 06-14 | 100 | thunderstorm, **rainy, rainy** | Weather safety. Mara's favorite (hiking/gardening) activities are all outdoors | 06-12 ∈ {`-12-1`, `-12-3`}; 06-13 = {`-13-0`}; 06-14 = {`-14-3`} (the only indoor options) |
| **G3** | Ana (28; art, music) | 06-10 → 06-11 | **30** | clear, partly cloudy | Exact budget edge: the cheapest valid plan is 15 + 15 | max 30; ≥1/day, so exactly one 15-priced activity per day (e.g. `-10-2`/`-10-3`, then `-11-0`) |
| **G4** | Leo (40; tennis) | **06-15 only** | 50 | sunny | Single-day trip + obvious best match | ≥1 on 06-15; must include `event-2025-06-15-3` (the only tennis event) |
| **G5** ⚡ | Kai (22; **theatre** only) | 06-10 → 06-11 | 60 | clear, partly cloudy | **Hallucination trap:** no activity offers theatre | ≥1/day; `theatre` uncoverable; any activity or reason claiming theatre = hallucination |
| **G6** | Yuri, Hiro (as G1) + Sam (31; hiking, photography) | **06-10 → 06-15** | 200 | full range incl. 3 bad-weather days | Scale: 6 days, 3 travelers, mixed weather | max 200; ≥1/day; 06-12/13/14 allow-lists as G2; `theatre` uncoverable |
| **G7** | Rin (27; hiking), Tom (33; movies) | **06-12 only** | 40 | thunderstorm | Conflicting interests + weather: hiking is only offered outdoors | 06-12 ∈ {`-12-1`, `-12-3`}; `hiking` uncoverable that day |
| **G8** | Yuri, Hiro (as G1) | 06-10 → 06-11 | **500** | clear, partly cloudy | Budget utilization: the known "1 activity/day" gap (max spend possible is 148) | max 500; ≥1/day; utilization and activities/day **reported** (soft, B4 target) |

⚡ = smoke subset (G1, G2, G5): baseline + weather + hallucination in 3 calls.

**Manifest** `evals/datasets/itinerary_golden/manifest.json`:
```json
{ "name": "itinerary_golden", "version": "1.0.0", "sha256": "<of v1.0.0.jsonl>",
  "case_count": 8, "smoke_cases": ["G1","G2","G5"], "approved_count": 0,
  "changelog": [{ "version": "1.0.0", "date": "...", "changes": "Initial 8 cases" }] }
```
**Versioning rules (semver):**
- **patch:** fix a typo or a note
- **minor:** add cases (e.g. B5 promotions → 1.1.0)
- **major:** change an existing expectation; old results become incomparable

A Layer A test fails if the file's hash doesn't match the manifest. That forces every change
through a version bump. The hash ignores line endings, and `.gitattributes` pins dataset files to
LF, because Git on Windows (`core.autocrlf`) would otherwise change the bytes on checkout.

## 4. Instrumented client (`llm.py`)

`project_lib.do_chat_completion` returns only the reply text. To get metrics without touching
course code:
- `InstrumentedClient(client)` wraps the OpenAI client.
  - Its `chat.completions.create(**kw)` calls the real client, measures `latency_ms`, and reads
    `response.usage.prompt_tokens / completion_tokens`.
  - It stores the result as `last_call`, and returns the response unchanged.
- `get_client()` returns the wrapped client, so the app gets metrics too (needed for Layer C).
- `ItineraryAgent.get_itinerary` copies `last_call` into new optional `PromptTrace` fields:
  `trace_id`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `cost_usd`.
- **Cost:** `quality/pricing.py` has an editable table of USD per 1M tokens (approximate list prices:
  `gpt-4.1` 2.00 in / 8.00 out, `gpt-4.1-mini` 0.40 / 1.60, `gpt-4.1-nano` 0.10 / 0.40). Unknown
  models get `cost_usd = None`. **The Vocareum billing may differ; this is an estimate for trends.**

## 5. Harness (`evals/harness/`)

### 5.1 Runner: `python -m evals.harness.runner`
| Option | Default | Meaning |
|---|---|---|
| `--mode smoke\|full` | smoke | smoke = G1, G2, G5 × 1 repeat (3 calls); full = 8 × `--repeats` |
| `--repeats` | 1 (smoke) / 3 (full) | non-determinism needs repeats |
| `--model` | `get_default_model()` | e.g. `gpt-4.1-nano` |
| `--prompt-version` | `PROMPT_VERSION` or `v1` | recorded now; selects the prompt file from B4 |
| `--cache replay-only\|record\|refresh` | record | see §5.2 |

Flow per (case, repeat): approved check → cache lookup or `ItineraryAgent.get_itinerary` →
graders → `EvalRecord` → `evals/results/<UTC-time>_<mode>/records.jsonl`, then the report.

### 5.2 Record/replay cache (`evals/harness/cache.py`)
- **Key:** sha256 of `case_id + dataset version + prompt_version + model + repeat + sha256(system
  prompt)`. Hashing the system prompt means any prompt change automatically misses the cache.
- **Stored** in `evals/cache/<key>.json`: raw reply, `PromptTrace` metrics, timestamp.
- **Modes:**
  - `record`: call the LLM only when there's no cached reply
  - `replay-only`: never call the LLM; fail if a reply is missing. Used to re-grade for free when
    graders change
  - `refresh`: always call the LLM
- `evals/cache/` and `evals/results/` are gitignored.

### 5.3 Graders in B0
- **`parse`** (hard): the reply validated as `TravelPlan`.
- Graders are plain functions `grade(case, plan | None, raw_response) -> GraderResult`, registered
  in a list (`quality/graders/GRADERS`), so B1–B3 only *add* functions. They take the raw reply
  rather than a `PromptTrace`, so cached replies can be re-graded; B3's reasoning grader reads the
  `ANALYSIS` section from it.

### 5.4 Report (`evals/harness/report.py`)
`report.md` + `report.json` contain:
- **Header:** dataset@version, prompt version, model, git SHA, mode, repeats, total calls
  (live vs cached).
- **Per case:** parse pass rate over repeats, mean and p95 latency, tokens, cost.
- **Totals:** parse rate, total cost, mean latency.
- A placeholder section per future grader.

### 5.5 pytest entry (`evals/test_evals.py`, marked `eval`)
- `test_smoke_eval`: runs the smoke mode and asserts parse rate = 100%.
- It's excluded from the default `pytest` (Layer A) by the existing marker, and run with
  `pytest -m eval`.

## 6. Layer A tests for B0 (free, run in CI)
| Test file | Checks |
|---|---|
| `tests/test_eval_dataset.py` | Every JSONL line validates as `EvalCase`; ids unique; dates inside the mock range; every id in an `allowed_activity_ids_by_date` exists on that date; `uncoverable_interests` really aren't offered on the trip dates; manifest sha256, counts and smoke list match |
| `tests/test_instrumented_client.py` | With `FakeOpenAIClient` (extended to return `usage`): `last_call` has latency ≥ 0 and the tokens; cost uses the pricing table; unknown model → `None` |
| `tests/test_eval_harness.py` | Cache key changes when the prompt changes; replay-only with no entry raises; runner end to end with the fake client (2 approved temporary cases → `records.jsonl` + `report.md`, parse grader pass/fail both covered); draft cases are skipped |

The dataset tests double as **ground-truth audits**: they prove the human-approved expectations
are consistent with the mock data.

## 7. Implementation steps

Branch: `feature/layer-b-b0-foundation` (from synced `main`). Each new file and function gets
`# Phase 5 – B0 Step N: …`.

| Step | Purpose | Depends on | Files |
|---|---|---|---|
| 1 | Schemas + draft dataset + manifest + dataset tests | — | `quality/__init__.py`, `quality/schema.py`, `evals/datasets/itinerary_golden/*`, `tests/test_eval_dataset.py` |
| 2 | **You review and approve the 8 cases.** I set `review.status: approved` and update the manifest | 1 | dataset files |
| 3 | Instrumented client + pricing + `PromptTrace` fields | — | `llm.py`, `quality/pricing.py`, `models.py`, `agents/itinerary.py`, `tests/conftest.py`, `tests/test_instrumented_client.py` |
| 4 | Cache, runner, parse grader, report | 1, 3 | `evals/harness/*.py`, `quality/graders/__init__.py`, `tests/test_eval_harness.py`, `.gitignore` |
| 5 | pytest eval entry + **first real smoke run (3 calls)**; report summary goes in the PR | 2, 4 | `evals/test_evals.py` |
| 6 | Docs: CLAUDE.md commands (`python -m evals.harness.runner …`, `pytest -m eval`) | 5 | `CLAUDE.md` |

Commit after each step, with your permission. Layer A must stay green, and CI runs it.

## 8. New concepts (learning notes)
- **Golden dataset:** a fixed, reviewed set of inputs with known-good expectations. It's the
  "exam" every prompt or model version takes, so results are comparable.
- **Semver for data:** version numbers tell you whether two eval runs can be compared.
- **Record/replay:** expensive, non-deterministic calls are saved once. Graders can then be
  improved and re-run for free and reproducibly.
- **Repeats and non-determinism:** one run tells you little. Pass rates over repeats tell you how
  reliable the behavior is.
- **Instrumentation:** latency, tokens and cost are measured at the client boundary, so offline
  evals and production report the same numbers.

## 9. Done when
- All 8 cases are approved, and the manifest hash test passes.
- `pytest` (Layer A) is green, including the new B0 tests, with no network.
- `python -m evals.harness.runner --mode smoke` makes 3 live calls and writes `records.jsonl` and
  `report.md` with latency, tokens and cost.
- Re-running with `--cache replay-only` makes **0** calls and produces the same parse results.
- `pytest -m eval` passes (smoke parse rate = 100%).
