# 11 – Deploy and CI

Part of [Part B master plan](../00-master-plan.md) · Component **11: Docker, CI paths, eval gate, Cloud Run release**

| | |
|---|---|
| Status | 📝 Not started – detailed step plan to be written and 👤-reviewed before any code |
| Depends on | 08, 09, 10 |
| Delivered in slice(s) | P6 Observability and release |
| Phase comment in code | `# Phase 9 – Step 11.<n>: <purpose>` |

## Tasks

1. Docker: confirm new files are included (`test_docker_image.py`); the image import check passes.
2. `evals-smoke.yml`: paths already cover `agents/`, `prompts/`, `quality/`, `evals/`. The gate now runs both datasets.
3. Optional manual `evals-full.yml` input: dataset choice.
4. Deploy behind a toggle `ASSISTANT_ENABLED` (env var, default on after the evals pass) so it can be switched off without a rollback.
5. Release flow: PR → CI green → merge → deploy → check the dashboard (checklist in blueprint §3d).

## Next steps
1. Write the detailed step plan `01-<topic>.md` in this folder (purpose, files, tests, dependencies per step).
2. 👤 review → branch from `main` → implement step by step → tests → PR (with permission).
