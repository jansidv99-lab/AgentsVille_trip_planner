# Phase 5 – B4 Step 5: the CI smoke-eval regression gate (decision Q1 = "strict with a confirm run").
#   1. Run the smoke set and compare with the accepted baseline.
#   2. If cases newly fail a hard grader (or hallucinate), re-run ONLY those cases once, with a fresh repeat
#      index (= a real new LLM call, not the cache).
#   3. Fail only if a case fails again (a confirmed regression); a one-off failure is reported as a flake.
#
# Usage: python -m evals.harness.gate [--prompt-version latest] [--compare-to <shipped version>]
# Exit code: 0 = pass, 1 = confirmed regression, 2 = no baseline to compare against.

import argparse
import os
import sys
from typing import Callable, Optional

from agents.prompts import available_prompt_versions, resolve_prompt_version
from evals.harness.runner import RunConfig, RunResult, run_eval
from llm import get_client

GATE_MODEL = "gpt-4.1-mini"  # baselines are recorded with this model


# Phase 5 – B4 Step 5: cases the first run flags (new hard failures, or any hallucination)
def suspicious_cases(result: RunResult) -> list[str]:
    cases = set(result.comparison["new_case_failures"])
    if "hallucination_rate" in result.comparison["regressions"]:
        cases |= {r.case_id for r in result.records
                  if any(x.passed is False and x.slice == "B1" and x.severity == "hard" for x in r.grader_results)}
    return sorted(cases)


# Phase 5 – B4 Step 5: run the gate; returns (exit_code, human-readable summary)
def run_gate(prompt_version: str, compare_to: str, client_factory: Callable = get_client,
             **run_kwargs) -> tuple[int, str]:
    first = run_eval(RunConfig(mode="smoke", model=GATE_MODEL, prompt_version=prompt_version, compare_to=compare_to),
                     client_factory=client_factory, **run_kwargs)
    if first.comparison is None:
        return 2, f"No accepted smoke baseline for prompt {compare_to} – nothing to gate against."
    lines = [f"### Smoke eval gate – prompt `{prompt_version}` vs baseline `{compare_to}`", "",
             f"First run: {'✅ pass' if first.comparison['passed'] else '⚠️ suspicious'} · "
             f"regressions: {first.comparison['regressions'] or 'none'} · "
             f"new case failures: {first.comparison['new_case_failures'] or 'none'}"]
    if first.comparison["passed"]:
        return 0, "\n".join(lines + ["", "**Verdict: ✅ PASS**"])

    suspects = suspicious_cases(first)
    if not suspects:  # an aggregate drop with no case to confirm (shouldn't happen with smoke) → fail safe
        return 1, "\n".join(lines + ["", "**Verdict: ❌ REGRESSION** (aggregate metrics dropped)"])
    confirm = run_eval(RunConfig(mode="smoke", model=GATE_MODEL, prompt_version=prompt_version,
                                 compare_to=compare_to, case_ids=suspects, repeat_start=1),
                       client_factory=client_factory, **run_kwargs)
    confirmed = sorted(set(confirm.comparison["new_case_failures"]) |
                       set(suspicious_cases(confirm) if "hallucination_rate" in confirm.comparison["regressions"] else []))
    flakes = sorted(set(suspects) - set(confirmed))
    lines += [f"Confirm run on {', '.join(suspects)}: confirmed {confirmed or 'none'} · flakes {flakes or 'none'}"]
    if confirmed:
        return 1, "\n".join(lines + ["", f"**Verdict: ❌ REGRESSION confirmed on {', '.join(confirmed)}**"])
    return 0, "\n".join(lines + ["", "**Verdict: ✅ PASS** (first-run failures did not reproduce: flaky)"])


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-eval regression gate with a confirm run.")
    parser.add_argument("--prompt-version", default="latest", help="version under test (default: newest template)")
    parser.add_argument("--compare-to", default=None, help="baseline version (default: PROMPT_VERSION env = shipped)")
    args = parser.parse_args(argv)
    under_test = available_prompt_versions()[-1] if args.prompt_version == "latest" else args.prompt_version
    code, summary = run_gate(resolve_prompt_version(under_test), resolve_prompt_version(args.compare_to))
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
