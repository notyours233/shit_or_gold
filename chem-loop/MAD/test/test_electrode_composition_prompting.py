import json
import unittest


class MaterialInputPromptingTests(unittest.TestCase):
    def test_name_only_input_omits_missing_optional_fields(self):
        from prompts.debate_phase_prompts import build_initial_debate_prompt
        from utils.material_input import MaterialInput

        prompt = build_initial_debate_prompt(None, task_type="OER", material_input=MaterialInput(material_name="CuO"))

        self.assertIn("Material name: CuO", prompt)
        self.assertIn("材料是CuO。", prompt)
        self.assertNotIn("unspecified", prompt.lower())
        self.assertNotIn("SWCNT", prompt)
        payload = json.loads(prompt.split("INPUT_JSON:\n", 1)[1])
        self.assertEqual(payload["material_name"], "CuO")
        self.assertEqual(payload["task_type"], "OER")
        self.assertNotIn("precursors", payload)

    def test_structured_and_custom_descriptions_are_both_preserved(self):
        from prompts.debate_phase_prompts import build_initial_debate_prompt
        from utils.material_input import MaterialInput

        material = MaterialInput(
            material_name="MoS2负载CuO纳米颗粒",
            precursors=["MoS2", "Cu(NO3)2"],
            feed_ratio="1:2",
            preparation_method="水热法",
            elements=["Mo", "S", "Cu", "O"],
            element_content="Mo 20%、S 30%、Cu 25%、O 25%",
            custom_prompt="CuO颗粒平均粒径约8 nm。",
        )
        prompt = build_initial_debate_prompt(None, task_type="photocatalytic_h2o2", material_input=material)

        self.assertIn("MoS2、Cu(NO3)2", prompt)
        self.assertIn("CuO颗粒平均粒径约8 nm。", prompt)
        self.assertIn("material data only", prompt)
        self.assertIn('"task_type": "photocatalytic_h2o2"', prompt)


if __name__ == "__main__":
    unittest.main()
