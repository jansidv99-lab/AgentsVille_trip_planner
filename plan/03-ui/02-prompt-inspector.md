# Phase 3 – Prompt Inspector (Steps 5–6)

Status: **Done** – Steps 5–6 implemented

## 1. Purpose

Show what happens "behind the scenes" of each itinerary generation, so you can learn from and
debug the prompt engineering in Part A. Four views:

| View | Content | Source |
|---|---|---|
| **System prompt** | Role, task, output format, TravelPlan JSON schema, and the weather + activities context for the chosen dates | `build_system_prompt(vacation_info)` |
| **User prompt** | The `VacationInfo` JSON sent as the user message | `vacation_info.model_dump_json(indent=2)` |
| **Raw response** | The LLM's full reply, including the `ANALYSIS` section and the `FINAL OUTPUT` JSON | return value of `ChatAgent.chat(...)` |
| **Final response** | The validated `TravelPlan` as formatted JSON (what the itinerary view renders) | `travel_plan.model_dump(mode="json")` |

## 2. Design

### Step 5 – Record a trace in the agent (`models.py`, `agents/itinerary.py`)

- New Pydantic model `PromptTrace` in `models.py`:
  ```python
  class PromptTrace(BaseModel):
      model: str
      system_prompt: str
      user_prompt: str
      raw_response: str
      travel_plan: TravelPlan | None = None   # None when parsing failed
  ```
- `ItineraryAgent.get_itinerary` fills `self.last_trace` **before** parsing, so a trace exists even
  when the reply is invalid. `ItineraryParseError` carries the trace in place of the bare
  `raw_response` string.
- `get_itinerary` still returns a `TravelPlan`, so `planner.py` doesn't change.

Why a model and not just four variables: it keeps the four pieces together, it's typed, and
`trace.model_dump_json()` gives a one-click download of the whole run for debugging.

### Step 6 – Inspector UI (`ui/render.py`, `app.py`)

- New `render_prompt_trace(trace)` in `ui/render.py`. It shows an expander
  **"🔍 Prompt inspector"** containing `st.tabs`:
  ```
  🔍 Prompt inspector ▾
  ┌ System prompt │ User prompt │ Raw response │ Final response ┐
  │ <scrollable code block, ~400px high, with copy button>      │
  └─────────────────────────────────────────────────────────────┘
  model: gpt-4.1-mini · system prompt 9,812 chars · reply 3,204 chars
  [Download trace JSON]
  ```
  - Each tab is an `st.code` block inside `st.container(height=400)` (scrollable, with a built-in
    copy button). Syntax: `markdown` for the prompts and raw reply, `json` for the user prompt
    and final response.
  - The **Final response** tab shows "No valid TravelPlan – see Raw response" when parsing failed.
- `app.py` stores the trace in `st.session_state.trace` and renders the inspector:
  - after a successful run: below the itinerary. It **replaces** the current "Request sent to the
    agent" expander, which the User prompt tab covers.
  - after a parse failure: below the error message, in place of today's "Raw model response"
    expander, so all four views are available for debugging.
- The inspector starts collapsed, so the itinerary stays the focus.

## 3. New concepts

- **`st.tabs`:** several views in the same space. Every tab's content is computed on each run;
  only the visible tab is shown.
- **`st.container(height=…)`:** a fixed-height, scrollable box, useful for long text like the
  ~10k-character system prompt.
- **Tracing / observability:** recording the exact inputs and outputs of each LLM call is
  the basis of prompt debugging and evaluation. The same idea is behind tools like LangSmith.

## 4. Steps and testing

| Step | Purpose | Depends on | Files |
|---|---|---|---|
| 5 | `PromptTrace` model; agent records `last_trace`; error carries the trace | Step 4 | `models.py`, `agents/itinerary.py` |
| 6 | Inspector expander + tabs; wire into success and parse-error paths | 5 | `ui/render.py`, `app.py` |

Testing: AppTest with a mocked agent that returns a trace (success + parse error), then one real
LLM run to check the four tabs show real content.
