-- Phase 5 – B5 Step 4: input distribution of live requests (input-drift signal vs the golden dataset).
SELECT
  DATE(timestamp) AS day,
  interest,
  COUNT(*) AS mentions,
  ROUND(AVG(features.budget), 1) AS avg_budget,
  ROUND(AVG(features.trip_days), 2) AS avg_trip_days,
  ROUND(AVG(features.travelers), 2) AS avg_travelers
FROM `${PROJECT}.${DATASET}.llm_runs`, UNNEST(features.interests) AS interest
GROUP BY day, interest
