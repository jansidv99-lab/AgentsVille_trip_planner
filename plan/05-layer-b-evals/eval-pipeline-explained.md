# The eval pipeline, end to end (learning note)

> golden data → graders → harness → thresholds → CI → production signal

This note follows **one quality question** through all six stages of Layer B. Each stage lists the
real files and commands. For what a single grader is and how it decides, see
[`graders-explained.md`](graders-explained.md); this note does not repeat that.

**Who it's for:** anyone (including future you) who wants to change a prompt, add a grader, or
understand why a PR's eval gate failed.

```
                 ┌────────────────────────── offline (dev / CI) ──────────────────────────┐
  1 golden data ─► 2 graders ─► 3 harness ─► 4 thresholds (baseline) ─► 5 CI gate ─► merge
        ▲                ▲                                                            │
        │                │ same code                                                  ▼
        │          ┌─────┴──────────────── online (Cloud Run) ─────────────────┐   deploy
        │          │ app runs graders on every live plan → llm_run / feedback  │◄─────┘
        │          └──────────────────────────────┬─────────────────────────────┘
        │                                         ▼
        └──── 6 production signal: BigQuery → promote.py mine → human review → new dataset version
```

The loop closes at stage 6: production failures become new golden cases, so the next offline run
tests exactly what broke in the real app.

---

## 1. Golden data: the questions and the answer key

**What:** a small, hand-approved set of trips. For each one we know what any acceptable plan must
satisfy.

| | |
|---|---|
| Files | `evals/datasets/itinerary_golden/v1.0.0.jsonl`, `manifest.json` |
| Schema | `EvalCase` in `quality/schema.py` |
| Extra ground truth | `quality/ground_truth/activity_labels.json` (indoor / outdoor / flex per activity) |

One case (G2, shortened):

```json
{"case_id": "G2", "title": "Weather safety: storm then two rainy days", "smoke": true,
 "vacation_info": {"travelers": [{"name": "Mara", "interests": ["hiking", "gardening", "dancing"]}],
                   "date_of_arrival": "2025-06-12", "date_of_departure": "2025-06-14", "budget": 100},
 "expectations": {"max_cost": 100, "min_activities_per_day": 1,
                  "allowed_activity_ids_by_date": {"2025-06-12": ["event-2025-06-12-1", "event-2025-06-12-3"],
                                                   "2025-06-13": ["event-2025-06-13-0"],
                                                   "2025-06-14": ["event-2025-06-14-3"]}},
 "review": {"status": "approved", "reviewer": "..."}}
```

**Rules that keep it trustworthy:**
- **Only `review.status: approved` cases run.** Approval is a human decision.
- **Versioned like a library:** `manifest.json` stores a sha256 of the file (line endings
  normalized), counts, the smoke subset (`G1, G2, G5`) and a changelog. Any edit bumps the version:
  patch for notes, minor for new cases, major for changed expectations.
- **Why a version matters:** a metric only means something next to the dataset that produced it.
  Baselines are keyed by `itinerary_golden@1.0.0`.

## 2. Graders: the examiners

**What:** pure, deterministic functions `grade(GradingInput) -> GraderResult`, registered in
`quality/graders/__init__.py` → `GRADERS`. Each one checks one property.

| Slice | Graders | Severity |
|---|---|---|
| B0 | `parse` | hard |
| B1 hallucination | `activity_exists`, `activity_details_match`, `activity_on_its_date`, `weather_matches_forecast`, `plan_matches_request`, `description_verbatim`, `uncoverable_interest_mentions` | hard |
| B2 constraints | `budget_within_limit`, `cost_arithmetic`, `day_coverage`, `no_time_overlaps`, `weather_safety`, `plan_shape` | hard (`plan_shape` is report-only) |
| B3 relevancy / reasoning | `interest_coverage`, `must_include`, `reason_grounding`, `analysis_structure`, `reasoning_covers_choices` | soft |
| B3 judge (offline only) | `judge_*` in `quality/graders/judge.py` | report-only until calibrated |

**The key design choice:** the same grader code runs in both worlds. Only the answer key changes:

