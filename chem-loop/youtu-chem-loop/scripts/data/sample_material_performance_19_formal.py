#!/usr/bin/env python3
"""Build the article-disjoint 950-question material-performance formal set."""

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
DEFAULT_EXCLUSION = (
    DATA_ROOT
    / "params"
    / "material_performance_19_hp_validation_s3_v3_seed20260803.jsonl"
)
DEFAULT_OUTPUT = (
    DATA_ROOT
    / "formal"
    / "material_performance_19_formal_s50_seed20260805.jsonl"
)
DEFAULT_MANIFEST = DEFAULT_OUTPUT.with_suffix(".manifest.json")


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
    return _meta_text(record, "doc_id").lower()


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _doc_id(record),
        _sample_id(record),
        json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
    )


def _task_seed(seed: int, task_type: str) -> int:
    raw = f"material-performance-19-formal:{seed}:{task_type}".encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _load_jsonl(path: Path, *, require_task: bool) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            sample_id = _sample_id(record)
            doc_id = _doc_id(record)
            task_type = _meta_text(record, "task_type")
            if not sample_id:
                raise ValueError(f"{path}:{line_number}: missing meta.sample_id")
            if not doc_id:
                raise ValueError(f"{path}:{line_number}: missing meta.doc_id")
            if require_task and not task_type:
                raise ValueError(f"{path}:{line_number}: missing meta.task_type")
            records.append(record)
    return records


def _validate_source(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sample_counts: Counter[str] = Counter()
    for record in records:
        task_type = _meta_text(record, "task_type")
        grouped[task_type].append(record)
        sample_counts[_sample_id(record)] += 1

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
            f"duplicate meta.sample_id values found: {duplicate_ids[:10]} "
            f"(total={len(duplicate_ids)})"
        )
    return grouped


def _load_exclusions(paths: list[Path]) -> tuple[set[str], set[str], list[dict[str, Any]]]:
    excluded_sample_ids: set[str] = set()
    excluded_doc_ids: set[str] = set()
    details: list[dict[str, Any]] = []
    for path in paths:
        records = _load_jsonl(path, require_task=False)
        sample_ids = {_sample_id(record) for record in records}
        doc_ids = {_doc_id(record) for record in records}
        excluded_sample_ids.update(sample_ids)
        excluded_doc_ids.update(doc_ids)
        details.append(
            {
                "path": str(path.resolve()),
                "sha256": _sha256(path),
                "total_samples": len(records),
                "unique_sample_ids": len(sample_ids),
                "unique_doc_ids": len(doc_ids),
            }
        )
    return excluded_sample_ids, excluded_doc_ids, details


