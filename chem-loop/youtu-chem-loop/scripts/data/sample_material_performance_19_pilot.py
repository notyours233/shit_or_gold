#!/usr/bin/env python3
"""Create a reproducible, task-balanced pilot from the 19-direction GRPO data."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


TASK_TYPES = [
    "HER",
    "OER",
    "ORR",
    "HOR",
    "UOR",
    "EOR",
    "HZOR",
    "O5H",
    "CO2RR",
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
]

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data" / "processed" / "material_performance_19"
DEFAULT_INPUT = DATA_ROOT / "material_performance_19_grpo_v1.jsonl"
DEFAULT_OUTPUT = DATA_ROOT / "pilots" / "material_performance_19_pilot_s1_v1.jsonl"
DEFAULT_MANIFEST = DATA_ROOT / "pilots" / "material_performance_19_pilot_s1_v1.manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sample_id(record: dict[str, Any]) -> str:
    meta = record.get("meta")
    if not isinstance(meta, dict):
        return ""
    return str(meta.get("sample_id") or "").strip()


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str]:
    return (
        _sample_id(record),
        json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    )


def _task_seed(seed: int, task_type: str) -> int:
    raw = f"{seed}:{task_type}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def build_pilot(
    *,
    input_file: Path,
    output_file: Path,
    manifest_file: Path,
    per_task: int,
    seed: int,
) -> dict[str, Any]:
    if per_task <= 0:
        raise ValueError("per_task must be greater than zero")
    if not input_file.is_file():
        raise FileNotFoundError(f"input file not found: {input_file}")
    if output_file.resolve() == input_file.resolve():
        raise ValueError("output_file must differ from input_file")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sample_id_counts: Counter[str] = Counter()
    total_input = 0

    with input_file.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number}: expected a JSON object")
            meta = record.get("meta")
            if not isinstance(meta, dict):
                raise ValueError(f"line {line_number}: missing object meta")
            task_type = str(meta.get("task_type") or "").strip()
            if not task_type:
                raise ValueError(f"line {line_number}: missing meta.task_type")
            sample_id = _sample_id(record)
            if not sample_id:
                raise ValueError(f"line {line_number}: missing meta.sample_id")
            grouped[task_type].append(record)
            sample_id_counts[sample_id] += 1
            total_input += 1

    actual_tasks = set(grouped)
    expected_tasks = set(TASK_TYPES)
    missing_tasks = sorted(expected_tasks - actual_tasks)
    extra_tasks = sorted(actual_tasks - expected_tasks)
    if missing_tasks or extra_tasks:
        raise ValueError(
            "input task coverage does not match the 19-direction contract: "
            f"missing={missing_tasks}, extra={extra_tasks}"
        )

    duplicate_ids = sorted(sample_id for sample_id, count in sample_id_counts.items() if count > 1)
    if duplicate_ids:
        preview = duplicate_ids[:10]
        raise ValueError(f"duplicate meta.sample_id values found: {preview} (total={len(duplicate_ids)})")

    selected: list[dict[str, Any]] = []
    selected_ids_by_task: dict[str, list[str]] = {}
    input_counts: dict[str, int] = {}
    selected_counts: dict[str, int] = {}

    for task_type in TASK_TYPES:
        pool = sorted(grouped[task_type], key=_record_sort_key)
        input_counts[task_type] = len(pool)
        if len(pool) < per_task:
            raise ValueError(
                f"not enough samples for task_type={task_type}: have {len(pool)}, need {per_task}"
            )
        rng = random.Random(_task_seed(seed, task_type))
        chosen = sorted(rng.sample(pool, per_task), key=_record_sort_key)
        selected.extend(chosen)
        selected_counts[task_type] = len(chosen)
        selected_ids_by_task[task_type] = [_sample_id(record) for record in chosen]

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as handle:
        for record in selected:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {
        "schema_version": "material_performance_19_pilot_manifest_v1",
        "source": {
            "path": str(input_file.resolve()),
            "sha256": _sha256(input_file),
            "total_samples": total_input,
        },
        "sampling": {
            "seed": seed,
            "per_task_requested": per_task,
            "task_order": TASK_TYPES,
            "input_counts_by_task": input_counts,
            "selected_counts_by_task": selected_counts,
            "selected_sample_ids_by_task": selected_ids_by_task,
            "total_selected": len(selected),
        },
        "output": {
            "path": str(output_file.resolve()),
            "sha256": _sha256(output_file),
        },
    }
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-file", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest-file", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--per-task", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260731)
    args = parser.parse_args()

    manifest = build_pilot(
        input_file=args.input_file,
        output_file=args.output_file,
        manifest_file=args.manifest_file,
        per_task=args.per_task,
        seed=args.seed,
    )
    print(f"pilot_output={manifest['output']['path']}")
    print(f"manifest_output={args.manifest_file.resolve()}")
    print(f"total_selected={manifest['sampling']['total_selected']}")
    for task_type in TASK_TYPES:
        count_in = manifest["sampling"]["input_counts_by_task"][task_type]
        count_out = manifest["sampling"]["selected_counts_by_task"][task_type]
        print(f"{task_type}: input={count_in} selected={count_out}")


if __name__ == "__main__":
    main()
