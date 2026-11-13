# AgentsVille operations runbook

**Use this when** an alert email arrives, the live app misbehaves, or you need to do a routine
production change: roll back, switch the prompt, rotate the API key, or throttle traffic.

Each alert policy carries a short summary of its own runbook (`deploy/monitoring/alerts/*.yaml` →
`documentation`). This page is the long form: triage, exact commands, rollback, and escalation.

---

## 0. Quick reference

| | |
|---|---|
| Service | `agentsville-trip-planner` (Cloud Run, region `asia-south1`) |
| Project | `$GCP_PROJECT_ID` (from `.env`) |
| Image | `asia-south1-docker.pkg.dev/$GCP_PROJECT_ID/agentsville/trip-planner:<commit-sha>` |
| API key secret | Secret Manager `agentsville-openai-api-key` (mounted as `OPENAI_API_KEY`) |
| Settings | GitHub repo variables `MODEL`, `PROMPT_VERSION`, `OPENAI_BASE_URL` (read by `deploy.yml`) |
| Dashboard | Cloud Monitoring → **"AgentsVille – AI quality & ops"** |
| Logs | Cloud Logging, filter `jsonPayload.app="agentsville"` |
| Analytics | BigQuery `agentsville_observability`: `llm_runs`, `feedback`, `runs_with_feedback`, `daily_quality`, `input_profile` |
| Deploys | GitHub Actions → **Deploy** (every push to `main`, or run it manually) |

Set these once per shell before using the commands below:

```bash
export PROJECT=$GCP_PROJECT_ID REGION=asia-south1 SERVICE=agentsville-trip-planner
gcloud config set project "$PROJECT"
```

### Prerequisites and access

- `gcloud` signed in as a project member who can manage Cloud Run, Logging, BigQuery, and Secret
  Manager.
- `gh` signed in with write access to `jansidv99-lab/AgentsVille_trip_planner`, to change repo
  variables and re-run workflows.
- `bq` (part of the Cloud SDK) for the BigQuery queries.
- A local checkout with `.env` filled in, for `promote.py` and the eval harness.

> **⚠️ The golden rule: the next deploy overwrites console changes.** `deploy.yml` re-applies the
> image, env vars, `--max-instances 2` and `--allow-unauthenticated` on every push to `main`. Every
> quick fix below says how to make it stick, usually by changing a repo variable or opening a PR.

---

## 1. Triage: the first 5 minutes

1. **Read the alert:** its name, severity, and the inline runbook in the email.
2. **Check the service is up:**
   ```bash
   curl -fsS "$(gcloud run services describe $SERVICE --region $REGION --format='value(status.url)')/_stcore/health"
   ```
3. **What changed recently?**
   ```bash
   gcloud run revisions list --service $SERVICE --region $REGION --limit 5
   gh run list --workflow deploy.yml --limit 5
   gh variable list            # MODEL / PROMPT_VERSION / OPENAI_BASE_URL
   ```
4. **Decide the severity:**

   | Severity | Alerts | Respond |
   |---|---|---|
   | CRITICAL: users get wrong facts or no answer | A1 hallucination, A4 LLM errors, A9 5xx | Now. Stop the bleeding first (roll back), then investigate |
   | WARNING: quality, latency or cost trend | A2, A3, A5, A6, A7 | Same day. Investigate before changing anything |

5. **Synthetic alert?** If the run's `trace_id` starts with `synthetic-` or its `prompt_version` is
   `synthetic`, it came from `fire_synthetic_event.py`. Close it; there's nothing to do.

---

## 2. Alert playbooks

### A1: Hallucination detected (CRITICAL)
A live plan contained a fabricated or altered fact. **The tolerance is 0.**

1. Find the run. The raw reply is logged because a hard grader failed:
   ```bash
   bq query --use_legacy_sql=false '
   SELECT timestamp, trace_id, prompt_version, model, hard_failed, graders, raw_response
   FROM agentsville_observability.llm_runs
   WHERE hallucination AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
   ORDER BY timestamp DESC'
   ```
2. Read `graders[].details_json` to see which grader failed and which field was invented
   (an activity ID, price, time, or the weather).
3. Decide:
   - **It started with a deploy or a prompt/model change:** roll back (§3.1) or revert
     `PROMPT_VERSION` (§3.2).
   - **One-off on the current version:** keep serving, and capture the case (§3.5).
   - **The grader is wrong** (false positive): fix the grader in a PR, with a mutation test.
4. Always turn it into a golden case (§3.5). The same failure must never reach production silently
   again.

### A2: Task-success drift (WARNING)
More than 60% of live runs failed task success over 6 h (at least 5 runs). The v1 baseline is
about 42% failures.

1. On the dashboard, find the grader that accounts for most failures (weather, cost arithmetic,
   coverage).
2. Check for a change: a new revision, `PROMPT_VERSION`, `MODEL`, or a silent model update on the
   provider's side.
