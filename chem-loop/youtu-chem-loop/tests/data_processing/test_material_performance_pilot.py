from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.data.sample_material_performance_19_pilot import TASK_TYPES, build_pilot


def _write_source(path: Path, *, tasks: list[str] = TASK_TYPES, samples_per_task: int = 3) -> None:
    records = []
    for task_type in tasks:
        for index in range(samples_per_task):
            sample_id = f"{task_type}_{index}"
            records.append(
                {
                    "question": f"question {sample_id}",
                    "answer": '{"metric": 1.0}',
                    "source": "test",
                    "meta": {"task_type": task_type, "sample_id": sample_id},
                }
            )
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in reversed(records)),
        encoding="utf-8",
    )


def test_build_pilot_is_balanced_and_reproducible(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _write_source(source)

    first_output = tmp_path / "first.jsonl"
    first_manifest_path = tmp_path / "first.manifest.json"
    first = build_pilot(
        input_file=source,
        output_file=first_output,
        manifest_file=first_manifest_path,
        per_task=2,
        seed=20260731,
    )
    second_output = tmp_path / "second.jsonl"
    second = build_pilot(
        input_file=source,
        output_file=second_output,
        manifest_file=tmp_path / "second.manifest.json",
        per_task=2,
        seed=20260731,
    )

    assert first["sampling"]["total_selected"] == 38
    assert first["sampling"]["selected_counts_by_task"] == {task_type: 2 for task_type in TASK_TYPES}
    assert first["sampling"]["selected_sample_ids_by_task"] == second["sampling"]["selected_sample_ids_by_task"]
    assert first_output.read_bytes() == second_output.read_bytes()
    output_records = [json.loads(line) for line in first_output.read_text(encoding="utf-8").splitlines()]
    assert [record["meta"]["task_type"] for record in output_records] == [
        task_type for task_type in TASK_TYPES for _ in range(2)
    ]


def test_build_pilot_rejects_incomplete_task_coverage(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _write_source(source, tasks=TASK_TYPES[:-1])

    with pytest.raises(ValueError, match="missing=.*furfural_hydrogenation"):
        build_pilot(
            input_file=source,
            output_file=tmp_path / "pilot.jsonl",
            manifest_file=tmp_path / "pilot.manifest.json",
            per_task=1,
            seed=1,
        )


def test_build_pilot_rejects_duplicate_sample_ids(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _write_source(source)
    lines = source.read_text(encoding="utf-8").splitlines()
    duplicate = json.loads(lines[0])
    duplicate["meta"]["task_type"] = TASK_TYPES[0]
    source.write_text("\n".join([*lines, json.dumps(duplicate)]) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate meta.sample_id"):
        build_pilot(
            input_file=source,
            output_file=tmp_path / "pilot.jsonl",
            manifest_file=tmp_path / "pilot.manifest.json",
            per_task=1,
            seed=1,
        )
