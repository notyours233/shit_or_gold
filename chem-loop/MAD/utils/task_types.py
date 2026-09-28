"""Unified task vocabulary for reaction and material-property recommendations.

The merged recommender ranks one candidate pool, but retrieval must keep reaction
evidence/experience separated from material-property evidence/experience.
"""

from __future__ import annotations

import re
from typing import Optional

from utils.material_properties import (
    MATERIAL_PROPERTY_TYPES,
    PROPERTY_DISPLAY_NAMES,
    PROPERTY_METRICS,
    PROPERTY_METRIC_LISTS,
    canonical_property_type,
)


TASK_FAMILY_REACTION = "reaction"
TASK_FAMILY_MATERIAL = "material_property"
TASK_FAMILY_GLOBAL = "global"

REACTION_TYPES: list[str] = [
    "HER",
    "OER",
    "ORR",
    "HOR",
    "UOR",
    "EOR",
    "HZOR",
    "O5H",
    "CO2RR",
]

UNIFIED_TASK_TYPES: list[str] = REACTION_TYPES + list(MATERIAL_PROPERTY_TYPES)

REACTION_DISPLAY_NAMES: dict[str, str] = {
    "HER": "Hydrogen evolution reaction",
    "OER": "Oxygen evolution reaction",
    "ORR": "Oxygen reduction reaction",
    "HOR": "Hydrogen oxidation reaction",
    "UOR": "Urea oxidation reaction",
    "EOR": "Ethanol oxidation reaction",
    "HZOR": "Hydrazine oxidation reaction",
    "O5H": "O5H reaction",
    "CO2RR": "CO2 reduction reaction",
}

REACTION_METRICS: dict[str, dict[str, str]] = {
    "HER": {"metric_key": "eta10", "metric_name": "eta10", "unit": "mV"},
    "OER": {"metric_key": "eta10", "metric_name": "eta10", "unit": "mV"},
    "ORR": {"metric_key": "e_half", "metric_name": "E1/2", "unit": "V"},
    "HOR": {"metric_key": "j0", "metric_name": "j0", "unit": "mA cm-2"},
    "UOR": {"metric_key": "e_at_10", "metric_name": "E@10", "unit": "V"},
    "EOR": {"metric_key": "mass_activity", "metric_name": "Mass activity", "unit": "A mgmetal-1"},
    "HZOR": {"metric_key": "e_at_10", "metric_name": "E@10", "unit": "mV"},
    "O5H": {"metric_key": "faradaic_efficiency", "metric_name": "FE", "unit": "%"},
    "CO2RR": {
        "metric_key": "faradaic_efficiency",
        "metric_name": "Product FE",
        "unit": "%",
        "optional_metric_key": "partial_current_density",
        "optional_unit": "mA cm-2",
    },
}

_REACTION_ALIASES: dict[str, str] = {
    "her": "HER",
    "hydrogen evolution": "HER",
    "hydrogen evolution reaction": "HER",
    "oer": "OER",
    "oxygen evolution": "OER",
    "oxygen evolution reaction": "OER",
    "orr": "ORR",
    "oxygen reduction": "ORR",
    "oxygen reduction reaction": "ORR",
    "hor": "HOR",
    "hydrogen oxidation": "HOR",
    "hydrogen oxidation reaction": "HOR",
    "uor": "UOR",
    "urea oxidation": "UOR",
    "urea oxidation reaction": "UOR",
    "eor": "EOR",
    "ethanol oxidation": "EOR",
    "ethanol oxidation reaction": "EOR",
    "hzor": "HZOR",
    "hydrazine oxidation": "HZOR",
    "hydrazine oxidation reaction": "HZOR",
    "o5h": "O5H",
    "co2rr": "CO2RR",
    "co2 reduction": "CO2RR",
    "co2 reduction reaction": "CO2RR",
    "carbon dioxide reduction": "CO2RR",
    "carbon dioxide reduction reaction": "CO2RR",
}


