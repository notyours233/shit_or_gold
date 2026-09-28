"""Material-name-first helpers shared by experimental-feedback ingestion.

The historical closed-loop feedback pipeline was keyed by ``metals``.  New
recommendations instead use a required material name plus optional material
context.  This module keeps that new contract in one place while allowing
older metal-only feedback records to remain readable.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


REACTION_TASK_TYPES: tuple[str, ...] = (
    "HER",
    "OER",
    "ORR",
    "HOR",
    "UOR",
    "EOR",
    "HZOR",
    "O5H",
    "CO2RR",
)

MATERIAL_TASK_TYPES: tuple[str, ...] = (
    "photothermal_conversion_efficiency",
    "conductivity",
    "thermal_conductivity",
    "ferromagnetism",
    "ferrimagnetism",
    "antiferromagnetism",
    "photocatalytic_h2o2",
    "antibacterial",
    "thermoelectric",
    "furfural_hydrogenation",
)

TASK_TYPES: tuple[str, ...] = REACTION_TASK_TYPES + MATERIAL_TASK_TYPES

TASK_METRICS: dict[str, tuple[str, str]] = {
    "HER": ("overpotential_10mAcm-2", "mV"),
    "OER": ("overpotential_10mAcm-2", "mV"),
    "ORR": ("half_wave_potential", "V"),
    "HOR": ("exchange_current_density", "mA cm-2"),
    "UOR": ("potential_10mAcm-2", "V"),
    "EOR": ("mass_activity", "A mg-1"),
    "HZOR": ("overpotential_10mAcm-2", "mV"),
    "O5H": ("faradaic_efficiency", "fraction_0_to_1"),
    "CO2RR": ("partial_current_density", "mA cm-2"),
    "photothermal_conversion_efficiency": ("photothermal_conversion_efficiency", "%"),
    "conductivity": ("conductivity", "S/m"),
    "thermal_conductivity": ("thermal_conductivity", "W m-1 K-1"),
    "ferromagnetism": ("saturation_magnetization", "emu/g"),
    "ferrimagnetism": ("saturation_magnetization", "emu/g"),
    "antiferromagnetism": ("neel_temperature", "K"),
    "photocatalytic_h2o2": ("apparent_quantum_efficiency", "%"),
    "antibacterial": ("minimum_concentration", "ppm"),
    "thermoelectric": ("figure_of_merit", "dimensionless"),
    "furfural_hydrogenation": ("furfuryl_alcohol_yield", "%"),
}

TASK_DISPLAY_NAMES: dict[str, str] = {
    "HER": "析氢反应（HER）",
    "OER": "析氧反应（OER）",
    "ORR": "氧还原反应（ORR）",
    "HOR": "氢氧化反应（HOR）",
    "UOR": "尿素氧化反应（UOR）",
    "EOR": "乙醇氧化反应（EOR）",
    "HZOR": "肼氧化反应（HZOR）",
    "O5H": "5-羟甲基糠醛氧化（O5H）",
    "CO2RR": "二氧化碳电还原（CO2RR）",
    "photothermal_conversion_efficiency": "光热转换效率",
    "conductivity": "电导率",
    "thermal_conductivity": "热导率",
    "ferromagnetism": "铁磁性能",
    "ferrimagnetism": "亚铁磁性能",
    "antiferromagnetism": "反铁磁性能",
    "photocatalytic_h2o2": "光催化 H2O2 生成性能",
    "antibacterial": "抑菌性能",
    "thermoelectric": "热电性能",
    "furfural_hydrogenation": "糠醛加氢性能",
}

_ALIASES: dict[str, str] = {
    "hzor": "HZOR",
    "hydrazine oxidation": "HZOR",
    "hydrazine oxidation reaction": "HZOR",
    "photothermal": "photothermal_conversion_efficiency",
    "photothermal conversion efficiency": "photothermal_conversion_efficiency",
    "electrical conductivity": "conductivity",
    "thermal conductivity": "thermal_conductivity",
    "ferromagnetic": "ferromagnetism",
    "ferrimagnetic": "ferrimagnetism",
    "antiferromagnetic": "antiferromagnetism",
    "anti ferromagnetism": "antiferromagnetism",
    "photocatalytic h2o2": "photocatalytic_h2o2",
    "photocatalytic hydrogen peroxide": "photocatalytic_h2o2",
    "h2o2 photocatalysis": "photocatalytic_h2o2",
    "antimicrobial": "antibacterial",
    "bactericidal": "antibacterial",
    "thermoelectricity": "thermoelectric",
    "zt": "thermoelectric",
    "furfural hydrogenation": "furfural_hydrogenation",
    "furfuryl alcohol": "furfural_hydrogenation",
    "光热转换效率": "photothermal_conversion_efficiency",
    "电导率": "conductivity",
    "热导率": "thermal_conductivity",
    "铁磁性": "ferromagnetism",
    "亚铁磁性": "ferrimagnetism",
    "反铁磁性": "antiferromagnetism",
    "光催化h2o2": "photocatalytic_h2o2",
    "抑菌": "antibacterial",
    "热电": "thermoelectric",
    "糠醛加氢": "furfural_hydrogenation",
}

MATERIAL_INPUT_FIELDS: tuple[str, ...] = (
    "material_serial_no",
    "material_name",
    "major_category",
    "components",
    "structure_relationships",
    "precursors",
    "feed_ratio",
    "preparation_method",
    "elements",
    "element_content",
    "conditions",
    "custom_prompt",
)


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, Mapping):
        cleaned_map = {str(key): _clean(item) for key, item in value.items()}
        return {key: item for key, item in cleaned_map.items() if item not in (None, "", [], {})} or None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        cleaned_items = [_clean(item) for item in value]
        return [item for item in cleaned_items if item not in (None, "", [], {})] or None
    return value


def _alias_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("_", " ")
    text = re.sub(r"[\u2010-\u2015]+", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.casefold()


def canonical_task_type(value: object) -> str | None:
    """Return one of the 19 current task keys, accepting legacy aliases."""
    raw = str(value or "").strip()
    if not raw:
        return None
    upper = raw.upper().replace("-", "")
    if upper == "HZOR":
        return "HZOR"
    if upper in REACTION_TASK_TYPES:
        return upper
    if raw in MATERIAL_TASK_TYPES:
        return raw
    normalized = _alias_key(raw)
    if normalized in _ALIASES:
        return _ALIASES[normalized]
    underscored = normalized.replace("-", "_").replace(" ", "_")
    return underscored if underscored in MATERIAL_TASK_TYPES else None


def task_metric_spec(task_type: object) -> tuple[str, str] | None:
    task = canonical_task_type(task_type)
    return TASK_METRICS.get(task) if task else None


def is_material_task(task_type: object) -> bool:
    return canonical_task_type(task_type) in MATERIAL_TASK_TYPES


def task_display_name(task_type: object) -> str:
    task = canonical_task_type(task_type)
    return TASK_DISPLAY_NAMES.get(task or "", str(task_type or "").strip())


def parse_list(value: Any) -> list[str]:
    """Return explicit user-supplied list values without formula inference."""
    cleaned = _clean(value)
    if cleaned is None:
        return []
    if isinstance(cleaned, str):
        return [part.strip() for part in re.split(r"[,，;；、/]+", cleaned) if part.strip()]
    if isinstance(cleaned, Sequence) and not isinstance(cleaned, (str, bytes, bytearray)):
        return [str(item).strip() for item in cleaned if str(item).strip()]
    return [str(cleaned).strip()] if str(cleaned).strip() else []


def material_input_from_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Clean known material-input keys while preserving only provided context."""
    if not isinstance(value, Mapping):
        return {}
    payload: dict[str, Any] = {}
    for key in MATERIAL_INPUT_FIELDS:
        cleaned = _clean(value.get(key))
        if cleaned not in (None, "", [], {}):
            payload[key] = cleaned
    if "material_serial_no" in payload:
        raw_serial = payload["material_serial_no"]
        serial_text = str(raw_serial or "").strip()
        if re.fullmatch(r"[0-9]+", serial_text) and int(serial_text) >= 1:
            payload["material_serial_no"] = int(serial_text)
        else:
            payload.pop("material_serial_no", None)
    name = str(payload.get("material_name") or "").strip()
    if name:
        payload["material_name"] = name
    else:
        payload.pop("material_name", None)
    if "elements" in payload:
        elements = parse_list(payload["elements"])
        if elements:
            payload["elements"] = elements
        else:
            payload.pop("elements", None)
    return payload


