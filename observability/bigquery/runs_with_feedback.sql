-- Phase 5 – B5 Step 4: runs joined to their (latest) feedback by trace_id – input for promote.py.
SELECT r.*, f.rating, f.comment, f.timestamp AS feedback_at
FROM `${PROJECT}.${DATASET}.llm_runs` AS r
LEFT JOIN (
  SELECT * EXCEPT(rn) FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY trace_id ORDER BY timestamp DESC) AS rn
    FROM `${PROJECT}.${DATASET}.feedback`)
  WHERE rn = 1
) AS f USING (trace_id)
