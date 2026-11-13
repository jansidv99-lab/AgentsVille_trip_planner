# Layer B – B1 Hallucination & grounding

Status: **Draft – awaiting review**

Parent plan: `00-layer-b-overview.md` · Builds on: `01-b0-foundation.md` (merged) · Background:
`graders-explained.md`

## 1. Question this slice answers

**"Is everything in the plan real?"** Every fact in the structured `TravelPlan` must trace back to
one of:
- the mock APIs (`ACTIVITY_CALENDAR`, `WEATHER_FORECAST` in `project_lib.py`)
- the traveler's request (`VacationInfo`)

## 2. Evidence from the B0 cache (read-only, 0 calls)

- **G5 (theatre trap):**
  - The structured data is **not** fabricated: real IDs, interests and prices.
  - The ANALYSIS honestly says "No direct theatre activity available".
  - The reasons **stretch** relevance ("aligns closely with theatre interest").

  So B1 (hard) covers fabricated or altered **facts**, and honest vs stretched **reasons** is B3's
  job. B1 surfaces such mentions as `info`.
- **G2:** the outdoor hike on the thunderstorm day is a **constraint** failure (B2), not a
  hallucination. B1 should pass G2.

## 3. Design change: graders receive the request (`GradingInput`)

Production has no golden case, but grounding needs the trip's dates and destination. B1 changes the
grader signature from `grade(case, plan, raw_response)` to:

```python
grade(inp: GradingInput) -> GraderResult

class GradingInput:            # quality/graders/__init__.py
    vacation_info: VacationInfo          # always present (offline: from the case; prod: the user's request)
    plan: TravelPlan | None              # None when the reply didn't parse
    raw_response: str
    expectations: Expectations           # offline: the golden case's; prod: Expectations(max_cost=budget)
    source: "offline" | "prod"
```

- `GradingInput.for_case(case, plan, raw)` and `GradingInput.for_request(vacation_info, plan, raw)`
  build the two variants.
- **Not applicable:** a grader that needs data it doesn't have (no plan, or a golden-only
  expectation) returns `passed=None`. A `None` result isn't counted in pass rates.
- **Migration:** `grade_parse`, `run_graders`, the runner and the existing harness tests switch to
  the new signature. Behavior is unchanged, and the B0 tests prove that.

## 4. Graders (`quality/graders/grounding.py`, all deterministic, online-safe)

| Grader | Severity | Fails when | `details` |
|---|---|---|---|
| `activity_exists` | hard | an `activity_id` is not in `ACTIVITY_CALENDAR` | `unknown_ids` |
| `activity_details_match` | hard | name, start_time, end_time, location, price or related_interests differ from the calendar | `mismatches: {id: {field: {expected, got}}}` |
| `activity_on_its_date` | hard | an activity is listed under a day other than its real date | `misplaced: [{id, listed, actual}]` |
| `weather_matches_forecast` | hard | a day's condition, temperature or unit differs from `WEATHER_FORECAST` | `mismatches: {day: {field: {expected, got}}}` |
| `plan_matches_request` | hard | city ≠ destination; start/end ≠ arrival/departure; a day outside the trip; a duplicated day | `problems: [...]` |
| `description_verbatim` | soft | a description was paraphrased (the prompt requires an exact copy) | `paraphrased_ids` |
| `uncoverable_interest_mentions` | info | a reason mentions an interest in `expectations.uncoverable_interests` | `mentions: [{id, reason}]`, handed to B3 |

**Scoring:**
- `score` = fraction of checked items that pass (e.g. 6 of 7 activities match = 0.86).
- `passed` = all items pass.
- Unknown IDs are excluded from `activity_details_match` and `activity_on_its_date` (they're already
  failed by `activity_exists`), so one fabrication isn't counted three times.
- The `info` grader always has `passed=None`. It's a signal, not a verdict.

**Registry:** each grader declares a `slice` (`B0`, `B1`, …) for report grouping.
`HALLUCINATION_GRADERS` = the five hard B1 graders.

## 5. Metrics and report

