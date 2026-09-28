#!/usr/bin/env python3
"""Build an uploadable dataset JSONL from processed chem-performance records.

This is the bridge between:
- raw extracted data: `data/*.jsonl`
- processed records: `data/processed/chem_performance/*.jsonl`
- DB upload format: `scripts/data/upload_dataset.py --data_format default`

Output JSONL records match the DatasetSample "default" format fields:
- source (must be "training_free_grpo" for the Training-Free GRPO processor)
- question (string prompt)
- answer (JSON dict string: metric_key -> raw string value)
- meta (dict with id/metals/reaction_type/product/metrics_gt/units/etc.)

This script intentionally uses only the standard library so it can run without
installing the full `utu` package into the active environment.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from utu.data_processing.material_feedback import (
    MATERIAL_INPUT_FIELDS,
    build_material_description,
    canonical_task_type,
    material_input_from_mapping,
    task_display_name,
)


MATERIAL_PROPERTY_METRICS: dict[str, dict[str, str]] = {
    "photothermal_conversion_efficiency": {
        "metric_key": "photothermal_conversion_efficiency",
        "unit": "%",
        "display": "Photothermal conversion efficiency",
    },
    "conductivity": {"metric_key": "conductivity", "unit": "S/m", "display": "Conductivity"},
    "thermal_conductivity": {
        "metric_key": "thermal_conductivity",
        "unit": "W m-1 K-1",
        "display": "Thermal conductivity",
    },
    "ferromagnetism": {"metric_key": "saturation_magnetization", "unit": "emu/g", "display": "Ferromagnetism"},
    "ferrimagnetism": {"metric_key": "saturation_magnetization", "unit": "emu/g", "display": "Ferrimagnetism"},
    "antiferromagnetism": {"metric_key": "neel_temperature", "unit": "K", "display": "Antiferromagnetism"},
}


ALLOWED_DATASET_SAMPLE_KEYS = {
    # DatasetSample fields we use
    "source",
    "source_index",
    "question",
    "answer",
    "topic",
    "level",
    "file_name",
    "meta",
}


def _has_material_name(record: dict[str, Any]) -> bool:
    return bool(str(record.get("material_name") or "").strip())


def _metrics_items(metrics_gt: dict[str, Any], units: dict[str, Any], *, include_unit_hint: bool) -> list[Any]:
    items: list[Any] = []
    for key in sorted(metrics_gt):
        if include_unit_hint:
            item: dict[str, Any] = {"key": key}
            unit = str(units.get(key) or "").strip()
            if unit:
                item["unit_hint"] = unit
            items.append(item)
        else:
            items.append(key)
    return items


def _material_input_json(record: dict[str, Any], *, include_unit_hint: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the 19-direction prompt payload from actual feedback fields only."""
    material = material_input_from_mapping(record)
    material_name = str(material.get("material_name") or record.get("material_name") or "").strip()
    if not material_name:
        raise ValueError("material_name is required for a material-name feedback sample")
    material["material_name"] = material_name

    metrics_gt = record.get("metrics_gt") or {}
    units = record.get("units") or {}
    if not isinstance(metrics_gt, dict) or not metrics_gt:
        raise ValueError("material-name feedback record requires metrics_gt")
    if not isinstance(units, dict):
        units = {}

    task = canonical_task_type(record.get("task_type") or record.get("property_type") or record.get("reaction_type"))
    if not task:
        raise ValueError(f"Unknown material-name feedback task: {record.get('task_type') or record.get('reaction_type')!r}")

    description = str(record.get("material_description") or "").strip()
    if not description:
        description = build_material_description(material)
    input_obj: dict[str, Any] = {
        "material_name": material_name,
        "material_description": description,
        "task_type": task,
        "metrics_to_predict": _metrics_items(metrics_gt, units, include_unit_hint=include_unit_hint),
    }
    # The full structured input is already represented in material_description,
    # but custom text remains a separate user-provided signal rather than an
    # instruction that can replace the output contract.
    if material.get("custom_prompt"):
        input_obj["custom_prompt"] = material["custom_prompt"]
    if material.get("elements"):
        input_obj["elements"] = material["elements"]
    conditions = material.get("conditions")
    condition_raw = str(record.get("condition_raw") or "").strip()
    if conditions not in (None, "", [], {}):
        input_obj["conditions"] = conditions
    elif condition_raw:
        input_obj["conditions"] = {"measurement_condition": condition_raw}
    if record.get("product"):
        input_obj["product"] = record["product"]
    return input_obj, material


