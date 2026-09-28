import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from agents import Agent
from agents.models.interface import Model

from utu.config import ConfigLoader
from utu.db import EvaluationSample
from utu.eval.benchmarks import base_benchmark as benchmark_module
from utu.eval.benchmarks.base_benchmark import BaseBenchmark


class _DatasetSpy:
    def __init__(self) -> None:
        self.saved = []

    def save(self, sample) -> None:
        self.saved.append(sample)


def test_single_grpo_config_has_no_mad_engine() -> None:
    config = ConfigLoader.load_training_free_grpo_config("chem_performance_single")

    assert config.evaluation.agent.type == "simple"
    assert config.evaluation.agent.env.name is None
    assert config.evaluation.agent.agent.name == "material_performance_grpo_agent"
    assert list(config.evaluation.agent.toolkits) == ["chem_literature_db"]
    assert "material_name" in config.evaluation.agent.agent.instructions
    assert "task_type" in config.evaluation.agent.agent.instructions
    assert "Do not simulate a debate" in config.evaluation.agent.agent.instructions


def test_material_performance_doc_id_is_injected_without_legacy_id() -> None:
    agent_config = ConfigLoader.load_agent_config("practice/chem_performance_agent_single")
    sample = EvaluationSample(
        dataset="material_performance_19_v1",
        raw_question="Q",
        meta={
            "task_type": "conductivity",
            "sample_id": "mp19_example",
            "doc_id": "10.1234/held-out",
        },
    )

    prepared, masked_doc_ids = BaseBenchmark._prepare_rollout_agent_config(sample, agent_config)

    assert masked_doc_ids == ["10.1234/held-out"]
    assert prepared is not agent_config
    assert prepared.toolkits["chem_literature_db"].config["masked_doc_ids"] == ["10.1234/held-out"]
    assert "masked_doc_ids" not in agent_config.toolkits["chem_literature_db"].config


def test_single_agent_rag_can_be_disabled_without_switching_engines() -> None:
    agent_config = ConfigLoader.load_agent_config("practice/chem_performance_agent_single")
    agent_config.toolkits["chem_literature_db"].config["enabled"] = "false"

    assert BaseBenchmark._build_single_agent_tools(agent_config) == []
    assert agent_config.env.name is None


@pytest.mark.asyncio
async def test_rollout_one_routes_non_mad_config_to_single_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    benchmark = object.__new__(BaseBenchmark)
    benchmark.config = ConfigLoader.load_eval_config("chem/chem_performance_single")
    benchmark.dataset = _DatasetSpy()
    benchmark._run_single_agent = AsyncMock(
        return_value=(
            '<think>estimate</think><answer>{"conductivity": 12.0}</answer>',
            [{"agent": "material_performance_grpo_agent", "trajectory": []}],
        )
    )

    class _ForbiddenMADAdapter:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("MAD adapter must not be constructed for a single-agent GRPO rollout")

    monkeypatch.setattr(benchmark_module, "MADEngineAdapter", _ForbiddenMADAdapter)
    sample = EvaluationSample(
        dataset="material_performance_19_v1",
        raw_question="Q",
        augmented_question="Q augmented",
        meta={"task_type": "conductivity", "sample_id": "mp19_example"},
    )

    result = await benchmark.rollout_one(sample)

    assert result.stage == "rollout"
    assert result.response.endswith('<answer>{"conductivity": 12.0}</answer>')
    assert json.loads(result.trajectories)[0]["agent"] == "material_performance_grpo_agent"
    benchmark._run_single_agent.assert_awaited_once()
    assert benchmark.dataset.saved == [sample]


@pytest.mark.asyncio
async def test_single_agent_runner_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    benchmark = object.__new__(BaseBenchmark)
    agent_config = ConfigLoader.load_agent_config("practice/chem_performance_agent_single")
    agent_config.toolkits = {}
    fake_model = MagicMock(spec=Model)
    fake_result = SimpleNamespace(final_output="<think>x</think><answer>{}</answer>")
    run_mock = AsyncMock(return_value=fake_result)

    monkeypatch.setattr(benchmark_module.AgentsUtils, "get_agents_model", lambda **kwargs: fake_model)
    monkeypatch.setattr(
        benchmark_module.AgentsUtils,
        "get_trajectory_from_agent_result",
        lambda result: {"agent": "material_performance_grpo_agent", "trajectory": []},
    )
    monkeypatch.setattr(benchmark_module.Runner, "run", run_mock)

    response, trajectories = await benchmark._run_single_agent(question="predict", agent_config=agent_config)

    assert response == "<think>x</think><answer>{}</answer>"
    assert trajectories == [{"agent": "material_performance_grpo_agent", "trajectory": []}]
    kwargs = run_mock.await_args.kwargs
    assert isinstance(kwargs["starting_agent"], Agent)
    assert kwargs["starting_agent"].model is fake_model
    assert kwargs["input"] == "predict"
    assert kwargs["max_turns"] == 4
