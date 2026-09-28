from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.db.select_material_performance_hp import select_best


def _write_report(
    path: Path,
    *,
    batch_size: int,
    reward: float,
    coverage: int,
    min_reward: float = 0.1,
    failures: float = 0.0,
) -> None:
    payload = {
        "hyperparameters": {"batch_size": batch_size, "grpo_n": 3},
        "training": {"n_judged": 171, "estimated_experience_update_llm_calls": 100},
        "experiences": {"tasks_covered": coverage, "n_experiences": 40},
        "heldout": {
            "tasks_present": 19,
            "macro_task_reward": reward,
            "min_task_reward": min_reward,
            "output_contract_failure_rate": failures,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_selection_uses_heldout_reward_before_experience_coverage(tmp_path: Path) -> None:
    lower_reward = tmp_path / "lower.json"
    higher_reward = tmp_path / "higher.json"
    _write_report(lower_reward, batch_size=19, reward=0.50, coverage=19)
    _write_report(higher_reward, batch_size=38, reward=0.51, coverage=17)

    best, _ = select_best([lower_reward, higher_reward], "batch_size")

    assert best["value"] == 38


def test_selection_breaks_reward_tie_with_coverage_then_smaller_value(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    third = tmp_path / "third.json"
    _write_report(first, batch_size=19, reward=0.5, coverage=18)
    _write_report(second, batch_size=38, reward=0.5, coverage=19)
    _write_report(third, batch_size=57, reward=0.5, coverage=19)

    best, _ = select_best([first, second, third], "batch_size")

    assert best["value"] == 38


def test_selection_rejects_incomplete_heldout_task_coverage(tmp_path: Path) -> None:
    report = tmp_path / "incomplete.json"
    _write_report(report, batch_size=19, reward=0.5, coverage=19)
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["heldout"]["tasks_present"] = 18
    report.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not cover all 19"):
        select_best([report], "batch_size")
