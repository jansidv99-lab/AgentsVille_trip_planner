# Layer B – B3 Relevancy & reasoning verification

Status: **Approved**: ~22 judge calls OK; labels given in chat

Parent plan: `00-layer-b-overview.md` · Builds on: B0, B1, B2 (merged) · Background: `graders-explained.md`

## 1. Question this slice answers

**"Is the plan relevant to these travelers, are its reasons honest, and does its step-by-step
reasoning (ANALYSIS) actually match the final plan?"**

This is Part A's **reasoning verification**. Tool-use accuracy waits for the Part B extension.

## 2. Evidence from the cached full run (0 calls)

| Signal | Result | What it teaches |
|---|---|---|
| ANALYSIS has all 5 required steps | 22/22 parsed runs | A structure check is a cheap regression guard, not a discriminator |
| Interest coverage (naive) | mostly full; gaps e.g. G1#1 Hiro 1/3, G6#2 Yuri 2/4 | Coverage must count only **coverable** interests: G1's "Yuri 3/4" is because comedy is only offered on 06-13, outside the trip |
| Final activities discussed in the ANALYSIS | 84/88 (95%); misses in 6-day G6 plans | Long plans skip explaining some choices: a soft "unexplained choice" signal |
| Reasons naming an interest the activity lacks (keyword) | 10 flagged: **8 real** (6 × G5 "theatre", "Hiro's art" for a dancing/writing event, "music and art" for a music-only event) + **2 false alarms** ("after the morning hiking event", "complements tennis activity") | Keywords catch most over-claims but can't read context, so we need a **judge**, and **calibration** to know how far to trust each |
| Regex for "total" inside the ANALYSIS | noisy (picks up stray numbers) | Free-text consistency needs judgement, so this goes to the judge rather than a regex |

## 3. Deterministic graders (`quality/graders/relevancy.py`, `reasoning.py`; online-safe, in `GRADERS`)

| Grader | Severity | Measures | Prod mode |
|---|---|---|---|
| `interest_coverage` | soft | Per traveler: covered ÷ **coverable** interests. "Coverable" = offered by a weather-safe activity on the trip dates (whole-day policy, approved labels). Passes if every traveler with ≥ 1 coverable interest gets ≥ 1 | ✅ |
| `must_include` | soft | Golden `must_include_activity_ids` present (e.g. G4's tennis rally) | ➖ not applicable |
| `reason_grounding` | soft | Reasons naming an interest the activity doesn't have, flagged with quotes. Known false-alarm mode: contextual mentions; the judge adjudicates | ✅ |
| `reasoning_covers_choices` | soft | Every final activity is discussed (by ID or name) in the ANALYSIS | ✅ |
| `analysis_structure` | soft | The 5 required ANALYSIS steps are present | ✅ |

All are **soft**: they're quality signals tracked over time, not task-success gates (task success
stays B0 + B1 + B2). Each gets a mutation test that fails exactly that grader.

## 4. LLM judge (`quality/graders/judge.py`, offline only, not in the online registry)

- **Model:** `JUDGE_MODEL` env var (default `gpt-4.1-mini`, as decided), temperature 0.
- **Structured output:** `client.beta.chat.completions.parse(response_format=JudgeScore)`. The
  `InstrumentedClient` is extended to also measure `beta…parse` calls, so judge latency, tokens and
  cost are recorded too.
- **Judge input:**
  - the traveler request
  - a compact view of the final plan (day, activity, its real interests and setting, the reasons)
  - the ANALYSIS text
  - a compact list of the activities **available** on the trip dates. This lets the judge rate
    relevancy against what was possible, not an ideal.
- **`JudgeScore`** (Pydantic), each field with a rubric and anchored examples:

  | Field | Scale | Rubric anchor |
  |---|---|---|
  | `relevancy` | 1–5 + rationale | 5 = every traveler's coverable interests are well served given what's available; 1 = choices ignore the travelers |
  | `coherence` | 1–5 + rationale | 5 = sensible daily flow and pacing; 1 = random or contradictory |
  | `reasons_honest` | yes/no + quoted `stretched_reasons` | "no" if any reason claims a match the activity doesn't have (the G5 "close to theatre" pattern); contextual mentions are fine |
  | `reasoning_faithful` | yes/no + evidence | "no" if the ANALYSIS decides X but the final plan does Y (e.g. "avoid outdoor on the 12th", then schedules it) |

- **Metrics:**
  - **answer relevancy** = mean of (relevancy − 1) / 4, in 0–1
  - coherence (same normalization)
  - reasons-honest rate
  - reasoning-faithful rate