def parse_material_input_json(value: Any) -> dict[str, Any]:
    """Decode an optional CSV JSON cell, returning an empty mapping on bad data."""
    if isinstance(value, Mapping):
        return material_input_from_mapping(value)
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return material_input_from_mapping(decoded if isinstance(decoded, Mapping) else None)


def _render_sequence(value: Any, *, separator: str = "、") -> str:
    cleaned = _clean(value)
    if cleaned is None:
        return ""
    if isinstance(cleaned, Mapping):
        return separator.join(f"{key} {item}" for key, item in cleaned.items())
    if isinstance(cleaned, Sequence) and not isinstance(cleaned, (str, bytes, bytearray)):
        rendered: list[str] = []
        for item in cleaned:
            if isinstance(item, Mapping):
                name = item.get("component_name") or item.get("name") or item.get("material_name")
                rendered.append(str(name or json.dumps(item, ensure_ascii=False, sort_keys=True)))
            else:
                rendered.append(str(item))
        return separator.join(rendered)
    return str(cleaned)


def _render_ratio(value: Any) -> str:
    cleaned = _clean(value)
    if cleaned is None:
        return ""
    if isinstance(cleaned, Mapping):
        return "：".join(str(item) for item in cleaned.values())
    if isinstance(cleaned, Sequence) and not isinstance(cleaned, (str, bytes, bytearray)):
        return "：".join(str(item) for item in cleaned)
    return str(cleaned)


