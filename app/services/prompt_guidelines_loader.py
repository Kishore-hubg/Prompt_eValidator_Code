from __future__ import annotations

import json
from functools import lru_cache
from app.core.settings import BASE_DIR


_CONFIG_DIR = BASE_DIR / "app" / "config"

@lru_cache
def load_prompt_guidelines() -> dict:
    path = _CONFIG_DIR / "prompt_guidelines_source_truth.json"
    if not path.exists():
        return {
            "strict_mode": True,
            "strict_penalty_per_miss": 3,
            "strict_penalty_cap": 15,
            "global_checks": [],
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
