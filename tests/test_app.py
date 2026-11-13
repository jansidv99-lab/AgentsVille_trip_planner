# Phase 4 – Step 4: Layer A UI tests for app.py using Streamlit's headless AppTest.
# The itinerary agent is patched, so no LLM call is made; we test the page flow only.

from unittest.mock import patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from agents.itinerary import ItineraryAgent, ItineraryParseError
from models import PromptTrace

APP_PATH = "app.py"
INSPECTOR_TABS = ["System prompt", "User prompt", "Raw response", "Final response"]


# Phase 4 – Step 4: a fresh app per test; clear Streamlit's process-wide resource cache first
@pytest.fixture
def app() -> AppTest:
    st.cache_resource.clear()
    return AppTest.from_file(APP_PATH, default_timeout=30).run()


# Phase 4 – Step 4: small helpers that act like a user
def fill_first_traveler(at: AppTest, name: str = "Yuri", interest: str = "tennis") -> None:
    at.text_input(key="name_0").input(name)
    at.multiselect(key="interests_0").select(interest)
    at.run()


def click_generate(at: AppTest) -> None:
    next(b for b in at.button if b.label == "Generate itinerary").click().run()


def make_trace(vacation_info, model, raw_response, travel_plan=None) -> PromptTrace:
    return PromptTrace(
        model=model.value,
        system_prompt="Role: You are an expert travel planner.",
        user_prompt=vacation_info.model_dump_json(),
        raw_response=raw_response,
        travel_plan=travel_plan,
    )


# Phase 4 – Step 4: invalid input is caught by the form; the agent is never called
def test_empty_form_shows_errors_and_skips_agent(app):
    with patch.object(ItineraryAgent, "get_itinerary") as agent_call:
        click_generate(app)

    assert not app.exception
    error = app.error[0].value
    assert "Traveler 1 → name" in error
    assert "Traveler 1 → interests" in error
    agent_call.assert_not_called()
    assert not app.header  # no itinerary rendered


# Phase 4 – Step 4: happy path – itinerary, budget metric, and the 4-tab prompt inspector
def test_generate_shows_itinerary_and_inspector(app, sample_plan, llm_reply):
    def fake_get_itinerary(self, vacation_info, model=None):
        self.last_trace = make_trace(vacation_info, model, llm_reply, sample_plan)
        return sample_plan

    fill_first_traveler(app)
    with patch.object(ItineraryAgent, "get_itinerary", autospec=True, side_effect=fake_get_itinerary) as agent_call:
        click_generate(app)

    assert not app.exception
    assert not app.error
    agent_call.assert_called_once()
    sent_info = agent_call.call_args.kwargs["vacation_info"]
    assert sent_info.travelers[0].name == "Yuri"

    assert app.header[0].value == "Your AgentsVille itinerary"
    metrics = {m.label: m.value for m in app.metric}
    assert metrics["Total cost"] == "108 / 130"
    assert [t.label for t in app.tabs] == INSPECTOR_TABS


# Phase 4 – Step 4: unparseable LLM reply – error + inspector for debugging, but no itinerary
def test_parse_error_shows_error_and_inspector(app):
    def fake_get_itinerary(self, vacation_info, model=None):
        self.last_trace = make_trace(vacation_info, model, "sorry, no JSON")
        raise ItineraryParseError("The model's reply did not match the TravelPlan schema (1 errors).", self.last_trace)

    fill_first_traveler(app)
    with patch.object(ItineraryAgent, "get_itinerary", autospec=True, side_effect=fake_get_itinerary):
        click_generate(app)

    assert not app.exception
    assert "did not match the TravelPlan schema" in app.error[0].value
    assert not app.header  # no itinerary
    assert [t.label for t in app.tabs] == INSPECTOR_TABS
    assert "No valid TravelPlan" in app.warning[0].value
    assert any(code.value == "sorry, no JSON" for code in app.code)
