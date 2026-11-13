# Phase 5 – B0 Step 3: Layer A tests for the instrumented client and cost estimation (no network).

import pytest

from agents.itinerary import ItineraryAgent
from llm import InstrumentedClient, get_client
from models import OpenAIModel
from quality.pricing import estimate_cost


# Phase 5 – B0 Step 3: latency and token usage are recorded; the response is returned unchanged
def test_records_latency_tokens_and_cost(fake_client):
    client = InstrumentedClient(fake_client("hello", prompt_tokens=1000, completion_tokens=500))

    response = client.chat.completions.create(model="gpt-4.1-mini", messages=[])

    assert response.choices[0].message.content == "hello"
    m = client.last_call
    assert m.model == "gpt-4.1-mini"
    assert m.latency_ms >= 0
    assert (m.prompt_tokens, m.completion_tokens) == (1000, 500)
    assert m.cost_usd == pytest.approx((1000 * 0.40 + 500 * 1.60) / 1_000_000)


@pytest.mark.parametrize(
    ("model", "tokens", "expected"),
    [
        pytest.param("gpt-4.1", (1_000_000, 0), 2.00, id="gpt-4.1-input"),
        pytest.param("gpt-4.1-nano", (0, 1_000_000), 0.40, id="nano-output"),
        pytest.param("gpt-4o-mini", (100, 100), None, id="unknown-model"),
        pytest.param("gpt-4.1-mini", (None, 100), None, id="missing-usage"),
    ],
)
def test_estimate_cost(model, tokens, expected):
    assert estimate_cost(model, *tokens) == (pytest.approx(expected) if expected is not None else None)


# Phase 5 – B0 Step 3: enum model values are recorded as plain strings
def test_enum_model_is_recorded_as_string(fake_client):
    client = InstrumentedClient(fake_client("x"))
    client.chat.completions.create(model=OpenAIModel.GPT_41_NANO, messages=[])
    assert client.last_call.model == "gpt-4.1-nano"


# Phase 5 – B0 Step 3: a failing call doesn't leave stale metrics behind
def test_failed_call_clears_last_call(fake_client):
    inner = fake_client("x")
    client = InstrumentedClient(inner)
    client.chat.completions.create(model="gpt-4.1-mini", messages=[])

    def boom(**kwargs):
        raise ConnectionError("network down")

    inner.chat.completions.create = boom
    with pytest.raises(ConnectionError):
        client.chat.completions.create(model="gpt-4.1-mini", messages=[])
    assert client.last_call is None


# Phase 5 – B0 Step 3: other attributes pass through to the real client
def test_get_client_is_instrumented_and_passes_through(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    client = get_client()
    assert isinstance(client, InstrumentedClient)
    assert str(client.base_url).rstrip("/") == "https://example.test/v1"


# Phase 5 – B0 Step 3: the agent copies the metrics into its PromptTrace
def test_agent_trace_has_metrics_and_trace_id(vacation_info, fake_client, llm_reply):
    agent = ItineraryAgent(client=InstrumentedClient(fake_client(llm_reply, 2000, 800)), model=OpenAIModel.GPT_41_MINI)
    agent.get_itinerary(vacation_info)

    trace = agent.last_trace
    assert len(trace.trace_id) == 36  # UUID
    assert (trace.prompt_tokens, trace.completion_tokens) == (2000, 800)
    assert trace.latency_ms is not None and trace.cost_usd is not None


def test_agent_without_instrumentation_has_no_metrics(vacation_info, fake_client, llm_reply):
    agent = ItineraryAgent(client=fake_client(llm_reply), model=OpenAIModel.GPT_41_MINI)
    agent.get_itinerary(vacation_info)
    assert agent.last_trace.latency_ms is None and agent.last_trace.cost_usd is None