- **Hallucination rate** = share of parsed runs where **any** hard grounding grader fails.
  **Threshold: 0%.** Unparsed runs are counted by the parse rate, not here.
- **Per-field mismatch counts**, e.g. "price altered 2×, location 1×": which fields the model
  tends to change.
- `report.md` gets a **Hallucination** section (rate, failing cases, top mismatched fields, info
  mentions) and groups grader pass rates by slice.

## 6. End to end for this scenario

1. **Layer A mutation tests** (free, CI):
   - `sample_plan.json` passes every grounding grader.
   - Then one mutated plan per failure mode, each failing **exactly its own grader** with correct
     details:

     | Mutation | Expected failing grader |
     |---|---|
     | fake activity id | `activity_exists` |
     | price 15 → 5 | `activity_details_match` (price) |
     | wrong location | `activity_details_match` (location) |
     | interest relabeled `theatre` | `activity_details_match` (related_interests) |
     | activity moved to another day | `activity_on_its_date` |
     | weather "sunny" on 06-12 | `weather_matches_forecast` |
     | extra day outside the trip / wrong city | `plan_matches_request` |
     | paraphrased description | `description_verbatim` (soft) |
     | reason mentioning theatre, with theatre uncoverable | `uncoverable_interest_mentions` (info) |

   - Prod-mode input (`for_request`, no golden expectations): graders still run, and golden-only
     checks give `None`.
2. **Replay-only re-grade** of the cached B0 smoke replies (**0 calls**). Expected: G1, G2 and G5
   pass all hard grounding graders; G5 shows 2 `uncoverable_interest_mentions`.
3. **First full run:** 8 cases × 3 repeats = **24 live calls** (≈ $0.13 at the B0 rate), within
   the 50-call budget. It produces the first real hallucination rate. **I'll ask before running.**
4. **Live app, "Quality checks" tab:** the prompt inspector gets a 5th tab that runs the
   deterministic graders on the live itinerary (`for_request`, `source="prod"`). It shows each
   verdict, score and details. This is online grading, demonstrated before Layer C starts logging
   it. `test_app.py` is updated.
5. **Layer C hook:** C1 will log these same `GraderResult`s per live run. B1 guarantees the graders
   work in prod mode.

## 7. Implementation steps

Branch `feature/layer-b-b1-grounding` (from synced `main`). Phase comments: `# Phase 5 – B1 Step N: …`.

| Step | Purpose | Depends on | Files |
|---|---|---|---|
| 1 | `GradingInput` + signature migration | B0 | `quality/graders/__init__.py`, `evals/harness/runner.py`, `tests/test_eval_harness.py` |
| 2 | Grounding graders + mutation tests | 1 | `quality/graders/grounding.py`, `tests/test_grounding_graders.py` |
| 3 | Report: slice grouping + Hallucination section | 2 | `evals/harness/report.py`, `tests/test_eval_harness.py` |
| 4 | Replay-only re-grade of the B0 smoke cache (0 calls); findings in the PR | 2, 3 | — |
| 5 | "Quality checks" inspector tab | 2 | `ui/render.py`, `app.py`, `tests/test_app.py` |
| 6 | Full run (24 calls, **with your permission**); results in the PR; CLAUDE.md update | 4 | `CLAUDE.md` |

Commit after each step with your permission. Layer A must stay green in CI.

## 8. New concepts (learning notes)
- **Grounding vs fabrication vs over-claiming:** why G5's reasons are a B3 problem.
- **Exact ground-truth lookup vs fuzzy matching:** with a known source of truth, compare exactly.
- **Severity in practice:** what blocks (hard), what's trended (soft), what's just shown (info).
- **Mutation testing:** proving each grader catches *its own* failure mode and nothing else.
- **Online grading with derived expectations:** the same graders on production traffic without a
  golden answer key.

## 9. Done when
- Every mutation in §6.1 is caught by exactly its grader. Layer A is green, including in CI.
- Replay of the B0 cache gives the expected verdicts with 0 calls.
- The full-run report shows the hallucination rate and the per-field breakdown.
- The live app's "Quality checks" tab shows the grader verdicts for a generated itinerary.
