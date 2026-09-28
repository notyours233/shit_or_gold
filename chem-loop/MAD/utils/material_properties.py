"""Canonical material-property task vocabulary.

The project still carries some legacy "reaction_type" plumbing from the
electrocatalysis version. These helpers provide the new material-property
vocabulary while letting old call sites normalize user/model strings in one
place.
"""

from __future__ import annotations

import re
from typing import Optional


PHOTOTHERMAL_CONVERSION_EFFICIENCY = "photothermal_conversion_efficiency"
CONDUCTIVITY = "conductivity"
THERMAL_CONDUCTIVITY = "thermal_conductivity"
FERROMAGNETISM = "ferromagnetism"
FERRIMAGNETISM = "ferrimagnetism"
ANTIFERROMAGNETISM = "antiferromagnetism"
PHOTOCATALYTIC_H2O2 = "photocatalytic_h2o2"
ANTIBACTERIAL = "antibacterial"
THERMOELECTRIC = "thermoelectric"
FURFURAL_HYDROGENATION = "furfural_hydrogenation"


MATERIAL_PROPERTY_TYPES: list[str] = [
    PHOTOTHERMAL_CONVERSION_EFFICIENCY,
    CONDUCTIVITY,
    THERMAL_CONDUCTIVITY,
    FERROMAGNETISM,
    FERRIMAGNETISM,
    ANTIFERROMAGNETISM,
    PHOTOCATALYTIC_H2O2,
    ANTIBACTERIAL,
    THERMOELECTRIC,
    FURFURAL_HYDROGENATION,
]


PROPERTY_DISPLAY_NAMES: dict[str, str] = {
    PHOTOTHERMAL_CONVERSION_EFFICIENCY: "Photothermal conversion efficiency",
    CONDUCTIVITY: "Conductivity",
    THERMAL_CONDUCTIVITY: "Thermal conductivity",
    FERROMAGNETISM: "Ferromagnetism",
    FERRIMAGNETISM: "Ferrimagnetism",
    ANTIFERROMAGNETISM: "Antiferromagnetism",
    PHOTOCATALYTIC_H2O2: "Photocatalytic H2O2 production",
    ANTIBACTERIAL: "Antibacterial performance",
    THERMOELECTRIC: "Thermoelectric performance",
    FURFURAL_HYDROGENATION: "Furfural hydrogenation",
}


PROPERTY_METRICS: dict[str, dict[str, str]] = {
    PHOTOTHERMAL_CONVERSION_EFFICIENCY: {
        "metric_key": PHOTOTHERMAL_CONVERSION_EFFICIENCY,
        "metric_name": "Photothermal conversion efficiency",
        "unit": "%",
    },
    CONDUCTIVITY: {
        "metric_key": CONDUCTIVITY,
        "metric_name": "Conductivity",
        "unit": "S/m",
    },
    THERMAL_CONDUCTIVITY: {
        "metric_key": THERMAL_CONDUCTIVITY,
        "metric_name": "Thermal conductivity",
        "unit": "W m-1 K-1",
    },
    FERROMAGNETISM: {
        "metric_key": "saturation_magnetization",
        "metric_name": "Saturation magnetization",
        "unit": "emu/g",
    },
    FERRIMAGNETISM: {
        "metric_key": "saturation_magnetization",
        "metric_name": "Saturation magnetization",
        "unit": "emu/g",
    },
    ANTIFERROMAGNETISM: {
        "metric_key": "neel_temperature",
        "metric_name": "Neel temperature",
        "unit": "K",
    },
    PHOTOCATALYTIC_H2O2: {
        "metric_key": "apparent_quantum_efficiency",
        "metric_name": "Apparent quantum efficiency",
        "unit": "%",
    },
    ANTIBACTERIAL: {
        "metric_key": "minimum_concentration",
        "metric_name": "Minimum concentration for the reported bactericidal endpoint",
        "unit": "ppm",
        "optional_metric_key": "bactericidal_threshold",
        "optional_unit": "%",
    },
    THERMOELECTRIC: {
        "metric_key": "figure_of_merit",
        "metric_name": "Dimensionless figure of merit (zT)",
        "unit": "dimensionless",
    },
    FURFURAL_HYDROGENATION: {
        "metric_key": "furfuryl_alcohol_yield",
        "metric_name": "Furfuryl alcohol yield",
        "unit": "%",
    },
}


PROPERTY_METRIC_LISTS: dict[str, list[dict[str, str]]] = {
    task: [dict(spec)] for task, spec in PROPERTY_METRICS.items()
}
PROPERTY_METRIC_LISTS[ANTIBACTERIAL] = [
    {
        "metric_key": "minimum_concentration",
        "metric_name": "Minimum concentration for the reported bactericidal endpoint",
        "unit": "ppm",
        "accepted_units": "ppm | ug/mL | mg/L",
    },
    {
        "metric_key": "bactericidal_threshold",
        "metric_name": "Bactericidal threshold",
        "unit": "%",
    },
]


