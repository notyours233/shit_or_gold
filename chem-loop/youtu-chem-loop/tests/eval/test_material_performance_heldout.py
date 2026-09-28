from __future__ import annotations

from pathlib import Path

import pytest

from scripts.eval_material_performance_experience import _agent_config_name, build_eval_config


def test_build_heldout_config_uses_generated_single_agent_contract() -> None:
    config = build_eval_config(
        agent_config="practice/material_performance_19_pilot_s1_n2_20260731_agent",
        dataset="material_performance_19_hp_validation_s3_seed20260803",
        exp_id="heldout_test",
        concurrency=2,
    )

    assert config.exp_id == "heldout_test"
    assert config.data.dataset == "material_performance_19_hp_validation_s3_seed20260803"
    assert config.concurrency == 2
    assert config.pass_k == 1
    assert config.agent.type == "simple"
    assert config.agent.env is None or config.agent.env.name != "mad"
    assert config.verify_filename == "chem_performance_verify.py"


def test_agent_config_path_must_stay_under_agents_directory(tmp_path: Path) -> None:
    outside = tmp_path / "agent.yaml"
    outside.write_text("type: simple\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must be under"):
        _agent_config_name(str(outside))


def test_build_heldout_config_rejects_mad() -> None:
    with pytest.raises(ValueError, match="MAD is not allowed"):
        build_eval_config(
            agent_config="practice/chem_performance_agent_mad",
            dataset="validation",
            exp_id="heldout_test",
            concurrency=1,
        )
