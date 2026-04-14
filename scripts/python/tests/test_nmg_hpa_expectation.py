from __future__ import annotations

import unittest

from scripts.python.helpers.nmg.hpa_expectation import (
    aggregate_expectation,
    classify_hpa_expectation_fit,
    compute_fit_rmse,
    fit_linear_rule,
    get_expectation_method_spec,
    map_boe39_code_to_hpa,
)


class TestNmgHpaExpectation(unittest.TestCase):
    def test_midpoint_exact_mapping_uses_default_open_cap(self) -> None:
        spec = get_expectation_method_spec("midpoint_exact")
        self.assertEqual(spec.lower_open_cap, -0.30)
        self.assertEqual(spec.upper_open_cap, 0.30)
        self.assertAlmostEqual(map_boe39_code_to_hpa(6, method_name=spec.method_name), 0.035, places=12)
        self.assertAlmostEqual(map_boe39_code_to_hpa(7, method_name=spec.method_name), 0.075, places=12)
        self.assertIsNone(map_boe39_code_to_hpa(10, method_name=spec.method_name))

    def test_weighted_boe39_aggregation_excludes_dont_know(self) -> None:
        rows = [
            {"we_factor": "2.0", "boe39": "6"},
            {"we_factor": "1.0", "boe39": "7"},
            {"we_factor": "5.0", "boe39": "10"},
        ]

        result = aggregate_expectation(rows, method_name="midpoint_exact")

        self.assertAlmostEqual(result.expectation_mean, ((2.0 * 0.035) + (1.0 * 0.075)) / 3.0, places=12)
        self.assertEqual(result.rows_read, 3)
        self.assertEqual(result.rows_used, 2)
        self.assertEqual(result.rows_dont_know, 1)
        self.assertAlmostEqual(result.weight_total_used, 3.0, places=12)

    def test_weighted_boe39_aggregation_skips_invalid_weights_and_blank_codes(self) -> None:
        rows = [
            {"we_factor": "", "boe39": "6"},
            {"we_factor": "-1", "boe39": "7"},
            {"we_factor": "4.0", "boe39": ""},
            {"we_factor": "2.5", "boe39": "5"},
        ]

        result = aggregate_expectation(rows, method_name="midpoint_rounded")

        self.assertAlmostEqual(result.expectation_mean, 0.0, places=12)
        self.assertEqual(result.rows_invalid_weight, 2)
        self.assertEqual(result.rows_missing_code, 1)
        self.assertEqual(result.rows_used, 1)
        self.assertAlmostEqual(result.weight_total_used, 2.5, places=12)

    def test_fit_linear_rule_matches_two_point_line(self) -> None:
        factor, const = fit_linear_rule(
            x_values=[0.10, 0.20],
            y_values=[0.037, 0.081],
        )

        self.assertAlmostEqual(factor, 0.44, places=12)
        self.assertAlmostEqual(const, -0.007, places=12)

    def test_classify_plausibility_distinguishes_preferred_and_admissible_only(self) -> None:
        self.assertEqual(classify_hpa_expectation_fit(0.44, -0.007).label, "preferred")
        self.assertEqual(classify_hpa_expectation_fit(1.0, 0.02).label, "admissible")
        self.assertEqual(classify_hpa_expectation_fit(-0.1, 0.0).label, "inadmissible")

    def test_compute_fit_rmse_uses_all_anchor_years(self) -> None:
        rmse = compute_fit_rmse(
            x_values=[0.01, 0.02, 0.03],
            y_values=[0.03, 0.04, 0.05],
            factor=1.0,
            const=0.02,
        )

        self.assertAlmostEqual(rmse, 0.0, places=12)


if __name__ == "__main__":
    unittest.main()
