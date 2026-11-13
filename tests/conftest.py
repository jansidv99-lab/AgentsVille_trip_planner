# Phase 4 – Step 1: shared pytest fixtures for Layer A.
# pytest loads this file automatically; any test can use a fixture by naming it as a parameter.

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import planner
from models import TravelPlan, VacationInfo

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PLAN_PATH = ROOT / "sample_plan.json"


# Phase 4 – Step 1: isolate every test from the developer's real .env
@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Use a dummy API key and no MODEL / base URL, so tests behave the same locally and in CI.

    monkeypatch restores the original values after each test.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MODEL", raising=False)


# Phase 4 – Step 1: the sample two-traveler trip from planner.py, validated
@pytest.fixture
def vacation_info() -> VacationInfo:
    return VacationInfo.model_validate(planner.VACATION_INFO_DICT)


# Phase 4 – Step 1: the raw sample_plan.json text (a valid TravelPlan built from the mock data)
@pytest.fixture
def sample_plan_json() -> str:
    return SAMPLE_PLAN_PATH.read_text(encoding="utf-8")


# Phase 4 – Step 1: sample_plan.json parsed into a TravelPlan
@pytest.fixture
def sample_plan(sample_plan_json) -> TravelPlan:
    return TravelPlan.model_validate_json(sample_plan_json)


# Phase 4 – Step 1: a stand-in for openai.OpenAI that never touches the network
class FakeOpenAIClient:
    """Mimics client.chat.completions.create(...) and records every call's arguments."""

    # Phase 5 – B0 Step 3: also returns token usage, like the real API
    def __init__(self, reply: str, prompt_tokens: int = 1000, completion_tokens: int = 500):
        self.reply = reply
        self.usage = SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        # Copy the messages: ChatAgent keeps mutating its own list after the call.
        self.calls.append({**kwargs, "messages": [dict(m) for m in kwargs.get("messages", [])]})
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=self.usage)


# Phase 4 – Step 1: factory fixture, e.g. client = fake_client("```json {...} ```")
@pytest.fixture
def fake_client():
    return FakeOpenAIClient


# Phase 4 – Step 1: helper to wrap a JSON string the way the planner prompt asks the LLM to reply
def as_llm_reply(plan_json: str) -> str:
    return f"ANALYSIS:\n1. Weather Analysis: ...\n\nFINAL OUTPUT:\n```json\n{plan_json}\n```"


@pytest.fixture
def llm_reply(sample_plan_json) -> str:
    """A well-formed LLM reply containing sample_plan.json."""
    return as_llm_reply(sample_plan_json)
