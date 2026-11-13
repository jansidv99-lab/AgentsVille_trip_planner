# Phase 3 – Step 0: LLM client setup. Reads credentials and the model name from .env,
# so no secrets live in the code.
# Phase 5 – B0 Step 3: the client is wrapped in InstrumentedClient to measure latency and tokens.

import os
import time
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

from dotenv import load_dotenv
from openai import OpenAI

from models import OpenAIModel
from quality.pricing import estimate_cost

# Load variables from .env into os.environ (existing env vars win, so Cloud Run
# settings override a local .env).
load_dotenv()

DEFAULT_MODEL = OpenAIModel.GPT_41_MINI


# Phase 5 – B0 Step 3: metrics of the most recent chat completion call
@dataclass
class CallMetrics:
    model: Optional[str]
    latency_ms: float
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    cost_usd: Optional[float]


# Phase 5 – B0 Step 3: wraps an OpenAI(-like) client; records latency + token usage per call.
# project_lib.do_chat_completion only returns the reply text, so this wrapper is how we get metrics
# without modifying course-provided code.
class InstrumentedClient:
    def __init__(self, client: Any):
        self._client = client
        self.last_call: Optional[CallMetrics] = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    # Phase 5 – B0 Step 3: same signature as client.chat.completions.create; returns the response unchanged
    def _create(self, **kwargs):
        self.last_call = None  # never report a previous call's metrics if this one fails
        start = time.perf_counter()
        response = self._client.chat.completions.create(**kwargs)
        latency_ms = round((time.perf_counter() - start) * 1000, 1)
        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None)
        completion_tokens = getattr(usage, "completion_tokens", None)
        model = getattr(kwargs.get("model"), "value", kwargs.get("model"))
        self.last_call = CallMetrics(
            model=model,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=estimate_cost(model, prompt_tokens, completion_tokens),
        )
        return response

    # Everything else (base_url, api_key, beta, audio, ...) is passed through to the real client.
    def __getattr__(self, name: str):
        return getattr(self._client, name)


# Phase 3 – Step 0: build an OpenAI client for the configured (OpenAI-compatible) endpoint
# Phase 5 – B0 Step 3: returned wrapped in InstrumentedClient
def get_client() -> InstrumentedClient:
    """Return an instrumented OpenAI client using OPENAI_API_KEY and OPENAI_BASE_URL."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in.")
    # base_url=None makes the SDK use the default OpenAI endpoint.
    return InstrumentedClient(OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None))


# Phase 3 – Step 0: pick the model from the MODEL env var, falling back to gpt-4.1-mini
def get_default_model() -> OpenAIModel:
    """Return MODEL from the environment if it is a known model, else the default."""
    try:
        return OpenAIModel(os.getenv("MODEL", DEFAULT_MODEL.value))
    except ValueError:
        return DEFAULT_MODEL