3. Separate model drift from input drift:
   ```bash
   python -m evals.harness.gate --prompt-version v1 --compare-to v1   # golden smoke, ~3–6 calls
   ```
   - The gate **fails** on fixed golden inputs: the model or provider changed. Roll back the
     change, or pin a different `MODEL` (§3.2).
   - The gate **passes**: the inputs changed. Query `input_profile` for longer trips, other
     interests, or tighter budgets, and capture new cases (§3.5).

### A3: Weather-safety spike (WARNING)
More than half of live runs put an outdoor activity on a rainy or stormy day. v1 runs at about
35%, so this is a known weak spot.

1. Look at examples:
   ```sql
   SELECT trace_id, request, graders FROM agentsville_observability.llm_runs
   WHERE 'weather_safety' IN UNNEST(hard_failed) ORDER BY timestamp DESC LIMIT 20
   ```
2. Usually there's no emergency action. Check whether the trip mix moved toward 06-12 … 06-14 (the
   storm and rain days) in `input_profile`.
3. The lasting fix is in the backlog (a validate-and-repair guardrail, or a new prompt version
   through the eval gate). Don't edit v1.

### A4: LLM errors (CRITICAL)
Three or more calls failed with no reply in 10 min.

1. Read the error text:
   ```bash
   gcloud logging read 'jsonPayload.app="agentsville" AND jsonPayload.event="llm_error"' \
     --freshness=1h --limit 20 --format='value(timestamp,jsonPayload.error)'
   ```
2. Match the error to its cause:

   | Error text contains | Likely cause | Action |
   |---|---|---|
   | `401` / `invalid api key` | key revoked or expired | Rotate the key (§3.3) |
   | `429` / `quota` / `insufficient` | Vocareum credits or rate limit used up | Check the Vocareum balance; throttle (§3.4) if A7 is also firing |
   | `timeout` / `connection` / `5xx` | provider or network outage | Wait and watch; check the provider's status; nothing to roll back |
   | `404` / `model not found` | wrong `MODEL` or `OPENAI_BASE_URL` | Fix the repo variable (§3.2) |

### A5: Slow responses, p95 above 60 s (WARNING)
Normal p95 is about 31–42 s.

1. On the dashboard, look at latency by prompt version and model. A new version with a longer
   prompt or more output costs time.
2. Check `input_profile` for a move toward 6-day trips, which are the slowest.
3. Check the provider's status. With no change on our side, wait for it to recover. `--timeout 300`
   keeps requests alive until then.

### A6: Unhappy users, 👎 above 50% (WARNING)
At least 5 ratings in 24 h.

1. Read the comments:
   ```sql
   SELECT feedback_at, comment, hard_failed, prompt_version
   FROM agentsville_observability.runs_with_feedback WHERE rating = 'down' ORDER BY feedback_at DESC
   ```
2. A 👎 on a plan that passed every grader means the **graders miss something users care about**.
   That's a candidate for a new grader or golden case.
3. Capture the cases (§3.5).

### A7: Cost / abuse guard, above 60 runs/h (WARNING)
Every run spends LLM credits.

1. Look for a single source or a script:
   ```bash
   gcloud logging read "resource.labels.service_name=\"$SERVICE\" AND httpRequest.requestUrl:*" \
     --freshness=1h --limit 50 --format='value(httpRequest.remoteIp,httpRequest.userAgent)' | sort | uniq -c | sort -rn | head
   ```
2. A real but unusual demo spike: no action.
3. Abuse: throttle or close the app (§3.4).

### A9: Server errors, 5xx (CRITICAL)

1. Read the tracebacks:
   ```bash
   gcloud logging read "resource.labels.service_name=\"$SERVICE\" AND severity>=ERROR" --freshness=1h --limit 20
   ```
2. **Started right after a deploy:** roll back (§3.1) first, debug second.
3. **Not tied to a deploy:** look for memory (`512Mi`) or out-of-memory kills in the logs, and a
   failing dependency.

---

## 3. Procedures

### 3.1 Roll back to the previous revision
Use this for a bad deploy (A9, or A1/A2 starting with a release). It takes about a minute and needs
no rebuild.

```bash
gcloud run revisions list --service $SERVICE --region $REGION --limit 5     # pick the last good one
gcloud run services update-traffic $SERVICE --region $REGION --to-revisions <good-revision>=100
```

**Verify:** the health check (§1.2) passes, the 5xx and error charts flatten, and `revision` in new
`llm_runs` rows shows the good revision.

**Make it stick:** revert the bad commit on `main` through a PR (`git revert <sha>`). When the fixed
version deploys, send traffic back to the newest revision:
```bash
gcloud run services update-traffic $SERVICE --region $REGION --to-latest
```

### 3.2 Change `PROMPT_VERSION` or `MODEL`
Use this to revert to a known-good prompt or model, or to fix a wrong model or endpoint.

