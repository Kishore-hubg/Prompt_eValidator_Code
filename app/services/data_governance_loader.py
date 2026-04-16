from __future__ import annotations

import json
from functools import lru_cache

from app.core.settings import BASE_DIR


_CONFIG_DIR = BASE_DIR / "app" / "config"
_POLICY_FILE = "data_strategy_business_rules_source_truth.json"


@lru_cache
def load_data_governance_policy() -> dict:
    """Load Day2 data-governance source-of-truth policy from app config."""
    path = _CONFIG_DIR / _POLICY_FILE
    if not path.exists():
        return {
            "document": {"title": "missing", "scope": "missing"},
            "governance_rules": {},
            "alerting_rules": [],
            "implementation_constraints_for_current_repo": {},
        }
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
