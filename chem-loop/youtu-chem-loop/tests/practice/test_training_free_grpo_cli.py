from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from utu.practice import utils


def _dummy_config() -> SimpleNamespace:
    return SimpleNamespace(
        exp_id="default",
        practice=SimpleNamespace(
            epochs=1,
            batch_size=1,
            grpo_n=1,
            rollout_concurrency=1,
            task_timeout=1800,
            rollout_data_truncate=1,
            eval_strategy="epoch",
            eval_steps=1,
            eval_data_truncate=None,
            restart_step=None,
            seed_experience_yaml=None,
            agent_objective=None,
            learning_objective=None,
            num_experiences_per_query=1,
        ),
        data=SimpleNamespace(practice_dataset_name="dataset"),
        evaluation=SimpleNamespace(
            exp_id="default",
            agent=SimpleNamespace(),
            verify_filename=None,
            verify_func_name=None,
            pass_k=1,
        ),
    )


def test_cli_can_override_positive_task_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _dummy_config()
    monkeypatch.setattr(utils.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_training_free_GRPO.py", "--config_name", "chem_performance_single", "--task_timeout", "300"],
    )

    parsed = utils.parse_training_free_grpo_config()

    assert parsed.practice.task_timeout == 300


def test_cli_rejects_nonpositive_task_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _dummy_config()
    monkeypatch.setattr(utils.ConfigLoader, "load_training_free_grpo_config", lambda _name: config)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_training_free_GRPO.py", "--config_name", "chem_performance_single", "--task_timeout", "0"],
    )

    with pytest.raises(SystemExit):
        utils.parse_training_free_grpo_config()
