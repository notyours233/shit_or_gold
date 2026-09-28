"""Parse ground-truth (DatasetSample.answer / EvaluationSample.correct_answer).

GT is stored as a JSON dict string mapping metric_key -> raw string value.
The raw value must begin with a numeric literal, optionally followed by units.

This module lives under `chem_performance_lib/` to avoid shadowing the
`chem_performance.py` verify entrypoint module.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any


_NUMERIC_PREFIX_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")


def _parse_numeric_prefix(value: str) -> float:
    m = _NUMERIC_PREFIX_RE.match(value.strip())
    if not m:
        raise ValueError(f"GT value is not parseable (must start with a number): {value!r}")
    out = float(m.group(0))
    if not math.isfinite(out):
        raise ValueError(f"GT value must be finite, got {value!r}")
    return out


def parse_gt_json(correct_answer: str | None) -> dict[str, float]:
    if correct_answer is None:
        raise ValueError("correct_answer is None")
    if not isinstance(correct_answer, str) or not correct_answer.strip():
        raise ValueError("correct_answer is empty")

    try:
        payload = json.loads(correct_answer)
    except json.JSONDecodeError as e:
        raise ValueError(f"correct_answer is not valid JSON: {e}") from e

    if not isinstance(payload, dict) or not payload:
        raise ValueError("correct_answer must be a non-empty JSON dict string")

    out: dict[str, float] = {}
    for k, v in payload.items():
        if not isinstance(k, str) or not k.strip():
            raise ValueError(f"GT metric key must be a non-empty string, got {k!r}")

        if isinstance(v, bool) or v is None:
            raise ValueError(f"GT value must be parseable, got {v!r}")

        if isinstance(v, (int, float)):
            num = float(v)
        elif isinstance(v, str):
            num = _parse_numeric_prefix(v)
        else:
            raise ValueError(f"GT value must be str/int/float, got type={type(v)}")

        out[k] = num

    return out
