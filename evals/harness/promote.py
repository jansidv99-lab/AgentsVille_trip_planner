# Phase 5 – B5 Step 6: the data flywheel – production runs that failed a hard grader or got 👎 become DRAFT golden
# cases; after human review, approved ones are promoted into a new MINOR dataset version (with a changelog).
#
#   python -m evals.harness.promote mine --days 7          # BigQuery → evals/datasets/<ds>/candidates.jsonl (gitignored)
#   python -m evals.harness.promote approve P1 P3 --reviewer <name>   # → v1.1.0.jsonl + manifest (commit via PR)
#
# Privacy: logs/BigQuery keep real traveler names (decision), but candidates get SYNTHETIC names, because
# approved cases are committed to the public repo.

import argparse
import datetime
import json
import string
import subprocess
import sys
from pathlib import Path
from typing import Optional

from evals.harness.dataset import DATASETS_DIR, content_sha256, dataset_path, load_dataset
from quality.graders.constraints import CONSTRAINT_GRADERS
from quality.graders.grounding import HALLUCINATION_GRADERS
from quality.schema import EvalCase, Expectations, Review

BQ_DATASET = "agentsville_observability"
MINE_SQL = """
SELECT trace_id, CAST(timestamp AS STRING) AS ts, prompt_version, TO_JSON_STRING(request) AS request_json,
       hard_failed, rating, comment, task_success
FROM `{project}.{dataset}.runs_with_feedback`
WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
  AND (rating = 'down' OR ARRAY_LENGTH(hard_failed) > 0)
ORDER BY timestamp DESC
"""


def candidates_path(dataset: str = "itinerary_golden", datasets_dir: Path = DATASETS_DIR) -> Path:
    return datasets_dir / dataset / "candidates.jsonl"


# Phase 5 – B5 Step 6: query BigQuery with the bq CLI (no extra Python dependency)
def fetch_flagged_rows(project: str, days: int) -> list[dict]:
    sql = MINE_SQL.format(project=project, dataset=BQ_DATASET, days=int(days))
    out = subprocess.run(["bq", "--project_id", project, "query", "--use_legacy_sql=false", "--format=json",
                          "--max_rows=1000", sql], capture_output=True, text=True, check=True).stdout
    return json.loads(out or "[]")


def _signature(request: dict) -> tuple:
    """Two runs with the same trip request are one candidate (dedupe)."""
    return (request["date_of_arrival"], request["date_of_departure"], request["budget"],
            tuple(sorted((t["age"], tuple(sorted(t["interests"]))) for t in request["travelers"])))


def _tags(hard_failed: list[str], rating: Optional[str]) -> list[str]:
    tags = []
    if any(g in HALLUCINATION_GRADERS for g in hard_failed):
        tags.append("grounding")
    if any(g in CONSTRAINT_GRADERS for g in hard_failed) or "parse" in hard_failed:
        tags.append("constraints")
    if "weather_safety" in hard_failed:
        tags.append("weather")
    if rating == "down" or not tags:
        tags.append("relevancy")
    return tags


# Phase 5 – B5 Step 6: flagged rows → draft EvalCases (synthetic names, derived expectations, review = draft)
def rows_to_candidates(rows: list[dict], existing_ids: set[str]) -> list[EvalCase]:
    seen, out = set(), []
    n = 1 + max([int(i[1:]) for i in existing_ids if i.startswith("P") and i[1:].isdigit()] or [0])
    for row in rows:
        request = json.loads(row["request_json"]) if isinstance(row.get("request_json"), str) else row["request"]
        sig = _signature(request)
        if sig in seen:
            continue
        seen.add(sig)
        for i, t in enumerate(request["travelers"]):
            t["name"] = f"Traveler {string.ascii_uppercase[i]}"  # synthetic – never real names in the repo
        hard = list(row.get("hard_failed") or [])
        rating, comment = row.get("rating"), (row.get("comment") or "").strip()
        test_flag = " [PIPELINE TEST – reject]" if "pipeline test" in comment.lower() else ""
        notes = (f"From production trace {row['trace_id'][:8]} ({str(row.get('ts', ''))[:10]}, prompt "
                 f"{row.get('prompt_version')}): hard_failed={hard or 'none'}"
                 + (f"; feedback={rating}" if rating else "") + (f"; comment: \"{comment[:200]}\"" if comment else "")
                 + test_flag)
        out.append(EvalCase(
            case_id=f"P{n}", title=f"Production: {', '.join(hard) or 'thumbs down'}"[:80], tags=_tags(hard, rating),
            vacation_info=request, expectations=Expectations(max_cost=request["budget"], notes=notes),
            review=Review(status="draft"),
        ))
        n += 1
    return out


