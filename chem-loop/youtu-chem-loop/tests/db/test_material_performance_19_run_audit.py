from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import yaml


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "db"
    / "audit_material_performance_19_run.py"
)
SPEC = importlib.util.spec_from_file_location("audit_material_performance_19_run", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _make_db(path: Path, *, dataset: str, rows: list[dict], exp_id: str, grpo_n: int) -> None:
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE data (id INTEGER, dataset TEXT, "index" INTEGER, meta JSON)')
        con.execute(
            "CREATE TABLE evaluation_data ("
            "id INTEGER, dataset TEXT, dataset_index INTEGER, meta JSON, response TEXT, "
            "trajectories TEXT, reward REAL, reasoning TEXT, exp_id TEXT, stage TEXT)"
        )
        for index, row in enumerate(rows):
            con.execute(
                'INSERT INTO data VALUES (?, ?, ?, ?)',
                (index + 1, dataset, index, json.dumps(row["meta"])),
            )
            for rollout in range(grpo_n):
                con.execute(
                    "INSERT INTO evaluation_data VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        index * grpo_n + rollout + 1,
                        dataset,
                        index,
                        json.dumps(row["meta"]),
                        '<think>x</think><answer>{"value": 1}</answer>',
                        json.dumps([{"agent": "material_performance_grpo_agent", "trajectory": [{}]}]),
                        0.5,
                        None,
                        exp_id,
                        "judged",
                    ),
                )


def test_dataset_status_requires_exact_ordered_sample_ids(tmp_path: Path) -> None:
    dataset_jsonl = tmp_path / "data.jsonl"
    rows = [
        {"meta": {"sample_id": "a", "task_type": "HER"}},
        {"meta": {"sample_id": "b", "task_type": "OER"}},
    ]
    _write_jsonl(dataset_jsonl, rows)
    db = tmp_path / "test.db"
    _make_db(db, dataset="formal", rows=rows, exp_id="run", grpo_n=3)

    assert MODULE.dataset_status(
        db_path=db,
        dataset_name="formal",
        dataset_jsonl=dataset_jsonl,
    )["status"] == "match"

    with sqlite3.connect(db) as con:
        con.execute('UPDATE data SET "index" = 5 - "index"')
    assert MODULE.dataset_status(
        db_path=db,
        dataset_name="formal",
        dataset_jsonl=dataset_jsonl,
    )["status"] == "mismatch"


def test_audit_checks_rollouts_cards_hzor_and_protected_files(tmp_path: Path, monkeypatch) -> None:
    task_types = list(MODULE.TASK_TYPES)
    monkeypatch.setattr(MODULE, "TASK_TYPES", task_types)
    rows = [
        {
            "meta": {
                "sample_id": f"sample-{task_type}",
                "task_type": task_type,
            }
        }
        for task_type in task_types
    ]
    dataset_jsonl = tmp_path / "data.jsonl"
    _write_jsonl(dataset_jsonl, rows)
    db = tmp_path / "test.db"
    _make_db(db, dataset="canary", rows=rows, exp_id="canary_epoch_0", grpo_n=3)

    agent = tmp_path / "agent.yaml"
    agent.write_text(
        yaml.safe_dump(
            {
                "agent": {
                    "instructions": "\n".join(
                        f"[G{i}]. TASK={task}; TAKEAWAY=test" for i, task in enumerate(task_types)
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    log = tmp_path / "run.log"
    log.write_text("Training-free GRPO completed\n", encoding="utf-8")
    stable = tmp_path / "experience.yaml"
    stable.write_text("agent: {}\n", encoding="utf-8")
    snapshot = tmp_path / "protected.json"
    MODULE.snapshot_protected_files(files=[stable], output=snapshot)

    report = MODULE.audit_run(
        db_path=db,
        dataset_name="canary",
        dataset_jsonl=dataset_jsonl,
        exp_id="canary_epoch_0",
        agent_config=agent,
        log_file=log,
        protected_snapshot=snapshot,
        expected_questions=19,
        grpo_n=3,
        expected_per_task=1,
    )

    assert report["status"] == "pass"
    assert report["run"]["judged_rollouts"] == 57
    assert report["run"]["mad_rollout_rows"] == 0
    assert report["hzor"]["questions"] == 1
    assert report["hzor"]["experience_cards"] == 1


def test_audit_fails_on_mad_rollout_provider_error_and_pack_change(tmp_path: Path) -> None:
    rows = [{"meta": {"sample_id": "sample-HER", "task_type": "HER"}}]
    dataset_jsonl = tmp_path / "data.jsonl"
    _write_jsonl(dataset_jsonl, rows)
    db = tmp_path / "test.db"
    _make_db(db, dataset="canary", rows=rows, exp_id="canary_epoch_0", grpo_n=1)
    with sqlite3.connect(db) as con:
        con.execute(
            "UPDATE evaluation_data SET trajectories=?",
            (json.dumps([{"agent": "mad_engine", "trajectory": [{}]}]),),
        )
    agent = tmp_path / "agent.yaml"
    agent.write_text("agent:\n  instructions: '[G0]. TASK=HER; test'\n", encoding="utf-8")
    log = tmp_path / "run.log"
    log.write_text("HTTP status 429 rate limited\n", encoding="utf-8")
    stable = tmp_path / "experience.yaml"
    stable.write_text("old\n", encoding="utf-8")
    snapshot = tmp_path / "protected.json"
    MODULE.snapshot_protected_files(files=[stable], output=snapshot)
    stable.write_text("changed\n", encoding="utf-8")

    report = MODULE.audit_run(
        db_path=db,
        dataset_name="canary",
        dataset_jsonl=dataset_jsonl,
        exp_id="canary_epoch_0",
        agent_config=agent,
        log_file=log,
        protected_snapshot=snapshot,
        expected_questions=1,
        grpo_n=1,
        expected_per_task=0,
    )

    assert report["status"] == "fail"
    assert report["run"]["mad_rollout_rows"] == 1
    assert report["run"]["provider_error_markers"]
    assert report["protected_packs"]["changes"]


def test_group_state_matches_experience_updater_strict_reward_filter() -> None:
    assert MODULE._group_state([0.0, 0.0, 0.0]) == "all_wrong"
    assert MODULE._group_state([1.0, 1.0, 1.0]) == "all_correct"
    assert MODULE._group_state([1e-237, 1e-237, 1e-237]) == "partial_reward"
