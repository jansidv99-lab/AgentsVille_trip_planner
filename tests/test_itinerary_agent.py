# Phase 4 – Step 3: Layer A tests for agents/itinerary.py (Part A – the Expert Planner).
# The LLM is replaced by FakeOpenAIClient (conftest.py), so these tests are free and deterministic.

import datetime

import pytest

from agents.itinerary import (
    ItineraryAgent,
    ItineraryParseError,
    build_system_prompt,
    extract_json,
    trip_dates,
)
from models import OpenAIModel, TravelPlan


# Phase 4 – Step 3: trip_dates includes both arrival and departure days
@pytest.mark.parametrize(
    ("arrival", "departure", "expected"),
    [
        pytest.param("2025-06-10", "2025-06-12", ["2025-06-10", "2025-06-11", "2025-06-12"], id="three-days"),
        pytest.param("2025-06-15", "2025-06-15", ["2025-06-15"], id="single-day"),
    ],
)
def test_trip_dates_is_inclusive(vacation_info, arrival, departure, expected):
    info = vacation_info.model_copy(
        update={
            "date_of_arrival": datetime.date.fromisoformat(arrival),
            "date_of_departure": datetime.date.fromisoformat(departure),
        }
    )
    assert trip_dates(info) == expected


# Phase 4 – Step 3: JSON is extracted with or without a ```json fence
@pytest.mark.parametrize(
    "reply",
    [
        pytest.param('ANALYSIS: ...\nFINAL OUTPUT:\n```json\n{"a": 1}\n```\nThanks!', id="fenced"),
        pytest.param('  {"a": 1}  ', id="bare"),
    ],
)
def test_extract_json(reply):
    assert extract_json(reply) == '{"a": 1}'


# Phase 4 – Step 3: the prompt's context covers exactly the chosen dates
def test_system_prompt_uses_only_the_trip_dates(vacation_info):
    info = vacation_info.model_copy(
        update={
            "date_of_arrival": datetime.date(2025, 6, 13),
            "date_of_departure": datetime.date(2025, 6, 14),
        }
    )
    prompt = build_system_prompt(info)

    # Activities: 06-13 and 06-14 are in; 06-10 is out. ("event-2025-06-10-0" appears in the
    # prompt's instructions as an ID example, so check a different 06-10 activity.)
    assert "event-2025-06-13-0" in prompt
    assert "event-2025-06-14-3" in prompt
    assert "event-2025-06-10-1" not in prompt
    # Weather for the chosen dates only.
    assert '"date": "2025-06-13"' in prompt
    assert '"date": "2025-06-10"' not in prompt
    # The output schema is included, so the LLM knows the exact field names.
    assert "itinerary_days" in prompt and "activity_recommendations" in prompt


# Phase 4 – Step 3: happy path – plan returned, trace recorded, LLM called correctly
def test_get_itinerary_returns_plan_and_records_trace(vacation_info, fake_client, llm_reply, sample_plan):
    client = fake_client(llm_reply)
    agent = ItineraryAgent(client=client, model=OpenAIModel.GPT_41_NANO)

    plan = agent.get_itinerary(vacation_info)

    assert isinstance(plan, TravelPlan)
    assert plan == sample_plan

    # Exactly one LLM call, with the agent's model and a system + user message.
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == OpenAIModel.GPT_41_NANO
    assert [m["role"] for m in call["messages"]] == ["system", "user"]

    # The trace records exactly what was sent and received.
    trace = agent.last_trace
    assert trace.model == "gpt-4.1-nano"
    assert trace.system_prompt == call["messages"][0]["content"]
    assert trace.user_prompt == call["messages"][1]["content"]
    assert "Yuri" in trace.user_prompt and "Hiro" in trace.user_prompt
    assert trace.raw_response == llm_reply.strip()
    assert trace.travel_plan == sample_plan


# Phase 4 – Step 3: a model passed to get_itinerary overrides the agent's default
def test_get_itinerary_model_override(vacation_info, fake_client, llm_reply):
    client = fake_client(llm_reply)
    agent = ItineraryAgent(client=client, model=OpenAIModel.GPT_41_NANO)

    agent.get_itinerary(vacation_info, model=OpenAIModel.GPT_41)

    assert client.calls[0]["model"] == OpenAIModel.GPT_41
    assert agent.last_trace.model == "gpt-4.1"


# Phase 4 – Step 3: an unparseable reply raises ItineraryParseError and keeps the trace
def test_get_itinerary_bad_reply_raises_with_trace(vacation_info, fake_client):
    agent = ItineraryAgent(client=fake_client("sorry, no JSON"), model=OpenAIModel.GPT_41_MINI)

    with pytest.raises(ItineraryParseError) as exc_info:
        agent.get_itinerary(vacation_info)

    trace = exc_info.value.trace
    assert trace.raw_response == "sorry, no JSON"
    assert trace.travel_plan is None
    assert trace is agent.last_trace  # the same trace is available on the agent for debugging
