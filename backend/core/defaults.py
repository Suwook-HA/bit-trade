import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path


DEFAULTS_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "config" / "scalpingDefaults.json"


@lru_cache(maxsize=1)
def load_scalping_defaults() -> dict:
    return json.loads(DEFAULTS_PATH.read_text(encoding="utf-8"))


SCALPING_DEFAULTS = load_scalping_defaults()


def get_strategy_params(strategy: str) -> dict:
    return deepcopy(SCALPING_DEFAULTS["strategy_params"][strategy])
