# Phase 5 – B0 Step 5: Layer B eval entry points for pytest. These CALL THE LLM (cost credits),
# so they're marked `eval` and excluded from the default `pytest` run (see pytest.ini).
#
#   pytest -m eval                      # smoke: 3 approved smoke cases × 1 repeat (≤ 3 live calls)
#
# Replies are cached (evals/cache/), so re-running only calls the LLM for missing coordinates.

import pytest

from evals.harness.report import pass_rate
from evals.harness.runner import RunConfig, run_eval

pytestmark = pytest.mark.eval


# Phase 5 – B0 Step 5: smoke eval – every approved smoke case must parse into a TravelPlan
def test_smoke_eval():
    result = run_eval(RunConfig(mode="smoke"))
    print(f"\nReport: {result.out_dir / 'report.md'}")

    assert result.records, f"no approved smoke cases to run (skipped drafts: {result.skipped_drafts})"
    assert pass_rate(result.records, "parse") == 1.0, [r.error for r in result.records if r.error]
