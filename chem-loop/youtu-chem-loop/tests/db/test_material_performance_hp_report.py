from __future__ import annotations

from pathlib import Path

from scripts.db.report_material_performance_hp import (
    _experience_summary,
    _is_output_contract_failure,
    _reward_summary,
    _training_group_summary,
)


def _row(*, index: int, task: str, reward: float, reasoning: str | None = None) -> dict:
    return {
        "dataset_index": index,
        "reward": reward,
        "reasoning": reasoning,
        "meta": {"task_type": task},
        "trajectories": None,
        "time_cost": 1.0,
    }


def test_training_group_summary_classifies_experience_eligibility() -> None:
    rows = [
        _row(index=0, task="HER", reward=1.0),
        _row(index=0, task="HER", reward=1.0),
        _row(index=1, task="EOR", reward=0.0),
        _row(index=1, task="EOR", reward=0.0),
        _row(index=2, task="OER", reward=0.0, reasoning="Failed to parse predicted answer object"),
        _row(index=2, task="OER", reward=0.7),
    ]

    summary = _training_group_summary(rows)

    assert summary["n_questions"] == 3
    assert summary["groups"] == {"all_correct": 1, "all_wrong": 1, "partial_reward": 1}
    assert summary["partial_group_rate"] == 1 / 3
    assert summary["estimated_experience_update_llm_calls"] == 4
    assert summary["output_contract_failures"] == 1
    assert summary["per_task_groups"]["OER"]["partial_reward"] == 1


def test_reward_summary_reports_macro_and_missing_task_coverage() -> None:
    rows = [
        _row(index=0, task="HER", reward=1.0),
        _row(index=1, task="HER", reward=0.0),
        _row(index=2, task="OER", reward=0.75),
    ]

    summary = _reward_summary(rows)

    assert summary["avg_reward"] == 0.5833333333333334
    assert summary["macro_task_reward"] == 0.625
    assert summary["min_task_reward"] == 0.5
    assert summary["tasks_present"] == 2
    assert summary["normalized_error"] == 1 - summary["avg_reward"]


def test_output_contract_failure_does_not_count_numeric_miss() -> None:
    assert _is_output_contract_failure("Extra keys in prediction not allowed")
    assert _is_output_contract_failure("Missing keys: ['metric']")
    assert not _is_output_contract_failure("Wrong product: pred='CO' gt='H2'")
    assert not _is_output_contract_failure(None)


def test_experience_summary_detects_known_pilot_coverage() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    agent = repo_root / "configs" / "agents" / "practice" / "material_performance_19_pilot_s1_n2_20260731_agent.yaml"

    summary = _experience_summary(agent)

    assert summary["n_experiences"] == 17
    assert summary["tasks_covered"] == 17
    assert summary["missing_tasks"] == ["EOR", "antiferromagnetism"]