def _render_relationships(value: Any) -> str:
    cleaned = _clean(value)
    if not isinstance(cleaned, Sequence) or isinstance(cleaned, (str, bytes, bytearray)):
        return _render_sequence(cleaned, separator="；")
    rendered: list[str] = []
    for item in cleaned:
        if not isinstance(item, Mapping):
            rendered.append(str(item))
            continue
        subject = str(item.get("subject") or "").strip()
        relation = str(item.get("relation") or item.get("relation_normalized") or "").strip()
        object_name = str(item.get("object") or "").strip()
        phrase = " ".join(part for part in (subject, relation, object_name) if part)
        if phrase:
            rendered.append(phrase)
    return "；".join(rendered)


def build_material_description(material_input: Mapping[str, Any]) -> str:
    """Render the material template using only actual populated user fields."""
    material = material_input_from_mapping(material_input)
    name = str(material.get("material_name") or "").strip()
    if not name:
        raise ValueError("material_name is required")
    sentences = [f"材料是{name}。"]
    if material.get("major_category"):
        sentences.append(f"材料类别是{material['major_category']}。")
    if material.get("components"):
        sentences.append(f"材料组分包括：{_render_sequence(material['components'])}。")
    if material.get("structure_relationships"):
        sentences.append(f"结构关系：{_render_relationships(material['structure_relationships'])}。")
    if material.get("precursors"):
        sentences.append(f"该材料是以{_render_sequence(material['precursors'])}为前驱体。")
    if material.get("feed_ratio"):
        sentences.append(f"前驱体投料比为：{_render_ratio(material['feed_ratio'])}。")
    if material.get("preparation_method"):
        sentences.append(f"通过{material['preparation_method']}的方式制备。")
    if material.get("elements"):
        sentences.append(f"含有元素：{_render_sequence(material['elements'])}。")
    if material.get("element_content"):
        sentences.append(f"元素含量大概分别为：{_render_sequence(material['element_content'])}。")
    if material.get("conditions"):
        sentences.append(f"已有实验或测试条件：{_render_sequence(material['conditions'], separator='；')}。")
    return "".join(sentences)
