import unittest


class MaterialInputTests(unittest.TestCase):
    def test_material_name_is_required(self):
        from utils.material_input import MaterialInput

        with self.assertRaisesRegex(ValueError, "material_name is required"):
            MaterialInput(material_name="  ")

    def test_empty_optional_fields_are_omitted(self):
        from utils.material_input import MaterialInput

        material = MaterialInput(material_name="CuO", precursors=[], conditions="  ", custom_prompt=None)
        self.assertEqual(material.to_dict(), {"material_name": "CuO"})
        self.assertEqual(material.build_material_description(), "材料是CuO。")

    def test_formula_derived_retrieval_elements_are_not_promoted_to_user_composition(self):
        from agents.react_agent import _infer_task_constraints
        from prompts.debate_phase_prompts import build_initial_debate_prompt
        from utils.material_input import MaterialInput

        material = MaterialInput(material_name="CuO")
        prompt = build_initial_debate_prompt(None, task_type="conductivity", material_input=material)
        components, task_type = _infer_task_constraints(
            prompt + "\nRetrieval filter elements (may be derived from a formula; not experimenter-provided composition): Cu, O",
            fallback_components=material.retrieval_elements(),
            fallback_reaction=None,
        )

        self.assertEqual(material.retrieval_elements(), ["Cu", "O"])
        self.assertNotIn("含有元素", prompt)
        self.assertEqual(components, [])
        self.assertEqual(task_type, "conductivity")

        explicit_material = MaterialInput(material_name="CuO", elements=["Cu", "O"])
        explicit_prompt = build_initial_debate_prompt(
            None,
            task_type="conductivity",
            material_input=explicit_material,
        )
        explicit_components, explicit_task_type = _infer_task_constraints(
            explicit_prompt,
            fallback_components=[],
            fallback_reaction=None,
        )
        self.assertEqual(explicit_components, ["Cu", "O"])
        self.assertEqual(explicit_task_type, "conductivity")

    def test_nonmetal_elements_are_preserved(self):
        from utils.material_input import MaterialInput

        material = MaterialInput(material_name="MoS2/CuO", elements="Mo, S, Cu, O")
        self.assertEqual(material.explicit_elements(), ["Mo", "S", "Cu", "O"])
        self.assertIn("含有元素：Mo, S, Cu, O。", material.build_material_description())


if __name__ == "__main__":
    unittest.main()
