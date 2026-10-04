"""Scenario loading and nested configuration overrides."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


class ScenarioError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioError(f"Could not read scenario {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ScenarioError(f"Scenario {path} must contain an object")
    return value


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result

