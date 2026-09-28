from __future__ import annotations

import unittest


class LangGraphSampleContextPromptTests(unittest.TestCase):
    def _coordinator(self):
        from debate.langgraph_coordinator import LangGraphDebateCoordinator

        return LangGraphDebateCoordinator(agents=[], config={"max_rounds": 1})

    def _proposal(self):
        from agents.react_reasoning import ReActStep, ReActTrajectory
        from debate.langgraph_coordinator import DebateReview, ProposalState

        traj = ReActTrajectory(query="dummy")
        traj.add_step(
            ReActStep(
                step_number=1,
                thought="estimate conductivity",
                action="conclude",
                action_input={},
                observation="obs",
            )
        )
        proposal = ProposalState(
            proposal_id="agent1",
            agent_name="A",
            claim=(
                "Task Type: conductivity\n"
                "Reaction Type: conductivity\n"
                "Material Name: Ti3C2Tx MXene film\n"
                "Material Description: 材料是Ti3C2Tx MXene film。含有元素：Ti、C。\n"
                "Performance Metrics: 1.0e5 S/m\n"
            ),
            propose_trajectory=traj,
        )
        review = DebateReview(
            review_id="rev_r1_agent2_0",
            round_number=1,
            from_proposal_id="agent2",
            target_proposal_id="agent1",
            target_step_number=1,
            flaw_type="wrong_inference",
            critique="The sample context must be considered.",
            evidence=[{"source_id": "llm"}],
            valid=True,
        )
        return proposal, review

    def assert_has_sample_context(self, prompt: str):
        self.assertIn("Material Name", prompt)
        self.assertIn("Ti3C2Tx MXene film", prompt)
        self.assertIn("材料是Ti3C2Tx MXene film", prompt)
        self.assertIn("Do not invent missing synthesis", prompt)
        self.assertNotIn("SWCNT-COOH", prompt)
        self.assertNotIn("100 C", prompt)
        self.assertNotIn("900 C", prompt)

    def test_review_prompt_preserves_authoritative_material_context(self):
        coord = self._coordinator()
        proposal, _review = self._proposal()
        prompt = coord._build_review_prompt(
            round_number=1,
            reviewer_id="agent2",
            proposals={"agent1": proposal},
            target_ids=["agent1"],
            reaction_type="conductivity",
        )

        self.assert_has_sample_context(prompt)

    def test_rebuttal_prompt_preserves_authoritative_material_context(self):
        coord = self._coordinator()
        proposal, review = self._proposal()
        prompt = coord._build_rebuttal_prompt(
            round_number=1,
            proposal_id="agent1",
            proposal=proposal,
            target_reviews=[review],
            reaction_type="conductivity",
        )

        self.assert_has_sample_context(prompt)


if __name__ == "__main__":
    unittest.main()
