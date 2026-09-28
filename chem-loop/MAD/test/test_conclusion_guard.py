import unittest


class ConclusionGuardTests(unittest.TestCase):
    def test_all_required_elements_with_extra_element_is_allowed(self):
        from agents.react_agent import _validate_conclusion_against_task_with_evidence

        required = ["Ni", "Fe", "Co"]
        conclusion = (
            "Reaction Type: ORR\n"
            "Catalyst metal elements (exactly as provided): Ni, Fe, Co\n"
            "Benchmark: Pt/C (commercial) is often used for comparison.\n"
        )

        ok, reason = _validate_conclusion_against_task_with_evidence(conclusion, required, trajectory=None)
        self.assertTrue(ok)
        # Extra elements should be warning-only (or empty), not a blocker.
        self.assertTrue((reason or "").strip() == "" or "warning:" in (reason or "").lower())

    def test_missing_required_element_blocks(self):
        from agents.react_agent import _validate_conclusion_against_task

        required = ["Ni", "Fe", "Co"]
        conclusion = "Reaction Type: ORR\nCatalyst metal elements: Ni, Fe\n"

        ok, reason = _validate_conclusion_against_task(conclusion, required)
        self.assertFalse(ok)
        self.assertIn("missing required", (reason or "").lower())

    def test_percentage_tokens_are_counted_as_mentions(self):
        from agents.react_agent import _validate_conclusion_against_task

        required = ["Ni", "Co", "Fe", "Cu", "Zn"]
        conclusion = (
            "Electrode composition (exactly as provided): "
            "Ni(69.00%), Co(19.07%), Fe(11.48%), Cu(0.40%), Zn(0.05%)\n"
        )

        ok, reason = _validate_conclusion_against_task(conclusion, required)
        self.assertTrue(ok)
        self.assertEqual("", (reason or "").strip())

    def test_co2rr_products_must_be_single_clean_label(self):
        from agents.react_agent import _validate_conclusion_against_task_with_evidence

        required = ["Ni", "Fe", "Cu"]
        conclusion = (
            "Reaction Type: CO2RR\n"
            "Catalyst metal elements (exactly as provided): Ni, Fe, Cu\n"
            "Products: H2 (overall dominant); CO (top CO2RR carbon product, minor)\n"
            "Performance Metrics: CO FE 3% and CO partial current density 0.6 mA/cm^2 (Confidence: low)\n"
            "Evidence: llm\n"
        )

        ok, reason = _validate_conclusion_against_task_with_evidence(conclusion, required, trajectory=None)
        self.assertFalse(ok)
        self.assertIn("Products must be exactly one CO2RR product label only", reason)


if __name__ == "__main__":
    unittest.main()