def _build_material_question(input_obj: dict[str, Any]) -> str:
    task = str(input_obj["task_type"])
    metric_names = [item["key"] if isinstance(item, dict) else str(item) for item in input_obj["metrics_to_predict"]]
    lines = [
        f"请预测下列材料在{task_display_name(task)}方向的性能。",
        "",
        str(input_obj["material_description"]),
    ]
    if input_obj.get("custom_prompt"):
        lines.extend(["", f"实验人员补充信息：{input_obj['custom_prompt']}。"])
    if input_obj.get("conditions"):
        lines.extend(["", f"已有测试条件：{json.dumps(input_obj['conditions'], ensure_ascii=False, sort_keys=True)}。"])
    if input_obj.get("product"):
        lines.extend(["", f"目标产物：{input_obj['product']}。"])
    lines.extend(
        [
            "",
            f"只预测以下指标：{'、'.join(metric_names)}。",
            "请用 JSON 对象返回，每个指标值必须是纯数字，不要附带单位。",
            "",
            "INPUT_JSON:",
            json.dumps(input_obj, ensure_ascii=False, indent=2, sort_keys=True),
        ]
    )
    return "\n".join(lines)


def _build_material_feedback_sample(
    processed_record: dict[str, Any],
    *,
    source: str,
    include_unit_hint: bool,
    doc_id: str | None,
    metric_keys: set[str] | None,
) -> dict[str, Any]:
    record = dict(processed_record)
    metrics_gt = _filter_metric_mapping(record.get("metrics_gt") or {}, metric_keys)
    if not metrics_gt:
        raise ValueError(f"No metrics left after filtering for metric_keys={sorted(metric_keys or [])}")
    record["metrics_gt"] = metrics_gt
    record["units"] = _filter_metric_mapping(record.get("units") or {}, metric_keys)
    input_obj, material = _material_input_json(record, include_unit_hint=include_unit_hint)
    task = str(input_obj["task_type"])

    meta: dict[str, Any] = {
        "id": record.get("id"),
        "recommendation_job_id": record.get("recommendation_job_id"),
        "task_type": task,
        "material_name": input_obj["material_name"],
        "material_description": input_obj["material_description"],
        "material_input": material,
        "elements": material.get("elements"),
        "product": record.get("product"),
        "condition_raw": record.get("condition_raw"),
        "source_type": record.get("source_type"),
        "metrics_gt": metrics_gt,
        "metrics_raw": _filter_metric_mapping(record.get("metrics_raw") or {}, metric_keys),
        "units": record["units"],
        "source_file": record.get("source_file"),
        "doc_id": doc_id,
        "input_json": input_obj,
    }
    for key in MATERIAL_INPUT_FIELDS:
        value = material.get(key)
        if value not in (None, "", [], {}):
            meta[key] = value
    return {
        "source": source,
        "question": _build_material_question(input_obj),
        "answer": json.dumps(metrics_gt, ensure_ascii=False, sort_keys=True),
        "meta": {key: value for key, value in meta.items() if value not in (None, "", [], {})},
    }


def _build_input_json(record: dict[str, Any], *, include_unit_hint: bool) -> dict[str, Any]:
    metals = record["metals"]
    reaction_type = record["reaction_type"]
    property_type = str(record.get("property_type") or "").strip()
    metrics_gt: dict[str, str] = record["metrics_gt"]
    units: dict[str, str] = record.get("units") or {}

    metrics_items: list[Any] = []
    for k in sorted(metrics_gt.keys()):
        if include_unit_hint:
            item: dict[str, Any] = {"key": k}
            if units.get(k):
                item["unit_hint"] = units[k]
            metrics_items.append(item)
        else:
            metrics_items.append(k)

    if property_type:
        input_obj: dict[str, Any] = {
            "metals": metals,
            "property_type": property_type,
            "application_name": record.get("application_name") or MATERIAL_PROPERTY_METRICS.get(property_type, {}).get("display"),
            "reaction_type": reaction_type,
            "metrics_to_predict": metrics_items,
        }
    else:
        input_obj = {
            "metals": metals,
            "reaction_type": reaction_type,
            "metrics_to_predict": metrics_items,
        }
    # Optional: in real wastewater experiments the provided `metals` list may represent only the dominant
    # (e.g., top-5) metals; keep additional context as separate fields (do NOT silently change `metals`).
    metals_scope = record.get("metals_scope")
    if metals_scope is not None and str(metals_scope).strip():
        input_obj["metals_scope"] = str(metals_scope).strip()
    metals_other = record.get("metals_other")
    if metals_other is not None and str(metals_other).strip():
        input_obj["metals_other"] = str(metals_other).strip()
    # Legacy CO2RR requires product as input context.
    if reaction_type == "CO2RR" and record.get("product") is not None:
        input_obj["product"] = record["product"]
    return input_obj


