import pytest

from utu.config import ConfigLoader
from utu.practice.training_free_grpo import TrainingFreeGRPO


def test_training_free_grpo_accepts_single_agent_config() -> None:
    config = ConfigLoader.load_training_free_grpo_config("chem_performance_single")

    grpo = TrainingFreeGRPO(config)

    assert grpo.config.evaluation.agent.env.name is None


def test_training_free_grpo_rejects_mad_rollout_config() -> None:
    config = ConfigLoader.load_training_free_grpo_config("chem_performance_mad")

    with pytest.raises(ValueError, match="requires a single-agent rollout config"):
        TrainingFreeGRPO(config)
