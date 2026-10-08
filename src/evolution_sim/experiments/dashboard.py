"""Generate a dependency-free interactive viewer for a frozen evidence report."""

import json
from pathlib import Path
from typing import Any


def render_dashboard(report: dict[str, Any]) -> str:
    payload = json.dumps(report, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    # A script element is raw text even when its type is application/json.
    # Escaping '<' prevents a report label from terminating that element.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    template = Path(__file__).with_suffix(".html").read_text(encoding="utf-8")
    return template.replace("__VIKASA_EVIDENCE__", payload)
