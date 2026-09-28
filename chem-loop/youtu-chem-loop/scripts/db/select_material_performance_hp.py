#!/usr/bin/env python3
"""Select a GRPO hyperparameter from complete held-out candidate reports."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from typing import Any


def _number(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _candidate(report_path: Path, parameter: str) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    heldout = report.get("heldout") or {}
    experiences = report.get("experiences") or {}
    training = report.get("training") or {}
    hyperparameters = report.get("hyperparameters") or {}
    value = hyperparameters.get(parameter)
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{report_path}: missing positive integer hyperparameter {parameter!r}")
    if int(heldout.get("tasks_present") or 0) != 19:
        raise ValueError(f"{report_path}: held-out report does not cover all 19 tasks")

    rollout_calls = int(training.get("n_judged") or 0)
    updater_calls = int(training.get("estimated_experience_update_llm_calls") or 0)
    candidate = {
        "path": str(report_path.resolve()),
        "value": value,
        "heldout_macro_reward": _number(heldout.get("macro_task_reward"), default=-1.0),
        "heldout_min_task_reward": _number(heldout.get("min_task_reward"), default=-1.0),
        "heldout_contract_failure_rate": _number(
            heldout.get("output_contract_failure_rate"), default=1.0
        ),
        "experience_tasks_covered": int(experiences.get("tasks_covered") or 0),
        "experience_cards": int(experiences.get("n_experiences") or 0),
        "estimated_training_llm_calls": rollout_calls + updater_calls,
    }
    candidate["selection_key"] = (
        candidate["heldout_macro_reward"],
        candidate["experience_tasks_covered"],
        candidate["heldout_min_task_reward"],
        -candidate["heldout_contract_failure_rate"],
        -candidate["estimated_training_llm_calls"],
        -candidate["value"],
    )
    return candidate


def select_best(report_paths: list[Path], parameter: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if parameter not in {"batch_size", "grpo_n"}:
        raise ValueError(f"unsupported parameter: {parameter}")
    candidates = [_candidate(path, parameter) for path in sorted(set(report_paths))]
    if not candidates:
        raise ValueError("no candidate reports found")
    best = max(candidates, key=lambda item: item["selection_key"])
    return best, candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", default=[])
    parser.add_argument("--report-glob", action="append", default=[])
    parser.add_argument("--parameter", choices=["batch_size", "grpo_n"], required=True)
    parser.add_argument("--value-only", action="store_true")
    args = parser.parse_args()

    report_paths = list(args.report)
    for pattern in args.report_glob:
        report_paths.extend(Path(path) for path in glob.glob(pattern))
    best, candidates = select_best(report_paths, args.parameter)

    if args.value_only:
        print(best["value"])
        return
    for candidate in sorted(candidates, key=lambda item: item["value"]):
        print(
            f"candidate {args.parameter}={candidate['value']} "
            f"heldout_macro_reward={candidate['heldout_macro_reward']:.6f} "
            f"experience_tasks={candidate['experience_tasks_covered']}/19 "
            f"heldout_min_task_reward={candidate['heldout_min_task_reward']:.6f} "
            f"contract_failure_rate={candidate['heldout_contract_failure_rate']:.6f} "
            f"estimated_training_llm_calls={candidate['estimated_training_llm_calls']}"
        )
    print(f"best_{args.parameter}={best['value']}")
    print(f"best_report={best['path']}")


if __name__ == "__main__":
    main()
