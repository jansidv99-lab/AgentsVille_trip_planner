# 10 – Layer C observability

Part of [Part B master plan](../00-master-plan.md) · Component **10: Events, BigQuery view, metrics, alerts**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | 05, 07 |
| Delivered in slice(s) | P6 Observability and release |
| Phase comment in code | `# Phase 9 – Step 10.<n>: <purpose>` |

## Tasks

1. Event `assistant_turn`, one per user turn (never on re-runs):
   - `trace_id`, `parent_trace_id`, `prompt_version`, `model`
   - `steps`, `tools_json` (details as a JSON string, BigQuery-stable)
   - `stop_reason`, `plan_changed`
   - grader results, tokens, cost, latency
2. `tool_error` details go inside the event. Privacy rules as in Part A: names logged privately, the raw replies only on a hard failure.
3. BigQuery view `observability/bigquery/assistant_turns.sql`; extend `deploy/observability-setup.sh`.
4. Log metrics and dashboard tiles: turns, steps per turn, step-limit/format-error rate, tool errors, assistant task success.
5. New alerts with runbooks: A10 step-limit/format-error spike, A11 assistant hallucination. Adjust A7 (cost guard), because one turn makes several calls.
6. Update the `tests/test_monitoring_config.py` contract.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