def build_formal_sample(
    *,
    input_file: Path,
    output_file: Path,
    manifest_file: Path,
    exclusion_files: list[Path],
    per_task: int,
    seed: int,
    write_outputs: bool = True,
) -> dict[str, Any]:
    """Select a deterministic balanced set with no document overlap anywhere."""
    if per_task <= 0:
        raise ValueError("per_task must be greater than zero")
    resolved_paths = {input_file.resolve(), output_file.resolve(), manifest_file.resolve()}
    if len(resolved_paths) != 3:
        raise ValueError("input, output, and manifest paths must be distinct")

    source_records = _load_jsonl(input_file, require_task=True)
    grouped = _validate_source(source_records)
    excluded_sample_ids, excluded_doc_ids, exclusion_details = _load_exclusions(exclusion_files)

    eligible_by_task: dict[str, list[dict[str, Any]]] = {}
    for task_type in TASK_TYPES:
        eligible = [
            record
            for record in grouped[task_type]
            if _sample_id(record) not in excluded_sample_ids and _doc_id(record) not in excluded_doc_ids
        ]
        eligible = sorted(eligible, key=_record_sort_key)
        random.Random(_task_seed(seed, task_type)).shuffle(eligible)
        eligible_by_task[task_type] = eligible

    # Allocate directions with the fewest eligible articles first so shared papers
    # cannot consume the only usable rows for a scarce direction.
    allocation_order = sorted(
        TASK_TYPES,
        key=lambda task: (
            len({_doc_id(record) for record in eligible_by_task[task]}),
            TASK_TYPES.index(task),
        ),
    )
    selected_docs: set[str] = set()
    selected_sample_ids: set[str] = set()
    selected_by_task: dict[str, list[dict[str, Any]]] = {}

    for task_type in allocation_order:
        chosen: list[dict[str, Any]] = []
        for record in eligible_by_task[task_type]:
            sample_id = _sample_id(record)
            doc_id = _doc_id(record)
            if sample_id in selected_sample_ids or doc_id in selected_docs:
                continue
            chosen.append(record)
            selected_sample_ids.add(sample_id)
            selected_docs.add(doc_id)
            if len(chosen) == per_task:
                break
        if len(chosen) != per_task:
            raise ValueError(
                f"not enough globally article-disjoint samples for task_type={task_type}: "
                f"selected={len(chosen)}/{per_task}, "
                f"eligible_rows={len(eligible_by_task[task_type])}, "
                f"eligible_docs={len({_doc_id(record) for record in eligible_by_task[task_type]})}"
            )
        selected_by_task[task_type] = sorted(chosen, key=_record_sort_key)

    selected = [record for task in TASK_TYPES for record in selected_by_task[task]]
    selected_doc_ids = {_doc_id(record) for record in selected}
    selected_ids = {_sample_id(record) for record in selected}
    doc_overlap = selected_doc_ids & excluded_doc_ids
    sample_overlap = selected_ids & excluded_sample_ids
    if len(selected) != len(TASK_TYPES) * per_task:
        raise AssertionError("formal sample count does not match task balance")
    if len(selected_doc_ids) != len(selected):
        raise AssertionError("formal sample contains duplicate document IDs")
    if doc_overlap or sample_overlap:
        raise AssertionError("formal sample overlaps an excluded held-out set")

    if write_outputs:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8") as handle:
            for record in selected:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    manifest: dict[str, Any] = {
        "schema_version": "material_performance_19_formal_manifest_v1",
        "source": {
            "path": str(input_file.resolve()),
            "sha256": _sha256(input_file),
            "total_samples": len(source_records),
        },
        "exclusions": {
            "files": exclusion_details,
            "unique_sample_ids": len(excluded_sample_ids),
            "unique_doc_ids": len(excluded_doc_ids),
        },
        "sampling": {
            "seed": seed,
            "per_task_requested": per_task,
            "task_order": list(TASK_TYPES),
            "allocation_order": allocation_order,
            "input_counts_by_task": {task: len(grouped[task]) for task in TASK_TYPES},
            "eligible_counts_by_task": {
                task: len(eligible_by_task[task]) for task in TASK_TYPES
            },
            "eligible_doc_counts_by_task": {
                task: len({_doc_id(record) for record in eligible_by_task[task]})
                for task in TASK_TYPES
            },
        },
        "formal": {
            "path": str(output_file.resolve()),
            "total_samples": len(selected),
            "unique_sample_ids": len(selected_ids),
            "unique_doc_ids": len(selected_doc_ids),
            "counts_by_task": {task: len(selected_by_task[task]) for task in TASK_TYPES},
            "sample_ids_by_task": {
                task: [_sample_id(record) for record in selected_by_task[task]]
                for task in TASK_TYPES
            },
            "doc_ids_by_task": {
                task: [_doc_id(record) for record in selected_by_task[task]]
                for task in TASK_TYPES
            },
        },
        "leakage_checks": {
            "duplicate_formal_sample_ids": len(selected) - len(selected_ids),
            "duplicate_formal_doc_ids": len(selected) - len(selected_doc_ids),
            "excluded_sample_id_overlap": len(sample_overlap),
            "excluded_doc_id_overlap": len(doc_overlap),
        },
    }
    if write_outputs:
        manifest["formal"]["sha256"] = _sha256(output_file)
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
    parser.add_argument(
        "--exclude-file",
        action="append",
        type=Path,
        default=None,
        help="JSONL whose sample and document IDs must remain excluded; repeat as needed.",
    )
    parser.add_argument("--per-task", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    manifest = build_formal_sample(
        input_file=args.input_file,
        output_file=args.output_file,
        manifest_file=args.manifest_file,
        exclusion_files=args.exclude_file or [DEFAULT_EXCLUSION],
        per_task=args.per_task,
        seed=args.seed,
        write_outputs=not args.check_only,
    )
    formal = manifest["formal"]
    leakage = manifest["leakage_checks"]
    print(f"mode={'check-only' if args.check_only else 'write'}")
    print(f"formal_output={formal['path']}")
    print(f"manifest_output={args.manifest_file.resolve()}")
    print(f"formal_total={formal['total_samples']}")
    print(f"formal_unique_docs={formal['unique_doc_ids']}")
    print(f"excluded_doc_id_overlap={leakage['excluded_doc_id_overlap']}")
    for task_type in TASK_TYPES:
        print(
            f"{task_type}: input={manifest['sampling']['input_counts_by_task'][task_type]} "
            f"eligible={manifest['sampling']['eligible_counts_by_task'][task_type]} "
            f"selected={formal['counts_by_task'][task_type]}"
        )


if __name__ == "__main__":
    main()
