# Phase 5 – B0 Step 4: Layer A tests for the eval harness (runner, cache, report) – fake LLM, no cost.

import json

import pytest

from evals.harness.cache import CacheMiss, CacheMode, ResponseCache, cache_key
from evals.harness.dataset import DatasetIntegrityError, content_sha256, load_dataset
from evals.harness.report import percentile
from evals.harness.runner import RunConfig, run_eval
from llm import InstrumentedClient
from quality.schema import EvalRecord

_, GOLDEN = load_dataset("itinerary_golden")


# Phase 5 – B0 Step 4: write a small dataset (G1 + G5 approved, G2 draft) into tmp_path
@pytest.fixture
def datasets_dir(tmp_path):
    cases = []
    for c in GOLDEN:
        if c.case_id in ("G1", "G2", "G5"):
            status = "draft" if c.case_id == "G2" else "approved"
            cases.append(c.model_copy(update={"review": c.review.model_copy(update={"status": status})}))
    folder = tmp_path / "datasets" / "mini"
    folder.mkdir(parents=True)
    jsonl = folder / "v0.1.0.jsonl"
    jsonl.write_text("".join(c.model_dump_json() + "\n" for c in cases), encoding="utf-8")
    manifest = {
        "name": "mini", "version": "0.1.0", "sha256": content_sha256(jsonl), "case_count": 3,
        "approved_count": 2, "smoke_cases": ["G1", "G2", "G5"],
        "changelog": [{"version": "0.1.0", "date": "2026-11-13", "changes": "test"}],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path / "datasets"


@pytest.fixture
def run(datasets_dir, tmp_path, fake_client):
    """Run the harness against the mini dataset with a fake client that returns `reply`."""
    fakes = []

    def _run(reply, cache_mode=CacheMode.RECORD, mode="smoke", repeats=None):
        def factory():
            fake = fake_client(reply)
            fakes.append(fake)
            return InstrumentedClient(fake)

        config = RunConfig(mode=mode, repeats=repeats, model="gpt-4.1-mini", cache_mode=cache_mode, dataset="mini")
        return run_eval(config, client_factory=factory, datasets_dir=datasets_dir,
                        cache=ResponseCache(tmp_path / "cache"), results_dir=tmp_path / "results")

    _run.fakes = fakes
    return _run


# Phase 5 – B0 Step 4: happy path – approved cases only, records + report written, metrics captured
def test_smoke_run_writes_records_and_report(run, llm_reply):
    result = run(llm_reply)

    assert [r.case_id for r in result.records] == ["G1", "G5"]
    assert result.skipped_drafts == ["G2"]
    assert (result.live_calls, result.cached_calls) == (2, 0)
    assert all(r.parsed and r.result("parse").passed for r in result.records)
    assert all(r.prompt_tokens == 1000 and r.cost_usd is not None for r in result.records)
    assert all(r.dataset == "mini@0.1.0" and r.source == "offline" for r in result.records)

    lines = (result.out_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
    assert [EvalRecord.model_validate_json(ln).case_id for ln in lines] == ["G1", "G5"]
    report = (result.out_dir / "report.md").read_text(encoding="utf-8")
    assert "parse pass rate | 100%" in report and "Skipped drafts:** G2" in report
    assert result.summary["overall"]["pass_rates"]["parse"] == 1.0


# Phase 5 – B1 Step 3: the same 06-10..12 plan is grounded for G1 but NOT for G5 (06-10..11 trip)
def test_report_hallucination_section(run, llm_reply):
    result = run(llm_reply)
    h = result.summary["hallucination"]

    assert h["rate"] == 0.5
    assert h["failing_runs"] == ["G5#0"]
    g5 = next(r for r in result.records if r.case_id == "G5")
    assert g5.result("plan_matches_request").passed is False
    assert result.summary["slices"]["activity_exists"] == "B1"

    report = (result.out_dir / "report.md").read_text(encoding="utf-8")
    assert "**Hallucination rate** (target 0%) | **50%**" in report
    assert "B1 · plan_matches_request pass rate | 50%" in report
    assert "Failing runs:** G5#0" in report


# Phase 5 – B0 Step 4: an unparseable reply is graded as a parse failure (and still cached)
def test_bad_reply_fails_parse_grader(run):
    result = run("sorry, no JSON")
    assert all(not r.parsed and r.result("parse").passed is False for r in result.records)
    assert result.summary["overall"]["pass_rates"]["parse"] == 0.0
    assert result.live_calls == 2


# Phase 5 – B0 Step 4: replay-only re-grades from the cache with zero LLM calls
def test_replay_only_makes_no_calls(run, llm_reply):
    first = run(llm_reply)
    replay = run("this reply must never be used", cache_mode=CacheMode.REPLAY_ONLY)

    assert (replay.live_calls, replay.cached_calls) == (0, 2)
    assert len(run.fakes) == 1  # the client factory was only used by the first run
    assert [r.trace_id for r in replay.records] == [r.trace_id for r in first.records]
    assert all(r.parsed for r in replay.records)


def test_replay_only_without_cache_raises(run):
    with pytest.raises(CacheMiss):
        run("unused", cache_mode=CacheMode.REPLAY_ONLY)


# Phase 5 – B0 Step 4: repeats are separate experiment coordinates (separate cache entries)
def test_repeats_are_cached_separately(run, llm_reply):
    result = run(llm_reply, repeats=2)
    assert [(r.case_id, r.repeat) for r in result.records] == [("G1", 0), ("G1", 1), ("G5", 0), ("G5", 1)]
    assert result.live_calls == 4
    assert len({r.cache_key for r in result.records}) == 4


# Phase 5 – B0 Step 4: API failures are recorded as errors, not cached
def test_api_error_is_recorded_not_cached(datasets_dir, tmp_path):
    class Exploding:
        def __init__(self):
            self.chat = type("C", (), {"completions": type("X", (), {"create": staticmethod(self.boom)})})()

        @staticmethod
        def boom(**kwargs):
            raise ConnectionError("network down")

    config = RunConfig(mode="smoke", model="gpt-4.1-mini", dataset="mini")
    result = run_eval(config, client_factory=lambda: InstrumentedClient(Exploding()), datasets_dir=datasets_dir,
                      cache=ResponseCache(tmp_path / "cache"), results_dir=tmp_path / "results")
    assert all(r.error == "ConnectionError: network down" and not r.parsed for r in result.records)
    assert not (tmp_path / "cache").exists() or not any((tmp_path / "cache").iterdir())


# Phase 5 – B0 Step 4: the cache key reacts to every coordinate, including the prompt text
@pytest.mark.parametrize("change", ["case", "dataset", "prompt_version", "model", "repeat", "prompt_text"])
def test_cache_key_changes_with_each_coordinate(change):
    base = dict(case_id="G1", dataset="d@1.0.0", prompt_version="v1", model="gpt-4.1-mini", repeat=0,
                system_prompt="Role: planner")
    changed = dict(base)
    field = {"case": "case_id", "prompt_text": "system_prompt"}.get(change, change)
    changed[field] = 1 if field == "repeat" else f"{base[field]}-changed"
    assert cache_key(**base) != cache_key(**changed)
    assert cache_key(**base) == cache_key(**dict(base))  # stable


def test_edited_dataset_without_version_bump_is_rejected(datasets_dir):
    jsonl = datasets_dir / "mini" / "v0.1.0.jsonl"
    jsonl.write_text(jsonl.read_text(encoding="utf-8").replace("Yuri", "Yuki"), encoding="utf-8")
    with pytest.raises(DatasetIntegrityError, match="bump the dataset version"):
        load_dataset("mini", datasets_dir)


def test_percentile_nearest_rank():
    assert percentile([], 95) is None
    assert percentile([10.0], 95) == 10.0
    assert percentile([float(v) for v in range(1, 21)], 95) == 19.0


def test_invalid_run_config():
    with pytest.raises(ValueError):
        RunConfig(mode="huge")
    with pytest.raises(ValueError):
        RunConfig(model="gpt-5")
