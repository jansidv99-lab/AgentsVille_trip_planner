# Phase 4 – Step 2: Layer A tests for llm.py (model selection and client configuration).
# The autouse isolated_env fixture (conftest.py) starts each test with a dummy key and no MODEL.

import pytest

from llm import get_client, get_default_model
from models import OpenAIModel


# Phase 4 – Step 2: MODEL env var → model, with fallback to gpt-4.1-mini
@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        pytest.param(None, OpenAIModel.GPT_41_MINI, id="unset-uses-default"),
        pytest.param("gpt-4.1-nano", OpenAIModel.GPT_41_NANO, id="valid-model"),
        pytest.param("gpt-5", OpenAIModel.GPT_41_MINI, id="unknown-falls-back"),
    ],
)
def test_get_default_model(monkeypatch, env_value, expected):
    if env_value is not None:
        monkeypatch.setenv("MODEL", env_value)
    assert get_default_model() == expected


# Phase 4 – Step 2: a missing key gives a clear error instead of a confusing API failure
def test_get_client_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        get_client()


# Phase 4 – Step 2: OPENAI_BASE_URL is passed to the client (creating a client makes no network call)
def test_get_client_uses_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    client = get_client()
    assert str(client.base_url).rstrip("/") == "https://example.test/v1"
    assert client.api_key == "test-key"
