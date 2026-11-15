# 05 – Agent loop (`agents/assistant.py`)

Part of [Part B master plan](../00-master-plan.md) · Component **05: Parser + THINK/ACT/OBSERVE loop + stop rules**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | 02, 03, 04 |
| Delivered in slice(s) | P1 Walking skeleton, P2 Modifications |
| Phase comment in code | `# Phase 9 – Step 05.<n>: <purpose>` |

## Tasks

1. Parser: extract `THOUGHT:` and the `ACTION:` JSON (fenced or bare, like `extract_json`), then validate into a `ToolCall`. A format error becomes a corrective observation, not a crash.
2. Loop:
   - build the messages
   - call the LLM with `stop=["OBSERVATION:"]`
   - parse, execute the tool, append the assistant message and `OBSERVATION: {json}` as a user message
   - repeat
3. Stop rules:
   - `final_answer` that passes the guardrail
   - `MAX_STEPS` (default 8)
   - 3 consecutive format errors
   - an LLM/API error (handled like `app.run_agent`)
4. Record an `AssistantTrace` with every step, plus metrics from `InstrumentedClient`.
5. Multi-turn: keep the conversation per Streamlit session; a new user turn starts a new trace with the same `parent_trace_id`.
6. A CLI demo `assistant_demo.py` (like `planner.py`): sample plan + "at least two activities per day".
- **Done when:** the scripted-LLM tests cover a happy path, unknown tool, bad JSON, max steps, LLM error, and an invented `OBSERVATION` being cut off.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
