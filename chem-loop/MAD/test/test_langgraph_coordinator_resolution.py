import unittest


class LangGraphCoordinatorResolutionTests(unittest.TestCase):
    def test_resolve_stalemate_prefers_complete_co2rr_claim_and_parses_inline_fields(self):
        from debate.langgraph_coordinator import LangGraphDebateCoordinator, ProposalState

        coordinator = LangGraphDebateCoordinator(agents=[], config={})
        surviving = [
            ProposalState(
                proposal_id="agent1",
                agent_name="agent1",
                claim=(
                    "Reaction Type: CO2RR; "
                    "Electrode composition: Cu(32.88%), Ag(1.79%), Sn(28.15%), Bi(2.06%), In(35.12%); "
                    "Metal catalyst elements: Cu, Ag, Sn, Bi, In; "
                    "Products: HCOOH (formate, hypothesized). "
                    "Performance Metrics: FE(HCOOH)=60%; j(HCOOH)=10 mA/cm^2 (Confidence: low). "
                    "Evidence: llm"
                ),
            ),
            ProposalState(
                proposal_id="agent2",
                agent_name="agent2",
                claim=(
                    "Reaction Type: CO2RR\n"
                    "Electrode composition (exactly as provided): Cu(32.88%), Ag(1.79%), Sn(28.15%), Bi(2.06%), In(35.12%)\n"
                    "Metal catalyst elements (explicit): Cu, Ag, Sn, Bi, In\n"
                    "Products: HCOOH\n"
                    "Performance Metrics: Faradaic efficiency: 25-40% for HCOOH (Confidence: low)\n"
                    "Evidence: llm"
                ),
            ),
        ]

        winner_id, final_products, final_performance, details = coordinator._resolve_stalemate_score(
            surviving=surviving,
            expected_reaction_type="CO2RR",
            expected_electrode_composition="Cu(32.88%), Ag(1.79%), Sn(28.15%), Bi(2.06%), In(35.12%)",
            expected_elements=["Cu", "Ag", "Sn", "Bi", "In"],
            percent_tolerance=0.05,
            range_strategy="conservative",
        )

        self.assertEqual(winner_id, "agent1")
        self.assertEqual(final_products, "HCOOH")
        self.assertIn("FE(HCOOH)=60%; j(HCOOH)=10 mA/cm^2", final_performance)
        self.assertEqual(details.get("winner_proposal_id"), "agent1")

    def test_resolve_stalemate_prefers_clean_single_co2rr_product_label(self):
        from debate.langgraph_coordinator import LangGraphDebateCoordinator, ProposalState

        coordinator = LangGraphDebateCoordinator(agents=[], config={})
        surviving = [
            ProposalState(
                proposal_id="agent1",
                agent_name="agent1",
                claim=(
                    "Reaction Type: CO2RR\n"
                    "Electrode composition (exactly as provided): Ni(60%), Fe(25%), Cu(15%)\n"
                    "Metal catalyst elements (explicit): Ni, Fe, Cu\n"
                    "Products: H2 (overall dominant); CO (top CO2RR carbon product, minor)\n"
                    "Performance Metrics: CO FE 3% and CO partial current density 0.6 mA/cm^2 (Confidence: low)\n"
                    "Evidence: llm\n"
                ),
            ),
            ProposalState(
                proposal_id="agent2",
                agent_name="agent2",
                claim=(
                    "Reaction Type: CO2RR\n"
                    "Electrode composition (exactly as provided): Ni(60%), Fe(25%), Cu(15%)\n"
                    "Metal catalyst elements (explicit): Ni, Fe, Cu\n"
                    "Products: CO\n"
                    "Performance Metrics: FE(CO)=3%; j(CO)=0.6 mA/cm^2 (Confidence: low)\n"
                    "Evidence: llm\n"
                ),
            ),
        ]

        winner_id, final_products, final_performance, details = coordinator._resolve_stalemate_score(
            surviving=surviving,
            expected_reaction_type="CO2RR",
            expected_electrode_composition="Ni(60%), Fe(25%), Cu(15%)",
            expected_elements=["Ni", "Fe", "Cu"],
            percent_tolerance=0.05,
            range_strategy="conservative",
        )

        self.assertEqual(winner_id, "agent2")
        self.assertEqual(final_products, "CO")
        self.assertIn("FE(CO)=3%; j(CO)=0.6 mA/cm^2", final_performance)
        self.assertEqual(details.get("winner_proposal_id"), "agent2")


if __name__ == "__main__":
    unittest.main()
