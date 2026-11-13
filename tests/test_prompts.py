# Phase 5 – B4 Step 1: Layer A tests for prompt versioning (no LLM).

import hashlib

import pytest

import planner
from agents.itinerary import ItineraryAgent, build_system_prompt
from agents.prompts import PROMPTS_DIR, available_prompt_versions, load_prompt_template, resolve_prompt_version
from models import OpenAIModel, VacationInfo

# sha256 of the ORIGINAL hardcoded prompt (before B4), captured for two trips. v1 must stay byte-identical,
# because eval cache keys hash the system prompt – any drift would silently invalidate the v1 baseline.
V1_FINGERPRINTS = {
    ("2025-06-10", "2025-06-12"): "eb0e24f739bee566ffff90cf1d8746de3646258768d3d436b635e6b211b7d7d8",
    ("2025-06-12", "2025-06-14"): "0e3e6c4c7ccc120151221484cf0b29351c89d1962d413889913e79d83ee4468d",
}


@pytest.mark.parametrize(("dates", "fingerprint"), V1_FINGERPRINTS.items(), ids=["06-10..12", "06-12..14"])
def test_v1_is_byte_identical_to_the_original_prompt(dates, fingerprint):
    vi = VacationInfo.model_validate({**planner.VACATION_INFO_DICT,
                                      "date_of_arrival": dates[0], "date_of_departure": dates[1]})
    assert hashlib.sha256(build_system_prompt(vi, "v1").encode()).hexdigest() == fingerprint


@pytest.mark.parametrize(("arg", "env", "expected"), [
    (None, None, "v1"),          # default
    (None, "V1", "v1"),          # GitHub variable is uppercase today
    ("v1", "v9", "v1"),          # explicit argument wins over env
])
def test_resolve_prompt_version(monkeypatch, arg, env, expected):
    if env is None:
        monkeypatch.delenv("PROMPT_VERSION", raising=False)
    else:
        monkeypatch.setenv("PROMPT_VERSION", env)
    assert resolve_prompt_version(arg) == expected


def test_unknown_prompt_version_is_rejected():
    with pytest.raises(ValueError, match="Unknown prompt version"):
        resolve_prompt_version("v99")


def test_templates_have_exactly_the_three_placeholders():
    for version in available_prompt_versions():
        text = load_prompt_template(version).template
        assert text.count("$") == 3, version
        assert all(f"${p}" in text for p in ("schema", "weather", "activities")), version


def test_crlf_checkout_renders_identically(tmp_path, monkeypatch):
    original = (PROMPTS_DIR / "v1.md").read_text(encoding="utf-8")
    crlf_dir = tmp_path / "itinerary"
    crlf_dir.mkdir()
    (crlf_dir / "v1.md").write_bytes(original.replace("\n", "\r\n").encode("utf-8"))
    import agents.prompts as prompts
    monkeypatch.setattr(prompts, "PROMPTS_DIR", crlf_dir)
    assert prompts.load_prompt_template("v1").template == original


def test_trace_records_prompt_version(vacation_info, fake_client, llm_reply):
    agent = ItineraryAgent(client=fake_client(llm_reply), model=OpenAIModel.GPT_41_MINI)
    agent.get_itinerary(vacation_info, prompt_version="v1")
    assert agent.last_trace.prompt_version == "v1"


# Phase 5 – B4 Step 3: prompt v2 states each rule that traces back to a measured v1 failure
V2_RULES = {
    "whole-day weather (8 storm-hike violations)": "regardless of the time of day",
    "group pricing (G1#1 per-person total)": "Prices are per GROUP, not per person",
    "exact sum (G6#2 undercount)": "total_cost MUST equal the exact sum",
    "honest reasons (G5 'close to theatre')": "never \"close to\" an interest",
    "explain every choice (G6 unexplained picks)": "naming EVERY activity (by ID)",
    "fuller days (1.0-1.7 activities/day)": "aim for 2-3",
    "always fenced JSON (G1#2 no JSON, G8#0 unfenced)": "followed by the JSON inside a ```json fence",
}


def test_v2_states_every_rule():
    v2 = load_prompt_template("v2").template
    missing = [name for name, phrase in V2_RULES.items() if phrase not in v2]
    assert not missing, f"v2 is missing rules: {missing}"


def test_v1_does_not_contain_the_v2_rules():
    v1 = load_prompt_template("v1").template
    assert not any(phrase in v1 for phrase in V2_RULES.values())


def test_v2_renders_and_differs_from_v1(vacation_info):
    v1, v2 = build_system_prompt(vacation_info, "v1"), build_system_prompt(vacation_info, "v2")
    assert v1 != v2 and "event-2025-06-10-0" in v2  # same context data, different instructions
    assert available_prompt_versions()[:2] == ["v1", "v2"]


# Phase 5 – B4 Step 3b: v3 = v2 + the fix for v2's G5 regression (empty plan when no interest matched)
def test_v3_keeps_v2_rules_and_forbids_empty_days():
    v3 = load_prompt_template("v3").template
    assert all(phrase in v3 for phrase in V2_RULES.values()), "v3 must keep every v2 rule"
    assert "NEVER a reason to leave a day empty" in v3
    assert "at least one activity on EVERY day" in v3
    assert "AFTER you finalize the activity list, recompute total_cost" in v3  # v3 smoke: G1 stated 130, spent 148
