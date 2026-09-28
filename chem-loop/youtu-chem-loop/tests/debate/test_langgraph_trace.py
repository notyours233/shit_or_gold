import json

from utu.debate.langgraph_trace import load_langgraph_debate


def test_load_langgraph_debate_supports_mad_schema(tmp_path):
    # MAD emits {experiment_id, timestamp, result.debate_history...}
    payload = {
        "experiment_id": "exp_20260210_deadbeef",
        "timestamp": "20260210_123456",
        "engine": "langgraph",
        "components": ["Ni", "Co", "Fe", "Cu", "Zn"],
        "electrode_composition": "Ni(69.00%), Co(19.07%), Fe(11.48%), Cu(0.40%), Zn(0.05%)",
        "result": {
            "debate_history": [
                {
                    "type": "propose",
                    "proposal_id": "agent1",
                    "agent_name": "agent1",
                    "claim": "Reaction Type: OER\nPerformance Metrics: 270 mV overpotential at 10 mA/cm^2",
                    "trajectory": {
                        "query": "Target reaction: OER\nComponents: Ni, Co, Fe, Cu, Zn",
                        "steps": [],
                        "final_answer": '{"overpotential_10mAcm-2": 270}',
                    },
                },
                {
                    "type": "review",
                    "round": 1,
                    "from_proposal_id": "agent2",
                    "target_proposal_id": "agent1",
                    "flaw_type": "wrong_inference",
                    "critique": "No evidence for exact composition; needs conservative estimate.",
                    "evidence": [],
                    "valid": True,
                },
            ],
            "surviving_proposals": [{"proposal_id": "agent1", "claim": "Reaction Type: OER ..."}],
            "defeated_proposals": [],
            "withdrawn_proposals": [],
        },
    }

    p = tmp_path / "result_20260210_123456.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    d = load_langgraph_debate(p)
    assert d.debate_id == "exp_20260210_deadbeef"
    assert d.run_id == "20260210_123456"
    assert d.engine == "langgraph"
    assert d.reaction_type == "OER"
    assert d.components == ["Ni", "Co", "Fe", "Cu", "Zn"]

    assert len(d.proposals) == 1
    assert d.proposals[0].proposal_id == "agent1"
    assert d.proposals[0].status == "surviving"

    assert len(d.critiques) == 1
    assert d.critiques[0].target_proposal_id == "agent1"
    assert d.critiques[0].valid is True
