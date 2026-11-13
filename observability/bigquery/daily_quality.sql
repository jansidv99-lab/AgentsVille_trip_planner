-- Phase 5 – B5 Step 4: online quality per day and prompt version (drift signal; C3 alerts compare it with the
-- accepted B4 baseline, e.g. v1 full task success 58%).
SELECT
  DATE(timestamp) AS day,
  prompt_version,
  COUNT(*) AS runs,
  ROUND(AVG(IF(task_success, 1, 0)), 3) AS task_success_rate,
  ROUND(AVG(IF(hallucination, 1, 0)), 3) AS hallucination_rate,
  ROUND(AVG(IF(parsed, 1, 0)), 3) AS parse_rate,
  ROUND(APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)], 1) AS p95_latency_ms,
  ROUND(SUM(cost_usd), 4) AS cost_usd,
  COUNTIF(rating IS NOT NULL) AS rated_runs,
  ROUND(SAFE_DIVIDE(COUNTIF(rating = 'down'), COUNTIF(rating IS NOT NULL)), 3) AS thumbs_down_share
FROM `${PROJECT}.${DATASET}.runs_with_feedback`
GROUP BY day, prompt_version
