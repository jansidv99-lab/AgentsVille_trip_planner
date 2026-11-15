# 03 – Tools (`agents/tools.py`)

Part of [Part B master plan](../00-master-plan.md) · Component **03: Tool registry + 6 simulated tools**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | 02 |
| Delivered in slice(s) | P1 Walking skeleton, P2 Modifications, P3 Guardrails |
| Phase comment in code | `# Phase 9 – Step 03.<n>: <purpose>` |

## Tasks

1. A registry: name → (args model, function, description). The prompt's tool list is generated from it, so the prompt and the code can't drift apart.
2. `get_activities_by_date(date, city)` wraps `call_activities_api_mocked`. An empty result returns a clear message ("no activities for 2025-06-20; data covers 06-10…06-15").
3. `get_activity_by_id(activity_id)` wraps `call_activity_by_id_api_mocked`.
4. `get_weather_for_date(date, city)` wraps `call_weather_api_mocked`.
5. `calculator(expression)`: **safe** arithmetic through `ast` (numbers, + − × ÷ and parentheses only; **never `eval`**). It targets the known `cost_arithmetic` slips.
6. `run_evals(travel_plan)`: parse into `TravelPlan`, then `run_graders(GradingInput.for_request(...))` plus any active turn requirements (e.g. min activities per day). Returns pass/fail per hard grader with the exact problems.
7. `final_answer(message, travel_plan?)`: ends the loop; the plan is validated in 06.
8. Every tool returns a JSON-serialisable `Observation` and never raises into the loop: errors become `ok=false`. Observations are truncated to a size limit.
9. Decision to record: should the agent see indoor/outdoor labels (`quality/labels.py`)? Recommend **yes**, as a field in `get_activities_by_date` results, so it can plan weather-safe days.
- **Done when:** every tool has unit tests for normal, empty, invalid-argument and error cases.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
