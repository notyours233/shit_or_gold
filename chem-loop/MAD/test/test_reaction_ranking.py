import unittest


class ReactionRankingTests(unittest.TestCase):
    def test_grade_precedence_for_properties(self):
        from utils.reaction_ranking import rank_reactions

        items = [
            {
                "property_type": "conductivity",
                "reaction_type": "conductivity",
                "performance_evaluation": {
                    "property_type": "conductivity",
                    "reaction_type": "conductivity",
                    "grade": "Good",
                    "metric_value": 1.2e5,
                    "metric_unit": "S/m",
                },
            },
            {
                "property_type": "thermal_conductivity",
                "reaction_type": "thermal_conductivity",
                "performance_evaluation": {
                    "property_type": "thermal_conductivity",
                    "reaction_type": "thermal_conductivity",
                    "grade": "Outstanding",
                    "metric_value": 410.0,
                    "metric_unit": "W m-1 K-1",
                },
            },
        ]
        ranking, top = rank_reactions(items, top_k=2)
        self.assertEqual(ranking[0].get("property_type"), "thermal_conductivity")
        self.assertEqual(top[0].get("property_type"), "thermal_conductivity")

    def test_tie_break_all_new_properties_higher_is_better(self):
        from utils.reaction_ranking import rank_reactions

        items = [
            {
                "property_type": "conductivity",
                "performance_evaluation": {"property_type": "conductivity", "grade": "Good", "metric_value": 2.0e5},
            },
            {
                "property_type": "thermal_conductivity",
                "performance_evaluation": {"property_type": "thermal_conductivity", "grade": "Good", "metric_value": 350.0},
            },
        ]
        ranking, _top = rank_reactions(items, top_k=2)
        self.assertEqual(ranking[0].get("property_type"), "conductivity")

    def test_cross_direction_tie_does_not_compare_raw_units(self):
        from utils.reaction_ranking import rank_reactions

        items = [
            {
                "task_type": "conductivity",
                "performance_evaluation": {"grade": "Good", "metric_value": 1.0e8, "metric_unit": "S/m"},
            },
            {
                "task_type": "thermal_conductivity",
                "performance_evaluation": {"grade": "Good", "metric_value": 1.0, "metric_unit": "W m-1 K-1"},
            },
        ]
        ranking, top = rank_reactions(items, top_k=2)
        self.assertEqual([item["task_type"] for item in ranking], ["conductivity", "thermal_conductivity"])
        self.assertEqual([item["normalized_score"] for item in top], [0.75, 0.75])
        self.assertTrue(all(item["ranking_basis"] == "task_specific_grade" for item in top))

    def test_missing_metric_sorts_last_within_grade(self):
        from utils.reaction_ranking import rank_reactions

        items = [
            {
                "property_type": "conductivity",
                "performance_evaluation": {"property_type": "conductivity", "grade": "Good", "metric_value": 240.0},
            },
            {
                "property_type": "ferromagnetism",
                "performance_evaluation": {"property_type": "ferromagnetism", "grade": "Good"},
            },
        ]
        ranking, _top = rank_reactions(items, top_k=2)
        self.assertEqual(ranking[-1].get("property_type"), "ferromagnetism")

    def test_error_only_items_are_not_returned_as_top_candidates(self):
        from utils.reaction_ranking import rank_reactions

        items = [
            {
                "reaction_type": "HER",
                "consensus_reached": False,
                "performance_evaluation": None,
                "metric_value": None,
                "grade": None,
                "error": "all providers failed",
            },
            {
                "property_type": "conductivity",
                "consensus_reached": True,
                "performance_evaluation": {
                    "property_type": "conductivity",
                    "grade": "Good",
                    "metric_value": 2.0e5,
                    "metric_unit": "S/m",
                },
                "error": None,
            },
        ]

        ranking, top = rank_reactions(items, top_k=2)

        self.assertEqual(ranking[0].get("property_type"), "conductivity")
        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].get("property_type"), "conductivity")

    def test_unscored_non_error_items_fill_requested_top_k_after_scored_items(self):
        from utils.reaction_ranking import rank_reactions

        items = [
            {
                "property_type": "conductivity",
                "performance_evaluation": {
                    "property_type": "conductivity",
                    "grade": "Good",
                    "metric_value": 2.0e5,
                    "metric_unit": "S/m",
                },
                "error": None,
            },
            {
                "property_type": "thermal_conductivity",
                "performance_evaluation": None,
                "grade": None,
                "metric_value": None,
                "error": None,
            },
            {
                "property_type": "ferrimagnetism",
                "performance_evaluation": None,
                "grade": None,
                "metric_value": None,
                "error": None,
            },
        ]

        _ranking, top = rank_reactions(items, top_k=3)

        self.assertEqual([it.get("property_type") for it in top], ["conductivity", "thermal_conductivity", "ferrimagnetism"])


if __name__ == "__main__":
    unittest.main()