```python
GradingInput.for_case(case, plan, raw)            # offline: golden, human-approved expectations
GradingInput.for_request(vacation_info, plan, raw) # production: expectations derived from the request
```

**Task success** (goal completion) = `parse` + every B1 grader + every B2 grader passed
(`task_succeeded()`). This is the headline number.

**Adding a grader:** decorate it with `@grader("B<n>")`, append it to `GRADERS`, and write a
mutation test that breaks `sample_plan` in one way and asserts that *only* the new grader fails
(see `tests/test_grounding_graders.py`).

## 3. Harness: the proctor

**What:** runs cases × repeats × model × prompt version, calls the LLM (or the cache), grades every
reply, and writes one `EvalRecord` per run.

| | |
|---|---|
| Code | `evals/harness/runner.py`, `cache.py`, `report.py`, `dataset.py` |
| Output | `evals/results/<UTC>_<mode>/{records.jsonl, report.md, report.json}` (gitignored) |

```bash
python -m evals.harness.runner --mode smoke                       # 3 cases × 1 ≈ 3 calls
python -m evals.harness.runner --mode full --judge                # 8 cases × 3 repeats + judge ≈ 32 calls
python -m evals.harness.runner --mode full --cache replay-only    # re-grade cached replies, 0 calls
```

**Why repeats:** the LLM is non-deterministic, so one run says little. With 3 repeats the report
gives:
- **pass^k:** the case passed on *every* repeat, so it works reliably
- **pass@k:** the case passed at least once, so it *can* work
- **flaky cases:** pass@k but not pass^k

**Why record/replay:** each reply is cached under a key built from case, dataset, prompt version,
model, repeat and a **hash of the system prompt**. So:
- improving a grader costs nothing: replay the stored replies
- any prompt edit misses the cache automatically, so you can never grade a stale reply by accident

**Budget rule:** a full run stays within ~50 LLM calls.

## 4. Thresholds: where "good enough" lives

The harness reports numbers. Thresholds decide what those numbers *mean*. There are two kinds.

**a) Absolute rules** (from the metrics catalogue in `00-layer-b-overview.md`):

| Metric | Rule |
|---|---|
| hallucination rate | **0%**: any fabricated fact is a regression, whatever the baseline |
| parse rate, task success, weather safety | hard metrics: must not drop below the baseline |
| interest coverage, reasoning consistency, reason grounding | soft: reported as deltas, never gate |
| judge metrics | report-only until ≥ 80% agreement with blind human labels (`evals/harness/calibration.py`) |

**b) The accepted baseline:** a frozen snapshot of the metrics for one
`(dataset@version, model, prompt version, mode)`.

```
evals/baselines/itinerary_golden@1.0.0__gpt-4.1-mini__v1__full.json
evals/baselines/itinerary_golden@1.0.0__gpt-4.1-mini__v1__smoke.json
```

For v1 full, the baseline is task success **58.3%**, hallucination **0%**, weather safety **65.2%**,
pass^3 **50%**, with flaky cases G1 and G6. These aren't targets. They're **the bar a change must
not fall below.**

