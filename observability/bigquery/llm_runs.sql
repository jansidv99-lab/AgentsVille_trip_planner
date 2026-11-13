-- Phase 7 – C1 Step 3: one row per generated itinerary (event = llm_run), graded online.
SELECT
  timestamp,
  jsonPayload.trace_id AS trace_id,
  jsonPayload.prompt_version AS prompt_version,
  jsonPayload.model AS model,
  jsonPayload.latency_ms AS latency_ms,
  jsonPayload.prompt_tokens AS prompt_tokens,
  jsonPayload.completion_tokens AS completion_tokens,
  jsonPayload.cost_usd AS cost_usd,
  jsonPayload.parsed AS parsed,
  jsonPayload.task_success AS task_success,
  jsonPayload.hallucination AS hallucination,
  jsonPayload.hard_failed AS hard_failed,
  jsonPayload.graders AS graders,
  jsonPayload.features AS features,
  jsonPayload.request AS request,
  jsonPayload.raw_response AS raw_response,
  resource.labels.revision_name AS revision
FROM `${PROJECT}.${DATASET}.run_googleapis_com_stdout`
WHERE jsonPayload.app = 'agentsville' AND jsonPayload.event = 'llm_run'
