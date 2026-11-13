# Layer B – B4 Consistency, regression gating & eval-driven improvement

Status: **Approved**: Q1 (b) confirm run · Q2 GitHub secret OK · Q3 ≈ 51 calls OK · Q4 ship v2 if it wins (via PR)

Parent plan: `00-layer-b-overview.md` · Builds on: B0–B2 (merged), B3 (PR #8)

## 1. Question this slice answers

**"Is quality stable across runs, and does a change actually make it better (without breaking
anything)?"**

B0–B3 *measure*. B4 closes the loop:
1. measure the baseline
2. change the prompt
3. prove the change with numbers
4. gate future changes in CI
5. ship the winner to the live app

## 2. The v1 baseline (already measured, 0 calls)

From the cached full run (`itinerary_golden@1.0.0`, gpt-4.1-mini, prompt v1, 24 runs):

| Metric | v1 | Gap → v2 target |
|---|---|---|
| Task success | **58%** | ↑ |
| Parse rate | 96% (G1#2 never wrote its JSON) | 100%: always end with a fenced FINAL OUTPUT |
| Hallucination | 0% | must stay 0% |
| Weather safety | 65% (8 × the 06-12 morning hike) | 100%: state the **whole-day** policy (B2 decision) |
| Cost arithmetic | 91% (G1#1 per-person pricing; G6#2 undercount) | 100%: state **group pricing** (B2 decision) |
| Reason grounding (keyword) | 74% (G5 "theatre" stretches, "Hiro's art") | ↑: claim only real interest matches |
| Reasoning covers choices | 91% (G6 leaves picks unexplained) | ↑: explain every chosen activity |
| Activities per day | 1.0–1.7 for most cases | ↑: fuller days when the budget allows (soft) |

## 3. Prompt versioning (`prompts/itinerary/`)

- Extract today's prompt **unchanged** into `prompts/itinerary/v1.md`, using `string.Template`
  placeholders (`$schema`, `$weather`, `$activities`) so the JSON braces need no escaping.
- `build_system_prompt(vacation_info, version=None)`: `version` falls back to the `PROMPT_VERSION`
  env var, normalized to lowercase (the GitHub variable is `V1` today), then to `v1`.
- **The critical test:** the rendered v1 is **byte-identical** to the current prompt. Then the cache
  keys (which include the system-prompt hash) don't change, and the whole existing cache stays valid
  as the v1 baseline. That's free.
- `PromptTrace` and `EvalRecord` already carry `prompt_version`. The live app records the version it
  used, so Layer C can split metrics by version.

## 4. Prompt v2 (`prompts/itinerary/v2.md`)

v1 plus explicit rules, each traced to a measured failure:

| Rule added in v2 | Fixes |
|---|---|
| "On any day whose forecast is **rainy or thunderstorm**, choose only **indoor** activities or ones that **explicitly move indoors** in rain, **regardless of the time of day**" | 8 weather violations (whole-day policy, B2) |
| "`total_cost` = the **sum of the activity prices**. Prices are **per group**, never multiplied by travelers" | G1#1, G6#2 |
| "Only say an activity matches an interest if that interest is in its `related_interests`. If a traveler's interest isn't offered, **say so plainly**; don't stretch" | G5, "Hiro's art" |
| "In Day-by-Day Planning, **name every activity** you put in the final plan" | unexplained choices |
| "When the budget allows, aim for **2–3 non-overlapping activities per day**" | under-filled days (soft) |
| "Always finish with `FINAL OUTPUT:` and the JSON inside a ```` ```json ```` fence" | G1#2 (no JSON), G8#0 (unfenced) |

Unit tests assert that v2 contains each rule. Whether the rules *work* is what the eval measures.

## 5. Consistency metrics (report)

- **pass^k:** a case counts only if **all k repeats** succeed. This is "reliably works" (k = 3).
- **pass@k:** a case counts if **at least one** repeat succeeds. This is "can work".
- **Flakiness:** cases where pass@k = 1 but pass^k = 0. These are the non-determinism hot spots.
- Spread across repeats (min/max) of activities per day and budget utilization.

## 6. Baselines and regression comparison

- **Baseline file:** `evals/baselines/itinerary_golden@1.0.0__gpt-4.1-mini__v1.json`, written from
  the cached v1 run with 0 calls. It holds the overall metrics, per-grader pass rates, per-case
  task-success and pass^k, plan shape, and the judge metrics (flagged `report_only` while calibration
  is pending).
- **`compare(run, baseline)` → regression report:**
  - per-metric deltas
  - **regressions:** a hard grader whose pass rate drops by more than the tolerance (§9 Q1), or **any**
    hallucination
  - improvements
- Report section: **"v2 vs baseline"**, a delta table plus per-case task-success changes.
- **Accepting a new baseline is explicit** (`--accept-baseline`) and goes through a PR, so the bar only
  moves on purpose.

## 7. CI gating

- **`evals-smoke.yml`:** on PRs touching `prompts/**`, `agents/**`, `models.py` or `quality/**`.
  - Runs the smoke set (G1, G2, G5 × 1 = **3 calls**, ≈ $0.02) and compares against the smoke baseline.
  - **Fails the PR on a hard-grader regression or any hallucination.**
  - Needs `OPENAI_API_KEY` as a **GitHub Actions secret** (§9 Q2). `OPENAI_BASE_URL` and `MODEL` come
    from the existing repo variables.
- **`evals-full.yml`:** manual (`workflow_dispatch`). The full run, plus the judge if requested.
  Uploads `report.md` and `records.jsonl` as artifacts.
- Other PRs run only Layer A (free), as today.
- **Flake guard:** a non-deterministic model can fail a smoke case by chance (e.g. G1#2's missing
  JSON). The policy for that is §9 Q1.

## 8. End to end for this scenario

1. Prompt templating with v1 byte-identical; tests prove the cache stays valid (free).
2. Consistency metrics, baseline writer, compare, and tests; **write the v1 baseline from the cache** (0 calls).
3. Prompt v2 with rule tests (free).
4. **v2 experiment:** smoke (3 calls), then full (24 planner calls), plus judge (24 calls), giving the
   **v1-vs-v2 report**. ≈ 51 calls, ≈ $0.17 (§9 Q3).
5. CI workflows: smoke gate + manual full run.
6. **Ship decision:** if v2 beats v1 on task success with no hard regression and 0% hallucination, set
   `PROMPT_VERSION=v2` (GitHub variable → deploy). The live app then uses v2, and its Quality checks
   tab shows the result. Otherwise keep v1 and record why.
7. **Layer C hook:** the accepted baseline is what C3's drift alerts compare live pass rates against.

## 9. Decisions (made: the recommended options)

1. **Regression tolerance and flake policy for the CI smoke gate** *(recommended: (b))*
   - (a) **Strict:** any hard-grader failure on a case that passed in the baseline fails CI. Simple, but
     occasionally flaky.
   - (b) **Strict with a confirm run:** on a new failure, re-run **only that case once**. It fails CI
     only if it fails again, so 1 extra call at most per failing case.
   - (c) **Tolerance:** fail only if overall hard pass rates drop by more than 10 points. Too coarse for
     3 cases.
2. **Store `OPENAI_API_KEY` as a GitHub Actions secret** for the eval workflows? Set with
   `gh secret set`, piped from `.env` and never printed. It's encrypted, and visible only to
   workflow runs.
3. **Budget for the v2 experiment:** ≈ 51 calls (3 smoke + 24 full + 24 judge), ≈ $0.17. That's slightly
   over the ~50-call guideline because of the judge. Alternatives: skip the judge (27 calls), or judge
   only the 8 repeat-0 runs (35 calls).
4. **Ship rule:** if v2 wins, should I switch the live app to v2 (`PROMPT_VERSION=v2`) as part of B4?
   *(recommended: yes, through a PR with the comparison report)*

## 10. Implementation steps

Branch `feature/layer-b-b4-regression` (rebased onto `main` after PR #8 merges). Phase comments:
`# Phase 5 – B4 Step N: …`.

| Step | Purpose | Depends on | Files |
|---|---|---|---|
| 1 | Prompt templates, v1 byte-identical | B3 merged | `prompts/itinerary/v1.md`, `agents/itinerary.py`, `llm.py` (version helper), tests |
| 2 | pass^k / pass@k, baseline writer, compare; v1 baseline (0 calls) | 1 | `evals/harness/baseline.py`, `report.py`, `runner.py`, `evals/baselines/*.json`, tests |
| 3 | Prompt v2 + rule tests | 1 | `prompts/itinerary/v2.md`, tests |
| 4 | **v2 experiment (with your permission)**; comparison report in the PR | 2, 3 | — |
| 5 | CI eval workflows (+ secret, with your permission) | 2 | `.github/workflows/evals-smoke.yml`, `evals-full.yml` |
| 6 | Ship v2 if it wins; docs | 4 | GitHub variable, `CLAUDE.md`, plan docs |

## 11. New concepts
- **Eval-driven development:** every prompt rule traces to a measured failure, and every change is
  judged against a baseline.
- **pass^k vs pass@k:** reliability vs capability under non-determinism.
- **Baselines and regression gates:** the bar only moves on purpose (accepted via PR).
- **Flakiness in LLM CI:** confirm runs vs tolerances.
- **Prompt versioning as configuration:** the live app switches by env var, with an instant rollback.

## 12. Done when
- v1 renders byte-identically, and the existing cache is reused (0 calls).
- The v1 baseline is committed, and compare flags regressions in tests.
- The v1-vs-v2 report exists, with task success, hallucination and per-grader deltas.
- The smoke gate runs on prompt PRs and blocks a seeded regression.
- The ship decision is made and recorded. If v2 wins, the live app runs v2.
