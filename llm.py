# Phase 3 – Step 0: LLM client setup. Reads credentials and the model name from .env,
# so no secrets live in the code.

import os

from dotenv import load_dotenv
from openai import OpenAI

from models import OpenAIModel

# Load variables from .env into os.environ (existing env vars win, so Cloud Run
# settings override a local .env).
load_dotenv()

DEFAULT_MODEL = OpenAIModel.GPT_41_MINI


# Phase 3 – Step 0: build an OpenAI client for the configured (OpenAI-compatible) endpoint
def get_client() -> OpenAI:
    """Return an OpenAI client using OPENAI_API_KEY and OPENAI_BASE_URL."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in.")
    # base_url=None makes the SDK use the default OpenAI endpoint.
    return OpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL") or None)


# Phase 3 – Step 0: pick the model from the MODEL env var, falling back to gpt-4.1-mini
def get_default_model() -> OpenAIModel:
    """Return MODEL from the environment if it is a known model, else the default."""
    try:
        return OpenAIModel(os.getenv("MODEL", DEFAULT_MODEL.value))
    except ValueError:
        return DEFAULT_MODEL
