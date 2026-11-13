# Phase 3 – UI Design (Streamlit)

Status: **Done** – Steps 0–4 implemented (app runs end to end against the LLM)

## 1. Purpose

Build a Streamlit page where a user enters trip preferences and clicks a button to generate an
AgentsVille itinerary. The UI collects input, validates it into the existing Pydantic models, calls
the itinerary agent, and displays the resulting `TravelPlan`.

This step is **UI only**. Steps 1–3 below use a fake (stub) result, so the page can be built and
tried without spending LLM calls. The real agent is connected in Step 4.

## 2. Requirements (from CLAUDE.md → UI)

| # | Component | Streamlit widget | Maps to |
|---|---|---|---|
| R1 | Traveler name | `st.text_input` | `Traveler.name` |
| R2 | City (only "AgentsVille" for now) | `st.selectbox(["AgentsVille"])` | `VacationInfo.destination` |
| R3 | Multiple interests from the `Interest` enum | `st.multiselect(list(Interest))` | `Traveler.interests` |
| R4 | OpenAI model (in the main form) | `st.selectbox` over `OpenAIModel`, default from the `MODEL` env var | the `model` argument of `get_itinerary` |
| R5 | Generate button | `st.button` (inside a form) | triggers itinerary generation |

## 3. Gap: fields the data model needs but the UI list doesn't have

`VacationInfo` (in `planner.py`) **requires** these fields, so validation fails without them:

| Field | Proposed widget | Default / constraint |
|---|---|---|
| `Traveler.age` | `st.number_input` (1–120) | 30 |
| `date_of_arrival` / `date_of_departure` | `st.date_input` (range) | 2025-06-10 → 2025-06-12; limited to **2025-06-10…2025-06-15**, the only dates the mock APIs have data for |
| `budget` | `st.number_input` | 130 (fictional currency) |
| More than one traveler | "Add traveler" button, one block per traveler (name, age, interests) | starts with 1 traveler |

**Decision (Q1):** add all of them to the UI, including multiple travelers.

## 4. Layout (wireframe)

```
┌─────────────────────── AgentsVille Trip Planner ───────────────────────┐
│ ┌─ Trip details ─────────────────────────────────────────────────────┐ │
│ │ City:   [AgentsVille ▼]        Model: [gpt-4.1-mini ▼]             │ │
│ │ Dates:  [2025-06-10] → [2025-06-12]     Budget: [130]              │ │
│ └────────────────────────────────────────────────────────────────────┘ │
│ ┌─ Traveler 1 ──────────────────────────────────────────── [Remove] ─┐ │
│ │ Name: [Yuri____]  Age: [30]                                        │ │
│ │ Interests: [tennis ×][cooking ×] [+]                               │ │
│ └────────────────────────────────────────────────────────────────────┘ │
│ ┌─ Traveler 2 ─ … ───────────────────────────────────────────────────┐ │
│ [+ Add traveler]                                                       │
│                                                                        │
│ [ Generate itinerary ]                                                 │
│ ──────────────────────────── Results ───────────────────────────────── │
│ Total cost: 115 / 130   ✅ within budget                               │
│ ▸ Day 1 – 2025-06-10 ☀ 31°C clear                                      │
│     09:00–11:00  FutureTech Breakfast (20)                             │
│        why: matches technology…                                        │
│ ▸ Day 2 …                                                              │
│ [Download JSON]                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

Results display: one `st.expander` per `ItineraryDay` showing the weather plus each recommended
activity (time, name, location, price, reasons), a total-cost metric, and a download button for
the raw `TravelPlan` JSON.

## 5. New concepts (learning notes)

- **Streamlit's execution model:** the whole script re-runs from top to bottom on every widget
  interaction. Anything that must survive a re-run (the generated plan, the number of travelers)
  goes in `st.session_state`.
- **`st.form` (considered, not used):** a form groups inputs so the script re-runs only on submit.
  But a form may contain only submit buttons, and each traveler block needs its own Add/Remove
  buttons. So Step 2 uses plain widgets with stable `key`s plus button `on_click` callbacks. The
  extra re-runs are cheap because nothing expensive happens until "Generate" is clicked.
- **`st.cache_resource`:** creates the OpenAI client once and reuses it across re-runs.
- **Validation at the edge:** build a `VacationInfo` from the form values and catch Pydantic's
  `ValidationError` to show friendly `st.error` messages (e.g. "pick at least one interest").
- **`st.spinner`:** shows progress while the LLM call runs (it takes several seconds).

## 6. Prerequisite: restructure `planner.py` (Step 0)

`planner.py` is currently a top-to-bottom script. **Importing it runs the LLM call** and prints
debug output, and it hardcodes the API key. Streamlit can't import it in that state. Proposed:

| New module | Contents (moved from `planner.py`) |
|---|---|
| `models.py` | `Traveler`, `VacationInfo`, `Weather`, `Activity`, `ActivityRecommendation`, `ItineraryDay`, `TravelPlan`, `OpenAIModel` |
| `llm.py` | `get_client()`, which reads `OPENAI_API_KEY` / `OPENAI_BASE_URL` from `.env` via `python-dotenv`, and `get_default_model()`, which reads `MODEL` with fallback `gpt-4.1-mini` |
| `agents/itinerary.py` | prompt builder plus `ItineraryAgent`; the weather and activities context is built **from the chosen dates** instead of hardcoded `"2025-06-10"`/`"2025-06-12"` |
| `planner.py` | kept as a thin CLI demo under `if __name__ == "__main__":` |

Strictly this belongs to Phase 2 (agents), but the UI depends on it, so it comes first.

## 7. Implementation steps

| Step | Purpose | Depends on | Files |
|---|---|---|---|
| 0 | Move the key to `.env`, split `planner.py` into importable modules (§6) | — | `models.py`, `llm.py`, `agents/itinerary.py`, `planner.py` |
| 1 | Set up dependencies: `streamlit`, `openai`, `pydantic`, `pandas`, `python-dotenv` | — | `requirements.txt` |
| 2 | Input form: sidebar model picker, trip details, traveler blocks, Generate button; Pydantic validation; show the validated `VacationInfo` as JSON | 0, 1 | `app.py` |
| 3 | Results view using a **stub** `TravelPlan` (sample JSON) | 2 | `app.py`, `ui/render.py` |
| 4 | Connect the real `ItineraryAgent`: spinner, error handling, store the plan in `session_state` | 0, 3 | `app.py` |

Run with: `streamlit run app.py`. After each step: manual check in the browser, then a commit
(with your permission).

Out of scope here: the Part B ReAct assistant chat UI (its own plan later), and deployment (Phase 4).

## 8. Decisions

- **Q1:** age, dates, budget, and multiple travelers are all in the UI.
- **Q2:** the model picker goes in the main form (no sidebar).
- **Q3:** the `planner.py` restructure in §6 is approved and done first.
