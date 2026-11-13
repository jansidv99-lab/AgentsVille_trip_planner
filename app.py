# Phase 3 – Step 2: Streamlit input form for the AgentsVille trip planner.
# Collects trip details and travelers and validates them into VacationInfo.
# Phase 3 – Step 4: sends the request to the ItineraryAgent and renders the TravelPlan.
#
# Run with:  streamlit run app.py

import datetime

import openai
import streamlit as st
from pydantic import ValidationError

from agents.itinerary import ItineraryAgent, ItineraryParseError
from llm import get_client, get_default_model
from models import OpenAIModel, PromptTrace, TravelPlan, VacationInfo
from project_lib import Interest
from ui.render import render_prompt_trace, render_travel_plan

CITIES = ["AgentsVille"]
# The mocked weather/activities APIs only have data for these dates.
MOCK_START = datetime.date(2025, 6, 10)
MOCK_END = datetime.date(2025, 6, 15)


# Phase 3 – Step 2: set up session_state on the first run (it survives every re-run)
def init_state() -> None:
    if "traveler_ids" not in st.session_state:
        st.session_state.traveler_ids = [0]  # one traveler block to start
        st.session_state.next_traveler_id = 1


# Phase 3 – Step 2: button callbacks; they run *before* the re-run, so the page redraws correctly
def add_traveler() -> None:
    st.session_state.traveler_ids.append(st.session_state.next_traveler_id)
    st.session_state.next_traveler_id += 1


def remove_traveler(traveler_id: int) -> None:
    st.session_state.traveler_ids.remove(traveler_id)


# Phase 3 – Step 2: city, dates, budget, and model picker
def render_trip_details() -> dict:
    st.subheader("Trip details")
    col1, col2 = st.columns(2)
    with col1:
        city = st.selectbox("City", CITIES)
        dates = st.date_input(
            "Travel dates",
            value=(MOCK_START, datetime.date(2025, 6, 12)),
            min_value=MOCK_START,
            max_value=MOCK_END,
            help="Mock data is available for 2025-06-10 to 2025-06-15.",
        )
    with col2:
        models = list(OpenAIModel)
        model = st.selectbox(
            "Model",
            models,
            index=models.index(get_default_model()),
            format_func=lambda m: m.value,
        )
        budget = st.number_input("Budget (fictional currency)", min_value=1, value=130, step=10)

    # While the user is still picking a range, date_input returns only the start date.
    arrival, departure = (dates[0], dates[-1]) if dates else (None, None)
    return {"city": city, "arrival": arrival, "departure": departure, "budget": budget, "model": model}


# Phase 3 – Step 2: one bordered block per traveler; widget keys use a stable id, not the index
def render_travelers() -> list[dict]:
    st.subheader("Travelers")
    travelers = []
    only_one = len(st.session_state.traveler_ids) == 1
    for n, tid in enumerate(st.session_state.traveler_ids, start=1):
        with st.container(border=True):
            head, remove = st.columns([5, 1])
            head.markdown(f"**Traveler {n}**")
            remove.button(
                "Remove", key=f"remove_{tid}", on_click=remove_traveler, args=(tid,), disabled=only_one
            )
            col1, col2 = st.columns([3, 1])
            name = col1.text_input("Name", key=f"name_{tid}")
            age = col2.number_input("Age", min_value=0, max_value=120, value=30, key=f"age_{tid}")
            interests = st.multiselect(
                "Interests", list(Interest), format_func=str, key=f"interests_{tid}"
            )
        travelers.append({"name": name.strip(), "age": age, "interests": interests})
    st.button("+ Add traveler", on_click=add_traveler)
    return travelers


# Phase 3 – Step 2: turn Pydantic errors into readable messages,
# e.g. "Traveler 1 → interests: List should have at least 1 item"
def format_errors(err: ValidationError) -> list[str]:
    messages = []
    for e in err.errors():
        loc = list(e["loc"])
        if len(loc) >= 2 and loc[0] == "travelers":
            loc = [f"Traveler {loc[1] + 1}"] + loc[2:]
        where = " → ".join(str(part) for part in loc)
        messages.append(f"{where}: {e['msg']}" if where else e["msg"])
    return messages


# Phase 3 – Step 4: one OpenAI client per server process, reused across re-runs and users
@st.cache_resource
def cached_client():
    return get_client()


# Phase 3 – Step 4: call the itinerary agent. A new agent per request, because ChatAgent keeps
# conversation state and the cached client is shared between users.
# Phase 3 – Step 5: also return the agent's PromptTrace for the inspector
def generate_plan(vacation_info: VacationInfo, model: OpenAIModel) -> tuple[TravelPlan, PromptTrace]:
    agent = ItineraryAgent(client=cached_client(), model=model)
    plan = agent.get_itinerary(vacation_info=vacation_info, model=model)
    return plan, agent.last_trace


# Phase 3 – Step 4: call the agent with a spinner; on failure show a friendly error.
# Phase 3 – Step 6: returns (plan, trace); on a parse error the trace is kept for debugging.
def run_agent(
    vacation_info: VacationInfo, model: OpenAIModel
) -> tuple[TravelPlan | None, PromptTrace | None]:
    try:
        with st.spinner(f"Planning your trip with {model.value}… this can take 20–60 seconds."):
            return generate_plan(vacation_info, model)
    except RuntimeError as err:  # raised by get_client() when OPENAI_API_KEY is missing
        st.error(str(err))
    except openai.AuthenticationError:
        st.error("The API key was rejected. Check OPENAI_API_KEY and OPENAI_BASE_URL in .env.")
    except openai.OpenAIError as err:  # network problems, rate limits, server errors
        st.error(f"The LLM request failed: {str(err).rstrip('.')}. Please try again.")
    except ItineraryParseError as err:
        st.error(f"{err} Open the prompt inspector below to see why, then try again or pick a stronger model.")
        return None, err.trace
    return None, None


# Phase 3 – Step 2: page layout and the Generate button
def main() -> None:
    st.set_page_config(page_title="AgentsVille Trip Planner", page_icon="🧳")
    st.title("🧳 AgentsVille Trip Planner")
    init_state()

    trip = render_trip_details()
    travelers = render_travelers()

    st.divider()
    if st.button("Generate itinerary", type="primary"):
        try:
            vacation_info = VacationInfo(
                travelers=travelers,
                destination=trip["city"],
                date_of_arrival=trip["arrival"],
                date_of_departure=trip["departure"],
                budget=trip["budget"],
            )
        except ValidationError as err:
            vacation_info = None
            st.error("Please fix the following:\n\n" + "\n".join(f"- {m}" for m in format_errors(err)))

        # Drop any earlier result so a stale plan isn't shown after a failed attempt.
        for k in ("vacation_info", "travel_plan", "trace"):
            st.session_state.pop(k, None)

        if vacation_info is not None:
            plan, trace = run_agent(vacation_info, trip["model"])
            if trace is not None:
                st.session_state.trace = trace
            if plan is not None:
                st.session_state.vacation_info = vacation_info
                st.session_state.travel_plan = plan

    # Phase 3 – Step 3: results are read from session_state, so they survive later re-runs
    # (e.g. clicking Download or expanding a day).
    if "travel_plan" in st.session_state:
        st.divider()
        render_travel_plan(st.session_state.travel_plan, st.session_state.vacation_info.budget)

    # Phase 3 – Step 6: shown after a success, and after a parse error (trace without a plan)
    if "trace" in st.session_state:
        render_prompt_trace(st.session_state.trace)


if __name__ == "__main__":
    main()