def _build_question(input_obj: dict[str, Any]) -> str:
    input_json_str = json.dumps(input_obj, ensure_ascii=False, indent=2)
    if input_obj.get("property_type"):
        extra_notes: list[str] = []
        scope = str(input_obj.get("metals_scope") or "").strip()
        other = str(input_obj.get("metals_other") or "").strip()
        if scope:
            low = scope.lower()
            if "top" in low or "dominant" in low:
                extra_notes.append(
                    "Note: The provided metals list may include only the dominant/top metals; real wastewater samples can contain additional minor metals/impurities that affect material properties."
                )
        if other:
            extra_notes.append(f"Reported other metals/impurities (not in the metals list): {other}")
        extra_block = ("\n".join([f"- {x}" for x in extra_notes]) + "\n") if extra_notes else ""
        return (
            "Task: Predict material-property performance metrics for the given metal composition.\n\n"
            "INPUT_JSON:\n"
            f"{input_json_str}\n\n"
            "Goal:\n"
            "- Predict ALL requested metrics in metrics_to_predict as best-effort numeric values.\n"
            "- Use the provided metals and property_type/application context.\n"
            "- Normalize units according to each unit_hint.\n"
            f"{extra_block}"
        )

    extra_notes: list[str] = []
    scope = str(input_obj.get("metals_scope") or "").strip()
    other = str(input_obj.get("metals_other") or "").strip()
    if scope:
        low = scope.lower()
        if "top" in low or "dominant" in low:
            extra_notes.append(
                "Note: The provided metals list may include only the dominant/top metals; real wastewater samples can contain additional minor metals/impurities that affect performance."
            )
    if other:
        extra_notes.append(f"Reported other metals/impurities (not in the metals list): {other}")
    extra_block = ("\n".join([f"- {x}" for x in extra_notes]) + "\n") if extra_notes else ""
    return (
        "Task: Predict electrochemical catalysis performance metrics for the given catalyst and reaction.\n\n"
        "INPUT_JSON:\n"
        f"{input_json_str}\n\n"
        "Goal:\n"
        "- Predict ALL requested metrics in metrics_to_predict (best-effort numeric values).\n"
        "- Use the provided metals/reaction_type (and product for CO2RR if present).\n"
        f"{extra_block}"
    )


def _filter_metric_mapping(values: dict[str, Any] | None, metric_keys: set[str] | None) -> dict[str, Any]:
    src = values or {}
    if metric_keys is None:
        return dict(src)
    return {k: v for k, v in src.items() if k in metric_keys}


def _build_co2rr_product_question(input_obj: dict[str, Any]) -> str:
    """Question template for CO2RR Task 1: predict the top-FE product (classification)."""
    input_json_str = json.dumps(input_obj, ensure_ascii=False, indent=2)
    extra_notes: list[str] = []
    scope = str(input_obj.get("metals_scope") or "").strip()
    other = str(input_obj.get("metals_other") or "").strip()
    if scope:
        low = scope.lower()
        if "top" in low or "dominant" in low:
            extra_notes.append(
                "Note: The provided metals list may include only the dominant/top metals; real wastewater samples can contain additional minor metals/impurities that affect selectivity."
            )
    if other:
        extra_notes.append(f"Reported other metals/impurities (not in the metals list): {other}")
    extra_block = ("\n".join([f"- {x}" for x in extra_notes]) + "\n\n") if extra_notes else ""
    return (
        "Task: For CO2RR, predict the main product (the product with the highest Faradaic efficiency).\n"
        "If possible, also predict the Faradaic efficiency of that main product as a fraction in [0, 1].\n\n"
        "INPUT_JSON:\n"
        f"{input_json_str}\n\n"
        f"{extra_block}"
        "Valid product labels in this dataset:\n"
        "- CO\n"
        "- HCOOH\n"
        "- CH4\n"
        "- C2H5OH\n"
        "- C2H4\n"
        "- CH3COOH\n"
        "\nPreferred JSON shape:\n"
        '- {"product": "<LABEL>", "faradaic_efficiency": <fraction>}\n'
        'Fallback if FE cannot be inferred: {"product": "<LABEL>"}\n'
    )


