# 06 – Plan revision and guardrails

Part of [Part B master plan](../00-master-plan.md) · Component **06: Final-answer validation, repair, plan diff, multi-turn state**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | 05, Part A graders |
| Delivered in slice(s) | P2 Modifications, P3 Guardrails |
| Phase comment in code | `# Phase 9 – Step 06.<n>: <purpose>` |

## Tasks

1. Final-answer guardrail: the revised plan must parse, pass every Part A hard grader, and meet the turn's requirements. Otherwise return an observation listing the exact failures (up to 2 repair rounds), then stop with `guardrail_failed` and keep the **old** plan. This also delivers the backlog item "validate-and-repair guardrail" for Part B.
2. Recompute `total_cost` in code and compare it with the model's figure (it must match; no silent fix).
3. Plan diff: activities added, removed or moved per day, plus the cost change. Used by the UI and the evals.
4. Question-only turns must return **no** plan; `plan_changed=false`.
5. Requirements per turn: a simple structured parse of known requirements (e.g. "at least N activities per day", a budget change) into checks that `run_evals` and the graders can use. Anything unknown is treated as free text (judge only).
- **Done when:** unit tests cover the guardrail's pass, repair and fail paths, and the diff.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
