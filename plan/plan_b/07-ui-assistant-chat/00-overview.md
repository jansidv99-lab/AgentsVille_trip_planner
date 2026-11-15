# 07 – UI: assistant chat (`app.py`, `ui/render.py`)

Part of [Part B master plan](../00-master-plan.md) · Component **07: Streamlit chat panel + step trace + plan diff**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | 05, 06 |
| Delivered in slice(s) | P4 UI |
| Phase comment in code | `# Phase 9 – Step 07.<n>: <purpose>` |

## Tasks

1. After a plan is generated, show a "💬 Travel assistant" chat (`st.chat_input` / `st.chat_message`).
2. Each turn: the answer, an expander with the THOUGHT/ACTION/OBSERVATION steps, the plan diff, and **Apply revised plan** / **Discard** buttons (the user stays in control).
3. Session state: conversation, current plan, plan history (undo last change).
4. A spinner with step progress; friendly errors (reuse the `run_agent` error handling).
5. 👍/👎 per assistant turn (reuse `render_feedback`, keyed by the assistant `trace_id`).
- **Done when:** `AppTest` with a mocked assistant covers ask → answer → apply → plan updated.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
