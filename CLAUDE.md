# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow rules

1. **Plan first:** before every step, write a detailed plan doc under `plan/` that explains each topic clearly. Keep plans organized by stage:
   ```
   plan/00-master-plan.md   # overall phases, goals, dependencies
   plan/01-setup/           # env, dependencies, repo setup
   plan/02-agents/          # LLM / agent logic
   plan/03-ui/              # Streamlit app
   plan/04-deploy/          # Cloud Run deployment
   ```
   Add new stage folders (e.g. `05-testing/`) as needed, keeping the numeric prefix.
2. **Review:** ask the user to review each plan doc before implementing it.
3. **Permission:** always ask for permission before making any change to code.
4. **Phased implementation:** start with the master plan, then plan the code phase by phase and step by step, stating each step's purpose and dependencies.
5. **Commits, PRs, merges:** always ask for permission before every commit, pull request, and merge.
6. **Branch naming:** use professional, descriptive names prefixed by type, e.g. `feature/streamlit-itinerary-form`, `fix/llm-timeout-handling`, `bugfix/date-parsing`, `chore/cloudrun-dockerfile`, `docs/master-plan`.
7. **Phase comments in code:** mark which phase/step produced the code, at the top of each new file and on each new function/class, for future reference:
   ```python
   # Phase 2 – Step 3: <purpose of this code>
   ```
8. **Learning-oriented:** this project is a hands-on learning exercise. Go step by step, explain new concepts as they come up, and never build everything in one go.

## Repository status

The project is not yet a git repository. Phase 0 of the master plan should run `git init` (default branch `main`) and add a `.gitignore` that excludes `.env`. The commit, PR, and branch rules above apply from then on.

## Environment

Copy `.env.example` to `.env` and fill it in (`.env` holds secrets and must stay gitignored). It defines:
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MODEL` — LLM access via an OpenAI-compatible endpoint.
- `GCP_PROJECT_ID`, `GCP_PROJECT_NUMBER` — deployment target.

## LLM models

Read the model name from the `MODEL` env var; never hardcode it. If `MODEL` is unset, fall back to `gpt-4.1-mini`. Valid options to experiment with:

| Model | Use for |
|---|---|
| `gpt-4.1` | Strongest; general-purpose reasoning and demanding tasks |
| `gpt-4.1-mini` | **Default.** Fast and affordable; good balance of speed and cost |
| `gpt-4.1-nano` | Fastest and cheapest; lightweight, high-frequency tasks |

## UI

Use Streamlit for the UI.

## Deployment

Deploy the app to Google Cloud Run in the project given by `GCP_PROJECT_ID`. Region: TBD (record it here once chosen).
