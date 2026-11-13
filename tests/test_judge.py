# Phase 5 – B3 Step 3: Layer A tests for the LLM judge plumbing – fake client, no network, no cost.

import json
from types import SimpleNamespace

import pytest

from evals.harness.cache import CacheMode, ResponseCache
from evals.harness.runner import RunConfig, run_eval
from llm import InstrumentedClient
from quality.graders.judge import JUDGE_GRADERS, JudgeScore, build_judge_input, call_judge, judge_results

GOOD = JudgeScore(relevancy=5, relevancy_rationale="all served", coherence=4, coherence_rationale="smooth",
                  reasons_honest=True, stretched_reasons=[], reasoning_faithful=True, faithfulness_evidence="matches")
STRETCHED = GOOD.model_copy(update={"relevancy": 3, "reasons_honest": False,
                                    "stretched_reasons": ["close to theatre interest"]})


class FakeClientWithJudge:
    """Planner calls (chat.completions.create) return `reply`; judge calls (beta…parse) return `score`."""

    def __init__(self, reply: str, score: JudgeScore = GOOD, fail_judge: bool = False):
        self.reply, self.score, self.fail_judge = reply, score, fail_judge
        self.judge_calls: list[dict] = []
        usage = SimpleNamespace(prompt_tokens=800, completion_tokens=200)
        self.chat = SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kw: SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))],
                                                usage=usage)))
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=self._parse)))
        self._usage = usage

    def _parse(self, **kw):
        self.judge_calls.append(kw)
        if self.fail_judge:
            raise TimeoutError("judge timed out")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=self.score))], usage=self._usage)


# Phase 5 – B3 Step 3: verdict → soft GraderResults with normalized scores
def test_judge_results_mapping():
    results = {r.grader: r for r in judge_results(STRETCHED)}
    assert set(results) == set(JUDGE_GRADERS)
    assert results["judge_relevancy"].score == 0.5 and results["judge_relevancy"].passed is False  # 3/5
    assert results["judge_coherence"].score == 0.75 and results["judge_coherence"].passed is True   # 4/5
    assert results["judge_reasons_honest"].passed is False
    assert results["judge_reasons_honest"].details["stretched_reasons"] == ["close to theatre interest"]
    assert all(r.slice == "B3" and r.severity == "soft" for r in results.values())


# Phase 5 – B3 Step 3: judge input carries ground truth (availability, real settings) and the ANALYSIS
def test_build_judge_input(vacation_info, sample_plan):
    payload = json.loads(build_judge_input(vacation_info, sample_plan, "ANALYSIS: think\nFINAL OUTPUT: {}"))
    assert [t["name"] for t in payload["travelers"]] == ["Yuri", "Hiro"]
    assert {a["date"] for a in payload["available_activities"]} == {"2025-06-10", "2025-06-11", "2025-06-12"}
    hike = next(a for a in payload["available_activities"] if a["id"] == "event-2025-06-12-0")
    assert hike["setting"] == "outdoor"
    assert payload["analysis"] == "ANALYSIS: think"
    assert payload["plan_total_cost"] == 108


# Phase 5 – B3 Step 3: structured output, temperature 0, model from JUDGE_MODEL; metrics captured
def test_call_judge_request_shape(monkeypatch, vacation_info, sample_plan):
    monkeypatch.setenv("JUDGE_MODEL", "gpt-4.1")
    fake = FakeClientWithJudge("unused")
    client = InstrumentedClient(fake)
    score = call_judge(client, vacation_info, sample_plan, "ANALYSIS: x")
    call = fake.judge_calls[0]
    assert score == GOOD
    assert call["model"] == "gpt-4.1" and call["temperature"] == 0 and call["response_format"] is JudgeScore
    assert client.last_call.prompt_tokens == 800 and client.last_call.cost_usd is not None


# Phase 5 – B3 Step 3: harness – judge runs on parsed plans, verdicts cached, replay makes 0 judge calls
def _run(tmp_path, datasets_dir, fake, cache_mode=CacheMode.RECORD):
    config = RunConfig(mode="smoke", model="gpt-4.1-mini", dataset="mini", judge=True, cache_mode=cache_mode)
    return run_eval(config, client_factory=lambda: InstrumentedClient(fake), datasets_dir=datasets_dir,
                    cache=ResponseCache(tmp_path / "cache"), results_dir=tmp_path / "results")


@pytest.fixture
def datasets_dir(tmp_path):
    from tests.test_eval_harness import GOLDEN  # reuse the real golden cases
    from evals.harness.dataset import content_sha256
    cases = [c.model_copy(update={"review": c.review.model_copy(update={"status": "approved"})})
             for c in GOLDEN if c.case_id in ("G1", "G5")]
    folder = tmp_path / "datasets" / "mini"
    folder.mkdir(parents=True)
    jsonl = folder / "v0.1.0.jsonl"
    jsonl.write_text("".join(c.model_dump_json() + "\n" for c in cases), encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({
        "name": "mini", "version": "0.1.0", "sha256": content_sha256(jsonl), "case_count": 2, "approved_count": 2,
        "smoke_cases": ["G1", "G5"], "changelog": [{"version": "0.1.0", "date": "2026-11-13", "changes": "t"}]}),
        encoding="utf-8")
    return tmp_path / "datasets"


def test_harness_judge_and_replay(tmp_path, datasets_dir, llm_reply):
    fake = FakeClientWithJudge(llm_reply, STRETCHED)
    first = _run(tmp_path, datasets_dir, fake)
    assert len(fake.judge_calls) == 2
    assert first.summary["meta"]["judge"]["live_calls"] == 2
    assert all(r.result("judge_reasons_honest").passed is False for r in first.records)

    replay = _run(tmp_path, datasets_dir, FakeClientWithJudge("unused"), CacheMode.REPLAY_ONLY)
    assert replay.summary["meta"]["judge"] == {**replay.summary["meta"]["judge"], "live_calls": 0, "cached_calls": 2}
    assert [r.result("judge_relevancy").details["rating"] for r in replay.records] == [3, 3]


def test_judge_failure_is_recorded_not_cached(tmp_path, datasets_dir, llm_reply):
    result = _run(tmp_path, datasets_dir, FakeClientWithJudge(llm_reply, fail_judge=True))
    assert all("TimeoutError" in r.result("judge_error").details["error"] for r in result.records)
    assert not (tmp_path / "cache" / "judge").exists() or not any((tmp_path / "cache" / "judge").iterdir())


def test_judge_skips_unparsed_replies(tmp_path, datasets_dir):
    fake = FakeClientWithJudge("sorry, no JSON")
    result = _run(tmp_path, datasets_dir, fake)
    assert fake.judge_calls == []
    assert all(r.result("judge_relevancy") is None for r in result.records)
