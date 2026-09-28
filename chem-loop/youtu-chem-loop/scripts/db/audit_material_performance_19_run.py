#!/usr/bin/env python3
"""Preflight and audit isolated 19-direction material-performance GRPO runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utu.data_processing.material_feedback import TASK_TYPES  # noqa: E402
from utu.practice.verify.chem_performance_lib.answer_parser import (  # noqa: E402
    extract_structured_answer_object,
)


_PROVIDER_ERROR_PATTERNS = (
    re.compile(r"(?:http|status(?: code)?)[^\n]{0,30}\b(?:401|403|429)\b", re.IGNORECASE),
    re.compile(r"\binsufficient[_ -]?quota\b", re.IGNORECASE),
    re.compile(r"\brate[ -]?limit(?:ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\bauthentication error\b", re.IGNORECASE),
    re.compile(r"\bprovider error\b", re.IGNORECASE),
    re.compile(r"\brequest timed out\b", re.IGNORECASE),
    re.compile(r"\btask timed out\b", re.IGNORECASE),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_dataset(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"dataset JSONL not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            meta = row.get("meta")
            if not isinstance(meta, dict):
                raise ValueError(f"{path}:{line_number}: missing object meta")
            if not str(meta.get("sample_id") or "").strip():
                raise ValueError(f"{path}:{line_number}: missing meta.sample_id")
            if not str(meta.get("task_type") or "").strip():
                raise ValueError(f"{path}:{line_number}: missing meta.task_type")
            rows.append(row)
    return rows


def _sample_id(row: dict[str, Any]) -> str:
    return str((_json_object(row.get("meta"))).get("sample_id") or "").strip()


def _task_type(row: dict[str, Any]) -> str:
    meta = _json_object(row.get("meta"))
    return str(meta.get("task_type") or meta.get("property_type") or meta.get("reaction_type") or "").strip()


def dataset_status(*, db_path: Path, dataset_name: str, dataset_jsonl: Path) -> dict[str, Any]:
    expected_rows = _read_dataset(dataset_jsonl)
    expected_ids = [_sample_id(row) for row in expected_rows]
    with sqlite3.connect(str(db_path)) as con:
        con.row_factory = sqlite3.Row
        actual = con.execute(
            "SELECT \"index\", meta FROM data WHERE dataset=? ORDER BY \"index\", id",
            (dataset_name,),
        ).fetchall()
    actual_ids = [str(_json_object(row["meta"]).get("sample_id") or "").strip() for row in actual]
    status = "missing" if not actual else ("match" if actual_ids == expected_ids else "mismatch")
    return {
        "status": status,
        "dataset_name": dataset_name,
        "dataset_jsonl": str(dataset_jsonl.resolve()),
        "expected_rows": len(expected_rows),
        "actual_rows": len(actual),
        "expected_sha256": _sha256(dataset_jsonl),
        "expected_sample_ids": expected_ids,
        "actual_sample_ids": actual_ids,
    }


def snapshot_protected_files(*, files: list[Path], output: Path) -> dict[str, Any]:
    entries = []
    for path in files:
        resolved = path.resolve()
        exists = resolved.is_file()
        entries.append(
            {
                "path": str(resolved),
                "exists": exists,
                "sha256": _sha256(resolved) if exists else None,
            }
        )
    payload = {"schema_version": "material_performance_19_protected_snapshot_v1", "files": entries}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _compare_protected_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"invalid protected snapshot: {path}")
    changes: list[dict[str, Any]] = []
    for entry in entries:
        protected = Path(str(entry.get("path") or ""))
        expected_exists = bool(entry.get("exists"))
        actual_exists = protected.is_file()
        expected_hash = entry.get("sha256")
        actual_hash = _sha256(protected) if actual_exists else None
        if actual_exists != expected_exists or actual_hash != expected_hash:
            changes.append(
                {
                    "path": str(protected),
                    "expected_exists": expected_exists,
                    "actual_exists": actual_exists,
                    "expected_sha256": expected_hash,
                    "actual_sha256": actual_hash,
                }
            )
    return {"snapshot": str(path.resolve()), "files_checked": len(entries), "changes": changes}


def _experience_summary(agent_config: Path) -> dict[str, Any]:
    if not agent_config.is_file():
        return {
            "agent_config": str(agent_config.resolve()),
            "exists": False,
            "n_experiences": 0,
            "tasks_covered": 0,
            "missing_tasks": list(TASK_TYPES),
            "counts_by_task": {task: 0 for task in TASK_TYPES},
        }
    payload = yaml.safe_load(agent_config.read_text(encoding="utf-8"))
    agent = payload.get("agent") if isinstance(payload, dict) else None
    instructions = agent.get("instructions") if isinstance(agent, dict) else None
    cards = []
    if isinstance(instructions, str):
        cards = [
            match.group(1).strip()
            for match in re.finditer(
                r"(?ms)^\[G[^\]]+\]\.\s*(.*?)(?=^\[G[^\]]+\]\.\s*|\Z)",
                instructions,
            )
            if match.group(1).strip()
        ]
    counts = {task: 0 for task in TASK_TYPES}
    for card in cards:
        for task_type in TASK_TYPES:
            pattern = rf"(?:TASK|task_type)\s*[=:]\s*{re.escape(task_type)}(?:\b|;)"
            if re.search(pattern, card, flags=re.IGNORECASE):
                counts[task_type] += 1
    covered = [task for task, count in counts.items() if count > 0]
    return {
        "agent_config": str(agent_config.resolve()),
        "exists": True,
        "sha256": _sha256(agent_config),
        "n_experiences": len(cards),
        "tasks_covered": len(covered),
        "missing_tasks": [task for task in TASK_TYPES if counts[task] == 0],
        "counts_by_task": counts,
    }


def _group_state(rewards: list[float]) -> str:
    # Keep this classification identical to ExperienceUpdater, which checks the
    # group average with strict 0 < average < 1 comparisons. Tiny positive
    # rewards therefore remain eligible partial-reward groups.
    if rewards and all(reward == 1.0 for reward in rewards):
        return "all_correct"
    if rewards and all(reward == 0.0 for reward in rewards):
        return "all_wrong"
    return "partial_reward"


def _scan_provider_errors(log_file: Path) -> list[str]:
    text = log_file.read_text(encoding="utf-8", errors="replace")
    hits: list[str] = []
    for pattern in _PROVIDER_ERROR_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append(match.group(0).strip())
    return hits


def preflight(
    *,
    db_path: Path,
    dataset_name: str,
    dataset_jsonl: Path,
    expected_questions: int,
    expected_per_task: int,
    chroma_dir: Path,
    chroma_collection: str,
) -> dict[str, Any]:
    failures: list[str] = []
    rows = _read_dataset(dataset_jsonl)
    task_counts = Counter(_task_type(row) for row in rows)
    if len(rows) != expected_questions:
        failures.append(f"dataset rows {len(rows)} != {expected_questions}")
    if set(task_counts) != set(TASK_TYPES):
        failures.append("dataset task coverage does not equal the 19-direction contract")
    for task_type in TASK_TYPES:
        if task_counts[task_type] != expected_per_task:
            failures.append(f"dataset task {task_type} has {task_counts[task_type]} != {expected_per_task}")

    db_check = dataset_status(db_path=db_path, dataset_name=dataset_name, dataset_jsonl=dataset_jsonl)
    if db_check["status"] != "match":
        failures.append(f"DB dataset status is {db_check['status']}, expected match")

    required_env = ("UTU_LLM_API_KEY", "UTU_LLM_BASE_URL", "UTU_LLM_MODEL")
    env_present = {name: bool(str(os.getenv(name) or "").strip()) for name in required_env}
    for name, present in env_present.items():
        if not present:
            failures.append(f"required environment variable is missing: {name}")

    chroma_count: int | None = None
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(chroma_dir.resolve()))
        chroma_count = int(client.get_collection(chroma_collection).count())
        if chroma_count <= 0:
            failures.append(f"Chroma collection is empty: {chroma_collection}")
    except Exception as exc:  # noqa: BLE001 - preflight must fail closed
        failures.append(f"Chroma preflight failed: {type(exc).__name__}: {exc}")

    return {
        "schema_version": "material_performance_19_preflight_v1",
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "dataset": {
            "path": str(dataset_jsonl.resolve()),
            "questions": len(rows),
            "counts_by_task": dict(task_counts),
            "db_status": db_check["status"],
        },
        "provider": {"required_env_present": env_present},
        "chroma": {
            "path": str(chroma_dir.resolve()),
            "collection": chroma_collection,
            "count": chroma_count,
        },
    }


def audit_run(
    *,
    db_path: Path,
    dataset_name: str,
    dataset_jsonl: Path,
    exp_id: str,
    agent_config: Path,
    log_file: Path,
    protected_snapshot: Path,
    expected_questions: int,
    grpo_n: int,
    expected_per_task: int,
    min_experience_task_coverage: int = 0,
) -> dict[str, Any]:
    failures: list[str] = []
    dataset_check = dataset_status(
        db_path=db_path,
        dataset_name=dataset_name,
        dataset_jsonl=dataset_jsonl,
    )
    if dataset_check["status"] != "match":
        failures.append(f"DB dataset status is {dataset_check['status']}, expected match")

    expected_rows = expected_questions * grpo_n
    with sqlite3.connect(str(db_path)) as con:
        con.row_factory = sqlite3.Row
        rows = [
            dict(row)
            for row in con.execute(
                "SELECT dataset, dataset_index, meta, response, trajectories, reward, reasoning "
                "FROM evaluation_data WHERE exp_id=? AND stage='judged' ORDER BY dataset_index, id",
                (exp_id,),
            ).fetchall()
        ]

    if len(rows) != expected_rows:
        failures.append(f"judged rollout rows {len(rows)} != {expected_rows}")
    if any(row.get("dataset") != dataset_name for row in rows):
        failures.append("one or more judged rows use a different dataset")

    by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    parse_failures = 0
    trajectory_failures = 0
    mad_rollout_rows = 0
    invalid_rewards = 0
    for row in rows:
        sample_id = _sample_id(row)
        task_type = _task_type(row)
        by_sample[sample_id].append(row)
        by_task[task_type].append(row)
        reward = row.get("reward")
        if reward is None or not math.isfinite(float(reward)) or not 0.0 <= float(reward) <= 1.0:
            invalid_rewards += 1
        if extract_structured_answer_object(str(row.get("response") or "")) is None:
            parse_failures += 1
        try:
            trajectories = json.loads(str(row.get("trajectories") or ""))
            if not isinstance(trajectories, list) or not trajectories:
                raise ValueError("empty trajectories")
            agents = [
                str(item.get("agent") or "").strip().lower()
                for item in trajectories
                if isinstance(item, dict)
            ]
            if any(agent == "mad_engine" for agent in agents):
                mad_rollout_rows += 1
        except Exception:
            trajectory_failures += 1

    expected_ids = dataset_check["expected_sample_ids"]
    if set(by_sample) != set(expected_ids):
        failures.append("judged sample IDs do not exactly match the dataset JSONL")
    wrong_group_sizes = {
        sample_id: len(sample_rows)
        for sample_id, sample_rows in by_sample.items()
        if len(sample_rows) != grpo_n
    }
    if wrong_group_sizes:
        failures.append(f"{len(wrong_group_sizes)} sample groups do not contain grpo_n={grpo_n} rows")
    if parse_failures:
        failures.append(f"{parse_failures} rollout responses have no parseable answer object")
    if trajectory_failures:
        failures.append(f"{trajectory_failures} rollout rows have invalid trajectories")
    if mad_rollout_rows:
        failures.append(f"{mad_rollout_rows} rollout rows used mad_engine")
    if invalid_rewards:
        failures.append(f"{invalid_rewards} rollout rows have invalid rewards")

    per_task: dict[str, Any] = {}
    for task_type in TASK_TYPES:
        task_rows = by_task.get(task_type, [])
        task_groups: dict[str, list[float]] = defaultdict(list)
        for row in task_rows:
            task_groups[_sample_id(row)].append(float(row["reward"]))
        states = Counter(_group_state(rewards) for rewards in task_groups.values())
        per_task[task_type] = {
            "questions": len(task_groups),
            "rollouts": len(task_rows),
            "avg_reward": (
                sum(float(row["reward"]) for row in task_rows) / len(task_rows) if task_rows else None
            ),
            "groups": dict(states),
        }
        if len(task_groups) != expected_per_task:
            failures.append(f"task {task_type} has {len(task_groups)} questions != {expected_per_task}")
        if len(task_rows) != expected_per_task * grpo_n:
            failures.append(
                f"task {task_type} has {len(task_rows)} rollouts != {expected_per_task * grpo_n}"
            )

    experiences = _experience_summary(agent_config)
    if not experiences["exists"]:
        failures.append("generated agent YAML does not exist")
    elif experiences["n_experiences"] <= 0:
        failures.append("generated agent YAML contains no usable experience cards")
    if experiences["tasks_covered"] < min_experience_task_coverage:
        failures.append(
            "generated experience task coverage "
            f"{experiences['tasks_covered']} < {min_experience_task_coverage}"
        )

    if not log_file.is_file():
        provider_errors = ["log file missing"]
        failures.append("run log does not exist")
    else:
        provider_errors = _scan_provider_errors(log_file)
        if provider_errors:
            failures.append(f"provider error markers found in log: {provider_errors}")

    protected = _compare_protected_snapshot(protected_snapshot)
    if protected["changes"]:
        failures.append("one or more protected stable experience packs changed")

    hz_groups = per_task.get("HZOR", {}).get("groups") or {}
    hz_card_count = experiences["counts_by_task"].get("HZOR", 0)
    hz_status = {
        "questions": per_task.get("HZOR", {}).get("questions", 0),
        "rollouts": per_task.get("HZOR", {}).get("rollouts", 0),
        "groups": hz_groups,
        "experience_cards": hz_card_count,
        "note": (
            "No HZOR card is expected when every HZOR group is all-correct or all-wrong; "
            "ExperienceUpdater only distills groups with average reward strictly between 0 and 1."
            if hz_card_count == 0
            else "HZOR generated at least one task-tagged experience card."
        ),
    }

    return {
        "schema_version": "material_performance_19_run_audit_v1",
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "run": {
            "exp_id": exp_id,
            "dataset_name": dataset_name,
            "expected_questions": expected_questions,
            "expected_rollouts": expected_rows,
            "judged_rollouts": len(rows),
            "grpo_n": grpo_n,
            "parse_failures": parse_failures,
            "trajectory_failures": trajectory_failures,
            "mad_rollout_rows": mad_rollout_rows,
            "invalid_rewards": invalid_rewards,
            "provider_error_markers": provider_errors,
        },
        "per_task": per_task,
        "experiences": experiences,
        "hzor": hz_status,
        "protected_packs": protected,
    }


def _write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("dataset-status")
    status_parser.add_argument("--db", type=Path, required=True)
    status_parser.add_argument("--dataset-name", required=True)
    status_parser.add_argument("--dataset-jsonl", type=Path, required=True)

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--file", action="append", type=Path, required=True)
    snapshot_parser.add_argument("--output", type=Path, required=True)

    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--db", type=Path, required=True)
    preflight_parser.add_argument("--dataset-name", required=True)
    preflight_parser.add_argument("--dataset-jsonl", type=Path, required=True)
    preflight_parser.add_argument("--expected-questions", type=int, required=True)
    preflight_parser.add_argument("--expected-per-task", type=int, required=True)
    preflight_parser.add_argument("--chroma-dir", type=Path, required=True)
    preflight_parser.add_argument("--chroma-collection", required=True)
    preflight_parser.add_argument("--output", type=Path, required=True)

    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--db", type=Path, required=True)
    audit_parser.add_argument("--dataset-name", required=True)
    audit_parser.add_argument("--dataset-jsonl", type=Path, required=True)
    audit_parser.add_argument("--exp-id", required=True)
    audit_parser.add_argument("--agent-config", type=Path, required=True)
    audit_parser.add_argument("--log-file", type=Path, required=True)
    audit_parser.add_argument("--protected-snapshot", type=Path, required=True)
    audit_parser.add_argument("--expected-questions", type=int, required=True)
    audit_parser.add_argument("--grpo-n", type=int, required=True)
    audit_parser.add_argument("--expected-per-task", type=int, required=True)
    audit_parser.add_argument("--min-experience-task-coverage", type=int, default=0)
    audit_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "dataset-status":
        report = dataset_status(
            db_path=args.db,
            dataset_name=args.dataset_name,
            dataset_jsonl=args.dataset_jsonl,
        )
        print(report["status"])
        return
    if args.command == "snapshot":
        report = snapshot_protected_files(files=args.file, output=args.output)
        print(f"protected_snapshot={args.output.resolve()}")
        print(f"protected_files={len(report['files'])}")
        return
    if args.command == "preflight":
        report = preflight(
            db_path=args.db,
            dataset_name=args.dataset_name,
            dataset_jsonl=args.dataset_jsonl,
            expected_questions=args.expected_questions,
            expected_per_task=args.expected_per_task,
            chroma_dir=args.chroma_dir,
            chroma_collection=args.chroma_collection,
        )
        _write_report(report, args.output)
        print(f"preflight_status={report['status']}")
        print(f"preflight_report={args.output.resolve()}")
        if report["failures"]:
            raise SystemExit(1)
        return

    report = audit_run(
        db_path=args.db,
        dataset_name=args.dataset_name,
        dataset_jsonl=args.dataset_jsonl,
        exp_id=args.exp_id,
        agent_config=args.agent_config,
        log_file=args.log_file,
        protected_snapshot=args.protected_snapshot,
        expected_questions=args.expected_questions,
        grpo_n=args.grpo_n,
        expected_per_task=args.expected_per_task,
        min_experience_task_coverage=args.min_experience_task_coverage,
    )
    _write_report(report, args.output)
    print(f"audit_status={report['status']}")
    print(f"judged_rollouts={report['run']['judged_rollouts']}")
    print(
        f"experience_cards={report['experiences']['n_experiences']} "
        f"experience_tasks={report['experiences']['tasks_covered']}/{len(TASK_TYPES)}"
    )
    print(
        f"hzor_groups={json.dumps(report['hzor']['groups'], sort_keys=True)} "
        f"hzor_cards={report['hzor']['experience_cards']}"
    )
    print(f"audit_report={args.output.resolve()}")
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
