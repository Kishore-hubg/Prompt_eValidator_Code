import json
from functools import lru_cache
from app.core.settings import BASE_DIR

_CONFIG_DIR = BASE_DIR / "app" / "config"

@lru_cache
def load_personas() -> dict:
    path = _CONFIG_DIR / "persona_criteria_source_truth.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_persona(persona_id: str) -> dict:
    personas = load_personas()
    return personas.get(persona_id, personas["persona_0"])
