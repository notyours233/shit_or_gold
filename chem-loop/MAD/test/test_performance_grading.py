import unittest


class PerformanceGradingTests(unittest.TestCase):
    def test_antibacterial_minimum_concentration_is_lower_better(self):
        from utils.performance_grading import evaluate_claim

        result = evaluate_claim(
            "Task Type: antibacterial\nPerformance Metrics: minimum_concentration=8 ug/mL (Confidence: medium)",
            reaction_type="antibacterial",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["metric_value"], 8.0)
        self.assertEqual(result["metric_unit"], "ppm")
        self.assertEqual(result["grade"], "Outstanding")

    def test_thermoelectric_zt_thresholds(self):
        from utils.performance_grading import evaluate_claim

        result = evaluate_claim(
            "Task Type: thermoelectric\nPerformance Metrics: figure_of_merit=1.3 (Confidence: medium)",
            reaction_type="thermoelectric",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["metric_value"], 1.3)
        self.assertEqual(result["metric_unit"], "dimensionless")
        self.assertEqual(result["grade"], "Good")

    def test_photocatalytic_h2o2_uses_documented_thresholds(self):
        from utils.performance_grading import evaluate_claim

        result = evaluate_claim(
            "Task Type: photocatalytic_h2o2\nPerformance Metrics: apparent_quantum_efficiency=7.5 % (Confidence: medium)",
            reaction_type="photocatalytic_h2o2",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["grade"], "Fair")
        self.assertTrue(result["grade_calibrated"])

        from utils.performance_grading import grade_value

        self.assertEqual(grade_value("photocatalytic_h2o2", 30), "Outstanding")
        self.assertEqual(grade_value("photocatalytic_h2o2", 10), "Good")
        self.assertEqual(grade_value("photocatalytic_h2o2", 2), "Fair")
        self.assertEqual(grade_value("photocatalytic_h2o2", 0.5), "Poor")
        self.assertEqual(grade_value("photocatalytic_h2o2", 0.49), "Terrible")

    def test_furfural_hydrogenation_uses_documented_thresholds(self):
        from utils.performance_grading import evaluate_claim, grade_value

        result = evaluate_claim(
            "Task Type: furfural_hydrogenation\nPerformance Metrics: furfuryl_alcohol_yield=45 % (Confidence: medium)",
            reaction_type="furfural_hydrogenation",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["grade"], "Terrible")
        self.assertTrue(result["grade_calibrated"])

        self.assertEqual(grade_value("furfural_hydrogenation", 95), "Outstanding")
        self.assertEqual(grade_value("furfural_hydrogenation", 85), "Good")
        self.assertEqual(grade_value("furfural_hydrogenation", 70), "Fair")
        self.assertEqual(grade_value("furfural_hydrogenation", 60), "Poor")
        self.assertEqual(grade_value("furfural_hydrogenation", 59.9), "Terrible")

    def test_material_property_grade_boundaries(self):
        from utils.performance_grading import grade_value

        self.assertEqual(grade_value("photothermal_conversion_efficiency", 90), "Outstanding")
        self.assertEqual(grade_value("photothermal_conversion_efficiency", 70), "Good")
        self.assertEqual(grade_value("photothermal_conversion_efficiency", 50), "Fair")
        self.assertEqual(grade_value("photothermal_conversion_efficiency", 20), "Poor")
        self.assertEqual(grade_value("photothermal_conversion_efficiency", 19.9), "Terrible")

        self.assertEqual(grade_value("conductivity", 1e7), "Outstanding")
        self.assertEqual(grade_value("conductivity", 1e6), "Good")
        self.assertEqual(grade_value("conductivity", 1e5), "Fair")
        self.assertEqual(grade_value("conductivity", 1e4), "Fair")
        self.assertEqual(grade_value("conductivity", 1e2), "Poor")
        self.assertEqual(grade_value("conductivity", 1e-2), "Poor")
        self.assertEqual(grade_value("conductivity", 9e-3), "Terrible")

        self.assertEqual(grade_value("thermal_conductivity", 400), "Outstanding")
        self.assertEqual(grade_value("thermal_conductivity", 200), "Good")
        self.assertEqual(grade_value("thermal_conductivity", 50), "Fair")
        self.assertEqual(grade_value("thermal_conductivity", 1), "Poor")
        self.assertEqual(grade_value("thermal_conductivity", 0.9), "Terrible")

        self.assertEqual(grade_value("ferromagnetism", 200), "Outstanding")
        self.assertEqual(grade_value("ferromagnetism", 150), "Good")
        self.assertEqual(grade_value("ferromagnetism", 50), "Fair")
        self.assertEqual(grade_value("ferromagnetism", 20), "Poor")
        self.assertEqual(grade_value("ferromagnetism", 19.9), "Terrible")

        self.assertEqual(grade_value("ferrimagnetism", 100), "Outstanding")
        self.assertEqual(grade_value("ferrimagnetism", 50), "Good")
        self.assertEqual(grade_value("ferrimagnetism", 10), "Fair")
        self.assertEqual(grade_value("ferrimagnetism", 1), "Poor")
        self.assertEqual(grade_value("ferrimagnetism", 0.9), "Terrible")

        self.assertEqual(grade_value("antiferromagnetism", 600), "Outstanding")
        self.assertEqual(grade_value("antiferromagnetism", 400), "Good")
        self.assertEqual(grade_value("antiferromagnetism", 300), "Fair")
        self.assertEqual(grade_value("antiferromagnetism", 100), "Poor")
        self.assertEqual(grade_value("antiferromagnetism", 99), "Terrible")

    def test_electrocatalysis_grade_boundaries_from_20260626_doc(self):
        from utils.performance_grading import grade_value

        self.assertEqual(grade_value("HER", 120), "Good")
        self.assertEqual(grade_value("HER", 170), "Fair")

        self.assertEqual(grade_value("OER", 260), "Good")
        self.assertEqual(grade_value("OER", 330), "Fair")
        self.assertEqual(grade_value("OER", 380), "Poor")

        self.assertEqual(grade_value("HOR", 2.0), "Good")
        self.assertEqual(grade_value("HOR", 1.2), "Fair")

        self.assertEqual(grade_value("UOR", 1.38), "Good")
        self.assertEqual(grade_value("UOR", 1.42), "Fair")

        self.assertEqual(grade_value("EOR", 25), "Outstanding")
        self.assertEqual(grade_value("EOR", 10), "Good")
        self.assertEqual(grade_value("EOR", 3), "Fair")
        self.assertEqual(grade_value("EOR", 0.75), "Poor")

        self.assertEqual(grade_value("HZOR", -80), "Outstanding")
        self.assertEqual(grade_value("HZOR", 75), "Fair")
        self.assertEqual(grade_value("HZOR", 150), "Poor")

    def test_co2rr_product_fe_grade_boundaries_from_20260626_doc(self):
        from utils.performance_grading import grade_co2rr_faradaic_efficiency

        self.assertEqual(grade_co2rr_faradaic_efficiency(82, "CO"), "Fair")
        self.assertEqual(grade_co2rr_faradaic_efficiency(77, "CO"), "Poor")
        self.assertEqual(grade_co2rr_faradaic_efficiency(74, "CO"), "Terrible")

        self.assertEqual(grade_co2rr_faradaic_efficiency(82, "HCOOH"), "Fair")
        self.assertEqual(grade_co2rr_faradaic_efficiency(77, "HCOOH"), "Poor")
        self.assertEqual(grade_co2rr_faradaic_efficiency(74, "HCOOH"), "Terrible")

        self.assertEqual(grade_co2rr_faradaic_efficiency(58, "CH4"), "Good")
        self.assertEqual(grade_co2rr_faradaic_efficiency(45, "CH4"), "Fair")
        self.assertEqual(grade_co2rr_faradaic_efficiency(37, "CH4"), "Poor")
        self.assertEqual(grade_co2rr_faradaic_efficiency(34, "CH4"), "Terrible")

        self.assertEqual(grade_co2rr_faradaic_efficiency(75, "C2+"), "Good")

        self.assertEqual(grade_co2rr_faradaic_efficiency(18, "C3+"), "Fair")
        self.assertEqual(grade_co2rr_faradaic_efficiency(10, "C3+"), "Poor")
        self.assertEqual(grade_co2rr_faradaic_efficiency(4, "C3+"), "Terrible")

    def test_parse_conductivity_units_to_s_per_m(self):
        from utils.performance_grading import parse_metric_value

        v, u = parse_metric_value("conductivity", "7781 S cm-1")
        self.assertAlmostEqual(v, 778100.0)
        self.assertEqual(u, "S/m")

        v2, u2 = parse_metric_value("conductivity", "46.65 mS/cm")
        self.assertAlmostEqual(v2, 4.665)
        self.assertEqual(u2, "S/m")

        v3, u3 = parse_metric_value("conductivity", "12 mS m-1")
        self.assertAlmostEqual(v3, 0.012)
        self.assertEqual(u3, "S/m")

    def test_parse_property_units(self):
        from utils.performance_grading import parse_metric_value

        v, u = parse_metric_value("photothermal_conversion_efficiency", "efficiency = 0.865")
        self.assertAlmostEqual(v, 86.5)
        self.assertEqual(u, "%")

        v2, u2 = parse_metric_value("thermal_conductivity", "0.53 W m-1 K-1")
        self.assertAlmostEqual(v2, 0.53)
        self.assertEqual(u2, "W m-1 K-1")

        v3, u3 = parse_metric_value("ferromagnetism", "Ms = 2.27 A m2/kg")
        self.assertAlmostEqual(v3, 2.27)
        self.assertEqual(u3, "emu/g")

        v4, u4 = parse_metric_value("antiferromagnetism", "TN = 250 K")
        self.assertAlmostEqual(v4, 250.0)
        self.assertEqual(u4, "K")

    def test_extract_last_performance_metrics_wins(self):
        from utils.performance_grading import extract_last_performance_metrics_text

        claim = (
            "Property Type: conductivity\n"
            "Performance Metrics: 100 S/m conductivity (Confidence: low)\n"
            "Performance Metrics: 120 S/m conductivity (Confidence: low)\n"
        )
        raw = extract_last_performance_metrics_text(claim)
        self.assertIn("120", raw or "")

    def test_evaluate_claim_happy_path(self):
        from utils.performance_grading import evaluate_claim

        claim = (
            "Property Type: conductivity\n"
            "Reaction Type: conductivity\n"
            "Material composition (exactly as provided): Ti\n"
            "Products: N/A\n"
            "Performance Metrics: 7781 S cm-1 conductivity (Confidence: medium)\n"
        )
        out = evaluate_claim(claim)
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("property_type"), "conductivity")
        self.assertEqual(out.get("reaction_type"), "conductivity")
        self.assertAlmostEqual(out.get("metric_value"), 778100.0)
        self.assertEqual(out.get("metric_unit"), "S/m")
        self.assertEqual(out.get("grade"), "Fair")

    def test_co2rr_uses_product_faradaic_efficiency_as_primary_metric(self):
        from utils.performance_grading import evaluate_claim

        claim = (
            "Reaction Type: CO2RR\n"
            "Products: HCOOH\n"
            "Performance Metrics: FE(HCOOH)=85%; j(HCOOH)=2 mA cm-2 (Confidence: medium)\n"
        )
        out = evaluate_claim(claim, reaction_type="CO2RR")
        self.assertIsInstance(out, dict)
        self.assertEqual(out.get("reaction_type"), "CO2RR")
        self.assertEqual(out.get("product"), "HCOOH")
        self.assertEqual(out.get("metric_key"), "faradaic_efficiency")
        self.assertEqual(out.get("metric_name"), "FE(HCOOH)")
        self.assertAlmostEqual(out.get("metric_value"), 85.0)
        self.assertEqual(out.get("metric_unit"), "%")
        self.assertEqual(out.get("partial_current_density"), 2.0)
        self.assertEqual(out.get("partial_current_density_unit"), "mA cm-2")
        self.assertNotEqual(out.get("grade"), "Outstanding")

    def test_co2rr_partial_current_density_two_ma_is_not_outstanding(self):
        from utils.performance_grading import grade_co2rr_partial_current_density

        self.assertEqual(grade_co2rr_partial_current_density(500.0), "Outstanding")
        self.assertEqual(grade_co2rr_partial_current_density(100.0), "Good")
        self.assertEqual(grade_co2rr_partial_current_density(40.0), "Fair")
        self.assertEqual(grade_co2rr_partial_current_density(20.0), "Poor")
        self.assertEqual(grade_co2rr_partial_current_density(2.0), "Terrible")


if __name__ == "__main__":
    unittest.main()