`compare()` in `evals/harness/baseline.py` flags a regression when:
1. task success or any hard grader's pass rate drops, or
2. the hallucination rate is above 0, or
3. **per case**, a hard grader fails that never failed on that case in the baseline (a "new case
   failure"). This catches a change that fixes one case and breaks another while the average stays
   flat.

```bash
python -m evals.harness.runner --mode full --prompt-version v3 --compare-to v1   # adds "Comparison vs baseline"
python -m evals.harness.runner --mode full --accept-baseline                      # move the bar, on purpose, via a PR
```

**The bar moves only on purpose:** a reviewed PR that commits a new file in `evals/baselines/`.

## 5. CI: the gate on every risky PR

| | |
|---|---|
| Workflow | `.github/workflows/evals-smoke.yml` (PRs to `main`); `evals-full.yml` (manual) |
| Trigger paths | `prompts/**`, `agents/**`, `models.py`, `quality/**`, `evals/harness/**`, `evals/datasets/**`, `evals/baselines/**` |
| Code | `evals/harness/gate.py` |
| Secrets | `OPENAI_API_KEY` (secret); `OPENAI_BASE_URL`, `PROMPT_VERSION` (repo variables) |

What the gate does (`python -m evals.harness.gate --prompt-version latest`):

```
smoke run: newest prompt  vs  baseline of the SHIPPED prompt (PROMPT_VERSION)
      │
      ├── no regression ───────────────────────────────► exit 0  PASS
      │
      └── suspicious cases (new hard failure / any hallucination)
             │  re-run ONLY those cases once, fresh repeat index (a real LLM call, not the cache)
             ├── fails again ──────────────────────────► exit 1  REGRESSION (PR blocked)
             └── passes ───────────────────────────────► exit 0  PASS (reported as flaky)
      (no baseline found ──────────────────────────────► exit 2)
```

**Why the confirm run:** with only 3 smoke cases, one unlucky sample would block good PRs. A
single re-run on the flagged cases separates real regressions from noise and costs about 1–3 calls.

The verdict goes to the job summary, and `evals/results/` is uploaded as the `smoke-eval-report`
artifact.

**History:** prompts v2 and v3 were both stopped here or in the full comparison, so **v1 is still
live.** That is the pipeline working as intended: "different" was not "better."

## 6. Production signal: closing the loop

After deploy, the same graders keep running on real traffic.

**Online grading** (`app.py`, `ui/render.py`):
- every generation runs `run_graders(GradingInput.for_request(...))`
- the inspector's "Quality checks" tab shows the results
- each generation emits **exactly one** `llm_run` JSON line (`observability/events.py`) with
  `trace_id`, model, prompt version, grader verdicts, latency, tokens and cost
- 👍/👎 emits a `feedback` event with the same `trace_id`

**Where the events go:**

```
stdout → Cloud Logging → sink agentsville-llm-events → BigQuery agentsville_observability
        └→ log-based metrics → dashboard "AgentsVille – AI quality & ops" → alerts A1–A9
```

The views are in `observability/bigquery/*.sql`. The alerts compare online rates with the offline
baseline. For example, A2 fires on more than 60% task-success failures over 6 h, against a v1
baseline of about 42%. See `plan/07-layer-c-monitoring/03-c3-alerting.md`.

**Back into golden data (the flywheel):**

```bash
python -m evals.harness.promote mine --days 7
#   BigQuery runs with a failed hard grader or 👎 → evals/datasets/itinerary_golden/candidates.jsonl
#   (gitignored; synthetic traveler names; review.status = draft)

# a human reads the candidates and picks the ones worth keeping

python -m evals.harness.promote approve P1 P3 --reviewer <name>
#   → v1.1.0.jsonl + manifest changelog (minor bump) → PR → record a new baseline on the new version
```

That takes us back to stage 1 with a dataset that now contains a real production failure.

**Privacy:**
- real traveler names stay in private GCP; committed cases always get synthetic names
- the raw LLM reply is logged only when a hard grader failed
- feedback comments are capped at 500 characters

---

## Common tasks, mapped to stages

| I want to… | Stages touched | Steps |
|---|---|---|
| Try a new prompt | 3 → 4 → 5 | Add `prompts/itinerary/v<N>.md` (never edit an evaluated version), run `runner --mode full --prompt-version v<N> --compare-to v1`, open a PR, and the gate runs automatically |
| Add a grader | 2 → 3 → 4 | Write the grader and its mutation test, run `runner --cache replay-only` (free), then re-record the baseline via a PR if the metrics change |
| Add a golden case | 1 → 4 | Draft it, have it approved, bump the minor version plus the changelog, and record a new baseline for the new dataset version |
| Investigate an alert | 6 → 1 | Look up the `trace_id` in BigQuery, run `promote mine`, review, and promote the case |
| Understand a failed PR gate | 5 → 4 | Open the job summary or the `smoke-eval-report` artifact to see which case and grader regressed versus the baseline |

## Further reading

- `plan/05-layer-b-evals/00-layer-b-overview.md`: design decisions and the metrics catalogue
- `plan/05-layer-b-evals/01-b0-foundation.md` … `06-b5-feedback-loop.md`: one plan per slice
- `plan/05-layer-b-evals/graders-explained.md`: how a single grader works
- `plan/07-layer-c-monitoring/`: logging, metrics, alerts
