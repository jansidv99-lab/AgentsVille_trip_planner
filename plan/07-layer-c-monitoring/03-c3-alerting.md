# Layer C – C3 Alerting, drift detection & uptime

Status: **Done** (verified with a synthetic alert test, §8): email (address confirmed in chat; kept out of the repo) · thresholds accepted · synthetic test once · no uptime check · no weekly drift · no billing alert

Builds on: C2 (log-based metrics), B4 (accepted baselines), C1/B5 (BigQuery views)

## 1. Purpose

**"Tell me when something breaks or drifts, before users do."**

Alerts turn the C2 metrics and B4 baselines into notifications. Each one has a clear owner action, so
they're actionable rather than noise.

## 2. Alert policies (`deploy/monitoring/alerts/*.yaml`)

Thresholds come from **measured baselines** (B4: v1 task success 58% → failure ≈ 42%; weather
violations ≈ 35% of runs; hallucination 0%). Rate-based alerts require a **minimum number of runs**,
so one bad itinerary at low traffic doesn't page anyone.

| # | Alert | Condition | Why / action |
|---|---|---|---|
| A1 | **Hallucination detected** | `agentsville_hallucinations` > 0 in 1 h | Fabricated facts are never acceptable. Inspect the run in BigQuery (raw reply logged) |
| A2 | **Task success drift** | failures / runs > **60%** over 6 h **and** ≥ 5 runs | Clearly worse than the v1 baseline (42% failures). Check the prompt version, the model, and provider changes |
| A3 | **Weather-safety spike** | weather violations / runs > **50%** over 6 h **and** ≥ 5 runs | Above the known v1 rate (≈ 35%). The guardrail backlog item would fix this |
| A4 | **LLM errors** | `agentsville_llm_errors` ≥ 3 in 10 min | Key expired, Vocareum quota, network. Check the secret and the provider |
| A5 | **Slow responses** | latency p95 > **60 s** over 30 min | Normal p95 ≈ 31–42 s (B1/B4). Check the provider and the model |
| A6 | **Unhappy users** | 👎 / all feedback > **50%** over 24 h **and** ≥ 5 ratings | Read the comments via `runs_with_feedback`; run `promote.py mine` |
| A7 | **Cost / abuse guard** | runs > **60 per hour** | The app is public with max 2 instances. Unusual volume means unusual spend |
| A9 | **Server errors** | Cloud Run 5xx > 0 over 10 min | Platform-level failures |

Each policy carries **documentation** (what it means, the first steps, links to the BigQuery view
and the dashboard) and **auto-closes** after 1 h without recurrence.

## 3. Drift detection: three kinds (closing the master-plan loop)

| Drift | Signal | Mechanism |
|---|---|---|
| **Output drift** | online task success, weather, hallucination | A1–A3 on live traffic (C2 metrics) |
| **Input drift** | interests, budget, trip length, travelers vs the golden dataset | the BigQuery `input_profile` view; a weekly comparison report (§4) |
| **Model / provider drift** | the same golden cases, a different result over time | a scheduled **weekly smoke gate** (§4) |

## 4. Scheduled drift check (`.github/workflows/drift-weekly.yml`)

- **Weekly cron (Mondays 06:00 UTC):** runs `python -m evals.harness.gate` (3 golden smoke cases,
  ≈ 3 calls ≈ $0.02/week) against the **shipped** baseline. It reuses B4's confirm-run logic.
- **On failure:** the workflow fails, and GitHub emails the repo owner. That catches the provider
  silently changing model behavior, even with zero user traffic.
- It also runs a short **input-drift query** (`input_profile` vs the golden dataset interests) and
  writes it to the job summary.

## 5. Verifying the alerts actually fire (synthetic events)

Alerting you never test is alerting you can't trust. With your permission (§6 Q3):
- Write **synthetic** log entries (a real `cloud_run_revision` resource, `jsonPayload.synthetic=true`,
  and for example a hallucination plus a weather violation) through the Logging API.
- Confirm A1 opens an incident and the notification arrives, then let it auto-close.
- BigQuery views and `promote.py` **exclude `synthetic=true`**, so tests never pollute analytics or
  golden data. A Layer A test enforces the exclusion.

## 6. Decisions (made)
- **Notification channel:** email, using the address confirmed in chat. It is **not stored in the repo** (public); the setup script reads `ALERT_EMAIL` at run time.
- **Thresholds:** the §2 table accepted as is.
- **Synthetic alert test:** run once. Synthetic events use a `trace_id` starting `synthetic-`, which the
  BigQuery views exclude. A prefix avoids adding a new BigQuery column.
- **Not built:** uptime check (A8), weekly drift workflow (§4), billing budget alert. Model/provider drift
  stays covered by the manual `evals-full.yml` and the PR smoke gate; input drift by the `input_profile`
  view.

### Original questions
1. **Notification email:** which address should alerts go to? *(I won't use any address you haven't
   confirmed in chat.)*
2. **Thresholds:** accept the table in §2 (baseline-derived, with minimum-run guards), or adjust any?
3. **Synthetic alert test (§5):** write labeled synthetic events once to prove A1 fires? *(recommended)*
4. **Uptime check (A8):** create a Cloud Monitoring uptime check on `/_stcore/health`? *(recommended; free tier)*
5. **Weekly drift workflow (§4):** about 3 LLM calls per week via the existing `OPENAI_API_KEY` secret? *(recommended)*
6. **GCP billing budget alert** (e.g. $5/month): needs billing-account permissions you may not have
   on this shared project. Skip *(recommended; A7 covers runaway usage)* or try?

## 7. Steps

| Step | Purpose | Depends on |
|---|---|---|
| 1 | Alert policy YAMLs + structure tests (each references a C2 metric; documentation present; min-run guards) | C2 Step 1 |
| 2 | Synthetic-event exclusion in BigQuery views + `promote.py` + test | — |
| 3 | `deploy/monitoring-setup.sh` extended: notification channel, uptime check, policies (idempotent), **with your permission** | C2 Step 3 |
| 4 | Weekly drift workflow | — |
| 5 | Synthetic alert test → incident + email received → auto-close | 3 |
| 6 | Docs: runbook section in CLAUDE.md (what each alert means, first steps) | 5 |

Phase comments: `# Phase 7 – C3 Step N`. Branch: `feature/layer-c-monitoring-alerting` (C2 + C3 together).

## 8. Results (2026-11-13)

| Item | Result |
|---|---|
| Log-based metrics | 10 created. Every filter was validated against the **real** live-check events first: llm_runs / task_failures / weather_violations / feedback = 1, hallucinations / parse / errors = 0 |
| Notification channel | "AgentsVille alerts" (email, address from `ALERT_EMAIL`, not stored in the repo) |
| Dashboard | "AgentsVille – AI quality & ops", 13 tiles |
| Alert policies | 8 created (A1–A7, A9), all enabled and wired to the channel |
| Synthetic test | 1 fake hallucination written (`trace_id synthetic-5225c5df…`), metric point `agentsville_hallucinations = 1` after ≈ 30 s; **A1's PromQL condition evaluates TRUE**, while A7 (negative control) is false; notification email sent to the confirmed address |
| Analytics hygiene | raw sink table: 2 `llm_run` rows; `llm_runs` view: 1 (synthetic excluded) |

**Implementation notes:**
- `gcloud alpha/beta monitoring` needs admin rights to install on this Windows machine, so the channel,
  dashboard and policies use a small REST client (`deploy/monitoring/monitoring_api.py`).
- The Monitoring API rejects `color` on xyChart thresholds, so it was removed from the generator.
