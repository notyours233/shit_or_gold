"""Serialize bound 19-direction material-performance candidates."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utu.data_processing.material_performance_audit import infer_material_elements, parse_numeric
from utu.data_processing.material_performance_candidates import MaterialPerformanceCandidate

SCHEMA_VERSION = "material_performance_19_v1"

TASK_DISPLAY_NAMES: dict[str, str] = {
    "CO2RR": "二氧化碳电还原（CO2RR）",
    "EOR": "乙醇氧化（EOR）",
    "HER": "析氢反应（HER）",
    "HOR": "氢氧化反应（HOR）",
    "HZOR": "肼氧化反应（HZOR）",
    "O5H": "5-羟甲基糠醛氧化（O5H）",
    "OER": "析氧反应（OER）",
    "ORR": "氧还原反应（ORR）",
    "UOR": "尿素氧化反应（UOR）",
    "antiferromagnetism": "反铁磁性能",
    "conductivity": "电导率",
    "ferrimagnetism": "亚铁磁性能",
    "ferromagnetism": "铁磁性能",
    "photothermal_conversion_efficiency": "光热转换效率",
    "thermal_conductivity": "热导率",
    "photocatalytic_h2o2": "光催化 H2O2 生成性能",
    "antibacterial": "抑菌性能",
    "thermoelectric": "热电性能",
    "furfural_hydrogenation": "糠醛加氢性能",
}

APPROXIMATE_COMPARATORS = {"~", "≈"}
BOUND_COMPARATORS = {">", ">=", "<", "<=", "≥", "≤"}


@dataclass(frozen=True)
class DatasetBuildResult:
    """Canonical records, point-value GRPO samples, and build accounting."""

    canonical_records: tuple[dict[str, Any], ...]
    grpo_samples: tuple[dict[str, Any], ...]
    manifest: Mapping[str, Any]


def _clean_list(value: object) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [item for item in value if item not in (None, "", [], {})]


def _clean_material(material: Mapping[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {
        "material_name": str(material.get("material_name") or "").strip(),
    }
    for key in ("major_category", "evidence"):
        value = str(material.get(key) or "").strip()
        if value:
            cleaned[key] = value
    for key in ("components", "structure_relationships"):
        values = _clean_list(material.get(key))
        if values:
            cleaned[key] = values
    for key in ("precursors", "feed_ratio", "preparation_method", "element_content"):
        value = material.get(key)
        if value not in (None, "", [], {}):
            cleaned[key] = value

    explicit_metals = {
        str(value).strip() for value in _clean_list(material.get("metal_elements")) if str(value).strip()
    }
    explicit_nonmetals = {
        str(value).strip() for value in _clean_list(material.get("nonmetal_elements")) if str(value).strip()
    }
    inferred = infer_material_elements(material)
    if explicit_metals:
        cleaned["metal_elements"] = sorted(explicit_metals)
    if explicit_nonmetals:
        cleaned["nonmetal_elements"] = sorted(explicit_nonmetals)
    inferred_only = inferred - explicit_metals - explicit_nonmetals
    if inferred_only:
        cleaned["inferred_elements"] = sorted(inferred_only)
    all_elements = sorted(explicit_metals.union(explicit_nonmetals).union(inferred))
    if all_elements:
        cleaned["elements"] = all_elements
    return cleaned


def build_material_description(material: Mapping[str, Any]) -> str:
    """Assemble only available material fields into the new prompt content."""
    name = str(material.get("material_name") or "").strip()
    if not name:
        raise ValueError("material_name is required")
    sentences = [f"材料是{name}。"]
    category = str(material.get("major_category") or "").strip()
    if category:
        sentences.append(f"材料类别是{category}。")

    components = _clean_list(material.get("components"))
    component_names = [
        str(item.get("component_name") or "").strip()
        for item in components
        if isinstance(item, Mapping) and str(item.get("component_name") or "").strip()
    ]
    if component_names:
        sentences.append(f"材料组分包括：{'、'.join(component_names)}。")

    relationships = _clean_list(material.get("structure_relationships"))
    relationship_text: list[str] = []
    for item in relationships:
        if not isinstance(item, Mapping):
            continue
        subject = str(item.get("subject") or "").strip()
        relation = str(item.get("relation") or item.get("relation_normalized") or "").strip()
        object_name = str(item.get("object") or "").strip()
        if subject and relation and object_name:
            relationship_text.append(f"{subject} {relation} {object_name}")
    if relationship_text:
        sentences.append(f"结构关系：{'；'.join(relationship_text)}。")

    precursors = material.get("precursors")
    if precursors not in (None, "", [], {}):
        rendered = "、".join(str(item) for item in precursors) if isinstance(precursors, list) else str(precursors)
        sentences.append(f"以前驱体{rendered}制备。")
    feed_ratio = material.get("feed_ratio")
    if feed_ratio not in (None, "", [], {}):
        if isinstance(feed_ratio, Mapping):
            rendered = "：".join(str(value) for value in feed_ratio.values())
        elif isinstance(feed_ratio, list):
            rendered = "：".join(str(value) for value in feed_ratio)
        else:
            rendered = str(feed_ratio)
        sentences.append(f"前驱体投料比为：{rendered}。")
    preparation_method = material.get("preparation_method")
    if preparation_method not in (None, "", [], {}):
        sentences.append(f"通过{preparation_method}的方式制备。")

    elements = _clean_list(material.get("elements"))
    if elements:
        sentences.append(f"含有元素：{'、'.join(str(value) for value in elements)}。")
    element_content = material.get("element_content")
    if element_content not in (None, "", [], {}):
        if isinstance(element_content, Mapping):
            rendered = "、".join(f"{key} {value}" for key, value in element_content.items())
        elif isinstance(element_content, list):
            rendered = "、".join(str(value) for value in element_content)
        else:
            rendered = str(element_content)
        sentences.append(f"元素含量大概分别为：{rendered}。")
    return "".join(sentences)


def _serialize_metric(raw: object, unit: object = None) -> dict[str, Any]:
    parsed = parse_numeric(raw)
    if parsed is None:
        raise ValueError(f"Metric is not numeric: {raw!r}")
    result: dict[str, Any] = {
        "raw_value": parsed.raw,
        "numeric_value": parsed.value,
        "comparator": parsed.comparator,
    }
    normalized_unit = str(unit or "").strip()
    if normalized_unit:
        result["unit"] = normalized_unit
    return result


def _stable_sample_id(candidate: MaterialPerformanceCandidate) -> str:
    payload = json.dumps(
        {
            "task_type": candidate.task_type,
            "doi": candidate.doi,
            "material_identity": candidate.material_identity,
            "context_key": candidate.context_key,
            "label_key": candidate.label_key,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"mp19_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20]}"


def candidate_to_canonical(candidate: MaterialPerformanceCandidate) -> dict[str, Any]:
    """Convert a selected candidate into the lossless canonical record."""
    if not isinstance(candidate.material, Mapping):
        raise ValueError("Selected candidate must have a bound material")
    material = _clean_material(candidate.material)
    material_description = build_material_description(material)
    metrics = {key: _serialize_metric(raw, candidate.units.get(key)) for key, raw in sorted(candidate.metrics.items())}
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "sample_id": _stable_sample_id(candidate),
        "task_type": candidate.task_type,
        "doi": candidate.doi,
        "material": material,
        "prompt_fields": {
            "material_name": material["material_name"],
            "material_description": material_description,
        },
        "performance": {
            "metrics": metrics,
            "conditions": dict(candidate.conditions),
        },
        "binding": {
            "status": candidate.status,
            "mode": candidate.binding_mode,
        },
        "quality_flags": list(candidate.quality_flags),
        "source": {
            "source_group": candidate.source_group,
            "source_file": candidate.source_file,
            "row_number": candidate.row_number,
            "extraction_index": candidate.extraction_index,
            "material_index": candidate.material_index,
        },
    }
    if candidate.product:
        record["performance"]["product"] = candidate.product
    if candidate.categorical_metrics:
        record["performance"]["categorical_metrics"] = dict(candidate.categorical_metrics)
    if candidate.truth_source_file:
        record["source"]["truth_source_file"] = candidate.truth_source_file
    if candidate.truth_source_index is not None:
        record["source"]["truth_source_index"] = candidate.truth_source_index
    return record


def _condition_lines(conditions: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in conditions.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            rendered = "、".join(str(item) for item in value)
        else:
            rendered = str(value)
        lines.append(f"{key}：{rendered}")
    return lines


def _point_metric_payload(
    task_type: str,
    metrics: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, float], dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    values: dict[str, float] = {}
    units: dict[str, str] = {}
    comparators: dict[str, str] = {}
    raw_values: dict[str, str] = {}
    deferred: dict[str, str] = {}
    for key, metric in metrics.items():
        comparator = str(metric.get("comparator") or "")
        raw_values[key] = str(metric.get("raw_value") or "")
        comparators[key] = comparator
        unit = str(metric.get("unit") or "").strip()
        if unit:
            units[key] = unit
        # Approximate values remain usable point estimates but keep their
        # uncertainty marker. One-sided bounds require interval-aware verify.
        if comparator in BOUND_COMPARATORS:
            deferred[key] = "one_sided_bound_requires_interval_verify"
            continue
        compact_unit = unit.casefold().replace(" ", "").replace("−", "-")
        if task_type == "HOR" and key == "exchange_current_density" and compact_unit != "macm-2":
            deferred[key] = "noncanonical_or_relative_exchange_current_density"
            continue
        values[key] = float(metric["numeric_value"])
    return values, units, comparators, raw_values, deferred


def canonical_to_grpo_sample(record: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build a current-verify-compatible DatasetSample from a canonical record."""
    performance = record["performance"]
    values, all_units, comparators, raw_values, deferred = _point_metric_payload(
        str(record["task_type"]), performance["metrics"]
    )
    if not values:
        return None
    metric_keys = sorted(values)
    units = {key: all_units[key] for key in metric_keys if key in all_units}
    conditions = dict(performance.get("conditions") or {})
    input_json: dict[str, Any] = {
        "material_name": record["material"]["material_name"],
        "material_description": record["prompt_fields"]["material_description"],
        "task_type": record["task_type"],
        "metrics_to_predict": [
            {"key": key, **({"unit_hint": units[key]} if key in units else {})} for key in metric_keys
        ],
    }
    if conditions:
        input_json["conditions"] = conditions
    if performance.get("product"):
        input_json["product"] = performance["product"]

    task_display = TASK_DISPLAY_NAMES.get(str(record["task_type"]), str(record["task_type"]))
    lines = [
        f"请预测下列材料在{task_display}方向的性能。",
        "",
        str(record["prompt_fields"]["material_description"]),
    ]
    condition_lines = _condition_lines(conditions)
    if condition_lines:
        lines.extend(["", f"已有测试条件：{'；'.join(condition_lines)}。"])
    if performance.get("product"):
        lines.extend(["", f"目标产物：{performance['product']}。"])
    lines.extend(
        [
            "",
            f"只预测以下指标：{'、'.join(metric_keys)}。",
            "请用 JSON 对象返回，每个指标值必须是纯数字，不要附带单位。",
            "",
            "INPUT_JSON:",
            json.dumps(input_json, ensure_ascii=False, indent=2, sort_keys=True),
        ]
    )

    answer = json.dumps(values, ensure_ascii=False, sort_keys=True)
    meta = {
        "schema_version": SCHEMA_VERSION,
        "sample_id": record["sample_id"],
        "doc_id": record["doi"],
        "task_type": record["task_type"],
        "material_name": record["material"]["material_name"],
        "material_description": record["prompt_fields"]["material_description"],
        "metrics_gt": values,
        "metrics_raw": {key: raw_values[key] for key in metric_keys},
        "units": units,
        "metric_comparators": {key: comparators[key] for key in metric_keys if comparators[key]},
        "deferred_metrics": deferred,
        "conditions": conditions,
        "binding_status": record["binding"]["status"],
        "binding_mode": record["binding"]["mode"],
        "quality_flags": record["quality_flags"],
        "source_file": record["source"]["source_file"],
        "row_number": record["source"].get("row_number"),
        "input_json": input_json,
    }
    if performance.get("product"):
        meta["product"] = performance["product"]
    return {
        "source": "training_free_grpo",
        "question": "\n".join(lines),
        "answer": answer,
        "meta": meta,
    }


