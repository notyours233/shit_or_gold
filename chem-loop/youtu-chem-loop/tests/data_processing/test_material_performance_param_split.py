from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.data.split_material_performance_19_param import build_param_split
from utu.data_processing.material_feedback import TASK_TYPES


def _write_source(path: Path, *, samples_per_task: int = 8) -> None:
    records = []
    for task_index, task_type in enumerate(TASK_TYPES):
        for sample_index in range(samples_per_task):
            sample_id = f"{task_type}_{sample_index}"
            # The first document is deliberately shared by adjacent tasks. A valid
            # split must never place this paper on opposite sides.
            if sample_index == 0:
                doc_id = f"shared_{task_index // 2}"
            else:
                doc_id = f"doc_{task_type}_{sample_index}"
            records.append(
                {
                    "question": f"question {sample_id}",
                    "answer": '{"metric": 1.0}',
                    "source": "training_free_grpo",
                    "meta": {
                        "task_type": task_type,
                        "sample_id": sample_id,
                        "doc_id": doc_id,
                    },
                }
            )
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in reversed(records)),
        encoding="utf-8",
    )


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_param_split_is_balanced_reproducible_and_article_disjoint(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _write_source(source)

    first_train = tmp_path / "first.train.jsonl"
    first_validation = tmp_path / "first.validation.jsonl"
    manifest = build_param_split(
        input_file=source,
        train_file=first_train,
        validation_file=first_validation,
        manifest_file=tmp_path / "first.manifest.json",
        train_per_task=2,
        validation_per_task=2,
        seed=20260803,
    )
    second_train = tmp_path / "second.train.jsonl"
    second_validation = tmp_path / "second.validation.jsonl"
    build_param_split(
        input_file=source,
        train_file=second_train,
        validation_file=second_validation,
        manifest_file=tmp_path / "second.manifest.json",
        train_per_task=2,
        validation_per_task=2,
        seed=20260803,
    )

    assert manifest["train"]["total_samples"] == 38
    assert manifest["validation"]["total_samples"] == 38
    assert manifest["train"]["counts_by_task"] == {task: 2 for task in TASK_TYPES}
    assert manifest["validation"]["counts_by_task"] == {task: 2 for task in TASK_TYPES}
    assert first_train.read_bytes() == second_train.read_bytes()
    assert first_validation.read_bytes() == second_validation.read_bytes()

    train = _records(first_train)
    validation = _records(first_validation)
    assert {record["meta"]["sample_id"] for record in train}.isdisjoint(
        {record["meta"]["sample_id"] for record in validation}
    )
    assert {record["meta"]["doc_id"] for record in train}.isdisjoint(
        {record["meta"]["doc_id"] for record in validation}
    )
    assert [record["meta"]["task_type"] for record in train] == [
        task for task in TASK_TYPES for _ in range(2)
    ]


def test_param_split_check_only_does_not_write(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _write_source(source)
    train = tmp_path / "train.jsonl"
    validation = tmp_path / "validation.jsonl"
    manifest_file = tmp_path / "manifest.json"

    manifest = build_param_split(
        input_file=source,
        train_file=train,
        validation_file=validation,
        manifest_file=manifest_file,
        train_per_task=1,
        validation_per_task=1,
        seed=1,
        write_outputs=False,
    )

    assert manifest["leakage_checks"] == {"sample_id_overlap": 0, "doc_id_overlap": 0}
    assert not train.exists()
    assert not validation.exists()
    assert not manifest_file.exists()


def test_param_split_rejects_insufficient_article_disjoint_pool(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _write_source(source, samples_per_task=2)

    with pytest.raises(ValueError, match="not enough article-disjoint samples"):
        build_param_split(
            input_file=source,
            train_file=tmp_path / "train.jsonl",
            validation_file=tmp_path / "validation.jsonl",
            manifest_file=tmp_path / "manifest.json",
            train_per_task=1,
            validation_per_task=2,
            seed=1,
        )
