from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from utu.data_processing.material_feedback import TASK_TYPES


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "data"
    / "sample_material_performance_19_formal.py"
)
SPEC = importlib.util.spec_from_file_location("sample_material_performance_19_formal", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _record(task_type: str, number: int, *, shared_doc: str | None = None) -> dict:
    sample_id = f"{task_type}-{number}"
    doc_id = shared_doc or f"10.1000/{task_type.lower()}-{number}"
    return {
        "question": f"question {sample_id}",
        "answer": '{"value": 1}',
        "meta": {
            "sample_id": sample_id,
            "doc_id": doc_id,
            "task_type": task_type,
        },
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _source_rows(per_task: int = 4) -> list[dict]:
    return [
        _record(task_type, number)
        for task_type in TASK_TYPES
        for number in range(per_task)
    ]


def test_formal_sample_is_balanced_reproducible_and_article_disjoint(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    exclusion = tmp_path / "heldout.jsonl"
    output_a = tmp_path / "formal_a.jsonl"
    output_b = tmp_path / "formal_b.jsonl"
    manifest_a = tmp_path / "formal_a.manifest.json"
    manifest_b = tmp_path / "formal_b.manifest.json"
    rows = _source_rows()
    _write_jsonl(source, rows)
    _write_jsonl(exclusion, [_record(task_type, 0) for task_type in TASK_TYPES])

    report_a = MODULE.build_formal_sample(
        input_file=source,
        output_file=output_a,
        manifest_file=manifest_a,
        exclusion_files=[exclusion],
        per_task=2,
        seed=20260805,
    )
    report_b = MODULE.build_formal_sample(
        input_file=source,
        output_file=output_b,
        manifest_file=manifest_b,
        exclusion_files=[exclusion],
        per_task=2,
        seed=20260805,
    )

    assert output_a.read_text(encoding="utf-8") == output_b.read_text(encoding="utf-8")
    assert report_a["formal"]["total_samples"] == 38
    assert report_a["formal"]["unique_doc_ids"] == 38
    assert set(report_a["formal"]["counts_by_task"].values()) == {2}
    assert report_a["leakage_checks"] == {
        "duplicate_formal_sample_ids": 0,
        "duplicate_formal_doc_ids": 0,
        "excluded_sample_id_overlap": 0,
        "excluded_doc_id_overlap": 0,
    }
    assert report_a["formal"]["sample_ids_by_task"] == report_b["formal"]["sample_ids_by_task"]


def test_formal_sample_reserves_shared_articles_for_scarce_tasks(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    exclusion = tmp_path / "heldout.jsonl"
    rows = _source_rows(per_task=3)
    scarce_task = TASK_TYPES[-1]
    abundant_task = TASK_TYPES[0]
    shared_doc = "10.1000/shared"
    rows.append(_record(scarce_task, 99, shared_doc=shared_doc))
    rows.append(_record(abundant_task, 99, shared_doc=shared_doc))
    _write_jsonl(source, rows)
    _write_jsonl(exclusion, [_record(task_type, 0) for task_type in TASK_TYPES])

    report = MODULE.build_formal_sample(
        input_file=source,
        output_file=tmp_path / "formal.jsonl",
        manifest_file=tmp_path / "formal.manifest.json",
        exclusion_files=[exclusion],
        per_task=2,
        seed=7,
        write_outputs=False,
    )

    assert report["formal"]["total_samples"] == 38
    assert report["formal"]["unique_doc_ids"] == 38


def test_formal_sample_fails_when_an_exclusion_leaves_too_few_articles(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    exclusion = tmp_path / "heldout.jsonl"
    _write_jsonl(source, _source_rows(per_task=2))
    _write_jsonl(exclusion, [_record(TASK_TYPES[0], 0)])

    with pytest.raises(ValueError, match="not enough globally article-disjoint samples"):
        MODULE.build_formal_sample(
            input_file=source,
            output_file=tmp_path / "formal.jsonl",
            manifest_file=tmp_path / "formal.manifest.json",
            exclusion_files=[exclusion],
            per_task=2,
            seed=1,
            write_outputs=False,
        )


def test_formal_sample_requires_real_document_ids(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    exclusion = tmp_path / "heldout.jsonl"
    rows = _source_rows(per_task=2)
    del rows[0]["meta"]["doc_id"]
    _write_jsonl(source, rows)
    _write_jsonl(exclusion, [_record(TASK_TYPES[0], 99)])

    with pytest.raises(ValueError, match="missing meta.doc_id"):
        MODULE.build_formal_sample(
            input_file=source,
            output_file=tmp_path / "formal.jsonl",
            manifest_file=tmp_path / "formal.manifest.json",
            exclusion_files=[exclusion],
            per_task=1,
            seed=1,
            write_outputs=False,
        )