def _clean_alias(value: object) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    s = s.replace("_", " ")
    s = re.sub(r"[\u2010-\u2015]+", "-", s)
    s = re.sub(r"[^a-z0-9+\-/ ]+", " ", s)
    return " ".join(s.split())


def canonical_reaction_type(value: object) -> Optional[str]:
    """Return the canonical reaction key, or None if unknown."""
    raw = str(value or "").strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper in REACTION_TYPES:
        return upper
    cleaned = _clean_alias(raw)
    if cleaned in _REACTION_ALIASES:
        return _REACTION_ALIASES[cleaned]
    compact = cleaned.replace(" ", "").replace("-", "")
    if compact in _REACTION_ALIASES:
        return _REACTION_ALIASES[compact]
    return None


def canonical_task_type(value: object) -> Optional[str]:
    """Return the canonical reaction or material-property task key."""
    prop = canonical_property_type(value)
    if prop:
        return prop
    return canonical_reaction_type(value)


def task_family(value: object) -> Optional[str]:
    task = canonical_task_type(value)
    if not task:
        return None
    if task in MATERIAL_PROPERTY_TYPES:
        return TASK_FAMILY_MATERIAL
    if task in REACTION_TYPES:
        return TASK_FAMILY_REACTION
    return None


def is_reaction_task(value: object) -> bool:
    return task_family(value) == TASK_FAMILY_REACTION


def is_material_task(value: object) -> bool:
    return task_family(value) == TASK_FAMILY_MATERIAL


def task_display_name(value: object) -> str:
    task = canonical_task_type(value)
    if not task:
        return str(value or "").strip()
    if task in PROPERTY_DISPLAY_NAMES:
        return PROPERTY_DISPLAY_NAMES[task]
    return REACTION_DISPLAY_NAMES.get(task, task)


def task_metric_spec(value: object) -> dict[str, str]:
    task = canonical_task_type(value)
    if not task:
        return {}
    if task in PROPERTY_METRICS:
        return dict(PROPERTY_METRICS[task])
    if task in REACTION_METRICS:
        return dict(REACTION_METRICS[task])
    return {}


def task_metric_specs(value: object) -> list[dict[str, str]]:
    """Return every supported metric for one task, primary metric first."""
    task = canonical_task_type(value)
    if not task:
        return []
    if task in PROPERTY_METRIC_LISTS:
        return [dict(spec) for spec in PROPERTY_METRIC_LISTS[task]]
    spec = REACTION_METRICS.get(task)
    if not spec:
        return []
    metrics = [
        {
            "metric_key": str(spec.get("metric_key") or ""),
            "metric_name": str(spec.get("metric_name") or spec.get("metric_key") or ""),
            "unit": str(spec.get("unit") or ""),
        }
    ]
    optional_key = str(spec.get("optional_metric_key") or "").strip()
    if optional_key:
        metrics.append(
            {
                "metric_key": optional_key,
                "metric_name": optional_key,
                "unit": str(spec.get("optional_unit") or ""),
                "optional": "true",
            }
        )
    return metrics


def task_metadata_aliases(value: object) -> list[str]:
    """Return metadata spellings that may appear in Chroma for a task key."""
    task = canonical_task_type(value)
    if not task:
        raw = str(value or "").strip()
        return [raw] if raw else []

    aliases: list[str] = [task]
    if task in PROPERTY_DISPLAY_NAMES:
        aliases.append(PROPERTY_DISPLAY_NAMES[task].lower())
    elif task in REACTION_DISPLAY_NAMES:
        aliases.append(task)

    compact: list[str] = []
    for alias in aliases:
        s = str(alias or "").strip()
        if s and s not in compact:
            compact.append(s)
    return compact


def canonical_task_or_raw(value: object) -> str:
    task = canonical_task_type(value)
    if task:
        return task
    return str(value or "").strip().upper()
