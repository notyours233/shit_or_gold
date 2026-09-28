#!/usr/bin/env python3
"""Report GRPO group, experience-card, and held-out metrics for one HP candidate."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml


TASK_TYPES = (
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
)

_OUTPUT_CONTRACT_MARKERS = (
    "failed to parse",
    "<answer> must",
    "invalid keys",
    "extra keys",
    "missing keys",
    "must be a number",
    "must be a non-empty",
    "missing or unscorable",
)


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        obj = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return obj if isinstance(obj, dict) else {}


def _task_type(row: dict[str, Any]) -> str:
    meta = _json_object(row.get("meta"))
    return str(
        meta.get("task_type") or meta.get("property_type") or meta.get("reaction_type") or "UNKNOWN"
    ).strip()


def _is_output_contract_failure(reasoning: Any) -> bool:
    text = str(reasoning or "").strip().lower()
    return bool(text) and any(marker in text for marker in _OUTPUT_CONTRACT_MARKERS)


def _tool_call_count(trajectories: Any) -> int:
    if not isinstance(trajectories, str) or not trajectories.strip():
        return 0
    try:
        payload = json.loads(trajectories)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, list):
        return 0
    count = 0
    for item in payload:
        if not isinstance(item, dict):
            continue
        trajectory = item.get("trajectory")
        if not isinstance(trajectory, list):
            continue
        count += sum(1 for event in trajectory if isinstance(event, dict) and event.get("role") == "tool")
    return count


def _reward_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [row for row in rows if row.get("reward") is not None]
    rewards = [float(row["reward"]) for row in judged]
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in judged:
        by_task[_task_type(row)].append(row)

    per_task: dict[str, dict[str, Any]] = {}
    for task_type in TASK_TYPES:
        task_rows = by_task.get(task_type, [])
        task_rewards = [float(row["reward"]) for row in task_rows]
        per_task[task_type] = {
            "n_rollouts": len(task_rows),
            "avg_reward": (sum(task_rewards) / len(task_rewards)) if task_rewards else None,
            "normalized_error": (1.0 - sum(task_rewards) / len(task_rewards)) if task_rewards else None,
            "output_contract_failures": sum(
                1 for row in task_rows if _is_output_contract_failure(row.get("reasoning"))
            ),
        }

    task_rewards_present = [
        metrics["avg_reward"] for metrics in per_task.values() if metrics["avg_reward"] is not None
    ]
    contract_failures = sum(1 for row in judged if _is_output_contract_failure(row.get("reasoning")))
    return {
        "n_judged": len(judged),
        "avg_reward": (sum(rewards) / len(rewards)) if rewards else None,
        "macro_task_reward": (
            sum(task_rewards_present) / len(task_rewards_present) if task_rewards_present else None
        ),
        "min_task_reward": min(task_rewards_present) if task_rewards_present else None,
        "normalized_error": (1.0 - sum(rewards) / len(rewards)) if rewards else None,
        "tasks_present": len(task_rewards_present),
        "output_contract_failures": contract_failures,
        "output_contract_failure_rate": contract_failures / len(judged) if judged else None,
        "tool_calls": sum(_tool_call_count(row.get("trajectories")) for row in judged),
        "time_cost_seconds": sum(float(row.get("time_cost") or 0.0) for row in judged),
        "per_task": per_task,
    }


def _training_group_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [row for row in rows if row.get("reward") is not None]
    grouped: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in judged:
        grouped[row.get("dataset_index")].append(row)

    group_states = {"all_correct": 0, "all_wrong": 0, "partial_reward": 0}
    partial_rollouts = 0
    per_task_groups: dict[str, dict[str, int]] = {
        task: {"groups": 0, "all_correct": 0, "all_wrong": 0, "partial_reward": 0}
        for task in TASK_TYPES
    }
    for group_rows in grouped.values():
        rewards = [float(row["reward"]) for row in group_rows]
        average = sum(rewards) / len(rewards)
        if all(abs(reward - 1.0) <= 1e-12 for reward in rewards):
            state = "all_correct"
        elif all(abs(reward) <= 1e-12 for reward in rewards):
            state = "all_wrong"
        else:
            state = "partial_reward"
            partial_rollouts += len(group_rows)
        group_states[state] += 1
        task_type = _task_type(group_rows[0])
        if task_type in per_task_groups:
            per_task_groups[task_type]["groups"] += 1
            per_task_groups[task_type][state] += 1

    rewards = _reward_summary(judged)
    rewards.update(
        {
            "n_questions": len(grouped),
            "groups": group_states,
            "partial_group_rate": (
                group_states["partial_reward"] / len(grouped) if grouped else None
            ),
            "estimated_experience_update_llm_calls": partial_rollouts
            + 2 * group_states["partial_reward"],
            "per_task_groups": per_task_groups,
        }
    )
    return rewards


def _experience_summary(agent_config: Path | None) -> dict[str, Any]:
    empty = {
        "agent_config": str(agent_config.resolve()) if agent_config else None,
        "n_experiences": 0,
        "tasks_covered": 0,
        "missing_tasks": list(TASK_TYPES),
        "counts_by_task": {task: 0 for task in TASK_TYPES},
    }
    if agent_config is None:
        return empty
    if not agent_config.is_file():
        raise FileNotFoundError(f"agent config not found: {agent_config}")
    payload = yaml.safe_load(agent_config.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return empty
    agent = payload.get("agent")
    instructions = agent.get("instructions") if isinstance(agent, dict) else None
    if not isinstance(instructions, str):
        return empty

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
        "n_experiences": len(cards),
        "tasks_covered": len(covered),
        "missing_tasks": [task for task in TASK_TYPES if counts[task] == 0],
        "counts_by_task": counts,
    }


def _load_exp_rows(con: sqlite3.Connection, exp_id: str | None) -> list[dict[str, Any]]:
    if not exp_id:
        return []
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT dataset_index, reward, reasoning, meta, trajectories, time_cost "
        "FROM evaluation_data WHERE exp_id=? AND stage='judged' ORDER BY dataset_index, id",
        (exp_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def build_report(
    *,
    db_path: Path,
    heldout_exp_id: str,
    training_exp_id: str | None,
    agent_config: Path | None,
    batch_size: int | None,
    grpo_n: int | None,
    expected_train_questions: int | None,
    expected_heldout_questions: int | None,
) -> dict[str, Any]:
    with sqlite3.connect(str(db_path)) as con:
        training_rows = _load_exp_rows(con, training_exp_id)
        heldout_rows = _load_exp_rows(con, heldout_exp_id)

    training = _training_group_summary(training_rows) if training_exp_id else None
    heldout = _reward_summary(heldout_rows)
    if expected_train_questions is not None and training is not None:
        if training["n_questions"] != expected_train_questions:
            raise ValueError(
                f"training question count mismatch: {training['n_questions']} != {expected_train_questions}"
            )
    if expected_heldout_questions is not None and heldout["n_judged"] != expected_heldout_questions:
        raise ValueError(
            f"held-out question count mismatch: {heldout['n_judged']} != {expected_heldout_questions}"
        )
    return {
        "schema_version": "material_performance_19_hp_report_v1",
        "training_exp_id": training_exp_id,
        "heldout_exp_id": heldout_exp_id,
        "hyperparameters": {"batch_size": batch_size, "grpo_n": grpo_n},
        "training": training,
        "experiences": _experience_summary(agent_config),
        "heldout": heldout,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("test.db"))
    parser.add_argument("--training-exp-id")
    parser.add_argument("--heldout-exp-id", required=True)
    parser.add_argument("--agent-config", type=Path)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--grpo-n", type=int)
    parser.add_argument("--expected-train-questions", type=int)
    parser.add_argument("--expected-heldout-questions", type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(
        db_path=args.db,
        heldout_exp_id=args.heldout_exp_id,
        training_exp_id=args.training_exp_id,
        agent_config=args.agent_config,
        batch_size=args.batch_size,
        grpo_n=args.grpo_n,
        expected_train_questions=args.expected_train_questions,
        expected_heldout_questions=args.expected_heldout_questions,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    heldout = report["heldout"]
    experiences = report["experiences"]
    training = report["training"] or {}
    groups = training.get("groups") or {}
    print(
        "hp_report "
        f"heldout_macro_reward={heldout['macro_task_reward']:.6f} "
        f"heldout_min_task_reward={heldout['min_task_reward']:.6f} "
        f"heldout_contract_failure_rate={heldout['output_contract_failure_rate']:.6f} "
        f"experience_tasks={experiences['tasks_covered']}/{len(TASK_TYPES)} "
        f"experience_cards={experiences['n_experiences']} "
        f"partial_groups={groups.get('partial_reward', 0)} "
        f"all_correct_groups={groups.get('all_correct', 0)} "
        f"all_wrong_groups={groups.get('all_wrong', 0)}"
    )
    print(f"report_path={args.output.resolve()}")


if __name__ == "__main__":
    main()
