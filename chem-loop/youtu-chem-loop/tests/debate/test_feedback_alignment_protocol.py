import json

from scripts.debate import update_experiences_from_feedback_alignment as feedback
from utu.debate import Proposal


class DummyDebate:
    raw = {"result": {}}

    def critiques_by_target(self, valid_only=True):
        return {}


def test_feedback_alignment_rollout_carries_lab_protocol_context(monkeypatch):
    proposal = Proposal(
        proposal_id="agent1",
        agent_name="agent1",
        status="surviving",
        claim="Property Type: conductivity\nPerformance Metrics: 1e5 S/m",
        trajectory={
            "query": "Target property: conductivity\nComponents: Ni, Co",
            "steps": [{"thought": "predict under target composition"}],
            "final_answer": "conductivity=1e5 S/m",
        },
    )

    monkeypatch.setattr(feedback, "load_langgraph_debate", lambda _path: DummyDebate())
    monkeypatch.setattr(feedback, "_select_focus_proposal", lambda _debate: proposal)

    example = {
        "update_job_id": "upd-1",
        "csv_row_index": 1,
        "recommendation_job_id": "rec-1",
        "recommendation_finished_at_utc": "2026-06-16T00:00:00Z",
        "reaction_type": "conductivity",
        "metric_key": "conductivity",
        "unit": "S/m",
        "predicted_value": 100000.0,
        "actual_value": 50000.0,
        "abs_error": 50000.0,
        "rel_error": 1.0,
        "score": 0.0,
        "components": "Ni(70%), Co(30%)",
        "condition": None,
        "actual_product": None,
        "predicted_product": None,
        "actual_faradaic_efficiency": None,
        "predicted_faradaic_efficiency": None,
        "final_performance": "Property Type: conductivity\nPerformance Metrics: 1e5 S/m",
        "trace_path": "/tmp/fake_trace.json",
        "trace_reaction_type": "conductivity",
        "csv_row": {},
    }

    rollout = feedback._make_rollout_from_example(example)

    assert rollout is not None
    assert "LAB_PROTOCOL:" in rollout.raw_question
    assert "SWCNT-COOH_4xMetal_100C_evap_900C_Ar_2h" in rollout.raw_question
    assert "Experimental ground truth from lab feedback" in rollout.correct_answer
    assert "Sample Protocol: SWCNT-COOH_4xMetal_100C_evap_900C_Ar_2h" in rollout.correct_answer
    assert "SOURCE=lab_feedback" in rollout.reasoning
    assert "SAMPLE_FORM=SWCNT-supported metal/oxide nanoparticle composite" in rollout.reasoning
    assert rollout.meta["sample_protocol"] == "SWCNT-COOH_4xMetal_100C_evap_900C_Ar_2h"

    traj = json.loads(rollout.trajectories)[0]
    assert traj["meta"]["sample_protocol"] == "SWCNT-COOH_4xMetal_100C_evap_900C_Ar_2h"
