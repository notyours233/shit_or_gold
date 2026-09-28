import unittest


class DebatePhasePromptContentTests(unittest.TestCase):
    def test_material_context_has_no_fixed_synthesis_assumptions(self):
        from prompts.debate_phase_prompts import build_initial_debate_prompt
        from utils.material_input import MaterialInput

        prompt = build_initial_debate_prompt(
            None,
            task_type="conductivity",
            material_input=MaterialInput(material_name="CuO", elements=["Cu", "O"]),
        )
        self.assertIn("Material name: CuO", prompt)
        self.assertIn("含有元素：Cu、O", prompt)
        self.assertNotIn("SWCNT", prompt)
        self.assertNotIn("900 C", prompt)
        self.assertNotIn("100 C", prompt)

    def test_unified_prompts_enforce_material_name_contract(self):
        from prompts.system_prompts import UNIFIED_DOMAIN_PROMPT, UNIFIED_SYSTEM_PROMPT

        for prompt in (UNIFIED_DOMAIN_PROMPT, UNIFIED_SYSTEM_PROMPT):
            self.assertIn("material_name", prompt)
            self.assertIn("Never invent", prompt)
            self.assertIn("Do not assume SWCNT", prompt)

    def test_propose_prompt_preserves_debate_protocol_and_new_schema(self):
        from prompts import debate_phase_prompts as dp

        prompt = dp.DEBATE_PROPOSE_SYSTEM_PROMPT
        self.assertIn("at most 5 ReAct steps", prompt)
        self.assertIn("FIRST ACTION: emit >=3 retrieval tool_calls", prompt)
        self.assertIn("One call MUST be `search_experience`", prompt)
        self.assertIn("Retrieval budget: at most TWO ACTION steps", prompt)
        self.assertIn("STRICT JSON ONLY", prompt)
        self.assertIn('"task_type"', prompt)
        self.assertIn('"material_name"', prompt)
        self.assertIn('"material_description"', prompt)
        self.assertIn('"predicted_metrics"', prompt)
        self.assertIn('"units"', prompt)
        self.assertIn("Mismatch:", prompt)
        self.assertIn("Mechanism:", prompt)
        self.assertIn("Adjustment:", prompt)

    def test_review_and_rebuttal_step_budgets_remain_unchanged(self):
        from prompts import debate_phase_prompts as dp

        self.assertIn("at most 3 ReAct steps", dp.DEBATE_REVIEW_SYSTEM_PROMPT)
        self.assertIn("target_step_number", dp.DEBATE_REVIEW_SYSTEM_PROMPT)
        self.assertIn("at most 4 ReAct steps", dp.DEBATE_REBUTTAL_SYSTEM_PROMPT)
        self.assertIn("defend | revise | withdraw | no_response", dp.DEBATE_REBUTTAL_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
