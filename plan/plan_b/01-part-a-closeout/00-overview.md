# 01 – Part A closeout

Part of [Part B master plan](../00-master-plan.md) · Component **01: Close Part A cleanly**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | — |
| Delivered in slice(s) | P0 |
| Phase comment in code | `# Phase 9 – Step 01.<n>: <purpose>` |

## Tasks

1. Merge or close open work: `docs/operations-runbook` and the blueprint doc (`plan/08-reference/`); decide what to do with the two PNG diagrams.
2. Mark Part A **closed** in `plan/00-master-plan.md`. List the carried-over backlog: branch protection + required eval gate, a committed shipped prompt version, the v1 weather weakness, B3 judge calibration, the `MODEL` repo variable.
3. Optional: tag the release `part-a-v1.0` on `main` (with permission).
4. Record the v1 baselines as the frozen Part A reference. Part B must not regress Part A: the smoke gate keeps running.

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
