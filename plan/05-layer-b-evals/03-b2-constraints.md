# Layer B – B2 Constraint compliance & goal completion

Status: **Approved**: Q1 = group price; activity labels approved as listed in §3

Parent plan: `00-layer-b-overview.md` · Builds on: B0 (merged), B1 (PR #6) · Background: `graders-explained.md`

## 1. Question this slice answers

**"Does the plan satisfy the traveler's hard constraints?"**

| Constraint | What it means |
|---|---|
| Budget | The total cost is within the budget |
| Cost arithmetic | The total equals the sum of the activity prices |
| Coverage | Every trip day has at least one activity |
| No overlaps | No two activities on the same day overlap in time |
| Weather safety | No outdoor activity on a rainy or thunderstorm day |

**Task success** (goal completion for Part A) is a run that parses, has no hallucination (B1), **and**
passes every hard B2 constraint.

## 2. Evidence from the cached B1 full run (0 calls)

I profiled the 24 cached replies (22 parse with the current `main` parser). B2 can be measured
**without any new LLM calls**:

| Finding | Runs | Constraint |
|---|---|---|
| Outdoor hike `event-2025-06-12-0` on the **thunderstorm** day | G2 #0 #1 #2, G6 #1 #2, G7 #0 #1 #2: **8 of 22** | weather safety ❌ |
| `total_cost` 110 but prices sum to 55 (**= 55 × 2 travelers**: priced per person) | G1#1 | cost arithmetic ❌ |
| `total_cost` 90 but prices sum to 100 (undercount) | G6#2 | cost arithmetic ❌ |
| Rainy 06-13 / 06-14 always got the single indoor event (`-13-0`, `-14-3`) | all multi-day runs | weather safety ✅ |
| Spend ranges from the minimum (G6#2: 6 activities over 6 days) to the maximum (G8#2: all 8 activities, 148) | — | utilization (info) |

The G1#1 finding shows a **gap in the spec**: the prompt never says whether a price is per person
or per group, so the model is inconsistent. That's decision **Q1** below.

## 3. Ground truth: activity setting labels (`quality/ground_truth/activity_labels.json`)

Weather safety needs to know whether each activity is indoors. The calendar has no such field, only
descriptions. The labels are drafted from each description's own wording, and **you approve them**
(the same human-in-the-loop rule as the golden dataset).

| Setting | Activities (`event-2025-06-…`) | Evidence (from the descriptions) |
|---|---|---|
| **indoor** (10) | `10-0`, `10-3`, `11-0`, `11-1`, `11-3`, `12-3`, `13-0`, `14-3`, `15-0`, `15-1` | "held indoors", "indoor event", "Held indoors at…", "(Indoors event)" |
| **flex** (2) | `10-2` Artful Athletics, `12-1` Soundtrack Picnic | outdoor, but "in case of rain, we move indoors" / "will move indoors to … Harmony Hall" |
| **outdoor** (12) | `10-1`, `11-2`, `12-0`, `12-2`, `13-1`, `13-2`, `13-3`, `14-0`, `14-1`, `14-2`, `15-2`, `15-3` | "outdoor courts", "open sky", "trails", "held entirely outdoors", "open-air" |

**Rule:** on days whose forecast condition is in `INCLIMATE_WEATHER_CONDITIONS` (`thunderstorm`,
`rainy`, from `project_lib`), `outdoor` is unsafe; `indoor` and `flex` are safe.

**Audits** (Layer A, free):
- Every calendar activity has exactly one label.
- Every case's `allowed_activity_ids_by_date` equals the indoor + flex activities of that date. This
  ties the human-approved dataset expectations to the labels, so the two can never disagree.
- The file carries `review.status`. Graders refuse to run on draft labels.

## 4. Graders (`quality/graders/constraints.py`, deterministic, online-safe)

| Grader | Severity | Fails when | `details` | Prod mode |
|---|---|---|---|---|
| `budget_within_limit` | hard | `total_cost > expectations.max_cost` | total, budget, over_by | ✅ budget from the request |
| `cost_arithmetic` | hard | `total_cost` ≠ the cost rule from Q1 | stated vs computed, diff | ✅ |
| `day_coverage` | hard | a trip day is missing or has fewer than `min_activities_per_day` | missing / underfilled days | ✅ |
| `no_time_overlaps` | hard | two activities on one day overlap (including the same activity twice) | pairs | ✅ |
| `weather_safety` | hard | an `outdoor` activity on a bad-weather day (forecast = truth, not the plan's claim) | `unsafe: {day: [ids]}` | ✅ |
| `plan_shape` | info | — (signal) | activities per day, budget utilization = total / min(budget, max possible spend) | ✅ |

- **Score:** the fraction of items that pass. For example, `weather_safety` = safe bad-weather days ÷
  bad-weather days, which gives 0.67 for G2#0.
- **Not double-counted:** fabricated IDs (B1) are skipped by the B2 graders, as in B1.
- **`TASK_SUCCESS_GRADERS`** = parse + the 5 B1 hallucination graders + the 5 B2 hard graders.

## 5. Metrics and report

- **Task success rate:** share of runs where every grader in `TASK_SUCCESS_GRADERS` passes. **Target
  100%** on approved cases.
- **Per-constraint pass rates**, plus a **weather violations** list (run, date, activity) and
  **cost errors** (run, stated, computed).
- **Plan shape:** mean activities per day and budget utilization per case. This feeds B4's prompt-v2
  target.
- `report.md` gains a **Constraints (B2)** section, and task success becomes the headline metric
  next to the hallucination rate.

**Expected from replaying the cached full run:** weather safety fails in 8 of 22 runs and cost
arithmetic in 2 of 22, so task success is about **55–60%**.

## 6. End to end for this scenario

1. **Labels + audits:** draft labels, the audit tests, then **your approval** (Step 2 gate).
2. **Mutation tests** (free). Each mutation adjusts `total_cost` where needed, so it fails **exactly
   one** grader:

   | Mutation of the sample plan | Expected failing grader |
   |---|---|
   | budget expectation 100 (plan totals 108) | `budget_within_limit` |
   | `total_cost` 107 (prices sum to 108) | `cost_arithmetic` |
   | day 06-11 emptied (total adjusted) | `day_coverage` |
   | the same activity twice on one day (total adjusted) | `no_time_overlaps` |
   | outdoor `event-2025-06-12-0` added on the thunderstorm day (total adjusted) | `weather_safety` |

   Prod mode works too, using the budget from the request.
3. **Replay re-grade** of the cached B1 full run (**0 calls**). This gives the first task success rate
   and confirms the findings in §2.
4. **Live app:** the Quality checks tab picks the B2 graders up automatically through the registry. An
   `AppTest` checks that a storm hike shows as a weather violation.
5. **Layer C hook:** C1 will log `weather_safety` and `budget_within_limit` per live run. These become
   the first production alert candidates.

**Budget for B2: 0 live calls.** Everything is measured from the existing cache.

## 7. Decision (made)

**Q1: what does an activity's `price` mean?** **Decided: (a) group price.**
- **(a) Group price** *(recommended)*:
  - `total_cost` = the sum of activity prices
  - this matches the original course project and the G3 budget-edge design (15 + 15 = 30)
  - G1#1 (55 × 2 = 110) then **fails** `cost_arithmetic`
- **(b) Per person:** `total_cost` = sum × number of travelers. Most cached plans would then fail
  arithmetic, and G3's budget of 30 becomes infeasible for multi-traveler cases.

Either way, B4's prompt v2 should **state the rule explicitly**, since the ambiguity is what causes
the inconsistency.

## 8. Implementation steps

Branch `feature/layer-b-b2-constraints` (rebased onto `main` after PR #6 merges). Phase comments:
`# Phase 5 – B2 Step N: …`.

| Step | Purpose | Depends on | Files |
|---|---|---|---|
| 1 | Draft labels + label and allow-list audits | B1 merged | `quality/ground_truth/activity_labels.json`, `quality/labels.py`, `tests/test_activity_labels.py` |
| 2 | **You approve the labels**; Q1 decided | 1 | labels file |
| 3 | Constraint graders + mutation tests | 2 | `quality/graders/constraints.py`, `quality/graders/__init__.py`, `tests/test_constraint_graders.py` |
| 4 | Report: Constraints section + task success | 3 | `evals/harness/report.py`, `tests/test_eval_harness.py` |
| 5 | Replay re-grade of the full run (0 calls); findings in the PR | 3, 4 | — |
| 6 | AppTest for a storm hike in Quality checks; CLAUDE.md | 3 | `tests/test_app.py`, `CLAUDE.md` |

## 9. New concepts
- **Hard constraints vs preferences:** constraints are pass/fail. Utilization is a signal you tune, not
  a gate.
- **Ground truth you have to create:** labels turn fuzzy descriptions into checkable facts, with a
  human sign-off.
- **Spec gaps show up as inconsistent model behavior:** the per-person vs per-group pricing case.
- **Task success / goal completion:** one composite metric that answers "did the agent do the job?"
- **Cross-checking ground truths:** dataset allow-lists are audited against the labels.

## 10. Done when
- The labels are approved, and both audits pass.
- Each mutation fails exactly its grader. Layer A is green in CI.
- The replay re-grade report shows the task success rate, weather violations and cost errors, with
  0 calls.
- The live Quality checks tab flags a storm hike.
