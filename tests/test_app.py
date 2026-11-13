# Phase 4 – Step 4: Layer A UI tests for app.py using Streamlit's headless AppTest.
# The itinerary agent is patched, so no LLM call is made; we test the page flow only.

from unittest.mock import patch

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from agents.itinerary import ItineraryAgent, ItineraryParseError
from models import PromptTrace

APP_PATH = "app.py"
INSPECTOR_TABS = ["System prompt", "User prompt", "Raw response", "Final response", "Quality checks"]


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

    # Phase 5 – B1 Step 5: the Quality checks tab grades the grounded sample plan as clean
    quality = " ".join(m.value for m in app.markdown)
    # Phase 5 – B2 Step 6: 11 hard checks now (parse + 5 grounding + 5 constraints)
    assert "Hard checks passed: 11/11" in quality and "task success" in quality
    assert "no hallucination detected" in quality and "all constraints met" in quality
    assert "`activity_exists`" in quality and "`weather_safety`" in quality
    assert "`interest_coverage`" in quality and "`reason_grounding`" in quality  # Phase 5 – B3: deterministic B3 graders shown live


# Phase 5 – B2 Step 6: an outdoor hike on the thunderstorm day (the G2/G7 failure) is flagged live
def test_quality_checks_flag_storm_hike(app, sample_plan, llm_reply):
    from models import ActivityRecommendation
    from project_lib import ACTIVITY_CALENDAR
    hike = next(a for a in ACTIVITY_CALENDAR if a["activity_id"] == "event-2025-06-12-0")
    bad_plan = sample_plan.model_copy(deep=True)
    bad_plan.itinerary_days[2].activity_recommendations.append(
        ActivityRecommendation(activity=hike, reasons_for_recommendation=["Matches hiking"]))
    bad_plan.total_cost += hike["price"]

    def fake_get_itinerary(self, vacation_info, model=None):
        self.last_trace = make_trace(vacation_info, model, llm_reply, bad_plan)
        return bad_plan

    fill_first_traveler(app)
    with patch.object(ItineraryAgent, "get_itinerary", autospec=True, side_effect=fake_get_itinerary):
        click_generate(app)

    assert not app.exception
    quality = " ".join(m.value for m in app.markdown)
    assert "Hard checks passed: 10/11" in quality and "task failed" in quality
    assert "constraints violated: weather_safety" in quality and "no hallucination detected" in quality
    assert any("event-2025-06-12-0" in str(j.value) for j in app.json)


# Phase 5 – B1 Step 5: an ungrounded itinerary (wrong price) is flagged live in the Quality checks tab
def test_quality_checks_flag_hallucination(app, sample_plan, llm_reply):
    bad_plan = sample_plan.model_copy(deep=True)
    bad_plan.itinerary_days[0].activity_recommendations[0].activity.price = 5
    bad_plan.total_cost -= 15  # keep the arithmetic consistent: isolate the hallucination

    def fake_get_itinerary(self, vacation_info, model=None):
        self.last_trace = make_trace(vacation_info, model, llm_reply, bad_plan)
        return bad_plan

    fill_first_traveler(app)
    with patch.object(ItineraryAgent, "get_itinerary", autospec=True, side_effect=fake_get_itinerary):
        click_generate(app)

    assert not app.exception
    quality = " ".join(m.value for m in app.markdown)
    assert "Hard checks passed: 10/11" in quality
    assert "hallucination detected: activity_details_match" in quality
    assert any("event-2025-06-10-0" in str(j.value) for j in app.json)


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


# Phase 7 – C1 Step 2 / B5 Step 3: structured events from the live app (captured from stdout)
def _events(capsys) -> list[dict]:
    import json
    out = capsys.readouterr().out
    return [json.loads(line) for line in out.splitlines() if line.startswith('{"app": "agentsville"')]


def test_generation_emits_exactly_one_llm_run_event(app, sample_plan, llm_reply, capsys):
    def fake_get_itinerary(self, vacation_info, model=None):
        self.last_trace = make_trace(vacation_info, model, llm_reply, sample_plan)
        return sample_plan

    fill_first_traveler(app)
    capsys.readouterr()  # ignore anything printed before Generate
    with patch.object(ItineraryAgent, "get_itinerary", autospec=True, side_effect=fake_get_itinerary):
        click_generate(app)
    events = _events(capsys)
    assert [e["event"] for e in events] == ["llm_run"]
    run = events[0]
    assert run["task_success"] is True and run["request"]["travelers"][0]["name"] == "Yuri"
    assert run["trace_id"] == app.session_state["trace"].trace_id

    app.number_input(key="age_0").set_value(41).run()  # a Streamlit re-run must NOT log again
    assert _events(capsys) == []


def test_feedback_is_logged_once_with_the_same_trace_id(app, sample_plan, llm_reply, capsys):
    def fake_get_itinerary(self, vacation_info, model=None):
        self.last_trace = make_trace(vacation_info, model, llm_reply, sample_plan)
        return sample_plan

    fill_first_traveler(app)
    with patch.object(ItineraryAgent, "get_itinerary", autospec=True, side_effect=fake_get_itinerary):
        click_generate(app)
    trace_id = app.session_state["trace"].trace_id
    capsys.readouterr()

    send = next(b for b in app.button if b.label == "Send feedback")
    assert send.disabled  # nothing selected yet
    app.radio(key=f"fb_rating_{trace_id}").set_value("👎 Not helpful")
    app.text_area(key=f"fb_comment_{trace_id}").input("pipeline test: day 2 too empty")
    app.run()
    next(b for b in app.button if b.label == "Send feedback").click().run()

    events = _events(capsys)
    assert [e["event"] for e in events] == ["feedback"]
    assert events[0]["trace_id"] == trace_id and events[0]["rating"] == "down"
    assert events[0]["comment"] == "pipeline test: day 2 too empty"
    assert any("feedback recorded (down)" in s.value for s in app.success)
    assert not any(b.label == "Send feedback" for b in app.button)  # the form was replaced by the thank-you
    app.run()  # a later re-run keeps showing the thank-you, never the form again
    assert not any(b.label == "Send feedback" for b in app.button)  # one feedback per itinerary
    assert _events(capsys) == []  # and no duplicate feedback event


def test_llm_error_emits_llm_error_event(app, capsys):
    import httpx
    import openai

    fill_first_traveler(app)
    capsys.readouterr()
    err = openai.APIConnectionError(request=httpx.Request("POST", "http://x"))
    with patch.object(ItineraryAgent, "get_itinerary", autospec=True, side_effect=err):
        click_generate(app)
    events = _events(capsys)
    assert [e["event"] for e in events] == ["llm_error"] and events[0]["severity"] == "ERROR"