def _validate_dataset_sample(sample: dict[str, Any]) -> None:
    extra = set(sample.keys()) - ALLOWED_DATASET_SAMPLE_KEYS
    if extra:
        raise ValueError(f"Unexpected keys in dataset sample: {sorted(extra)}")
    for k in ("source", "question", "answer"):
        if k not in sample or not sample[k]:
            raise ValueError(f"Missing required field '{k}' in dataset sample")
    # Ensure answer is a JSON dict string.
    parsed = json.loads(sample["answer"])
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError("answer must be a non-empty JSON dict string")


def build_dataset_sample(
    processed_record: dict[str, Any],
    *,
    source: str,
    include_unit_hint: bool,
    doc_id: str | None = None,
    metric_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Convert one processed record into a DatasetSample-like dict (default format)."""
    # Allow processed records to carry their own DOI/doc_id (e.g., manual curation imports)
    # so we can still enforce doc-level masking even when rawdata TSV mapping is incomplete.
    if not doc_id:
        raw_doc_id = processed_record.get("doc_id") or processed_record.get("doi")
        if raw_doc_id is not None and str(raw_doc_id).strip():
            doc_id = str(raw_doc_id).strip()

    # New feedback records share the same material-name-centered task payload
    # as the audited 19-direction base dataset. Legacy metal-only records keep
    # the historical branch below for backwards-compatible ingestion.
    if _has_material_name(processed_record):
        sample = _build_material_feedback_sample(
            processed_record,
            source=source,
            include_unit_hint=include_unit_hint,
            doc_id=doc_id,
            metric_keys=metric_keys,
        )
        _validate_dataset_sample(sample)
        return sample

    metric_keys = set(metric_keys) if metric_keys else None
    metrics_gt: dict[str, str] = _filter_metric_mapping(processed_record["metrics_gt"], metric_keys)
    if not metrics_gt:
        raise ValueError(f"No metrics left after filtering for metric_keys={sorted(metric_keys or [])}")
    units: dict[str, str] = _filter_metric_mapping(processed_record.get("units") or {}, metric_keys)
    record_for_input = dict(processed_record)
    record_for_input["metrics_gt"] = metrics_gt
    record_for_input["units"] = units

    input_obj = _build_input_json(record_for_input, include_unit_hint=include_unit_hint)
    question = _build_question(input_obj)
    answer = json.dumps(metrics_gt, ensure_ascii=False, sort_keys=True)

    meta: dict[str, Any] = {
        # Keep original identifiers and task conditions for later debugging.
        "id": processed_record.get("id"),
        # Optional: link this lab record back to a specific recommendation source (ChemCouncil web).
        "recommendation_job_id": processed_record.get("recommendation_job_id"),
        "metals": processed_record.get("metals"),
        # Optional: preserve the original metals text / composition if provided by an experimental CSV import.
        "metals_raw": processed_record.get("metals_raw"),
        "composition_pct": processed_record.get("composition_pct"),
        # Optional: wastewater scope context
        "metals_scope": processed_record.get("metals_scope"),
        "metals_other": processed_record.get("metals_other"),
        "property_type": processed_record.get("property_type"),
        "application_name": processed_record.get("application_name"),
        "reaction_type": processed_record.get("reaction_type"),
        "product": processed_record.get("product"),
        # Optional bibliographic metadata (if present in processed records).
        "title": processed_record.get("title"),
        # Optional: experimental-only condition/provenance fields.
        "condition_raw": processed_record.get("condition_raw"),
        "eta10_condition_status": processed_record.get("eta10_condition_status"),
        "eta10_condition_mA_cm-2": processed_record.get("eta10_condition_mA_cm-2"),
        "source_type": processed_record.get("source_type"),
        # Store both normalized and raw for traceability.
        "metrics_gt": metrics_gt,
        "metrics_raw": processed_record.get("metrics_raw") or {},
        "units": units,
        "source_file": processed_record.get("source_file"),
        # Optional: link this label back to a DOI/doc_id in the literature DB (Chroma).
        # This is used for doc-level masking during train/eval rollouts to prevent label leakage.
        "doc_id": doc_id,
        # Also store the structured input used to build the question.
        "input_json": input_obj,
    }

    # Remove nulls to keep meta clean.
    meta = {k: v for k, v in meta.items() if v is not None}

    sample = {
        "source": source,
        "question": question,
        "answer": answer,
        "meta": meta,
    }
    _validate_dataset_sample(sample)
    return sample


def build_co2rr_top_product_sample(
    processed_record: dict[str, Any],
    *,
    source: str,
    doc_id: str | None = None,
) -> dict[str, Any]:
    """CO2RR Task 1 sample: predict the top-FE product (string label)."""
    if not doc_id:
        raw_doc_id = processed_record.get("doc_id") or processed_record.get("doi")
        if raw_doc_id is not None and str(raw_doc_id).strip():
            doc_id = str(raw_doc_id).strip()

    metals = processed_record["metals"]
    reaction_type = processed_record["reaction_type"]
    if reaction_type != "CO2RR":
        raise ValueError(f"build_co2rr_top_product_sample called with reaction_type={reaction_type}")
    truth_product = str(processed_record.get("product") or "").strip()
    if not truth_product:
        raise ValueError("CO2RR processed record missing truth product")

    input_obj: dict[str, Any] = {"metals": metals, "reaction_type": reaction_type}
    metals_scope = processed_record.get("metals_scope")
    if metals_scope is not None and str(metals_scope).strip():
        input_obj["metals_scope"] = str(metals_scope).strip()
    metals_other = processed_record.get("metals_other")
    if metals_other is not None and str(metals_other).strip():
        input_obj["metals_other"] = str(metals_other).strip()
    question = _build_co2rr_product_question(input_obj)

    answer_obj = {"product": truth_product}
    truth_fe = (processed_record.get("metrics_gt") or {}).get("faradaic_efficiency")
    if truth_fe is not None:
        try:
            answer_obj["faradaic_efficiency"] = float(str(truth_fe).strip())
        except ValueError:
            answer_obj["faradaic_efficiency"] = truth_fe
    answer = json.dumps(answer_obj, ensure_ascii=False, sort_keys=True)

    meta: dict[str, Any] = {
        "task_type": "co2rr_top_product",
        "id": processed_record.get("id"),
        "recommendation_job_id": processed_record.get("recommendation_job_id"),
        "metals": processed_record.get("metals"),
        "metals_raw": processed_record.get("metals_raw"),
        "composition_pct": processed_record.get("composition_pct"),
        "metals_scope": processed_record.get("metals_scope"),
        "metals_other": processed_record.get("metals_other"),
        "reaction_type": processed_record.get("reaction_type"),
        # Store the truth product for debugging; this is also the label.
        "product": truth_product,
        "title": processed_record.get("title"),
        "condition_raw": processed_record.get("condition_raw"),
        "eta10_condition_status": processed_record.get("eta10_condition_status"),
        "eta10_condition_mA_cm-2": processed_record.get("eta10_condition_mA_cm-2"),
        "source_type": processed_record.get("source_type"),
        # Keep the regression GT too (partial current density) for traceability.
        "metrics_gt": processed_record.get("metrics_gt") or {},
        "metrics_raw": processed_record.get("metrics_raw") or {},
        "units": processed_record.get("units") or {},
        "source_file": processed_record.get("source_file"),
        "doc_id": doc_id,
        "input_json": input_obj,
    }
    meta = {k: v for k, v in meta.items() if v is not None}

    sample = {
        "source": source,
        "question": question,
        "answer": answer,
        "meta": meta,
    }
    _validate_dataset_sample(sample)
    return sample


def iter_processed_records(input_dir: Path, *, exclude_paths: set[Path] | None = None):
    exclude_paths = {p.resolve() for p in (exclude_paths or set())}
    fps = sorted(input_dir.glob("*.jsonl"))
    names = {p.name for p in fps}
    # If we have a final CO2RR processed file, ignore the legacy co2rr.jsonl to avoid duplicates.
    if "co2rr_final.jsonl" in names and "co2rr.jsonl" in names:
        fps = [p for p in fps if p.name != "co2rr.jsonl"]

    for fp in fps:
        if fp.resolve() in exclude_paths:
            continue
        with fp.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield fp.name, json.loads(line)


def _load_doc_id_map_from_tsv(
    tsv_path: Path,
    *,
    wanted_ids: set[str],
    index_col: str = "index",
    doi_col: str = "doi",
) -> dict[str, str]:
    """Scan a large TSV once and extract only the index->doi mapping we need.

    Rawdata TSV files can be hundreds of MB because they include full abstracts.
    We avoid loading everything into memory by scanning once and only keeping the
    pairs for ids present in the processed records.
    """

    if not wanted_ids:
        return {}

    # Some abstracts can be very long; raise the CSV field limit defensively.
    try:
        csv.field_size_limit(1024 * 1024 * 1024)  # 1 GiB
    except Exception:
        pass

    remaining = set(wanted_ids)
    out: dict[str, str] = {}

    with tsv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader, None)
        if not header:
            raise ValueError(f"Empty TSV: {tsv_path}")

        try:
            idx_i = header.index(index_col)
            doi_i = header.index(doi_col)
        except ValueError as e:
            raise ValueError(f"TSV missing required columns: {e}. header={header}") from e

        for row in reader:
            if not row:
                continue
            # Defensive: short rows can occur if the TSV is malformed.
            if idx_i >= len(row) or doi_i >= len(row):
                continue

            idx = str(row[idx_i]).strip()
            if idx not in remaining:
                continue

            doi = str(row[doi_i]).strip()
            if doi:
                out[idx] = doi

            remaining.remove(idx)
            if not remaining:
                break

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build chem-performance dataset JSONL from processed records.")
    parser.add_argument(
        "--input_dir",
        type=str,
        default="data/processed/chem_performance",
        help="Directory containing processed chem-performance JSONL files.",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        default="data/processed/chem_performance/chem_performance_dataset.jsonl",
        help="Path to write the uploadable dataset JSONL (default-format).",
    )
    parser.add_argument(
        "--source",
        type=str,
        default="training_free_grpo",
        help="DatasetSample.source value (must be 'training_free_grpo' for Training-Free GRPO).",
    )
    parser.add_argument(
        "--include_unit_hint",
        action="store_true",
        help="If set, include unit_hint in metrics_to_predict items inside INPUT_JSON.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional: limit the number of output samples (useful for smoke datasets).",
    )
    parser.add_argument(
        "--add_meta_doc_id",
        action="store_true",
        help=(
            "If set, populate meta.doc_id (DOI) by joining sample id -> DOI from `rawdata/2-cleaned-abstracts-about-*.tsv`. "
            "This is used for doc-level masking during train/eval rollouts to prevent label leakage."
        ),
    )
    parser.add_argument(
        "--require_meta_doc_id",
        action="store_true",
        help="If set together with --add_meta_doc_id, fail if any sample cannot be mapped to a DOI/doc_id.",
    )
    parser.add_argument(
        "--rawdata_dir",
        type=str,
        default="rawdata",
        help="Directory containing rawdata TSV mapping files (default: rawdata/).",
    )
    parser.add_argument(
        "--rawdata_file_template",
        type=str,
        default="2-cleaned-abstracts-about-{reaction_type}.tsv",
        help=(
            "Filename template under rawdata_dir for the mapping TSV "
            "(default: 2-cleaned-abstracts-about-{reaction_type}.tsv)."
        ),
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_file = Path(args.output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    counts = Counter()
    skipped = 0
    n = 0

    # Optional: build an id->doc_id(doi) mapping per reaction_type by scanning rawdata TSV files once.
    doc_id_by_rt: dict[str, dict[str, str]] = {}
    if args.add_meta_doc_id:
        rawdata_dir = Path(args.rawdata_dir)
        wanted_ids_by_rt: dict[str, set[str]] = {}

        # First pass: collect wanted ids per reaction_type (only for the records we will output).
        n_collect = 0
        for _, record in iter_processed_records(input_dir, exclude_paths={output_file}):
            if not record.get("metrics_gt") or not record.get("reaction_type"):
                continue
            if not _has_material_name(record) and not record.get("metals"):
                continue
            rt = str(record.get("reaction_type") or "").strip()
            sid = str(record.get("id") or "").strip()
            # rawdata TSV mapping uses integer-like indices; skip non-numeric ids to avoid
            # scanning huge TSV files without the early-exit optimization.
            if rt and sid and sid.isdigit():
                wanted_ids_by_rt.setdefault(rt, set()).add(sid)
            n_collect += 1
            if args.limit is not None and n_collect >= args.limit:
                break

        # Second: scan each TSV once and build mapping only for needed ids.
        for rt, wanted_ids in sorted(wanted_ids_by_rt.items()):
            tsv_path = rawdata_dir / args.rawdata_file_template.format(reaction_type=rt)
            print(f"Loading doc_id mapping for reaction_type={rt} from: {tsv_path} (wanted_ids={len(wanted_ids)})")
            if not tsv_path.exists():
                print(f"WARNING: rawdata TSV not found for reaction_type={rt}: {tsv_path}")
                doc_id_by_rt[rt] = {}
                continue
            m = _load_doc_id_map_from_tsv(tsv_path, wanted_ids=wanted_ids)
            doc_id_by_rt[rt] = m

            missing_ids = wanted_ids - set(m.keys())
            if missing_ids:
                example_missing = ", ".join(sorted(missing_ids)[:5])
                print(
                    f"WARNING: doc_id mapping incomplete for reaction_type={rt}: "
                    f"missing {len(missing_ids)}/{len(wanted_ids)} ids (example_missing={example_missing})"
                )

    with output_file.open("w", encoding="utf-8") as out:
        # If the output file is placed under input_dir, exclude it from the input glob.
        for source_file, record in iter_processed_records(input_dir, exclude_paths={output_file}):
            # Ensure source_file is preserved even if the processed record was generated elsewhere.
            record.setdefault("source_file", source_file)
            # Defensive: skip non-processed JSONL files that happen to live in the same directory.
            # This commonly occurs when output_file is also a *.jsonl under input_dir.
            if not record.get("metrics_gt") or not record.get("reaction_type"):
                skipped += 1
                continue
            if not _has_material_name(record) and not record.get("metals"):
                skipped += 1
                continue

            rt = str(record.get("reaction_type") or "").strip()
            sid = str(record.get("id") or "").strip()
            doc_id = None
            if args.add_meta_doc_id and rt and sid:
                doc_id = (doc_id_by_rt.get(rt) or {}).get(sid) if sid.isdigit() else None
                if not doc_id:
                    # Fallback: allow processed records to carry their own doc_id/doi
                    # (e.g., manual curation imports that are not in rawdata TSV).
                    raw_doc_id = record.get("doc_id") or record.get("doi")
                    doc_id = str(raw_doc_id).strip() if raw_doc_id is not None and str(raw_doc_id).strip() else None
                if args.require_meta_doc_id and not doc_id:
                    raise ValueError(
                        f"Missing DOI/doc_id for reaction_type={rt} id={sid}. "
                        "Tried rawdata TSV mapping and record['doc_id']/['doi'] fallback."
                    )

            # CO2RR is split into two tasks:
            # 1) classify the top-FE product
            # 2) regress the partial current density for that product
            if rt == "CO2RR" and not _has_material_name(record):
                # Task 1: product label (string)
                sample1 = build_co2rr_top_product_sample(record, source=args.source, doc_id=doc_id)
                out.write(json.dumps(sample1, ensure_ascii=False) + "\n")
                counts["CO2RR"] += 1
                n += 1
                if args.limit is not None and n >= args.limit:
                    break

                if "partial_current_density" in (record.get("metrics_gt") or {}):
                    # Task 2: numeric partial_current_density (use the standard metric template)
                    sample2 = build_dataset_sample(
                        record,
                        source=args.source,
                        include_unit_hint=args.include_unit_hint,
                        doc_id=doc_id,
                        metric_keys={"partial_current_density"},
                    )
                    # Make the task explicit in meta for easier debugging.
                    meta2 = sample2.get("meta") or {}
                    meta2["task_type"] = "co2rr_partial_current_density"
                    sample2["meta"] = meta2
                    out.write(json.dumps(sample2, ensure_ascii=False) + "\n")
                    counts["CO2RR"] += 1
                    n += 1
                    if args.limit is not None and n >= args.limit:
                        break
            else:
                sample = build_dataset_sample(
                    record,
                    source=args.source,
                    include_unit_hint=args.include_unit_hint,
                    doc_id=doc_id,
                )
                out.write(json.dumps(sample, ensure_ascii=False) + "\n")
                counts[record.get("property_type") or record.get("reaction_type")] += 1
                n += 1
                if args.limit is not None and n >= args.limit:
                    break

    print(f"Wrote {n} samples to: {output_file}")
    if skipped:
        print(f"Skipped {skipped} non-processed records/files (missing required keys).")
    print("Counts by reaction_type:")
    for rt, c in sorted(counts.items()):
        print(f"- {rt}: {c}")


if __name__ == "__main__":
    main()
