# 08 – Layer A tests (deterministic, no LLM)

Part of [Part B master plan](../00-master-plan.md) · Component **08: Deterministic tests (scripted fake LLM)**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | runs alongside 02–07 |
| Delivered in slice(s) | P1 Walking skeleton, P2 Modifications, P3 Guardrails, P4 UI |
| Phase comment in code | `# Phase 9 – Step 08.<n>: <purpose>` |

## Tasks

1. Fixture `scripted_client`: returns a given sequence of replies, one per call (extends `fake_client` in `tests/conftest.py`).
2. Tests per component: models (02), each tool (03), prompt render and placeholders (04), parser and loop paths (05), guardrail and diff (06), UI (07), event shape (10).
3. A mutation test for every new grader: break a known-good trace in one way and assert that **only** that grader fails.
4. Keep `pytest` around 2–5 s; all existing tests stay green.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
