"""Canonical material input contract for recommendation and debate prompts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping, Sequence


_OPTIONAL_FIELDS = (
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

_ELEMENT_SYMBOLS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al", "Si", "P", "S",
    "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga",
    "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd",
    "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Pm",
    "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os",
    "Ir", "Pt", "Au", "Hg", "Tl", "Pb", "Bi", "Po", "At", "Rn", "Fr", "Ra", "Ac", "Th", "Pa",
    "U", "Np", "Pu", "Am", "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr", "Rf", "Db", "Sg",
    "Bh", "Hs", "Mt", "Ds", "Rg", "Cn", "Nh", "Fl", "Mc", "Lv", "Ts", "Og",
}


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


def _render_sequence(value: Any, separator: str = "、") -> str:
    cleaned = _clean(value)
    if cleaned in (None, "", [], {}):
        return ""
    if isinstance(cleaned, Mapping):
        return separator.join(f"{key} {item}" for key, item in cleaned.items())
    if isinstance(cleaned, list):
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
    if cleaned in (None, "", [], {}):
        return ""
    if isinstance(cleaned, Mapping):
        return "：".join(str(item) for item in cleaned.values())
    if isinstance(cleaned, list):
        return "：".join(str(item) for item in cleaned)
    return str(cleaned)


def _render_structure_relationships(value: Any) -> str:
    cleaned = _clean(value)
    if not isinstance(cleaned, list):
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


@dataclass(frozen=True)
class MaterialInput:
    """Material-name-centered user input with optional experimental context."""

    material_name: str
    major_category: Any = None
    components: Any = None
    structure_relationships: Any = None
    precursors: Any = None
    feed_ratio: Any = None
    preparation_method: Any = None
    elements: Any = None
    element_content: Any = None
    conditions: Any = None
    custom_prompt: Any = None

    def __post_init__(self) -> None:
        name = str(self.material_name or "").strip()
        if not name:
            raise ValueError("material_name is required")
        object.__setattr__(self, "material_name", name)
        for field_name in _OPTIONAL_FIELDS:
            object.__setattr__(self, field_name, _clean(getattr(self, field_name)))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MaterialInput":
        if not isinstance(value, Mapping):
            raise TypeError("material input must be a mapping")
        allowed = {field.name for field in fields(cls)}
        payload = {key: value.get(key) for key in allowed if key in value}
        return cls(**payload)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "MaterialInput":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("material input JSON must contain an object")
        return cls.from_mapping(payload)

    @classmethod
    def from_legacy_components(cls, components: Sequence[str] | str) -> "MaterialInput":
        if isinstance(components, str):
            rendered = components.strip()
        else:
            rendered = ", ".join(str(item).strip() for item in components if str(item).strip())
        if not rendered:
            raise ValueError("material_name is required")
        return cls(material_name=rendered, components=list(components) if not isinstance(components, str) else rendered)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"material_name": self.material_name}
        for field_name in _OPTIONAL_FIELDS:
            value = getattr(self, field_name)
            if value not in (None, "", [], {}):
                payload[field_name] = value
        return payload

    def explicit_elements(self) -> list[str]:
        value = self.elements
        if isinstance(value, str):
            candidates = re.split(r"[\s,，;；、/]+", value)
        elif isinstance(value, list):
            candidates = [str(item) for item in value]
        else:
            candidates = []
        result: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            symbol = str(candidate).strip()
            if symbol in _ELEMENT_SYMBOLS and symbol not in seen:
                seen.add(symbol)
                result.append(symbol)
        return result

    def inferred_elements(self) -> list[str]:
        """Best-effort formula symbols for retrieval guards; never rendered as user-provided data."""
        result: list[str] = []
        seen: set[str] = set()
        for symbol in re.findall(r"[A-Z][a-z]?", self.material_name):
            if symbol in _ELEMENT_SYMBOLS and symbol not in seen:
                seen.add(symbol)
                result.append(symbol)
        return result

    def retrieval_elements(self) -> list[str]:
        return self.explicit_elements() or self.inferred_elements()

    def build_material_description(self) -> str:
        sentences = [f"材料是{self.material_name}。"]
        if self.major_category:
            sentences.append(f"材料类别是{self.major_category}。")
        if self.components:
            sentences.append(f"材料组分包括：{_render_sequence(self.components)}。")
        if self.structure_relationships:
            sentences.append(f"结构关系：{_render_structure_relationships(self.structure_relationships)}。")
        if self.precursors:
            sentences.append(f"该材料是以{_render_sequence(self.precursors)}为前驱体。")
        if self.feed_ratio:
            sentences.append(f"前驱体投料比为：{_render_ratio(self.feed_ratio)}。")
        if self.preparation_method:
            sentences.append(f"通过{self.preparation_method}的方式制备。")
        if self.elements:
            sentences.append(f"含有元素：{_render_sequence(self.elements)}。")
        if self.element_content:
            sentences.append(f"元素含量大概分别为：{_render_sequence(self.element_content)}。")
        if self.conditions:
            sentences.append(f"已有实验或测试条件：{_render_sequence(self.conditions, separator='；')}。")
        return "".join(sentences)

    def build_task_payload(self, *, task_type: str, metrics_to_predict: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        payload = self.to_dict()
        payload["material_description"] = self.build_material_description()
        payload["task_type"] = str(task_type or "").strip()
        payload["metrics_to_predict"] = [dict(item) for item in metrics_to_predict]
        return payload


def build_material_description(value: MaterialInput | Mapping[str, Any]) -> str:
    material = value if isinstance(value, MaterialInput) else MaterialInput.from_mapping(value)
    return material.build_material_description()
