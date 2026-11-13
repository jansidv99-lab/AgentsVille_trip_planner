# Layer B – B5 Production feedback loop & dataset lifecycle

Status: **Approved**: names kept in logs · raw reply only when a hard grader fails · comment ≤ 500 chars · BigQuery OK · live check by Claude

Parent plan: `00-layer-b-overview.md` · **Prerequisite:** C1 (`plan/07-layer-c-monitoring/01-c1-structured-logging.md`)
· Builds on: B0–B4

## 1. Question this slice answers

**"How does production traffic make the evals better?"**

B0–B4 evaluate a fixed golden dataset offline. B5 connects the **live app** to that loop:

```
live itinerary ─▶ online graders ─▶ llm_run event ─┐
user 👍/👎 + comment ─▶ feedback event ────────────┼─▶ Cloud Logging ─▶ BigQuery (C1)
                                                   │
          promote.py ◀── runs with 👎 or failed hard graders (SQL)
               │
     draft EvalCases ─▶ human review ─▶ itinerary_golden v1.1.0 (minor bump, changelog)
               │
       future evals include real failures  →  better prompts (B4)  →  better production
```

This is the **data flywheel**. It also covers dataset versioning across dev and prod.

## 2. Tracing (end to end, by `trace_id`)

- **Already exists:** `PromptTrace.trace_id` (B0), shown in the inspector caption, and `EvalRecord.trace_id`.
- **C1** logs `llm_run` with the `trace_id`. **B5's feedback** carries the same `trace_id`, so a
  rating joins to the exact prompt version, model, grader verdicts and request.

## 3. Feedback UI (`app.py`, `ui/render.py`)

- Under the itinerary: **"Was this itinerary helpful?"** using `st.feedback("thumbs")`, which is
  available in Streamlit 1.45, plus an optional comment (≤ 500 characters) and a **Send feedback**
  button.
- One feedback per itinerary: state is kept in `session_state` keyed by `trace_id`. After sending, it
  shows "Thanks – feedback recorded".
- Emits a `feedback` event (C1 schema). It's tested with `AppTest`: rating + comment produce exactly
  one event with the right `trace_id`.

## 4. Online drift signals (SQL views; Layer C3 alerts on them)

| Signal | View | Compared with |
|---|---|---|
| Online hard-grader pass rates and task success, per day and prompt version | `daily_quality` | the accepted B4 baseline (v1 full: task success 58%) |
| 👎 share per day and version | `daily_quality` | its own trailing average |
| Input distribution: interests, travelers, budget, trip length | `input_profile` | the golden dataset's profile |

B5 defines and tests these queries. C3 turns them into Cloud Monitoring alerts.

## 5. Candidate mining → dataset v1.1.0 (`evals/harness/promote.py`)

1. **Query** `runs_with_feedback` for the last N days: runs with **👎** or **any failed hard grader**,
   de-duplicated by request features.
2. **Draft** an `EvalCase` per run (`case_id` `P1`, `P2`, …, `review.status = draft`):
   - travelers get synthetic names (no PII)
   - the request comes from the logged features
   - expectations are derived from the request (`max_cost = budget`), plus a note on why the run was
     flagged (failing graders, the user's comment)

   These go to `evals/datasets/itinerary_golden/candidates.jsonl`, which is **not** part of the
   dataset.
3. **Human review**, same rule as G1–G8: you approve or reject each candidate in chat.
4. **Promote** the approved cases into `v1.1.0.jsonl` (minor bump: added cases), with a manifest
   changelog entry ("+P1–P3 from production feedback, 2026-…").
5. **Baselines:** v1.1.0 needs a new accepted baseline. That's one full run on the shipped prompt, done
   later with your permission. Results on v1.0.0 and v1.1.0 are never compared directly, because the
   dataset version is part of every record.

**Seeding while live traffic is low:** to exercise the pipeline end to end before real users exist,
you (or I, with your permission) generate a few itineraries on the live app and rate one 👎. That gives
one real candidate. **I won't fabricate production data.**

## 6. End to end

| Step | Purpose | Depends on | LLM calls |
|---|---|---|---|
| 1 | **C1:** event schema + emitter + tests | B4 | 0 |
| 2 | **C1:** app emits `llm_run` once per generation | 1 | 0 |
| 3 | **B5:** feedback UI + `feedback` event + tests | 1 | 0 |
| 4 | **B5:** SQL views (quality, feedback join, drift profile) + tests against sample rows | 1 | 0 |
| 5 | **C1:** GCP setup (dataset, sink, IAM, views), **with your permission** | 4 | 0 |
| 6 | **B5:** `promote.py` (BigQuery → draft candidates) + tests with injected rows | 4 | 0 |
| 7 | Merge → deploy → **live check:** generate 1–2 itineraries, rate one 👎, see `llm_run` + `feedback` joined in BigQuery, run `promote.py`, review the candidate | 2–6 | **1–2** (live app) |
| 8 | Promote approved candidates → dataset v1.1.0; docs | 7 + your approval | 0 (a new baseline later) |

Branch `feature/layer-b-b5-feedback-loop`, stacked on B4 (PRs #8 → #9 → this). Phase comments:
`# Phase 5 – B5 Step N` and `# Phase 7 – C1 Step N`.

## 7. New concepts
- **Online vs offline evaluation:** the same graders on live traffic, without an answer key.
- **Trace correlation:** one `trace_id` joins request, prompt version, verdicts and user feedback.
- **The data flywheel:** production failures become reviewed golden cases, which feed the next
  prompt iteration.
- **Dataset versioning across environments:** promotions are minor bumps with a changelog, and results
  are only compared within one dataset version.
- **Privacy by design:** no names in logs; raw replies only for cases that need review.

## 8. Decisions (made)

- **Names:** kept in the logs and BigQuery (private GCP). **Safeguard:** `promote.py` replaces names with
  synthetic ones only when writing candidates into the **public** repo.
- **Raw reply:** logged only when a hard grader failed.
- **Comment:** free text, ≤ 500 characters.
- **GCP resources:** BigQuery dataset, sink and IAM approved.
- **Live check:** done by Claude; the 👎 is labeled "pipeline test".
- **Deviation:** `st.feedback` can't be driven by Streamlit 1.45's `AppTest` (an internal TypeError), so
  the UI uses a horizontal `st.radio` (👍 Helpful / 👎 Not helpful, nothing pre-selected). It's
  equivalent for users and fully testable.

### Original questions
1. **Privacy:** don't log traveler names, only anonymized features (interests, ages, budget, dates).
   *(recommended)* Or log the full request?
2. **Raw LLM reply in logs:** only when a hard grader failed or the user gave 👎 *(recommended:
   enough for review, low volume)*, always, or never?
3. **Feedback comment:** free text allowed (≤ 500 characters, stored in BigQuery) *(recommended)*, or
   thumbs only?
4. **GCP resources:** create the BigQuery dataset `agentsville_observability` (`asia-south1`), the log
   sink and its least-privilege IAM? Cost is negligible at this volume.
5. **Live check (Step 7):** may I generate 1–2 itineraries on the live app (1–2 LLM calls) and submit
   one 👎 as a **clearly labeled test** (comment "pipeline test"), which promote.py then treats as a
   test? Or would you rather do it yourself in the browser?

## 9. Done when
- Every live generation logs exactly one `llm_run`, and every rating one `feedback`, joined by
  `trace_id` in BigQuery.
- The drift views return per-day quality, 👎 share and the input profile.
- `promote.py` drafts candidates from real flagged runs; approved ones are promoted into v1.1.0 with a
  changelog.
- Layer A is green (event schema, UI, SQL logic, promote with injected rows).
