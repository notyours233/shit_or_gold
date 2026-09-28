import unittest


class ProposeStrictJsonSchemaTests(unittest.TestCase):
    def test_coerce_proposal_uses_authoritative_material_and_numeric_metrics(self):
        from debate.langgraph_coordinator import _coerce_proposal_output, _render_proposal_claim
        from prompts.debate_phase_prompts import build_initial_debate_prompt
        from utils.material_input import MaterialInput

        prompt = build_initial_debate_prompt(
            None,
            task_type="OER",
            material_input=MaterialInput(material_name="NiFeOOH", elements=["Ni", "Fe", "O", "H"]),
        )
        parsed = {
            "task_type": "HER",
            "material_name": "wrong material",
            "material_description": "wrong description",
            "predicted_metrics": {"eta10": 310},
            "units": {"eta10": "mV"},
            "products": "CO",
            "confidence": "medium",
            "evidence": [{"source_id": "llm"}],
            "rationale": "Parametric estimate.",
        }

        out, schema_ok = _coerce_proposal_output(
            parsed=parsed,
            prompt=prompt,
            components=["Ni", "Fe", "O", "H"],
            reaction_type="OER",
            trajectory=None,
        )

        self.assertTrue(schema_ok)
        self.assertEqual(out.task_type, "OER")
        self.assertEqual(out.material_name, "NiFeOOH")
        self.assertEqual(out.predicted_metrics, {"eta10": 310.0})
        self.assertEqual(out.products, "N/A")
        claim = _render_proposal_claim(out)
        self.assertIn("Task Type: OER", claim)
        self.assertIn("Material Name: NiFeOOH", claim)
        self.assertIn("Performance Metrics: eta10=310.0 mV (Confidence: medium)", claim)

    def test_missing_required_metric_is_schema_failure(self):
        from debate.langgraph_coordinator import _coerce_proposal_output
        from prompts.debate_phase_prompts import build_initial_debate_prompt
        from utils.material_input import MaterialInput

        prompt = build_initial_debate_prompt(
            None,
            task_type="thermoelectric",
            material_input=MaterialInput(material_name="Bi2Te3"),
        )
        out, schema_ok = _coerce_proposal_output(
            parsed={
                "task_type": "thermoelectric",
                "material_name": "Bi2Te3",
                "predicted_metrics": {},
                "units": {},
            },
            prompt=prompt,
            components=["Bi", "Te"],
            reaction_type="thermoelectric",
            trajectory=None,
        )

        self.assertFalse(schema_ok)
        self.assertEqual(out.task_type, "thermoelectric")
        self.assertEqual(out.performance_metrics, "")
        self.assertIn("figure_of_merit", out.rationale)


if __name__ == "__main__":
    unittest.main()
