# Phase 5 – B0 Step 4: the eval runner – cases × repeats for one (model, prompt version),
# with record/replay caching, graders, EvalRecords (JSONL) and a report.
#
# Usage:
#   python -m evals.harness.runner --mode smoke                    # 3 live calls (first time)
#   python -m evals.harness.runner --mode smoke --cache replay-only # 0 calls: re-grade cached replies
#   python -m evals.harness.runner --mode full --repeats 3          # 8 cases × 3

import argparse
import hashlib
import datetime
import io
import json
import subprocess
import sys
import textwrap
import uuid
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from pydantic import ValidationError

from agents.itinerary import ItineraryAgent, ItineraryParseError, build_system_prompt, extract_json
from evals.harness.cache import CacheMiss, CacheMode, ResponseCache, cache_key
from evals.harness.dataset import DATASETS_DIR, load_dataset
from evals.harness.report import pass_rate, write_report
from llm import get_client, get_default_model
from models import OpenAIModel, TravelPlan
from quality.graders import GradingInput, run_graders
from quality.graders.judge import JudgeScore, call_judge, judge_model, judge_prompt_sha, judge_results
from quality.schema import EvalCase, EvalRecord, GraderResult

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


# Phase 5 – B0 Step 4: the experiment coordinates of one run
@dataclass
class RunConfig:
    mode: str = "smoke"                       # "smoke" or "full"
    repeats: Optional[int] = None             # default: 1 for smoke, 3 for full
    model: str = field(default_factory=lambda: get_default_model().value)
    prompt_version: str = "v1"
    cache_mode: CacheMode = CacheMode.RECORD
    dataset: str = "itinerary_golden"
    judge: bool = False                       # Phase 5 – B3 Step 3: also run the (offline) LLM judge

    def __post_init__(self):
        if self.mode not in ("smoke", "full"):
            raise ValueError(f"mode must be 'smoke' or 'full', not {self.mode!r}")
        if self.repeats is None:
            self.repeats = 1 if self.mode == "smoke" else 3
        self.model = OpenAIModel(self.model).value  # validates the model name
        self.cache_mode = CacheMode(self.cache_mode)


# Phase 5 – B0 Step 4: what a run produced
@dataclass
class RunResult:
    records: list[EvalRecord]
    out_dir: Path
    summary: dict
    live_calls: int
    cached_calls: int
    skipped_drafts: list[str]


def git_sha() -> Optional[str]:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return None


# Phase 5 – B0 Step 4: parse a (cached) raw reply exactly like the agent does
def parse_reply(raw_response: str) -> tuple[Optional[TravelPlan], Optional[str]]:
    try:
        return TravelPlan.model_validate_json(extract_json(raw_response)), None
    except ValidationError as err:
        return None, f"The model's reply did not match the TravelPlan schema ({err.error_count()} errors)."


# Phase 5 – B0 Step 4: smoke = approved smoke cases; full = all approved cases
def select_cases(cases: list[EvalCase], mode: str) -> tuple[list[EvalCase], list[str]]:
    wanted = [c for c in cases if mode == "full" or c.smoke]
    approved = [c for c in wanted if c.review.status == "approved"]
    skipped = [c.case_id for c in wanted if c.review.status != "approved"]
    return approved, skipped


# Phase 5 – B3 Step 3: judge one parsed plan, with its own record/replay cache
# (key = planner reply key + judge model + judge prompt hash, so a rubric change re-judges automatically)
def judge_plan(case: EvalCase, plan: TravelPlan, raw: str, planner_key: str, cache: ResponseCache,
               cache_mode: CacheMode, get_judge_client: Callable) -> tuple[list[GraderResult], dict]:
    model = judge_model()
    key = hashlib.sha256(f"{planner_key}|{model}|{judge_prompt_sha()}".encode()).hexdigest()[:32]
    entry = None if cache_mode == CacheMode.REFRESH else cache.get(key)
    if entry is None and cache_mode == CacheMode.REPLAY_ONLY:
        raise CacheMiss(f"No cached judge verdict for {case.case_id} ({model}). Run once with --judge.")
    if entry is None:
        client = get_judge_client()
        try:
            score = call_judge(client, case.vacation_info, plan, raw, model)
        except Exception as err:  # judge failure: record it as an info result, don't cache it
            return ([GraderResult(grader="judge_error", slice="B3", severity="info",
                                  details={"error": f"{type(err).__name__}: {err}"})],
                    {"live": 1, "cached": 0, "cost_usd": 0.0})
        m = getattr(client, "last_call", None)
        entry = {"score": score.model_dump(), "judge_model": model, "cost_usd": getattr(m, "cost_usd", None),
                 "latency_ms": getattr(m, "latency_ms", None)}
        cache.put(key, entry)
        stats = {"live": 1, "cached": 0, "cost_usd": entry["cost_usd"] or 0.0}
    else:
        stats = {"live": 0, "cached": 1, "cost_usd": 0.0}
    return judge_results(JudgeScore.model_validate(entry["score"])), stats