def build_dataset(
    candidates: Sequence[MaterialPerformanceCandidate], selection_stats: Mapping[str, Any]
) -> DatasetBuildResult:
    """Build both output layers and a deterministic manifest."""
    canonical_records = tuple(candidate_to_canonical(candidate) for candidate in candidates)
    grpo_samples = tuple(
        sample for sample in (canonical_to_grpo_sample(record) for record in canonical_records) if sample is not None
    )
    counts: Counter[str] = Counter()
    by_task: dict[str, Counter[str]] = defaultdict(Counter)
    for record in canonical_records:
        task = str(record["task_type"])
        counts["canonical_records"] += 1
        by_task[task]["canonical_records"] += 1
        if record["quality_flags"]:
            counts["canonical_records_with_quality_flags"] += 1
        _, _, _, _, deferred = _point_metric_payload(task, record["performance"]["metrics"])
        for metric_key, metric in record["performance"]["metrics"].items():
            counts["canonical_metric_values"] += 1
            comparator = str(metric.get("comparator") or "")
            if comparator:
                counts["metric_values_with_comparator"] += 1
            if comparator in BOUND_COMPARATORS:
                counts["bounded_metric_values_deferred_from_grpo"] += 1
                by_task[task]["bounded_metric_values_deferred_from_grpo"] += 1
            reason = deferred.get(metric_key)
            if reason == "noncanonical_or_relative_exchange_current_density":
                counts["semantic_metric_values_deferred_from_grpo"] += 1
                by_task[task]["semantic_metric_values_deferred_from_grpo"] += 1
        counts["categorical_metric_values"] += len(record["performance"].get("categorical_metrics", {}))
        by_task[task]["categorical_metric_values"] += len(record["performance"].get("categorical_metrics", {}))
    for sample in grpo_samples:
        task = str(sample["meta"]["task_type"])
        counts["grpo_samples"] += 1
        counts["grpo_metric_values"] += len(sample["meta"]["metrics_gt"])
        by_task[task]["grpo_samples"] += 1
        by_task[task]["grpo_metric_values"] += len(sample["meta"]["metrics_gt"])
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy": {
            "minimum_fields": ["material_name", "numeric_performance_truth", "task_type", "doi"],
            "optional_prompt_fields": [
                "major_category",
                "components",
                "structure_relationships",
                "elements",
                "conditions",
                "precursors",
                "feed_ratio",
                "preparation_method",
                "element_content",
            ],
            "point_value_grpo": (
                "Exact and approximate numeric values are emitted. One-sided bounds remain canonical-only until "
                "the verify function supports interval semantics. HOR exchange-current values with mass-normalized "
                "or relative semantics remain canonical-only so they are not mixed with area-normalized values."
            ),
        },
        "selection": dict(selection_stats),
        "outputs": dict(counts),
        "by_task": {task: dict(values) for task, values in sorted(by_task.items())},
    }
    return DatasetBuildResult(canonical_records, grpo_samples, manifest)


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> int:
    """Write mappings as UTF-8 JSONL and return the number of records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def write_dataset_outputs(
    result: DatasetBuildResult,
    *,
    canonical_path: Path,
    grpo_path: Path,
    manifest_path: Path,
) -> None:
    """Write the canonical dataset, GRPO projection, and build manifest."""
    canonical_count = write_jsonl(canonical_path, result.canonical_records)
    grpo_count = write_jsonl(grpo_path, result.grpo_samples)
    if canonical_count != result.manifest["outputs"]["canonical_records"]:
        raise RuntimeError("Canonical output count changed during serialization")
    if grpo_count != result.manifest["outputs"]["grpo_samples"]:
        raise RuntimeError("GRPO output count changed during serialization")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(result.manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
