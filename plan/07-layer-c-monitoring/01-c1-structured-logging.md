# Layer C – C1 Structured logging + BigQuery sink

Status: **Approved** (decisions recorded in B5 §8). Prerequisite of B5 (`plan/05-layer-b-evals/06-b5-feedback-loop.md`)

## 1. Purpose

Make every live itinerary **observable and queryable**:
- one structured log event per LLM run
- one per user feedback

Both flow from Cloud Run to Cloud Logging, and through a log sink into **BigQuery**. This is the
smallest Layer C piece Layer B needs. Dashboards and alerts come later (C2, C3).

## 2. What already exists (read-only checks)

- **Cloud Run:** the app runs in `asia-south1`, and its stdout already goes to Cloud Logging.
- **BigQuery** API is enabled. Only the default `_Required` / `_Default` log sinks exist.
- **`EvalRecord`** (`quality/schema.py`) was designed in B0 as the single record shape for offline and
  production runs. C1 emits it with `source="prod"`.
- **The app already computes online grades:** the Quality checks tab runs the deterministic graders on
  every itinerary (`GradingInput.for_request`). C1 logs those same results.

## 3. Events (`observability/events.py`)

Each event is **one JSON line on stdout**. Cloud Run's logging agent parses it into `jsonPayload`,
and `severity` and `message` are recognized automatically.

| Event | Emitted when | Key fields |
|---|---|---|
| `llm_run` | once per generated itinerary (in `run_agent`, **not** on Streamlit re-runs) | `trace_id`, `prompt_version`, `model`, `latency_ms`, tokens, `cost_usd`, `parsed`, `error`; **compact grader results** (name, slice, severity, passed, score); `task_success`, `hallucination`; **request features** for drift: number of travelers, interests (multiset), ages, budget, trip length, dates |
| `feedback` | the user submits 👍/👎 (B5) | `trace_id`, `rating`, `comment`, `prompt_version` |

Common envelope: `app="agentsville"`, `event`, `schema_version`, `severity`, `message`.

**Privacy and volume** (decisions in §6):
- Traveler **names are logged** (decision). They're kept private in GCP and replaced with synthetic
  names before anything is promoted into the public repo.
- The **raw LLM reply** is logged **only when** a hard grader failed (decision).

## 4. GCP resources (`deploy/observability-setup.sh`, idempotent, run with your permission)

| Resource | Name | Notes |
|---|---|---|
| BigQuery dataset | `agentsville_observability` (`asia-south1`) | dedicated, same pattern as the other `agentsville-*` resources |
| Log sink | `agentsville-llm-events` | filter: this Cloud Run service **and** `jsonPayload.app="agentsville"`; partitioned tables |
| IAM | the sink's writer identity → `roles/bigquery.dataEditor` **on that dataset only** | least privilege |
| Views | `llm_runs`, `feedback`, `runs_with_feedback` (joined on `trace_id`), `daily_quality` | SQL kept in `observability/bigquery/*.sql`, applied by the script |

The sink creates its table on the first matching event. The views are created after that (the script
re-runs safely).

## 5. Steps

| Step | Purpose | Files |
|---|---|---|
| 1 | Event schema + emitter + tests (capture stdout; no names; reply only on failure) | `observability/events.py`, `tests/test_events.py` |
| 2 | App: emit `llm_run` once per generation (`AppTest`: exactly one event, the same `trace_id` as the inspector) | `app.py`, `tests/test_app.py` |
| 3 | Setup script + SQL views (dataset, sink, IAM) – **with your permission** | `deploy/observability-setup.sh`, `observability/bigquery/*.sql` |
| 4 | Deploy (merge) → generate 1 itinerary on the live app → see the row in BigQuery | — |

Phase comments: `# Phase 7 – C1 Step N: …`.

## 6. Decisions (asked in the B5 plan)
See B5 §8: privacy (names), raw-reply logging, GCP resource creation.
