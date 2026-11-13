# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project goal

An AI-powered trip planner for the fictional destination AgentsVille. The system must:
1. **Understand and interpret** the user's preferences and constraints.
2. **Plan comprehensively:** produce a coherent, day-by-day itinerary tailored to the travelers, not just a list of activities.
3. **Evaluate and enhance:** use tools to evaluate the plan, fetch new information, and refine the schedule.

It is built in two parts:
- **Part A – The Expert Planner (initial itinerary):** from user preferences (destination, duration, interests, budget), prompt the LLM to act as an expert travel planner. The output must be structured JSON that validates against a predefined Pydantic itinerary model. This part relies on prompt design that elicits complex structured output and guides the LLM through planning.
- **Part B – The Resourceful Assistant (ReAct agent):** an "AI Travel Assistant" handles follow-up questions, change requests, and any extra requirements that must be met before the itinerary is final. It runs a ReAct loop:
  - **THINK:** reason about the request in the context of the current itinerary.
  - **ACT:** if a tool can help (e.g. the simulated activities API), emit a structured tool request.
  - **OBSERVATION:** our Python code simulates the tool and feeds the result back.
  - The agent continues reasoning or returns a final answer.

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

Git repo on `main`, tracking `origin` on GitHub. There is no application code yet: `plan/` is empty and the master plan (`plan/00-master-plan.md`) hasn't been written. `.gitignore` excludes `.env`, virtualenvs, and Python caches. Add a "Commands" section here (install, run the app, run tests, run a single test) once Phase 1 chooses the tooling.

## Environment

Copy `.env.example` to `.env` and fill it in (`.env` holds secrets and must stay gitignored). It defines:
- `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `MODEL`: LLM access via an OpenAI-compatible endpoint. `OPENAI_BASE_URL` points at a non-default endpoint, so create the client with `OpenAI(base_url=os.getenv("OPENAI_BASE_URL"))` rather than relying on the SDK default.
- `GCP_PROJECT_ID`, `GCP_PROJECT_NUMBER`: deployment target.

## LLM models

Read the model name from the `MODEL` env var; never hardcode it. If `MODEL` is unset, fall back to `gpt-4.1-mini`. Valid options to experiment with:

| Model | Use for |
|---|---|
| `gpt-4.1` | Strongest; general-purpose reasoning and demanding tasks |
| `gpt-4.1-mini` | **Default.** Fast and affordable; good balance of speed and cost |
| `gpt-4.1-nano` | Fastest and cheapest; lightweight, high-frequency tasks |

## Data models

Use Pydantic for all data models (traveler preferences, the itinerary, tool requests/responses).

## UI

Use Streamlit for the UI.
the UI should have following components - 
  window where traveler enter the name 
  select the city name form the list for now only one city - "AgentsVille"
  select multiple intrests provided in the class - Interest
  select the open ai models to use for the LLM generation
  button to generate the report   

## Deployment and CI/CD

Deploy the app to Google Cloud Run in the project given by `GCP_PROJECT_ID`. Region: TBD (record it here once chosen). Use GitHub Actions as the CI/CD pipeline that builds and deploys to Cloud Run.