_PROPERTY_ALIASES: dict[str, str] = {
    "photothermal_conversion_efficiency": PHOTOTHERMAL_CONVERSION_EFFICIENCY,
    "photothermal conversion efficiency": PHOTOTHERMAL_CONVERSION_EFFICIENCY,
    "photothermal efficiency": PHOTOTHERMAL_CONVERSION_EFFICIENCY,
    "photothermal": PHOTOTHERMAL_CONVERSION_EFFICIENCY,
    "pce": PHOTOTHERMAL_CONVERSION_EFFICIENCY,
    "conductivity": CONDUCTIVITY,
    "electrical conductivity": CONDUCTIVITY,
    "electric conductivity": CONDUCTIVITY,
    "thermal_conductivity": THERMAL_CONDUCTIVITY,
    "thermal conductivity": THERMAL_CONDUCTIVITY,
    "ferromagnetism": FERROMAGNETISM,
    "ferromagnetic": FERROMAGNETISM,
    "ferromagnetic magnetism": FERROMAGNETISM,
    "ferrimagnetism": FERRIMAGNETISM,
    "ferrimagnetic": FERRIMAGNETISM,
    "ferrimagnetic magnetism": FERRIMAGNETISM,
    "antiferromagnetism": ANTIFERROMAGNETISM,
    "anti ferromagnetism": ANTIFERROMAGNETISM,
    "anti-ferromagnetism": ANTIFERROMAGNETISM,
    "antiferromagnetic": ANTIFERROMAGNETISM,
    "anti ferromagnetic": ANTIFERROMAGNETISM,
    "anti-ferromagnetic": ANTIFERROMAGNETISM,
    "photocatalytic h2o2": PHOTOCATALYTIC_H2O2,
    "photocatalytic hydrogen peroxide": PHOTOCATALYTIC_H2O2,
    "h2o2 photocatalysis": PHOTOCATALYTIC_H2O2,
    "antibacterial": ANTIBACTERIAL,
    "antimicrobial": ANTIBACTERIAL,
    "bactericidal": ANTIBACTERIAL,
    "thermoelectric": THERMOELECTRIC,
    "thermoelectricity": THERMOELECTRIC,
    "zt": THERMOELECTRIC,
    "furfural hydrogenation": FURFURAL_HYDROGENATION,
    "furfuryl alcohol": FURFURAL_HYDROGENATION,
}


PROPERTY_KEYWORDS: dict[str, list[str]] = {
    PHOTOTHERMAL_CONVERSION_EFFICIENCY: [
        "photothermal",
        "photothermal conversion",
        "conversion efficiency",
        "solar-to-thermal",
    ],
    CONDUCTIVITY: [
        "conductivity",
        "electrical conductivity",
        "siemens",
        "s/m",
        "s cm-1",
    ],
    THERMAL_CONDUCTIVITY: [
        "thermal conductivity",
        "w m-1 k-1",
        "w/mk",
        "heat conduction",
    ],
    FERROMAGNETISM: [
        "ferromagnetism",
        "ferromagnetic",
        "saturation magnetization",
        "emu/g",
    ],
    FERRIMAGNETISM: [
        "ferrimagnetism",
        "ferrimagnetic",
        "saturation magnetization",
        "emu/g",
    ],
    ANTIFERROMAGNETISM: [
        "antiferromagnetism",
        "antiferromagnetic",
        "neel temperature",
        "neel",
        "tn",
    ],
    PHOTOCATALYTIC_H2O2: [
        "photocatalytic h2o2",
        "hydrogen peroxide production",
        "apparent quantum efficiency",
    ],
    ANTIBACTERIAL: [
        "antibacterial",
        "bactericidal",
        "minimum concentration",
        "99.9% killing",
    ],
    THERMOELECTRIC: [
        "thermoelectric",
        "figure of merit",
        "zt",
    ],
    FURFURAL_HYDROGENATION: [
        "furfural hydrogenation",
        "furfuryl alcohol yield",
    ],
}


def _clean_alias(value: str) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    s = s.replace("_", " ")
    s = re.sub(r"[\u2010-\u2015]+", "-", s)
    s = re.sub(r"[^a-z0-9%+\-/ ]+", " ", s)
    s = " ".join(s.split())
    return s


def canonical_property_type(value: object) -> Optional[str]:
    """Return the canonical material-property key, or None if unknown."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw in MATERIAL_PROPERTY_TYPES:
        return raw

    cleaned = _clean_alias(raw)
    if cleaned in _PROPERTY_ALIASES:
        return _PROPERTY_ALIASES[cleaned]

    underscored = cleaned.replace(" ", "_").replace("-", "_")
    if underscored in MATERIAL_PROPERTY_TYPES:
        return underscored
    return None


def is_material_property(value: object) -> bool:
    return canonical_property_type(value) is not None


def display_name(property_type: object) -> str:
    prop = canonical_property_type(property_type)
    if prop:
        return PROPERTY_DISPLAY_NAMES[prop]
    return str(property_type or "").strip()


def metric_spec(property_type: object) -> dict[str, str]:
    prop = canonical_property_type(property_type)
    if not prop:
        return {}
    return dict(PROPERTY_METRICS[prop])


def metric_specs(property_type: object) -> list[dict[str, str]]:
    prop = canonical_property_type(property_type)
    if not prop:
        return []
    return [dict(spec) for spec in PROPERTY_METRIC_LISTS[prop]]
