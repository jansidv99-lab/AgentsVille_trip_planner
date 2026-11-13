# Graders explained (learning note)

This is a reference for **what a grader is, why Layer B needs them, and how one verdict travels from an
eval run to production monitoring**. The examples come from this project's real B0 smoke run.

## 1. Definition

A **grader** is a small function that asks **one specific question about one LLM reply** and
answers with a structured verdict:

```python
grade(...) -> GraderResult(grader, severity, passed, score, details)
```

Examples of the questions:
- "Is every activity real?"
- "Is the plan within budget?"
- "Is any outdoor event planned in a storm?"

The graders live in `quality/graders/` and are registered in the `GRADERS` list. The harness runs
every registered grader on every reply.

## 2. Why LLM output needs graders instead of exact asserts

A Layer A test asserts **one exact answer**. That works because code is deterministic: the same
input always gives the same output.

An LLM itinerary has **no single correct answer**, and the same prompt gives a different plan each
run. So instead of "is the output equal to X?", Layer B asks a set of **property questions** that
*any* acceptable plan must satisfy. It then measures **how often** they hold over repeated runs:
the **pass rate**.

## 3. The exam analogy

| Exam | In this project |
|---|---|
| Exam questions | Golden dataset cases G1–G8 (`evals/datasets/itinerary_golden/v1.0.0.jsonl`) |
| Answer key | Each case's `Expectations`: budget, allowed activities, uncoverable interests |
| **Examiners** | **Graders**: each one checks one property |
| Proctor | Harness (`evals/harness/runner.py`): runs cases × repeats and calls every grader |
| Scorecard | One `EvalRecord` per run → `report.md` with pass rates |

## 4. A worked example from the B0 smoke run

Case **G2** (thunderstorm, then two rainy days) came back with `event-2025-06-12-0`, an **outdoor
hike on the thunderstorm day**. The reply *looked* fine:
- it parsed
- its total of 45 was within the budget of 100
- every activity ID was real

Only a grader that asks the right question catches the problem. B2's weather grader will report:

```python
GraderResult(
    grader="weather_safety",
    severity="hard",
    passed=False,
    score=0.67,  # 2 of 3 bad-weather days are safe
    details={"unsafe": {"2025-06-12": ["event-2025-06-12-0"]}},
)
```

## 5. What each field is for

| Field | Role |
|---|---|
| `passed` | Did this run satisfy the property? Averaged over runs, it becomes the **pass rate** |
| `score` (0–1) | Partial credit (2 of 3 days safe = 0.67). Shows *how close* a failure was |
| `severity` | `hard` = must pass, a gate (blocks CI, alerts in production); `soft` = quality signal tracked over time; `info` = measured only |
| `details` | *Why* it failed (which activity, which day). Makes a red result debuggable |

## 6. Where a verdict goes

```
LLM reply ─▶ parse ─▶ TravelPlan ─▶ [grader 1][grader 2] … [grader N]
                                              │
                                     list[GraderResult]
                                              ▼
                                         EvalRecord
           ┌──────────────────────────────────┼─────────────────────────────────┐
    OFFLINE (Layer B)                    CI (B4)                       ONLINE (Layer C)
 report.md: pass rate per        smoke eval blocks a PR when     every live itinerary is graded
 grader and case, v1 vs v2       a hard grader regresses         and logged → Cloud Monitoring
 prompt deltas                                                   metrics/alerts → BigQuery →
                                                                 failing runs become new cases
```

The **same grader code** serves all three paths. That's why graders must be **pure and
deterministic**: the live app can then run them on every request at no cost. The LLM judge is the
one exception, and it runs offline only.

## 7. Three kinds of graders

| Kind | How it decides | Examples here | Trade-off |
|---|---|---|---|
| **Code / lookup** | Exact comparison with ground truth | B1: activity exists and its details match `ACTIVITY_CALENDAR`; B2: budget, weather safety | Free, deterministic, runs online; only checks what can be defined precisely |
| **Heuristic** | Patterns in the text | B3: ANALYSIS states the same total as `total_cost` | Cheap; can be fragile |
| **Model-based (LLM judge)** | Another LLM scores against a rubric | B3: relevancy, coherence, faithful reasoning | Captures nuance; costs calls and is itself non-deterministic, so it must be **calibrated against human labels** |

## 8. Lesson: pick the grader that matches the failure (the G5 case)

Case **G5** is a traveler interested only in *theatre*, which no activity offers. The B0 reply:
- used **real** activities with their **real** interests and prices: no fabricated facts
- had an ANALYSIS that honestly said "No direct theatre activity available"
- but gave reasons that **stretch** relevance: "aligns closely with theatre interest", "close to
  theatre interest"

That's **over-claiming**, not **fabrication**:

| Failure | Example | Right grader |
|---|---|---|
| Fabrication / alteration | Invented activity ID, changed price, wrong weather | B1 code/lookup graders (hard) |
| Over-claiming | "Close to your theatre interest" for a writing workshop | B3 judge + heuristics |

A keyword check for "theatre" can't tell "close to theatre" from "no theatre available, so…".
That needs judgement, so it belongs to the calibrated judge. B1 only *surfaces* such mentions as an
`info` signal.

## 9. Roadmap: graders per slice

| Slice | Graders | Headline metric |
|---|---|---|
| B0 ✅ | `parse` | parse rate (smoke run: 3/3) |
| B1 | `activity_exists`, `activity_details_match`, `activity_on_its_date`, `weather_matches_forecast`, `plan_matches_request`, `description_verbatim`, `uncoverable_interest_mentions` | hallucination rate (target 0%) |
| B2 | `budget`, `cost_arithmetic`, `day_coverage`, `no_overlaps`, `weather_safety` | task success (target 100%) |
| B3 | `interest_coverage`, `reason_grounding`, `analysis_consistency`, `llm_judge` | interest coverage, answer relevancy, reasoning consistency |

The harness, records and report don't change as slices add graders. They already handle any
number of them.
