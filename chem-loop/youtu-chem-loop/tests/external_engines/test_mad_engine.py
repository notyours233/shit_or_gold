import sys

import pytest

from utu.external_engines.mad_engine import MADEngineAdapter, MADEngineConfig


@pytest.mark.asyncio
async def test_mad_engine_adapter_stitches_think_and_builds_trajectory(tmp_path):
    cfg = MADEngineConfig(
        mad_repo_path=str(tmp_path / "MAD"),  # unused by fake runner, but required by CLI args
        python_bin=sys.executable,
        runner_path="tests/fixtures/fake_mad_runner.py",
        timeout_s=10,
        max_react_steps=2,
        agent_name="mad_test",
    )
    adapter = MADEngineAdapter(cfg)

    res = await adapter.run(question="Task: ...\nINPUT_JSON: {}", meta={"metals": ["Mn"]})

    assert "<think>" in res.final_output
    assert "<answer>" in res.final_output
    assert "overpotential" in res.final_output

    assert isinstance(res.trajectories, list)
    assert len(res.trajectories) == 1

    t0 = res.trajectories[0]
    assert t0["agent"] == "mad_test"
    assert isinstance(t0["trajectory"], list)
    assert t0["trajectory"][0]["role"] == "user"
    assert t0["trajectory"][-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_mad_engine_adapter_wraps_json_dict_when_answer_tag_missing(tmp_path):
    cfg = MADEngineConfig(
        mad_repo_path=str(tmp_path / "MAD"),
        python_bin=sys.executable,
        runner_path="tests/fixtures/fake_mad_runner_no_answer_json.py",
        timeout_s=10,
        max_react_steps=2,
        agent_name="mad_test",
    )
    adapter = MADEngineAdapter(cfg)
    question = (
        "Task: Predict electrochemical catalysis performance metrics.\n\n"
        "INPUT_JSON:\n"
        "{\n"
        "  \"metals\": [\"Mn\"],\n"
        "  \"reaction_type\": \"OER\",\n"
        "  \"metrics_to_predict\": [\"overpotential\"]\n"
        "}\n"
    )
    res = await adapter.run(question=question, meta={"metals": ["Mn"]})
    assert "<answer>" in res.final_output
    assert "\"overpotential\"" in res.final_output


@pytest.mark.asyncio
async def test_mad_engine_adapter_extracts_number_for_single_metric_when_no_json(tmp_path):
    cfg = MADEngineConfig(
        mad_repo_path=str(tmp_path / "MAD"),
        python_bin=sys.executable,
        runner_path="tests/fixtures/fake_mad_runner_no_answer_text.py",
        timeout_s=10,
        max_react_steps=2,
        agent_name="mad_test",
    )
    adapter = MADEngineAdapter(cfg)
    question = (
        "Task: Predict electrochemical catalysis performance metrics.\n\n"
        "INPUT_JSON:\n"
        "{\n"
        "  \"metals\": [\"Ni\", \"Pt\"],\n"
        "  \"reaction_type\": \"HOR\",\n"
        "  \"metrics_to_predict\": [\"exchange_current_density\"]\n"
        "}\n"
    )
    res = await adapter.run(question=question, meta={"metals": ["Ni", "Pt"]})
    assert "<answer>" in res.final_output
    assert "\"exchange_current_density\"" in res.final_output
    assert "0.65" in res.final_output


@pytest.mark.asyncio
async def test_mad_engine_adapter_forwards_masked_doc_ids_to_runner(tmp_path):
    cfg = MADEngineConfig(
        mad_repo_path=str(tmp_path / "MAD"),
        python_bin=sys.executable,
        runner_path="tests/fixtures/fake_mad_runner_require_masked.py",
        timeout_s=10,
        max_react_steps=2,
        agent_name="mad_test",
    )
    adapter = MADEngineAdapter(cfg)

    res = await adapter.run(
        question="Task: ...\nINPUT_JSON: {}",
        meta={"metals": ["Ni"], "reaction_type": "OER", "id": "1", "doc_id": "10.1234/test-doi"},
        masked_doc_ids=["10.1234/test-doi"],
    )
    assert "<answer>" in res.final_output