- **Judge cache:** keyed by the planner reply's cache key, `JUDGE_MODEL` and the hash of the judge
  prompt, so judgements re-run for free (`--cache replay-only`).
- **Harness:** `--judge` flag. Judge verdicts are appended to `EvalRecord.grader_results` (slice
  `B3`, severity `soft`). The report adds the judge calls and cost.

## 5. Calibration: can we trust the judge (and the keyword heuristic)?

1. **Sample:** 10 cached plans, stratified across cases (G5 ×2, G6 ×2, and one each of G1, G2, G3,
   G4, G7, G8). These include the 10 keyword-flagged reasons.
2. **You label each** in `evals/calibration/b3_labeling_sheet.md`, a readable sheet I generate:
   - relevancy 1–5
   - reasons honest yes/no
   - reasoning faithful yes/no

   Your labels are stored in `evals/calibration/b3_human_labels.v1.jsonl` (versioned, same rules as
   datasets).
3. **Agreement report** (`evals/harness/calibration.py`, free once the judge is cached):
   - relevancy: exact and ±1 agreement
   - binary fields: agreement % plus the confusion counts
   - the **keyword heuristic vs your labels** on reason honesty (its precision and recall)
4. **Trust rule:** a judge metric may become a **gate** (in B4 regression checks) only if it agrees
   with you at least **80%**. Otherwise it stays report-only. The same-family bias (the judge and the
   planner are both 4.1-mini) is measured here, not assumed away.

## 6. End to end for this scenario

1. **Deterministic graders + mutation tests** (free).
2. **Replay re-grade** of the full run (0 calls). This gives the coverage, reason-flag and
   covers-choices rates.
3. **Judge module + instrumented `parse`** + tests with a fake client (free).
4. **Judge run on the 22 parsed cached plans: about 22 live judge calls** (small structured outputs,
   ≈ $0.03–0.05). **I'll ask first.** No new planner calls.
5. **Calibration:** I generate the labeling sheet, you label 10 items, and the agreement report
   decides which judge metrics can be trusted.
6. **Report section** "Relevancy & reasoning (B3)"; the Quality checks tab shows the deterministic B3
   graders (no judge online); docs.

**Layer C hook:** the deterministic B3 signals (coverage, reason flags) get logged per live run in C1.
The judge stays offline; C3 may schedule it later for sampled drift checks.

## 7. Implementation steps

Branch `feature/layer-b-b3-relevancy`. Phase comments: `# Phase 5 – B3 Step N: …`.

| Step | Purpose | Depends on | Files |
|---|---|---|---|
| 1 | Deterministic relevancy/reasoning graders + mutation tests | B2 | `quality/graders/relevancy.py`, `reasoning.py`, `__init__.py`, `tests/test_relevancy_graders.py` |
| 2 | Replay re-grade (0 calls) | 1 | — |
| 3 | Judge (`JudgeScore`, rubric prompt, cache) + instrumented `parse` + `--judge` flag + tests | 1 | `quality/graders/judge.py`, `llm.py`, `evals/harness/runner.py`, `tests/test_judge.py` |
| 4 | **Judge run (~22 calls, with your permission)** | 3 | — |
| 5 | Labeling sheet → **your labels** → agreement report | 4 | `evals/calibration/*`, `evals/harness/calibration.py`, tests |
| 6 | Report section + Quality checks tab + CLAUDE.md | 2, 5 | `evals/harness/report.py`, `ui/render.py`, tests, `CLAUDE.md` |

## 8. Decisions needed
1. **Judge budget:** about **22 judge calls** (all parsed cached plans, one judgement each), ≈ $0.03–0.05.
   OK?
2. **How you label:** I generate a readable markdown sheet with 10 items. You either **reply in chat**
   with compact scores (e.g. `1: 4 y y`), which I record into the JSONL, *(recommended)* or edit
   the sheet yourself.

## 9. New concepts
- **Relevancy against what's possible:** coverable vs desired interests.
- **Heuristic vs model-based graders:** precision and recall measured against humans.
- **LLM-as-judge:** rubrics, anchors, temperature 0, structured output.
- **Calibration and inter-rater agreement:** exact, ±1, confusion counts. A judge earns trust; it
  isn't assumed.
- **Faithfulness vs plausibility:** a well-written ANALYSIS that the final plan doesn't follow.

## 10. Done when
- Each deterministic grader has a mutation test, and Layer A is green in CI.
- The replay re-grade report shows the B3 signals with 0 calls.
- The judge has run on the cached plans, with its calls and cost reported.
- Your 10 labels are stored; the agreement report states which judge metrics are trustworthy.
- The live Quality checks tab shows the deterministic B3 graders.
