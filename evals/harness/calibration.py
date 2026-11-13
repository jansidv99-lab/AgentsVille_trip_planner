# Phase 5 – B3 Step 5: calibration – does the LLM judge (and the keyword heuristic) agree with a human?
# 1) build_sheet(): a BLIND labeling sheet (judge verdicts hidden, to avoid anchoring the human).
# 2) parse_labels(): the human's compact chat answers, e.g. "1: 4 y n" → relevancy 4, honest yes, faithful no.
# 3) agreement(): judge-vs-human and heuristic-vs-human agreement → which judge metrics may become gates.

import json
import re
from pathlib import Path
from typing import Optional

from evals.harness.dataset import load_dataset
from evals.harness.runner import parse_reply
from project_lib import ACTIVITY_CALENDAR
from quality.graders.reasoning import analysis_text
from quality.labels import setting_of
from quality.schema import EvalRecord

CALIBRATION_DIR = Path(__file__).resolve().parent.parent / "calibration"
TRUST_THRESHOLD = 0.80  # a judge metric may gate regressions only with ≥ 80% agreement

# Stratified sample (case, repeat): covers every keyword flag and the suspected judge-leniency cases.
SAMPLE: list[tuple[str, int]] = [("G5", 0), ("G5", 2), ("G6", 0), ("G6", 1), ("G1", 1),
                                 ("G2", 0), ("G3", 1), ("G4", 0), ("G7", 2), ("G8", 2)]
CALENDAR = {a["activity_id"]: a for a in ACTIVITY_CALENDAR}


def load_records(results_dir: Path) -> dict[tuple[str, int], EvalRecord]:
    lines = (results_dir / "records.jsonl").read_text(encoding="utf-8").splitlines()
    return {(r.case_id, r.repeat): r for r in (EvalRecord.model_validate_json(ln) for ln in lines)}


# Phase 5 – B3 Step 5: one readable, blind item for the human
def render_item(n: int, case, raw: str) -> str:
    plan, _ = parse_reply(raw)
    vi = case.vacation_info
    out = [f"## Item {n}: {case.case_id}",
           f"**Travelers:** " + "; ".join(f"{t.name} ({', '.join(map(str, t.interests))})" for t in vi.travelers),
           f"**Dates:** {vi.date_of_arrival} → {vi.date_of_departure} · **Budget:** {vi.budget} · "
           f"**Plan total_cost:** {plan.total_cost} (sum of prices: "
           f"{sum(r.activity.price for d in plan.itinerary_days for r in d.activity_recommendations)})", ""]
    for d in plan.itinerary_days:
        out.append(f"**{d.date} – {d.weather.condition}**")
        for r in d.activity_recommendations:
            real = CALENDAR.get(r.activity.activity_id, {}).get("related_interests", [])
            out.append(f"- `{r.activity.activity_id}` {r.activity.name} · real interests: {', '.join(real)} · "
                       f"{setting_of(r.activity.activity_id)} · {r.activity.price}")
            out += [f"  - reason: \"{reason}\"" for reason in r.reasons_for_recommendation]
    out += ["", "<details><summary>ANALYSIS (for judging faithfulness)</summary>", "", "```text",
            analysis_text(raw).strip(), "```", "</details>", ""]
    return "\n".join(out)


# Phase 5 – B3 Step 5: write the blind labeling sheet
def build_sheet(results_dir: Path, cache_dir: Path, out_path: Path, dataset: str = "itinerary_golden") -> Path:
    _, cases = load_dataset(dataset)
    by_id = {c.case_id: c for c in cases}
    records = load_records(results_dir)
    header = [
        "# B3 calibration – blind labeling sheet", "",
        "For each item, judge **independently** (the AI judge's verdicts are hidden on purpose).", "",
        "| Field | Answer | Meaning |", "|---|---|---|",
        "| relevancy | 1–5 | 5 = every traveler's *achievable* interests well served given what was available; "
        "3 = noticeable gaps; 1 = ignores the travelers |",
        "| honest | y / n | n if ANY reason claims a match the activity doesn't have (compare with its *real interests*); "
        "contextual mentions (\"after the hiking event\") are fine |",
        "| faithful | y / n | n if the ANALYSIS decides or claims something the final plan contradicts |", "",
        "**Reply in chat, one line per item:** `1: 4 y y`", "",
    ]
    items = []
    for n, (cid, rep) in enumerate(SAMPLE, start=1):
        rec = records[(cid, rep)]
        raw = json.loads((cache_dir / f"{rec.cache_key}.json").read_text(encoding="utf-8"))["raw_response"]
        items.append(render_item(n, by_id[cid], raw))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(header + items), encoding="utf-8")
    return out_path


# Phase 5 – B3 Step 5: "3: 4 y n" lines → {item: (relevancy, honest, faithful)}
def parse_labels(text: str) -> dict[int, tuple[int, bool, bool]]:
    labels = {}
    for m in re.finditer(r"(\d+)\s*[:.)-]\s*([1-5])\s+([yn])\s+([yn])", text.lower()):
        labels[int(m.group(1))] = (int(m.group(2)), m.group(3) == "y", m.group(4) == "y")
    return labels


def _rate(pairs: list[tuple]) -> Optional[float]:
    return round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else None


# Phase 5 – B3 Step 5: agreement report – judge vs human, keyword heuristic vs human
def agreement(labels: dict[int, tuple[int, bool, bool]], records: dict[tuple[str, int], EvalRecord]) -> dict:
    rel, rel_pm1, honest, faithful, heuristic = [], [], [], [], []
    # Disagreements on honesty, by direction (who said "dishonest"):
    errors = {"judge_missed_dishonest": [], "judge_false_alarm": [],
              "keyword_missed_dishonest": [], "keyword_false_alarm": []}
    for n, (cid, rep) in enumerate(SAMPLE, start=1):
        if n not in labels:
            continue
        h_rel, h_honest, h_faithful = labels[n]
        rec = records[(cid, rep)]
        j_rel = rec.result("judge_relevancy").details["rating"]
        j_honest = rec.result("judge_reasons_honest").passed
        j_faithful = rec.result("judge_reasoning_faithful").passed
        k_honest = rec.result("reason_grounding").passed  # keyword heuristic: no flags = honest
        rel.append((j_rel, h_rel))
        rel_pm1.append((abs(j_rel - h_rel) <= 1, True))
        honest.append((j_honest, h_honest))
        faithful.append((j_faithful, h_faithful))
        heuristic.append((k_honest, h_honest))
        item = f"{n} ({cid}#{rep})"
        for who, verdict in (("judge", j_honest), ("keyword", k_honest)):
            if not h_honest and verdict:
                errors[f"{who}_missed_dishonest"].append(item)
            elif h_honest and not verdict:
                errors[f"{who}_false_alarm"].append(item)
    metrics = {
        "judge_relevancy_exact": _rate(rel),
        "judge_relevancy_within_1": _rate(rel_pm1),
        "judge_reasons_honest": _rate(honest),
        "judge_reasoning_faithful": _rate(faithful),
        "keyword_heuristic_honest": _rate(heuristic),
    }
    trusted = {k: (v is not None and v >= TRUST_THRESHOLD) for k, v in metrics.items()}
    return {"n": len(rel), "agreement": metrics, "trusted_as_gate": trusted, "honesty_errors": errors, "pairs": {
        "relevancy (judge, human)": rel, "honest (judge, human)": honest, "faithful (judge, human)": faithful,
        "honest (keyword, human)": heuristic}}
