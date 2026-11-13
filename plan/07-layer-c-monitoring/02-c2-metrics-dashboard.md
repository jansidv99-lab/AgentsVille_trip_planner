# Layer C – C2 Log-based metrics + Cloud Monitoring dashboard

Status: **Done** (decisions in `03-c3-alerting.md` §6; results in its §8)

Builds on: C1 (events in Cloud Logging + BigQuery, merged and verified live) · Feeds: C3 alerts

## 1. Purpose

**"Is the app healthy and is quality holding up, right now?"**

C1 made every live itinerary a structured event, analyzable in BigQuery (good for *investigation*).
C2 turns the same events into **real-time metrics and one dashboard** in Cloud Monitoring (good for
*operations*). C3 alerts on them.

| Layer | Tool | Good for |
|---|---|---|
| C1 | BigQuery views (`daily_quality`, `input_profile`, …) | slicing, drift analysis, mining failures (B5) |
| **C2** | **Log-based metrics + a dashboard** | **live trends at a glance** |
| C3 | Alert policies + notification channel | being told when something breaks |

## 2. What exists (read-only check)
- **Cloud Monitoring is a clean slate for this app:** no dashboards, alert policies, notification
  channels or uptime checks. There's one unrelated log metric (`sql_planner_pm_planner_ms`).
  Everything new is prefixed `agentsville_`.
- **Built-in Cloud Run metrics** (requests, 5xx, latency, instances, memory) come free.

## 3. Log-based metrics (`deploy/monitoring/log_metrics.yaml`)

Every filter starts with this service's app events:
`resource.type="cloud_run_revision" AND resource.labels.service_name="agentsville-trip-planner" AND jsonPayload.app="agentsville"`.

| Metric | Kind | Extra filter | Labels | Used for |
|---|---|---|---|---|
| `agentsville_llm_runs` | counter | `event="llm_run"` | `prompt_version`, `model`, `task_success` | throughput; denominator for rates |
| `agentsville_task_failures` | counter | `event="llm_run" AND task_success=false` | `prompt_version` | task success rate (= 1 − failures/runs) |
| `agentsville_hallucinations` | counter | `event="llm_run" AND hallucination=true` | `prompt_version` | must stay 0 |
| `agentsville_weather_violations` | counter | `event="llm_run" AND hard_failed:"weather_safety"` | `prompt_version` | the known v1 weak spot |
| `agentsville_parse_failures` | counter | `event="llm_run" AND parsed=false` | `prompt_version` | reply-format health |
| `agentsville_llm_errors` | counter | `event="llm_error"` | — | API, auth and network failures |
| `agentsville_feedback` | counter | `event="feedback"` | `rating` (up/down) | 👎 share |
| `agentsville_llm_latency_ms` | distribution | `event="llm_run"`, value `latency_ms` | `prompt_version` | p50 / p95 latency |
| `agentsville_llm_cost_usd` | distribution | `event="llm_run"`, value `cost_usd` | `prompt_version` | spend per run and per day |
| `agentsville_llm_tokens` | distribution | `event="llm_run"`, value `completion_tokens` | `prompt_version` | output-length drift |

**Contract test (Layer A):** every field a metric filter or extractor references (`event`,
`task_success`, `hallucination`, `hard_failed`, `parsed`, `latency_ms`, `cost_usd`, …) must exist in
the events `observability/events.py` emits. If someone renames a field, CI fails instead of the
metric silently going flat.

Note: log-based metrics only count events **from creation onward** (no backfill). The BigQuery views
cover history.

## 4. Dashboard `AgentsVille – AI quality & ops` (`deploy/monitoring/dashboard.json`)

| Row | Tiles |
|---|---|
| **Quality** | task success rate (ratio, per prompt version) · hallucinations (count, should be flat 0) · weather violations · parse failures |
| **Users** | runs per hour · feedback 👍 vs 👎 · 👎 share |
| **Performance & cost** | LLM latency p50/p95 · cost per hour (sum) · completion tokens p50 |
| **Platform** (built-in Cloud Run) | request count · 5xx responses · instance count · container memory |
| **Errors** | `agentsville_llm_errors` · a logs panel showing WARNING+ app events |

Each quality tile shows the **B4 baseline** as a threshold line (v1 full run: task success 58%,
hallucination 0%) for context.

## 5. Steps

| Step | Purpose | Files |
|---|---|---|
| 1 | Metric definitions + contract test | `deploy/monitoring/log_metrics.yaml`, `tests/test_monitoring_config.py` |
| 2 | Dashboard JSON + structure test (every tile references a defined metric or a Cloud Run metric) | `deploy/monitoring/dashboard.json`, tests |
| 3 | `deploy/monitoring-setup.sh` (idempotent: create-or-update metrics, dashboard), **with your permission** | script |
| 4 | Verify: dashboard renders; metrics receive points (needs live traffic or the synthetic events in C3 §5) | — |

Phase comments: `# Phase 7 – C2 Step N`.
