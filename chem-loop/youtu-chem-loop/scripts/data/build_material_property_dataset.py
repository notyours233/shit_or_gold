#!/usr/bin/env python3
"""Build DatasetSample JSONL from extracted material-property records.

Input shape matches:
  material_property_extraction/results/final_review_package_20260415/all_results.jsonl

The output keeps the Training-Free GRPO default format used elsewhere in this
workspace:
  {"source": "training_free_grpo", "question": "...", "answer": "{...}", "meta": {...}}

RAG is optional for now. We still keep DOI as meta.doc_id so future literature
DB masking/retrieval can be wired without rebuilding labels.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROPERTY_METRICS: dict[str, dict[str, str]] = {
    "photothermal_conversion_efficiency": {
        "metric_key": "photothermal_conversion_efficiency",
        "unit": "%",
        "display": "Photothermal conversion efficiency",
    },
    "conductivity": {
        "metric_key": "conductivity",
        "unit": "S/m",
        "display": "Conductivity",
    },
    "thermal_conductivity": {
        "metric_key": "thermal_conductivity",
        "unit": "W m-1 K-1",
        "display": "Thermal conductivity",
    },
    "ferromagnetism": {
        "metric_key": "saturation_magnetization",
        "unit": "emu/g",
        "display": "Ferromagnetism",
    },
    "ferrimagnetism": {
        "metric_key": "saturation_magnetization",
        "unit": "emu/g",
        "display": "Ferrimagnetism",
    },
    "antiferromagnetism": {
        "metric_key": "neel_temperature",
        "unit": "K",
        "display": "Antiferromagnetism",
    },
    "photocatalytic_h2o2": {
        "metric_key": "apparent_quantum_efficiency",
        "unit": "%",
        "display": "Photocatalytic H2O2 production",
    },
    "antibacterial": {
        "metric_key": "minimum_concentration",
        "unit": "ppm",
        "display": "Antibacterial performance",
    },
    "thermoelectric": {
        "metric_key": "figure_of_merit",
        "unit": "dimensionless",
        "display": "Thermoelectric performance",
    },
    "furfural_hydrogenation": {
        "metric_key": "furfuryl_alcohol_yield",
        "unit": "%",
        "display": "Furfural hydrogenation",
    },
}

_ALIASES: dict[str, str] = {
    "photothermal conversion efficiency": "photothermal_conversion_efficiency",
    "photothermal_conversion_efficiency": "photothermal_conversion_efficiency",
    "conductivity": "conductivity",
    "thermal conductivity": "thermal_conductivity",
    "thermal_conductivity": "thermal_conductivity",
    "ferromagnetism": "ferromagnetism",
    "ferrimagnetism": "ferrimagnetism",
    "antiferromagnetism": "antiferromagnetism",
    "photocatalytic h2o2": "photocatalytic_h2o2",
    "photocatalytic hydrogen peroxide": "photocatalytic_h2o2",
    "h2o2 photocatalysis": "photocatalytic_h2o2",
    "antibacterial": "antibacterial",
    "antimicrobial": "antibacterial",
    "thermoelectric": "thermoelectric",
    "zt": "thermoelectric",
    "furfural hydrogenation": "furfural_hydrogenation",
    "furfuryl alcohol": "furfural_hydrogenation",
    "光催化h2o2": "photocatalytic_h2o2",
    "抑菌": "antibacterial",
    "热电": "thermoelectric",
    "糠醛加氢": "furfural_hydrogenation",
}


def _clean_label(value: object) -> str:
    s = str(value or "").strip().lower().replace("_", " ")
    s = re.sub(r"[\u2010-\u2015]+", "-", s)
    return " ".join(s.split())


def canonical_property(value: object) -> str | None:
    raw = str(value or "").strip()
    if raw in PROPERTY_METRICS:
        return raw
    cleaned = _clean_label(raw)
    if cleaned in _ALIASES:
        return _ALIASES[cleaned]
    underscored = cleaned.replace("-", "_").replace(" ", "_")
    return underscored if underscored in PROPERTY_METRICS else None


def _num_prefix(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        out = float(value)
        return out if math.isfinite(out) else None
    s = str(value or "").strip()
    m = re.match(r"^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)", s)
    if not m:
        return None
    out = float(m.group(1))
    return out if math.isfinite(out) else None


def _unit_text(value: object) -> str:
    s = str(value or "")
    s = s.replace("−", "-").replace("–", "-").replace("—", "-")
    s = s.replace("·", " ").replace("⋅", " ").replace("•", " ")
    s = s.replace("m²", "m2").replace("²", "2")
    s = s.replace("^", "")
    s = s.replace("/", " ")
    return " ".join(s.split())


def normalize_value(prop: str, raw_value: object) -> tuple[float, str] | None:
    value = _num_prefix(raw_value)
    if value is None:
        return None
    unit_text = _unit_text(raw_value).lower()

    if prop in {"photothermal_conversion_efficiency", "photocatalytic_h2o2", "furfural_hydrogenation"}:
        if "%" not in unit_text and 0.0 <= value <= 1.0:
            value *= 100.0
        return value, "%"

    if prop == "conductivity":
        raw_low = str(raw_value or "").lower()
        if "ms/cm" in raw_low or "ms cm-1" in raw_low or "ms cm^-1" in raw_low:
            return value * 0.1, "S/m"
        if "s/cm" in raw_low or "s cm-1" in raw_low or "s cm^-1" in raw_low:
            return value * 100.0, "S/m"
        if "ms/m" in raw_low or "ms m-1" in raw_low or "ms m^-1" in raw_low:
            return value * 1.0e-3, "S/m"
        if "s/m" in raw_low or "s m-1" in raw_low or "s m^-1" in raw_low:
            return value, "S/m"
        if re.search(r"\bms\s*cm-?1\b", unit_text):
            return value * 0.1, "S/m"
        if re.search(r"\bs\s*cm-?1\b", unit_text):
            return value * 100.0, "S/m"
        if re.search(r"\bms\s*m-?1\b", unit_text):
            return value * 1.0e-3, "S/m"
        if re.search(r"\bs\s*m-?1\b", unit_text) or "s m" in unit_text or "s/m" in str(raw_value).lower():
            return value, "S/m"
        return None

    if prop == "thermal_conductivity":
        if "w" in unit_text and ("m-1" in unit_text or "mk" in unit_text or "m k" in unit_text):
            return value, "W m-1 K-1"
        return None

    if prop in {"ferromagnetism", "ferrimagnetism"}:
        if "emu" in unit_text or ("a" in unit_text and "m2" in unit_text and "kg" in unit_text):
            return value, "emu/g"
        return None

    if prop == "antiferromagnetism":
        if re.search(r"\bk\b", unit_text):
            return value, "K"
        return None

    if prop == "antibacterial":
        raw_low = str(raw_value or "").lower().replace("μ", "u").replace("µ", "u")
        if not raw_low or any(token in raw_low for token in ("ppm", "ug/ml", "ug ml", "mg/l", "mg l")):
            return value, "ppm"
        return None

    if prop == "thermoelectric":
        raw_low = str(raw_value or "").lower()
        if re.fullmatch(r"\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s*", raw_low) or any(
            token in raw_low for token in ("zt", "dimensionless", "unitless")
        ):
            return value, "dimensionless"
        return None

    return None


def _build_question(input_obj: dict[str, Any]) -> str:
    input_json = json.dumps(input_obj, ensure_ascii=False, indent=2)
    return (
        "Task: Predict material-property performance metrics for the given metal composition.\n\n"
        "INPUT_JSON:\n"
        f"{input_json}\n\n"
        "Goal:\n"
        "- Predict ALL requested metrics in metrics_to_predict as best-effort numeric values.\n"
        "- Use the provided metals and property_type/application context.\n"
        "- Normalize units according to each unit_hint.\n"
    )


def build_sample(record: dict[str, Any], *, source: str, include_unit_hint: bool) -> dict[str, Any] | None:
    prop = canonical_property(record.get("_schema") or record.get("application_name"))
    if not prop:
        return None
    spec = PROPERTY_METRICS[prop]
    metric_key = spec["metric_key"]
    raw_metric = record.get(metric_key)
    normalized = normalize_value(prop, raw_metric)
    if normalized is None:
        return None
    value, unit = normalized

    metals = record.get("metals") or []
    if isinstance(metals, str):
        metals = [m.strip() for m in metals.split(",") if m.strip()]
    if not isinstance(metals, list) or not metals:
        return None
    metals = [str(m).strip() for m in metals if str(m).strip()]
    if not metals:
        return None

    metric_item: dict[str, Any] = {"key": metric_key}
    if include_unit_hint:
        metric_item["unit_hint"] = unit

    input_obj = {
        "metals": metals,
        "property_type": prop,
        "application_name": spec["display"],
        # Compatibility for older experience/query code.
        "reaction_type": prop,
        "metrics_to_predict": [metric_item if include_unit_hint else metric_key],
    }
    answer_obj = {metric_key: f"{value:g} {unit}"}
    doi = str(record.get("doi") or "").strip() or None

    meta = {
        "id": record.get("row_number"),
        "row_number": record.get("row_number"),
        "doi": doi,
        "doc_id": doi,
        "metals": metals,
        "property_type": prop,
        "application_name": spec["display"],
        "reaction_type": prop,
        "metrics_gt": answer_obj,
        "metrics_raw": {metric_key: raw_metric},
        "units": {metric_key: unit},
        "source_schema": record.get("_schema"),
        "input_json": input_obj,
    }
    meta = {k: v for k, v in meta.items() if v is not None}

    return {
        "source": source,
        "source_index": record.get("row_number"),
        "question": _build_question(input_obj),
        "answer": json.dumps(answer_obj, ensure_ascii=False, sort_keys=True),
        "topic": prop,
        "level": "material_property",
        "meta": meta,
    }


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _parse_property_order(value: str | None) -> list[str]:
    if not value:
        return list(PROPERTY_METRICS.keys())

    order: list[str] = []
    seen: set[str] = set()
    for part in str(value).replace("，", ",").replace("、", ",").split(","):
        prop = canonical_property(part)
        if not prop:
            raise SystemExit(f"Unsupported property in --property_order: {part!r}")
        if prop in seen:
            continue
        seen.add(prop)
        order.append(prop)

    if not order:
        raise SystemExit("--property_order must contain at least one supported property")
    return order


def _balanced_round_robin(
    samples: list[dict[str, Any]],
    *,
    samples_per_property: int,
    seed: int,
    property_order: list[str],
) -> list[dict[str, Any]]:
    if samples_per_property <= 0:
        raise SystemExit("--samples_per_property must be a positive integer")

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        meta = sample.get("meta") or {}
        prop = canonical_property(meta.get("property_type"))
        if prop:
            buckets[prop].append(sample)

    missing = [prop for prop in property_order if len(buckets.get(prop, [])) < samples_per_property]
    if missing:
        detail = ", ".join(f"{prop}={len(buckets.get(prop, []))}" for prop in missing)
        raise SystemExit(
            f"Not enough valid samples for balanced material-property dataset: need "
            f"{samples_per_property} per property, got {detail}"
        )

    rng = random.Random(seed)
    selected: dict[str, list[dict[str, Any]]] = {}
    for prop in property_order:
        bucket = list(buckets[prop])
        rng.shuffle(bucket)
        selected[prop] = bucket[:samples_per_property]

    # Round-robin order keeps every prefix approximately balanced. This matters
    # because Training-Free GRPO truncates before shuffling.
    out: list[dict[str, Any]] = []
    for i in range(samples_per_property):
        for prop in property_order:
            out.append(selected[prop][i])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build material-property dataset JSONL from all_results.jsonl.")
    parser.add_argument(
        "--input_file",
        default="../../material_property_extraction/results/final_review_package_20260415/all_results.jsonl",
        help="Path to extracted all_results.jsonl.",
    )
    parser.add_argument(
        "--output_file",
        default="data/processed/material_property/material_property_dataset.jsonl",
        help="Path to write DatasetSample default-format JSONL.",
    )
    parser.add_argument("--source", default="training_free_grpo")
    parser.add_argument("--include_unit_hint", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--samples_per_property",
        type=int,
        default=None,
        help=(
            "If set, sample this many valid records for each property direction and write them "
            "in round-robin property order. For the current 6-direction project, 50 gives 300 rows."
        ),
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed for balanced sampling.")
    parser.add_argument(
        "--property_order",
        default=",".join(PROPERTY_METRICS.keys()),
        help="Comma-separated property order used for balanced round-robin output.",
    )
    args = parser.parse_args()

    in_path = Path(args.input_file)
    if not in_path.is_absolute():
        in_path = (Path.cwd() / in_path).resolve()
    out_path = Path(args.output_file)
    if not out_path.is_absolute():
        out_path = (Path.cwd() / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    available_counts = Counter()
    skipped = 0
    samples: list[dict[str, Any]] = []
    for record in iter_jsonl(in_path):
        sample = build_sample(record, source=args.source, include_unit_hint=bool(args.include_unit_hint))
        if sample is None:
            skipped += 1
            continue
        samples.append(sample)
        available_counts[sample["meta"]["property_type"]] += 1

    final_samples = samples
    if args.samples_per_property is not None:
        property_order = _parse_property_order(args.property_order)
        final_samples = _balanced_round_robin(
            samples,
            samples_per_property=int(args.samples_per_property),
            seed=int(args.seed),
            property_order=property_order,
        )

    if args.limit is not None:
        final_samples = final_samples[: int(args.limit)]

    counts = Counter()
    with out_path.open("w", encoding="utf-8") as out:
        for sample in final_samples:
            out.write(json.dumps(sample, ensure_ascii=False) + "\n")
            counts[sample["meta"]["property_type"]] += 1

    print(f"Wrote {len(final_samples)} samples to: {out_path}")
    if skipped:
        print(f"Skipped {skipped} records with missing/unsupported metrics.")
    print("Available valid samples by property_type:")
    for prop, count in sorted(available_counts.items()):
        print(f"- {prop}: {count}")
    if args.samples_per_property is not None:
        print(
            f"Balanced sampling: {int(args.samples_per_property)} per property, "
            f"seed={int(args.seed)}, total={len(final_samples)}"
        )
    if args.limit is not None:
        print(f"Applied final --limit={int(args.limit)}")
    print("Counts by property_type:")
    for prop, count in sorted(counts.items()):
        print(f"- {prop}: {count}")


if __name__ == "__main__":
    main()
