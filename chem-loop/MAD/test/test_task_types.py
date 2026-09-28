import unittest


class TaskTypesTests(unittest.TestCase):
    def test_unified_task_vocabulary_contains_reactions_and_material_properties(self):
        from utils.task_types import (
            TASK_FAMILY_MATERIAL,
            TASK_FAMILY_REACTION,
            UNIFIED_TASK_TYPES,
            canonical_task_type,
            task_metric_specs,
            task_family,
        )

        self.assertIn("HER", UNIFIED_TASK_TYPES)
        self.assertIn("conductivity", UNIFIED_TASK_TYPES)
        self.assertEqual(len(UNIFIED_TASK_TYPES), 19)
        self.assertIn("photocatalytic_h2o2", UNIFIED_TASK_TYPES)
        self.assertIn("antibacterial", UNIFIED_TASK_TYPES)
        self.assertIn("thermoelectric", UNIFIED_TASK_TYPES)
        self.assertIn("furfural_hydrogenation", UNIFIED_TASK_TYPES)
        self.assertEqual(canonical_task_type("oxygen evolution reaction"), "OER")
        self.assertEqual(canonical_task_type("electrical conductivity"), "conductivity")
        self.assertEqual(task_family("OER"), TASK_FAMILY_REACTION)
        self.assertEqual(task_family("conductivity"), TASK_FAMILY_MATERIAL)
        antibacterial_metrics = task_metric_specs("antibacterial")
        self.assertEqual(
            [item["metric_key"] for item in antibacterial_metrics],
            ["minimum_concentration", "bactericidal_threshold"],
        )


if __name__ == "__main__":
    unittest.main()