def write_candidates(cands: list[EvalCase], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(c.model_dump_json() + "\n" for c in cands), encoding="utf-8", newline="\n")


def _bump_minor(version: str) -> str:
    major, minor, _ = (int(x) for x in version.split("."))
    return f"{major}.{minor + 1}.0"


# Phase 5 – B5 Step 6: approved candidates → new minor dataset version (+ manifest changelog)
def promote_to_dataset(approved_ids: list[str], reviewer: str, dataset: str = "itinerary_golden",
                       datasets_dir: Path = DATASETS_DIR, today: Optional[datetime.date] = None) -> Path:
    manifest, cases = load_dataset(dataset, datasets_dir)
    cands = {c.case_id: c for c in (EvalCase.model_validate_json(ln) for ln in
                                    candidates_path(dataset, datasets_dir).read_text(encoding="utf-8").splitlines() if ln)}
    missing = [i for i in approved_ids if i not in cands]
    if missing:
        raise KeyError(f"unknown candidate ids: {missing}")
    today = today or datetime.date.today()
    promoted = [cands[i].model_copy(update={"review": Review(status="approved", reviewer=reviewer, reviewed_on=today)})
                for i in approved_ids]
    new_version = _bump_minor(manifest.version)
    new_path = dataset_path(dataset, new_version, datasets_dir)
    write_candidates(cases + promoted, new_path)  # same JSONL format; existing cases unchanged
    all_cases = cases + promoted
    data = manifest.model_dump()
    data.update(version=new_version, sha256=content_sha256(new_path), case_count=len(all_cases),
                approved_count=sum(c.review.status == "approved" for c in all_cases))
    data["changelog"].append({"version": new_version, "date": today.isoformat(),
                              "changes": f"+{', '.join(approved_ids)} promoted from production feedback "
                                         f"(reviewed by {reviewer})"})
    (datasets_dir / dataset / "manifest.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8",
                                                          newline="\n")
    return new_path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Production → golden dataset candidates (B5).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    mine = sub.add_parser("mine")
    mine.add_argument("--days", type=int, default=7)
    mine.add_argument("--project", default=None, help="GCP project (default: GCP_PROJECT_ID from .env)")
    approve = sub.add_parser("approve")
    approve.add_argument("ids", nargs="+")
    approve.add_argument("--reviewer", required=True)
    args = parser.parse_args(argv)

    if args.cmd == "mine":
        import os
        from dotenv import load_dotenv
        load_dotenv()
        project = (args.project or os.getenv("GCP_PROJECT_ID", "")).strip("`\"' ")
        _, cases = load_dataset("itinerary_golden")
        cands = rows_to_candidates(fetch_flagged_rows(project, args.days), {c.case_id for c in cases})
        write_candidates(cands, candidates_path())
        print(f"{len(cands)} draft candidate(s) → {candidates_path()}")
        for c in cands:
            print(f"  {c.case_id}: {c.title} | {c.expectations.notes}")
    else:
        path = promote_to_dataset(args.ids, args.reviewer)
        print(f"Promoted {args.ids} → {path.name} (commit it via a PR; then record a new baseline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
