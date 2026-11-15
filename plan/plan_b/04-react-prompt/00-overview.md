# 04 – ReAct prompt (`prompts/assistant/v1.md`)

Part of [Part B master plan](../00-master-plan.md) · Component **04: Versioned ReAct system prompt**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | 02, 03 |
| Delivered in slice(s) | P1 Walking skeleton |
| Phase comment in code | `# Phase 9 – Step 04.<n>: <purpose>` |

## Tasks

1. Template with exactly `$tools`, `$vacation_info`, `$itinerary`, `$rules` (validated like the Part A prompts).
2. Content:
   - role
   - the request types (Q/M/R/X)
   - the business rules stated explicitly (group pricing, whole-day weather policy)
   - output format: **one** `THOUGHT:` + **one** `ACTION:` JSON per reply, never write `OBSERVATION:`
   - always `run_evals` before `final_answer` when the plan changed
   - never invent activities; answer honestly when a tool returns nothing
   - one worked example trajectory
3. Selection through `ASSISTANT_PROMPT_VERSION` (default `v1`). After the first eval, sha-pin v1 in `tests/test_prompts.py`; later changes go in a new version.
- **Done when:** a render test passes and the prompt is inspected by hand in the UI.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
