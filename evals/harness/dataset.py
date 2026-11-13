# Phase 5 – B0 Step 1: load a versioned golden dataset and verify it against its manifest.

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from quality.schema import EvalCase

DATASETS_DIR = Path(__file__).resolve().parent.parent / "datasets"


# Phase 5 – B0 Step 1: one changelog line in the manifest
class ChangelogEntry(BaseModel):
    version: str
    date: str
    changes: str


# Phase 5 – B0 Step 1: manifest.json – the dataset's identity card
class Manifest(BaseModel):
    name: str
    version: str
    sha256: str
    case_count: int
    approved_count: int
    smoke_cases: list[str]
    changelog: list[ChangelogEntry]


class DatasetIntegrityError(Exception):
    """The dataset file doesn't match its manifest (edited without a version bump)."""


# Phase 5 – B0 Step 1: hash with normalized line endings, so Windows (CRLF) and Linux (LF) agree
def content_sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def dataset_path(name: str, version: str, datasets_dir: Path = DATASETS_DIR) -> Path:
    return datasets_dir / name / f"v{version}.jsonl"


def load_manifest(name: str, datasets_dir: Path = DATASETS_DIR) -> Manifest:
    return Manifest.model_validate_json((datasets_dir / name / "manifest.json").read_text(encoding="utf-8"))


# Phase 5 – B0 Step 1: parse every JSONL line into an EvalCase
def read_cases(path: Path) -> list[EvalCase]:
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [EvalCase.model_validate(json.loads(ln)) for ln in lines]


# Phase 5 – B0 Step 1: load the manifest's current version, verifying hash and counts
def load_dataset(name: str, datasets_dir: Path = DATASETS_DIR) -> tuple[Manifest, list[EvalCase]]:
    manifest = load_manifest(name, datasets_dir)
    path = dataset_path(name, manifest.version, datasets_dir)
    actual = content_sha256(path)
    if actual != manifest.sha256:
        raise DatasetIntegrityError(
            f"{path.name} sha256 {actual[:12]}… != manifest {manifest.sha256[:12]}… – "
            "bump the dataset version and update manifest.json"
        )
    cases = read_cases(path)
    approved = sum(c.review.status == "approved" for c in cases)
    if len(cases) != manifest.case_count or approved != manifest.approved_count:
        raise DatasetIntegrityError(
            f"manifest counts (cases={manifest.case_count}, approved={manifest.approved_count}) "
            f"don't match the file (cases={len(cases)}, approved={approved})"
        )
    return manifest, cases
