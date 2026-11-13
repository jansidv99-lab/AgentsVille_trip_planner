# Phase 5 – B2 Step 1: human-approved ground truth for each activity's setting (indoor/outdoor/flex).
# The mock calendar only has free-text descriptions; these labels turn them into checkable facts
# for the weather_safety grader. Unapproved labels are refused, so a draft can't silently drive grading.

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

from project_lib import INCLIMATE_WEATHER_CONDITIONS
from quality.schema import Review

LABELS_PATH = Path(__file__).resolve().parent / "ground_truth" / "activity_labels.json"
Setting = Literal["indoor", "outdoor", "flex"]  # flex = outdoor with a stated indoor rain backup
BAD_WEATHER: frozenset[str] = frozenset(INCLIMATE_WEATHER_CONDITIONS)  # thunderstorm, rainy
SAFE_IN_BAD_WEATHER: frozenset[str] = frozenset({"indoor", "flex"})


class ActivityLabel(BaseModel):
    setting: Setting
    evidence: str  # quoted verbatim from the activity description


class LabelsFile(BaseModel):
    name: str
    version: str
    description: str
    review: Review
    labels: dict[str, ActivityLabel]


class UnapprovedLabelsError(Exception):
    """The labels file hasn't been approved by a human reviewer."""


# Phase 5 – B2 Step 1: load (once) and require human approval
@lru_cache(maxsize=1)
def load_labels(path: Path = LABELS_PATH) -> LabelsFile:
    data = LabelsFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if data.review.status != "approved":
        raise UnapprovedLabelsError(f"{path.name} v{data.version} is '{data.review.status}', not approved")
    return data


def setting_of(activity_id: str) -> Optional[Setting]:
    label = load_labels().labels.get(activity_id)
    return label.setting if label else None
