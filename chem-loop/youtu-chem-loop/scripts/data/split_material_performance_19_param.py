#!/usr/bin/env python3
"""Build deterministic, article-disjoint train/validation splits for GRPO tuning."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utu.data_processing.material_feedback import TASK_TYPES  # noqa: E402


DATA_ROOT = REPO_ROOT / "data" / "processed" / "material_performance_19"
DEFAULT_INPUT = DATA_ROOT / "material_performance_19_grpo_v1.jsonl"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _meta_text(record: dict[str, Any], key: str) -> str:
    meta = record.get("meta")
    if not isinstance(meta, dict):
        return ""
    return str(meta.get(key) or "").strip()


def _sample_id(record: dict[str, Any]) -> str:
    return _meta_text(record, "sample_id")


def _doc_id(record: dict[str, Any]) -> str:
    doc_id = _meta_text(record, "doc_id")
    if doc_id:
        return doc_id.lower()
    sample_id = _sample_id(record)
    return f"sample:{sample_id}" if sample_id else ""


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _doc_id(record),
        _sample_id(record),
        json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    )


def _task_seed(seed: int, task_type: str) -> int:
    raw = f"material-performance-19-param:{seed}:{task_type}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _load_records(input_file: Path) -> tuple[dict[str, list[dict[str, Any]]], int]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sample_counts: Counter[str] = Counter()
    total = 0

    with input_file.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"line {line_number}: expected a JSON object")
            task_type = _meta_text(record, "task_type")
            sample_id = _sample_id(record)
            doc_id = _doc_id(record)
            if not task_type:
                raise ValueError(f"line {line_number}: missing meta.task_type")
            if not sample_id:
                raise ValueError(f"line {line_number}: missing meta.sample_id")
            if not doc_id:
                raise ValueError(f"line {line_number}: missing both meta.doc_id and meta.sample_id")
            grouped[task_type].append(record)
            sample_counts[sample_id] += 1
            total += 1

    expected = set(TASK_TYPES)
    actual = set(grouped)
    if expected != actual:
        raise ValueError(
            "input task coverage does not match the 19-direction contract: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )
    duplicate_ids = sorted(sample_id for sample_id, count in sample_counts.items() if count > 1)
    if duplicate_ids:
        raise ValueError(
            f"duplicate meta.sample_id values found: {duplicate_ids[:10]} (total={len(duplicate_ids)})"
        )
    return grouped, total


def _choose_records(
    *,
    pool: list[dict[str, Any]],
    count: int,
    own_docs: set[str],
    other_docs: set[str],
    excluded_sample_ids: set[str],
) -> list[dict[str, Any]]:
    chosen: list[dict[str, Any]] = []
    for record in pool:
        sample_id = _sample_id(record)
        doc_id = _doc_id(record)
        if sample_id in excluded_sample_ids or doc_id in own_docs or doc_id in other_docs:
            continue
        chosen.append(record)
        own_docs.add(doc_id)
        excluded_sample_ids.add(sample_id)
        if len(chosen) == count:
            return chosen
    return chosen


def build_param_split(
    *,
    input_file: Path,
    train_file: Path,
    validation_file: Path,
    manifest_file: Path,
    train_per_task: int,
    validation_per_task: int,
    seed: int,
    write_outputs: bool = True,
) -> dict[str, Any]:
    if train_per_task <= 0 or validation_per_task <= 0:
        raise ValueError("train_per_task and validation_per_task must be greater than zero")
    if not input_file.is_file():
        raise FileNotFoundError(f"input file not found: {input_file}")
    output_paths = {train_file.resolve(), validation_file.resolve(), manifest_file.resolve()}
    if len(output_paths) != 3 or input_file.resolve() in output_paths:
        raise ValueError("input, train, validation, and manifest paths must all be distinct")

    grouped, total_input = _load_records(input_file)
    shuffled_by_task: dict[str, list[dict[str, Any]]] = {}
    for task_type in TASK_TYPES:
        pool = sorted(grouped[task_type], key=_record_sort_key)
        random.Random(_task_seed(seed, task_type)).shuffle(pool)
        shuffled_by_task[task_type] = pool

    # Allocate scarce directions first. Global doc sets make the two splits article-disjoint
    # and also maximize paper diversity inside each split.
    allocation_order = sorted(TASK_TYPES, key=lambda task: (len(grouped[task]), TASK_TYPES.index(task)))
    train_docs: set[str] = set()
    validation_docs: set[str] = set()
    selected_sample_ids: set[str] = set()
    train_by_task: dict[str, list[dict[str, Any]]] = {}
    validation_by_task: dict[str, list[dict[str, Any]]] = {}

    for task_type in allocation_order:
        pool = shuffled_by_task[task_type]
        train_records = _choose_records(
            pool=pool,
            count=train_per_task,
            own_docs=train_docs,
            other_docs=validation_docs,
            excluded_sample_ids=selected_sample_ids,
        )
        validation_records = _choose_records(
            pool=pool,
            count=validation_per_task,
            own_docs=validation_docs,
            other_docs=train_docs,
            excluded_sample_ids=selected_sample_ids,
        )
        if len(train_records) != train_per_task or len(validation_records) != validation_per_task:
            raise ValueError(
                f"not enough article-disjoint samples for task_type={task_type}: "
                f"train={len(train_records)}/{train_per_task}, "
                f"validation={len(validation_records)}/{validation_per_task}"
            )
        train_by_task[task_type] = sorted(train_records, key=_record_sort_key)
        validation_by_task[task_type] = sorted(validation_records, key=_record_sort_key)

    train_records = [record for task in TASK_TYPES for record in train_by_task[task]]
    validation_records = [record for task in TASK_TYPES for record in validation_by_task[task]]
    train_sample_ids = {_sample_id(record) for record in train_records}
    validation_sample_ids = {_sample_id(record) for record in validation_records}
    train_doc_ids = {_doc_id(record) for record in train_records}
    validation_doc_ids = {_doc_id(record) for record in validation_records}
    if train_sample_ids & validation_sample_ids:
        raise AssertionError("train and validation sample IDs overlap")
    if train_doc_ids & validation_doc_ids:
        raise AssertionError("train and validation doc IDs overlap")

    if write_outputs:
        for path, records in ((train_file, train_records), (validation_file, validation_records)):
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    manifest: dict[str, Any] = {
        "schema_version": "material_performance_19_param_split_v1",
        "source": {
            "path": str(input_file.resolve()),
            "sha256": _sha256(input_file),
            "total_samples": total_input,
        },
        "sampling": {
            "seed": seed,
            "allocation_order": allocation_order,
            "task_order": list(TASK_TYPES),
            "train_per_task": train_per_task,
            "validation_per_task": validation_per_task,
            "input_counts_by_task": {task: len(grouped[task]) for task in TASK_TYPES},
        },
        "train": {
            "path": str(train_file.resolve()),
            "total_samples": len(train_records),
            "unique_doc_ids": len(train_doc_ids),
            "counts_by_task": {task: len(train_by_task[task]) for task in TASK_TYPES},
            "sample_ids_by_task": {
                task: [_sample_id(record) for record in train_by_task[task]] for task in TASK_TYPES
            },
        },
        "validation": {
            "path": str(validation_file.resolve()),
            "total_samples": len(validation_records),
            "unique_doc_ids": len(validation_doc_ids),
            "counts_by_task": {task: len(validation_by_task[task]) for task in TASK_TYPES},
            "sample_ids_by_task": {
                task: [_sample_id(record) for record in validation_by_task[task]] for task in TASK_TYPES
            },
        },
        "leakage_checks": {
            "sample_id_overlap": 0,
            "doc_id_overlap": 0,
        },
    }
    if write_outputs:
        manifest["train"]["sha256"] = _sha256(train_file)
        manifest["validation"]["sha256"] = _sha256(validation_file)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--train-file", type=Path, required=True)
    parser.add_argument("--validation-file", type=Path, required=True)
    parser.add_argument("--manifest-file", type=Path, required=True)
    parser.add_argument("--train-per-task", type=int, default=3)
    parser.add_argument("--validation-per-task", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260803)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate allocation and print the plan without writing output files.",
    )
    args = parser.parse_args()

    manifest = build_param_split(
        input_file=args.input_file,
        train_file=args.train_file,
        validation_file=args.validation_file,
        manifest_file=args.manifest_file,
        train_per_task=args.train_per_task,
        validation_per_task=args.validation_per_task,
        seed=args.seed,
        write_outputs=not args.check_only,
    )
    print(f"mode={'check-only' if args.check_only else 'write'}")
    print(f"train_total={manifest['train']['total_samples']}")
    print(f"validation_total={manifest['validation']['total_samples']}")
    print(f"train_unique_docs={manifest['train']['unique_doc_ids']}")
    print(f"validation_unique_docs={manifest['validation']['unique_doc_ids']}")
    print("sample_id_overlap=0")
    print("doc_id_overlap=0")
    for task_type in TASK_TYPES:
        print(
            f"{task_type}: input={manifest['sampling']['input_counts_by_task'][task_type]} "
            f"train={manifest['train']['counts_by_task'][task_type]} "
            f"validation={manifest['validation']['counts_by_task'][task_type]}"
        )


if __name__ == "__main__":
    main()