**Durable route (preferred):** update the repo variable and redeploy the current `main`.
```bash
gh variable set PROMPT_VERSION --body v1        # or: gh variable set MODEL --body gpt-4.1-mini
gh workflow run deploy.yml
gh run list --workflow deploy.yml --limit 1     # then: gh run watch <run-id>
```

**Emergency route** (takes effect in seconds, but the next deploy overwrites it):
```bash
gcloud run services update $SERVICE --region $REGION --update-env-vars PROMPT_VERSION=v1
```
After the emergency route, also run the `gh variable set` above.

Rules:
- A new prompt version must pass the eval gate before it can be shipped. See
  `plan/05-layer-b-evals/eval-pipeline-explained.md`.
- The CI smoke gate also reads `PROMPT_VERSION` as "the shipped version". Changing it changes what
  future PRs are compared against.

### 3.3 Rotate the OpenAI / Vocareum API key
Use this for A4 with a 401, a leaked key, or a routine rotation.

```bash
# 1. Add the new key as a new secret version (paste it, then Ctrl-D; it is never echoed or stored in a file)
gcloud secrets versions add agentsville-openai-api-key --data-file=-

# 2. Roll a new revision so instances pick up :latest
gcloud run services update $SERVICE --region $REGION \
  --update-secrets OPENAI_API_KEY=agentsville-openai-api-key:latest

# 3. Update the CI copy used by the eval workflows
gh secret set OPENAI_API_KEY

# 4. Once a generation works, disable the old version
gcloud secrets versions list agentsville-openai-api-key
gcloud secrets versions disable <old-version> --secret agentsville-openai-api-key
```

**Verify:** generate one itinerary in the live app; there should be no new `llm_error` events.
**Also:** update your local `.env`. It's gitignored, so never commit it.

### 3.4 Throttle or close the public app
Use this for abuse (A7) or quota exhaustion.

```bash
# Throttle: one instance at most
gcloud run services update $SERVICE --region $REGION --max-instances 1

# Close: require authentication (the public URL then returns 403)
gcloud run services remove-iam-policy-binding $SERVICE --region $REGION \
  --member=allUsers --role=roles/run.invoker
```

**Reopen:**
```bash
gcloud run services add-iam-policy-binding $SERVICE --region $REGION --member=allUsers --role=roles/run.invoker
gcloud run services update $SERVICE --region $REGION --max-instances 2
```

**⚠️ Any merge to `main` reopens the app** (`deploy.yml` sets `--allow-unauthenticated
--max-instances 2`). While the app must stay closed, don't merge, or open a PR that changes those
flags first.

### 3.5 Turn a production failure into a golden case
Do this after every A1, and whenever A2, A3 or A6 shows a new pattern.

```bash
python -m evals.harness.promote mine --days 7
#   → evals/datasets/itinerary_golden/candidates.jsonl (gitignored; synthetic names; status = draft)
#   read the candidates and choose which are worth keeping (a human decision)
python -m evals.harness.promote approve P1 P3 --reviewer <name>
#   → new minor dataset version + changelog → open a PR → record a new baseline on it
```

Never commit real traveler names. `promote.py` replaces them with synthetic ones; check the output
before committing anyway.

### 3.6 Test the alerting itself
After you change an alert, or to check that email delivery still works:

```bash
python deploy/monitoring/fire_synthetic_event.py "$PROJECT"   # one labeled fake hallucination → A1 fires
```
A1 should fire within a few minutes. BigQuery views exclude `synthetic-` traces, so analytics and
golden data stay clean.

If you edited a policy, metric or dashboard, re-apply the config (it's idempotent):
```bash
ALERT_EMAIL=<address> bash deploy/monitoring-setup.sh
```

---

## 4. After the incident

1. **Verify recovery:** the alert auto-closes, the dashboard is back near baseline, and the health
   check is green.
2. **Make every quick fix durable:** repo variables, a reverting PR, or reopened access (see the
   golden rule above).
3. **Capture what was learned:** a golden case (§3.5), a new grader with a mutation test, or a
   backlog item.
4. **For CRITICAL incidents,** write a short blameless note: what happened, impact (runs or time
   affected), root cause, fix, and follow-ups.

## 5. Escalation

This is a single-owner project, so escalation means external providers:

| Problem | Who | Where |
|---|---|---|
| LLM quota, credits, endpoint or key | Vocareum / Udacity course support | Udacity workspace help |
| Model behavior changed upstream | OpenAI-compatible provider | Provider status page |
| Cloud Run, Logging or BigQuery outage | Google Cloud | status.cloud.google.com |
| GitHub Actions or WIF deploy failures | GitHub | githubstatus.com; re-check `deploy/gcp-setup.sh` bindings |

## 6. Deliberately not covered

These were decided against, so no runbook exists for them:
- uptime checks
- a weekly drift workflow
- billing budget alerts

A7 is the cost guard. If you add any of these later, add its section here.
