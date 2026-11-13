-- Phase 7 – C1 Step 3 / B5: one row per user rating (event = feedback).
SELECT
  timestamp,
  jsonPayload.trace_id AS trace_id,
  jsonPayload.rating AS rating,
  jsonPayload.comment AS comment,
  jsonPayload.prompt_version AS prompt_version
FROM `${PROJECT}.${DATASET}.run_googleapis_com_stdout`
WHERE jsonPayload.app = 'agentsville' AND jsonPayload.event = 'feedback'
  -- Phase 7 – C3: synthetic alert-test events (trace_id 'synthetic-…') never reach analytics or golden data
  AND NOT STARTS_WITH(IFNULL(jsonPayload.trace_id, ''), 'synthetic-')