# Phase 5 – B0 Step 4: run the experiment
def run_eval(
    config: RunConfig,
    client_factory: Callable = get_client,
    datasets_dir: Path = DATASETS_DIR,
    cache: Optional[ResponseCache] = None,
    results_dir: Path = RESULTS_DIR,
) -> RunResult:
    manifest, all_cases = load_dataset(config.dataset, datasets_dir)
    dataset_ref = f"{manifest.name}@{manifest.version}"
    cases, skipped = select_cases(all_cases, config.mode)
    cache = cache or ResponseCache()
    started = datetime.datetime.now(datetime.timezone.utc)
    sha = git_sha()
    client = None  # created lazily: replay-only runs never need an API key
    records: list[EvalRecord] = []
    live = cached = 0
    judge_cache = ResponseCache(cache.directory / "judge")  # Phase 5 – B3 Step 3
    judge_stats = {"live": 0, "cached": 0, "cost_usd": 0.0}

    def get_client_once():
        nonlocal client
        client = client or client_factory()
        return client

    for case in cases:
        # The agent sends the dedented, stripped prompt (ChatAgent.reset); hash exactly that.
        system_prompt = textwrap.dedent(build_system_prompt(case.vacation_info)).strip()
        for repeat in range(config.repeats):
            key = cache_key(case.case_id, dataset_ref, config.prompt_version, config.model, repeat, system_prompt)
            entry = None if config.cache_mode == CacheMode.REFRESH else cache.get(key)

            if entry is None and config.cache_mode == CacheMode.REPLAY_ONLY:
                raise CacheMiss(f"No cached reply for {case.case_id} repeat {repeat} ({config.model}, "
                                f"{config.prompt_version}). Run once without --cache replay-only.")

            if entry is None:
                client = client or client_factory()
                with redirect_stdout(io.StringIO()):  # ChatAgent prints every prompt; keep output readable
                    agent = ItineraryAgent(client=client, model=OpenAIModel(config.model))
                try:
                    with redirect_stdout(io.StringIO()):
                        plan = agent.get_itinerary(case.vacation_info, model=OpenAIModel(config.model))
                    trace, error = agent.last_trace, None
                except ItineraryParseError as err:
                    plan, trace, error = None, err.trace, str(err)
                except Exception as err:  # API/network failure: record it, don't cache it
                    records.append(EvalRecord(
                        trace_id=str(uuid.uuid4()), timestamp=datetime.datetime.now(datetime.timezone.utc),
                        source="offline", case_id=case.case_id, dataset=dataset_ref,
                        prompt_version=config.prompt_version, model=config.model, repeat=repeat,
                        parsed=False, error=f"{type(err).__name__}: {err}", cache_key=key, git_sha=sha,
                    ))
                    continue
                entry = {
                    "trace_id": trace.trace_id, "raw_response": trace.raw_response,
                    "latency_ms": trace.latency_ms, "prompt_tokens": trace.prompt_tokens,
                    "completion_tokens": trace.completion_tokens, "cost_usd": trace.cost_usd,
                    "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }
                cache.put(key, entry)
                live += 1
            else:
                plan, error = parse_reply(entry["raw_response"])
                cached += 1

            results = run_graders(GradingInput.for_case(case, plan, entry["raw_response"]))  # Phase 5 – B1 Step 1
            if config.judge and plan is not None:  # Phase 5 – B3 Step 3: offline LLM judge
                verdicts, stats = judge_plan(case, plan, entry["raw_response"], key, judge_cache,
                                             config.cache_mode, get_client_once)
                results += verdicts
                judge_stats = {k: judge_stats[k] + stats[k] for k in judge_stats}

            records.append(EvalRecord(
                trace_id=entry["trace_id"], timestamp=datetime.datetime.now(datetime.timezone.utc),
                source="offline", case_id=case.case_id, dataset=dataset_ref,
                prompt_version=config.prompt_version, model=config.model, repeat=repeat,
                latency_ms=entry["latency_ms"], prompt_tokens=entry["prompt_tokens"],
                completion_tokens=entry["completion_tokens"], cost_usd=entry["cost_usd"],
                parsed=plan is not None, error=error,
                grader_results=results,
                cache_key=key, git_sha=sha,
            ))

    out_dir = results_dir / f"{started:%Y%m%dT%H%M%SZ}_{config.mode}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "records.jsonl").write_text(
        "".join(r.model_dump_json() + "\n" for r in records), encoding="utf-8")
    meta = {
        "dataset": dataset_ref, "mode": config.mode, "model": config.model,
        "prompt_version": config.prompt_version, "repeats": config.repeats, "git_sha": sha,
        "started": started.isoformat(timespec="seconds"), "live_calls": live, "cached_calls": cached,
        "skipped_drafts": skipped,
        # Phase 5 – B3 Step 3: judge accounting (offline LLM judge)
        "judge": ({"model": judge_model(), "live_calls": judge_stats["live"], "cached_calls": judge_stats["cached"],
                   "cost_usd": round(judge_stats["cost_usd"], 6)} if config.judge else None),
    }
    summary = write_report(out_dir, records, meta)
    return RunResult(records, out_dir, summary, live, cached, skipped)


# Phase 5 – B0 Step 4: command-line entry point
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Layer B itinerary eval harness.")
    parser.add_argument("--mode", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--repeats", type=int, default=None)
    parser.add_argument("--model", default=get_default_model().value, choices=[m.value for m in OpenAIModel])
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--cache", choices=[m.value for m in CacheMode], default=CacheMode.RECORD.value)
    parser.add_argument("--judge", action="store_true", help="also run the offline LLM judge (costs calls; cached)")
    args = parser.parse_args(argv)

    result = run_eval(RunConfig(mode=args.mode, repeats=args.repeats, model=args.model,
                                prompt_version=args.prompt_version, cache_mode=args.cache, judge=args.judge))
    rate = pass_rate(result.records, "parse")
    print(f"Runs: {len(result.records)} ({result.live_calls} live, {result.cached_calls} cached) | "
          f"parse pass rate: {rate if rate is not None else '-'} | skipped drafts: {result.skipped_drafts or 'none'}")
    print(f"Report: {result.out_dir / 'report.md'}")
    print(json.dumps(result.summary["overall"], indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
