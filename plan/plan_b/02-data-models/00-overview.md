# 02 – Data models (`models.py`, Phase 9)

Part of [Part B master plan](../00-master-plan.md) · Component **02: Pydantic contracts for tools, steps, traces**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | 01 |
| Delivered in slice(s) | P1 Walking skeleton |
| Phase comment in code | `# Phase 9 – Step 02.<n>: <purpose>` |

## Tasks

1. `ToolName` enum: `get_activities_by_date`, `get_activity_by_id`, `get_weather_for_date`, `calculator`, `run_evals`, `final_answer`.
2. Per-tool argument models with validation, e.g. date `YYYY-MM-DD`, city `AgentsVille`, expression max length.
3. `ToolCall` {`tool_name`, `arguments`}, then `Observation` {`tool_name`, `ok`, `result` | `error`}.
4. `ReActStep` {`index`, `thought`, `action`: ToolCall | None, `observation`, `raw_response`, latency/tokens/cost}.
5. `StopReason` enum: `final_answer`, `max_steps`, `format_errors`, `llm_error`, `guardrail_failed`.
6. `AssistantTrace` {`trace_id`, `parent_trace_id` (the Part A run), `prompt_version`, `model`, `user_message`, `steps`, `stop_reason`, `final_message`, `revised_plan`: TravelPlan | None, `plan_changed`, totals}.
7. `FinalAnswer` arguments {`message`, `travel_plan`: TravelPlan | None}.
- **Done when:** the models' JSON schemas look right; validation tests cover good and bad inputs.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
