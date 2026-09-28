from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from .constants import O5H_KEY_ALIASES

_NUM_PREFIX_RE = re.compile(
    r"^\s*(?P<num>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
)


def _decimal_to_str(value: Decimal) -> str:
    """Convert Decimal to a non-scientific string, stripping trailing zeros."""
    s = format(value, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s == "-0":
        s = "0"
    return s


def normalize_metric_key(key: str, reaction_type: str) -> str:
    """Canonicalize metric keys.

    Currently:
    - O5H: casing normalization (Faradaic_efficiency -> faradaic_efficiency)
    - HER/OER/HzOR: make η@10 mA cm^-2 explicit in the overpotential key
    """
    k = (key or "").strip()
    # Normalize common dash variants so downstream comparisons are stable.
    k = k.replace("−", "-").replace("–", "-").replace("‑", "-")
    if reaction_type == "O5H":
        if k in O5H_KEY_ALIASES:
            return O5H_KEY_ALIASES[k]
        lower = k.lower()
        # Accept already-normalized variants.
        if lower in O5H_KEY_ALIASES.values():
            return lower
    if reaction_type == "UOR":
        # UOR extractions sometimes label the same thing as "potential" or "overpotential".
        # We unify them into a single metric key and make the 10 mA cm^-2 condition explicit.
        if k in {"potential", "overpotential", "potential_10mAcm-2", "overpotential_10mAcm-2"}:
            return "potential_10mAcm-2"
    if reaction_type in {"HER", "OER"}:
        # Raw extractions use a generic "overpotential" key; we make the
        # current-density condition explicit for the model: η@10 mA cm^-2.
        if k == "overpotential":
            return "overpotential_10mAcm-2"
    if reaction_type == "HzOR":
        # For HzOR we keep only η@10 mA cm^-2, and we encode that condition in the key.
        if k == "overpotential":
            return "overpotential_10mAcm-2"
    return k


@dataclass(frozen=True)
class NormalizedMetricValue:
    """Normalized metric value with an optional unit hint."""

    value_str: str
    unit_hint: str | None


def _normalize_unit_text(unit_text: str) -> str:
    # Make unit parsing robust to unicode dashes and spacing differences.
    u = (unit_text or "").strip()
    u = u.replace("−", "-").replace("–", "-").replace("‑", "-")
    # Collapse multiple whitespace.
    u = " ".join(u.split())
    return u


def normalize_metric_value(
    value: Any,
    *,
    metric_key: str | None = None,
    reaction_type: str | None = None,
) -> NormalizedMetricValue | None:
    """Normalize a raw metric value into a parseable string and (optional) unit hint.

    Rules:
    - value must be parseable and begin with a numeric literal (after whitespace)
    - overpotential is normalized to mV (accept V/mV; store as mV)
    - other potential-like metrics are normalized to V (accept V/mV; store as V)
    - exchange_current_density is normalized to mA cm^-2 (accept A/mA cm^-2; store as mA cm^-2)
    - mass_activity is normalized to A mg^-1 (accept A/mA ...; store as A ...)
    - % -> fraction (0~1) conversion
    """
    if value is None:
        return None

    # Support numeric values (e.g., smoke datasets) by converting to a string.
    if isinstance(value, (int, float)):
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            return None
        # Numeric values are treated as already in canonical units.
        unit_hint = None
        if isinstance(metric_key, str):
            if "overpotential" in metric_key:
                unit_hint = "mV"
            elif "potential" in metric_key:
                unit_hint = "V"
            elif metric_key == "exchange_current_density":
                unit_hint = "mA cm-2"
            elif metric_key == "mass_activity":
                unit_hint = "A mg^-1"
            elif metric_key in {"faradaic_efficiency"}:
                unit_hint = "fraction_0_to_1"
        return NormalizedMetricValue(value_str=_decimal_to_str(d), unit_hint=unit_hint)

    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s:
        return None

    m = _NUM_PREFIX_RE.match(s)
    if not m:
        return None

    num_raw = m.group("num")
    try:
        num = Decimal(num_raw)
    except InvalidOperation:
        return None

    rest = _normalize_unit_text(s[m.end() :])

    # Percent -> fraction
    if "%" in rest:
        frac = num / Decimal("100")
        return NormalizedMetricValue(value_str=_decimal_to_str(frac), unit_hint="fraction_0_to_1")

    metric_key_norm = (metric_key or "").strip()
    metric_key_norm = metric_key_norm.replace("−", "-").replace("–", "-").replace("‑", "-")

    tokens = rest.split() if rest else []

    # overpotential: store as mV (accept V or mV)
    if metric_key_norm and "overpotential" in metric_key_norm:
        if tokens and tokens[0].lower() == "v":
            mv = num * Decimal("1000")
        elif tokens and tokens[0].lower() == "mv":
            mv = num
        else:
            # If the unit is missing/unknown, assume the numeric is already in canonical mV.
            mv = num
        return NormalizedMetricValue(value_str=f"{_decimal_to_str(mv)} mV", unit_hint="mV")

    # potential-like metrics (including ORR half-wave): store as V (accept V or mV)
    if metric_key_norm and ("potential" in metric_key_norm) and ("overpotential" not in metric_key_norm):
        if tokens and tokens[0].lower() == "mv":
            v = num / Decimal("1000")
        elif tokens and tokens[0].lower() == "v":
            v = num
        else:
            # If the unit is missing/unknown, assume canonical V.
            v = num
        return NormalizedMetricValue(value_str=f"{_decimal_to_str(v)} V", unit_hint="V")

    # exchange_current_density: store as mA cm^-2 (accept mA/A cm^-2)
    if metric_key_norm == "exchange_current_density":
        # Canonicalize common "cm^-2" spelling.
        rest_u = rest.replace("cm^-2", "cm-2").replace("cm^−2", "cm-2").replace("cm−2", "cm-2")
        tokens_u = rest_u.split() if rest_u else []
        if len(tokens_u) >= 2 and tokens_u[1].lower() in {"cm-2", "cm2-1"}:
            if tokens_u[0].lower() == "ma":
                ma = num
            elif tokens_u[0].lower() == "a":
                ma = num * Decimal("1000")
            else:
                return None
            return NormalizedMetricValue(value_str=f"{_decimal_to_str(ma)} mA cm-2", unit_hint="mA cm-2")
        # Unknown unit -> drop (we only keep absolute exchange current density in mA cm^-2).
        return None

    # partial_current_density (CO2RR): store as mA cm^-2 (accept mA/A cm^-2).
    if metric_key_norm == "partial_current_density":
        # If the unit is missing, assume canonical mA cm^-2 (mirrors overpotential handling).
        if not rest:
            return NormalizedMetricValue(value_str=f"{_decimal_to_str(num)} mA cm-2", unit_hint="mA cm-2")

        # Canonicalize common "cm^-2" spellings and separators.
        rest_u = rest
        rest_u = rest_u.replace("cm^-2", "cm-2").replace("cm^−2", "cm-2").replace("cm−2", "cm-2")
        rest_u = rest_u.replace("cm2", "cm-2")  # tolerate "mA/cm2"
        rest_u = rest_u.replace("/", " ").replace("·", " ")
        tokens_u = rest_u.split() if rest_u else []

        if len(tokens_u) >= 2 and tokens_u[1].lower() in {"cm-2", "cm2-1"}:
            if tokens_u[0].lower() == "ma":
                ma = num
            elif tokens_u[0].lower() == "a":
                ma = num * Decimal("1000")
            else:
                return None
            return NormalizedMetricValue(value_str=f"{_decimal_to_str(ma)} mA cm-2", unit_hint="mA cm-2")

        return None

    # mass_activity: store as A ... (accept mA ... by converting to A)
    if metric_key_norm == "mass_activity" and tokens:
        if tokens[0].lower() == "ma":
            a = num / Decimal("1000")
            unit_tail = " ".join(tokens[1:])
            unit = ("A " + unit_tail).strip()
            return NormalizedMetricValue(value_str=f"{_decimal_to_str(a)} {unit}".strip(), unit_hint=unit)

    # Default: keep the unit suffix as-is (after normalizing the numeric string).
    num_norm = _decimal_to_str(num)
    value_norm = f"{num_norm} {rest}".strip() if rest else num_norm
    return NormalizedMetricValue(value_str=value_norm, unit_hint=rest or None)
