# Phase 5 – B0 Step 4: record/replay cache for raw LLM replies.
# Expensive, non-deterministic calls are stored once; graders can then be improved and re-run
# for free and reproducibly ("replay-only").

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


class CacheMode(str, Enum):
    RECORD = "record"            # call the LLM only when no cached reply exists (default)
    REPLAY_ONLY = "replay-only"  # never call the LLM; a missing reply is an error
    REFRESH = "refresh"          # always call the LLM and overwrite the cache


class CacheMiss(Exception):
    """replay-only mode found no cached reply for an experiment coordinate."""


# Phase 5 – B0 Step 4: the key covers every coordinate that could change the reply.
# Hashing the system prompt means ANY prompt change automatically misses the cache.
def cache_key(case_id: str, dataset: str, prompt_version: str, model: str, repeat: int, system_prompt: str) -> str:
    prompt_sha = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()
    raw = json.dumps([case_id, dataset, prompt_version, model, repeat, prompt_sha])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


# Phase 5 – B0 Step 4: one JSON file per cached reply
class ResponseCache:
    def __init__(self, directory: Path = CACHE_DIR):
        self.directory = directory

    def get(self, key: str) -> Optional[dict]:
        path = self.directory / f"{key}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def put(self, key: str, entry: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{key}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
