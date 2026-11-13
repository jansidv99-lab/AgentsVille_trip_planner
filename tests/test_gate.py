# Phase 5 – B4 Step 5: Layer A tests for the CI smoke gate (confirm-run policy) – scripted fake LLM, no cost.

from types import SimpleNamespace

import pytest

import evals.harness.baseline as baseline_mod
import evals.harness.runner as runner_mod
from evals.harness.cache import ResponseCache
from evals.harness.gate import run_gate
from llm import InstrumentedClient


class ScriptedClient:
    """Returns the scripted replies in order (one per planner call), then repeats the last one."""

    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        msg = SimpleNamespace(content=reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10))


@pytest.fixture
def gate(tmp_path, monkeypatch):
    from evals.harness.dataset import content_sha256
    from tests.test_eval_harness import GOLDEN
    import json
    # mini dataset: G1 only, approved, smoke
    case = next(c for c in GOLDEN if c.case_id == "G1")
    folder = tmp_path / "datasets" / "mini"
    folder.mkdir(parents=True)
    jsonl = folder / "v0.1.0.jsonl"
    jsonl.write_text(case.model_dump_json() + "\n", encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({
        "name": "mini", "version": "0.1.0", "sha256": content_sha256(jsonl), "case_count": 1, "approved_count": 1,
        "smoke_cases": ["G1"], "changelog": [{"version": "0.1.0", "date": "2026-11-13", "changes": "t"}]}),
        encoding="utf-8")
    bdir = tmp_path / "baselines"
    monkeypatch.setattr(runner_mod, "baseline_path", lambda *a, **k: baseline_mod.baseline_path(*a, directory=bdir))
    original = runner_mod.RunConfig

    def mini_config(**kw):  # point every gate run at the mini dataset
        return original(**{**kw, "dataset": "mini"})
    monkeypatch.setattr("evals.harness.gate.RunConfig", mini_config)

    counter = {"n": 0}

    def run(replies, accept_baseline_with=None):
        counter["n"] += 1
        kwargs = dict(datasets_dir=tmp_path / "datasets", cache=ResponseCache(tmp_path / f"cache{counter['n']}"),
                      results_dir=tmp_path / "results")
        if accept_baseline_with is not None:  # record a baseline from a known-good reply (own cache, like CI)
            good = runner_mod.run_eval(original(mode="smoke", model="gpt-4.1-mini", prompt_version="v1", dataset="mini"),
                                       client_factory=lambda: InstrumentedClient(ScriptedClient([accept_baseline_with])),
                                       **{**kwargs, "cache": ResponseCache(tmp_path / f"baseline-cache{counter['n']}")})
            baseline_mod.write_baseline(good.snapshot, bdir)
        client = ScriptedClient(replies)
        code, summary = run_gate("v1", "v1", client_factory=lambda: InstrumentedClient(client), **kwargs)
        return code, summary, client.calls
    return run


def test_gate_passes_when_nothing_regresses(gate, llm_reply):
    code, summary, calls = gate([llm_reply], accept_baseline_with=llm_reply)
    assert code == 0 and calls == 1 and "PASS" in summary


def test_gate_treats_a_non_reproducing_failure_as_flaky(gate, llm_reply):
    code, summary, calls = gate(["sorry, no JSON", llm_reply], accept_baseline_with=llm_reply)
    assert code == 0 and calls == 2  # 1 smoke call + 1 confirm call
    assert "flaky" in summary and "flakes ['G1']" in summary


def test_gate_fails_on_a_confirmed_regression(gate, llm_reply):
    code, summary, calls = gate(["sorry, no JSON", "still no JSON"], accept_baseline_with=llm_reply)
    assert code == 1 and calls == 2
    assert "REGRESSION confirmed on G1" in summary


def test_gate_without_baseline_returns_2(gate, llm_reply):
    code, summary, _ = gate([llm_reply])
    assert code == 2 and "No accepted smoke baseline" in summary
