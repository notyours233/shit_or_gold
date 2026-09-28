"""Parse model outputs for chem-performance tasks.

Expected output contains:
  <think>...</think>
  <answer>{...json...}</answer>

We only parse the <answer> JSON payload into a dict[str, float] and provide a helper
to detect the presence of a <think> block.

This module lives under `chem_performance_lib/` to avoid shadowing the
`chem_performance.py` verify entrypoint module.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any


_NUMERIC_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_NUM_PREFIX_RE = re.compile(r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
_DASH_TRANSLATION = str.maketrans({"−": "-", "–": "-", "‑": "-", "—": "-"})


def has_think_block(text: str) -> bool:
    return re.search(r"<think>\s*.*?\s*</think>", text, flags=re.IGNORECASE | re.DOTALL) is not None


def extract_tag_block(text: str, tag: str) -> str:
    """Extract the inner text of a <tag>...</tag> block."""
    m = re.search(
        rf"<{re.escape(tag)}>\s*(.*?)\s*</{re.escape(tag)}>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not m:
        raise ValueError(f"Missing <{tag}>...</{tag}> block")
    return m.group(1)


def _find_matching_brace(text: str, start: int) -> int | None:
    """Find matching '}' for a '{' at position start (handles strings/escapes)."""
    if start < 0 or start >= len(text) or text[start] != "{":
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def _extract_json_dict_from_text(text: str) -> dict[str, Any] | None:
    """Extract a JSON dict embedded in arbitrary text (best-effort)."""
    if not text or not isinstance(text, str):
        return None
    for pos in (m.start() for m in re.finditer(r"\{", text)):
        end = _find_matching_brace(text, pos)
        if end is None:
            continue
        raw = text[pos : end + 1]
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict) and obj:
            return obj
    return None


def extract_structured_answer_object(response_text: str) -> dict[str, Any] | None:
    """Extract the answer object from either legacy tags or structured JSON.

    Supported response shapes:
    - Legacy: <answer>{...}</answer>
    - Structured: {"think": "...", "answer": {...}}
    - Direct dict: {...}  (treated as answer dict)
    """
    # 1) Legacy <answer> tag
    try:
        answer_text = extract_tag_block(response_text, "answer")
        payload = json.loads(answer_text)
        if isinstance(payload, dict) and payload:
            return payload
    except Exception:
        pass

    # 2) Structured JSON object in the full text
    obj = None
    s = (response_text or "").strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except Exception:
            obj = None
    if obj is None:
        obj = _extract_json_dict_from_text(response_text)

    if not isinstance(obj, dict) or not obj:
        return None

    if isinstance(obj.get("answer"), dict) and obj.get("answer"):
        return obj.get("answer")

    # Fallback: treat the dict itself as the answer dict.
    return obj


def _normalize_unit_text(text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return ""
    s = s.translate(_DASH_TRANSLATION)
    s = s.replace("·", " ").replace("⋅", " ").replace("•", " ")
    s = s.replace("cm^-2", "cm-2").replace("cm^−2", "cm-2").replace("cm−2", "cm-2")
    s = s.replace("mg^-1", "mg-1").replace("mg^−1", "mg-1").replace("mg−1", "mg-1")
    s = s.replace("g^-1", "g-1").replace("g^−1", "g-1").replace("g−1", "g-1")
    s = s.replace("m^-1", "m-1").replace("m^−1", "m-1").replace("m−1", "m-1")
    s = s.replace("K^-1", "K-1").replace("K^−1", "K-1").replace("K−1", "K-1")
    s = s.replace("k^-1", "k-1").replace("k^−1", "k-1").replace("k−1", "k-1")
    s = s.replace("cm^-1", "cm-1").replace("cm^−1", "cm-1").replace("cm−1", "cm-1")
    s = s.replace("/cm2", " cm-2").replace("/cm²", " cm-2")
    s = s.replace("/cm", " cm-1").replace("/m", " m-1").replace("/kg", " kg-1").replace("/g", " g-1")
    s = s.replace("cm²", "cm2").replace("cm2", "cm-2")
    s = s.replace("m²", "m2")
    s = re.sub(r"(?i)W\s*/\s*\(\s*m\s*K\s*\)", "W m-1 K-1", s)
    s = re.sub(r"(?i)W\s*/\s*m\s*K\b", "W m-1 K-1", s)
    s = re.sub(r"(?i)W\s*/\s*mK\b", "W m-1 K-1", s)
    s = s.replace("/", " ")
    s = " ".join(s.split())
    return s


def _canonical_unit(unit: str) -> str:
    u = _normalize_unit_text(unit).lower()
    u = u.replace("s m-1", "S m-1").replace("s cm-1", "S cm-1")
    return u


def _coerce_number_with_unit(value_text: str, *, expected_unit: str) -> float:
    """Best-effort repair: accept a numeric string that includes units.

    This is ONLY used when the caller provides an expected_unit hint for the metric key.
    """
    expected_unit = str(expected_unit or "").strip()
    if not expected_unit:
        raise ValueError("Expected unit is required for unit-repair parsing")

    s = str(value_text or "").strip()
    m = _NUM_PREFIX_RE.match(s)
    if not m:
        raise ValueError(f"Predicted value must start with a number, got {value_text!r}")
    num = float(m.group("num"))
    if not math.isfinite(num):
        raise ValueError(f"Predicted value must be finite, got {value_text!r}")

    rest = _normalize_unit_text(s[m.end() :])
    rest_low = rest.lower()

    # Special: faradaic_efficiency is canonicalized to fraction_0_to_1 in this project.
    if expected_unit == "fraction_0_to_1":
        # Percent forms.
        if "%" in rest:
            return num / 100.0
        # Common "unitless" hints.
        if not rest or any(tok in rest_low for tok in ("fraction", "unitless", "dimensionless", "ratio")):
            return num
        raise ValueError(f"Unit mismatch for fraction metric: expected {expected_unit!r}, got {rest!r}")

    if expected_unit == "%":
        if not rest:
            return num * 100.0 if 0.0 <= num <= 1.0 else num
        if "%" in rest:
            return num
        if any(tok in rest_low for tok in ("fraction", "ratio", "unitless", "dimensionless")):
            return num * 100.0 if 0.0 <= num <= 1.0 else num
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    # overpotential: canonical mV (accept V/mV)
    if expected_unit == "mV":
        if not rest:
            return num
        tok0 = rest_low.split()[0] if rest_low.split() else ""
        if tok0 in {"mv"}:
            return num
        if tok0 in {"v"}:
            return num * 1000.0
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    # potential-like metrics: canonical V (accept V/mV)
    if expected_unit == "V":
        if not rest:
            return num
        tok0 = rest_low.split()[0] if rest_low.split() else ""
        if tok0 in {"v"}:
            return num
        if tok0 in {"mv"}:
            return num / 1000.0
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    # current density: canonical mA cm-2 (accept mA/A cm-2)
    if expected_unit == "mA cm-2":
        if not rest:
            return num
        toks = rest_low.split()
        if len(toks) >= 2 and toks[1] in {"cm-2"}:
            if toks[0] == "ma":
                return num
            if toks[0] == "a":
                return num * 1000.0
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    if expected_unit == "S/m":
        if not rest:
            return num
        toks = rest_low.split()
        if len(toks) >= 2 and toks[0] in {"s", "ms"} and toks[1] in {"m-1", "cm-1"}:
            out = num
            if toks[0] == "ms":
                out *= 1.0e-3
            if toks[1] == "cm-1":
                out *= 100.0
            return out
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    if expected_unit == "W m-1 K-1":
        if not rest:
            return num
        toks = rest_low.split()
        if len(toks) >= 3 and toks[0] == "w" and toks[1] == "m-1" and toks[2] == "k-1":
            return num
        if rest_low in {"w mk-1", "w m k-1"}:
            return num
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    if expected_unit == "emu/g":
        if not rest:
            return num
        toks = rest_low.split()
        if len(toks) >= 2 and toks[0] == "emu" and toks[1] == "g-1":
            return num
        # SI identity: 1 A m2/kg == 1 emu/g for mass magnetization.
        if len(toks) >= 3 and toks[0] == "a" and toks[1] == "m2" and toks[2] == "kg-1":
            return num
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    if expected_unit == "K":
        if not rest:
            return num
        tok0 = rest_low.split()[0] if rest_low.split() else ""
        if tok0 == "k":
            return num
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    # Mass activity: keep strict on the mass basis (mg vs g), but allow mA->A conversion.
    if expected_unit in {"A mg^-1", "A g^-1"}:
        if not rest:
            return num
        toks = rest_low.split()
        if len(toks) >= 2:
            current, mass_basis = toks[0], toks[1]
            # Normalize "mg-1"/"g-1" token to expected spelling.
            if expected_unit.endswith("mg^-1") and mass_basis != "mg-1":
                raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")
            if expected_unit.endswith("g^-1") and mass_basis != "g-1":
                raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")
            if current == "a":
                return num
            if current == "ma":
                return num / 1000.0
        raise ValueError(f"Unit mismatch: expected {expected_unit!r}, got {rest!r}")

    # Unknown unit hint: do not attempt repair.
    raise ValueError(f"Unsupported expected_unit for repair: {expected_unit!r}")


def _coerce_number(value: Any, *, expected_unit: str | None = None) -> float:
    """Convert a JSON value into a finite float.

    Accepts:
    - int/float (but not bool)
    - numeric strings like "0.6" (no units)
    - when expected_unit is provided: numeric strings with units, e.g. "300 mV"
    """
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Predicted value must be a number, got {value!r}")

    if isinstance(value, (int, float)):
        out = float(value)
    elif isinstance(value, str):
        s = value.strip()
        if _NUMERIC_RE.match(s):
            out = float(s)
        else:
            if expected_unit is None:
                raise ValueError(f"Predicted value must be a unit-free number, got {value!r}")
            out = _coerce_number_with_unit(s, expected_unit=str(expected_unit))
    else:
        raise ValueError(f"Predicted value must be a number, got type={type(value)}")

    if not math.isfinite(out):
        raise ValueError(f"Predicted value must be finite, got {value!r}")
    if expected_unit == "%" and 0.0 <= out <= 1.0:
        out *= 100.0
    return out


def parse_answer_json(response_text: str) -> dict[str, float]:
    """Parse <answer> JSON dict from the model response."""
    answer_text = extract_tag_block(response_text, "answer")
    try:
        payload = json.loads(answer_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"<answer> is not valid JSON: {e}") from e

    if not isinstance(payload, dict) or not payload:
        raise ValueError("<answer> must be a non-empty JSON object (dict)")

    out: dict[str, float] = {}
    for k, v in payload.items():
        if not isinstance(k, str) or not k.strip():
            raise ValueError(f"Metric key must be a non-empty string, got {k!r}")
        out[k] = _coerce_number(v)
    return out


def parse_answer_numbers(response_text: str, *, expected_units: dict[str, str] | None = None) -> dict[str, float]:
    """Parse a predicted answer dict with numeric values.

    This is the unified parser used by verify:
    - prefers <answer>...</answer> when present
    - otherwise accepts the structured JSON shapes emitted by newer MAD runners

    By default we enforce "numbers-only" (no units). If expected_units are provided,
    we allow a best-effort repair pass that strips/validates units and converts to
    the expected canonical unit (e.g., V <-> mV).
    """
    payload = extract_structured_answer_object(response_text)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Missing or invalid answer object (expected a non-empty JSON dict)")

    out: dict[str, float] = {}
    for k, v in payload.items():
        if not isinstance(k, str) or not k.strip():
            raise ValueError(f"Metric key must be a non-empty string, got {k!r}")
        unit_hint = None
        if expected_units is not None:
            unit_hint = expected_units.get(k)
        out[k] = _coerce_number(v, expected_unit=unit_hint)
    return out
