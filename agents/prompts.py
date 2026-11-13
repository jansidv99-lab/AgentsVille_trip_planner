# Phase 5 – B4 Step 1: versioned prompt templates (prompts/itinerary/v*.md), selected by PROMPT_VERSION.
# Prompt versioning as configuration: the live app switches versions via an env var (instant rollback),
# and every trace/eval record carries the version it used.

import os
from pathlib import Path
from string import Template
from typing import Optional

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "itinerary"
DEFAULT_PROMPT_VERSION = "v1"


# Phase 5 – B4 Step 1: explicit version > PROMPT_VERSION env (case-insensitive, e.g. "V1") > v1
def resolve_prompt_version(version: Optional[str] = None) -> str:
    chosen = (version or os.getenv("PROMPT_VERSION") or DEFAULT_PROMPT_VERSION).strip().lower()
    if chosen not in available_prompt_versions():
        raise ValueError(f"Unknown prompt version {chosen!r}; available: {available_prompt_versions()}")
    return chosen


def available_prompt_versions() -> list[str]:
    return sorted(p.stem for p in PROMPTS_DIR.glob("v*.md"))


# Phase 5 – B4 Step 1: load a template; normalize line endings so Windows checkouts render identically
def load_prompt_template(version: str) -> Template:
    text = (PROMPTS_DIR / f"{version}.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    return Template(text)


# Phase 5 – B4 Step 1: fill $schema / $weather / $activities (substitute() fails loudly on a typo)
def render_prompt(version: str, *, schema: str, weather: str, activities: str) -> str:
    return load_prompt_template(version).substitute(schema=schema, weather=weather, activities=activities)
