from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.python.helpers.nmg.hpa_expectation import (
    HpaExpectationCandidateResult,
    HpaExpectationCandidateSpec,
    SurveyTargetSpec,
    aggregate_expectation,
    build_survey_target_result,
    classify_hpa_expectation_fit,
    compute_fit_rmse,
    fit_linear_rule,
    get_expectation_method_spec,
    load_nmg_wave_csv,
    map_boe39_code_to_hpa,
    matches_legacy_printed_precision,
    rank_legacy_candidates,
    select_production_candidate,
)


class TestNmgHpaExpectation(unittest.TestCase):
    def _write_nmg_csv(self, filename: str, rows: list[dict[str, object]]) -> Path:
        temp_dir = tempfile.mkdtemp()
        path = Path(temp_dir) / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return path

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

    def test_matches_legacy_printed_precision_uses_config_display_precision(self) -> None:
        self.assertTrue(matches_legacy_printed_precision(0.4407356112, -0.0066328562))
        self.assertFalse(matches_legacy_printed_precision(0.452, -0.0066328562))
        self.assertFalse(matches_legacy_printed_precision(0.4407356112, -0.0059))

    def test_compute_fit_rmse_uses_all_anchor_years(self) -> None:
        rmse = compute_fit_rmse(
            x_values=[0.01, 0.02, 0.03],
            y_values=[0.03, 0.04, 0.05],
            factor=1.0,
            const=0.02,
        )

        self.assertAlmostEqual(rmse, 0.0, places=12)

    def test_load_nmg_wave_csv_accepts_2015_style_wave_with_valid_boe39(self) -> None:
        csv_path = self._write_nmg_csv(
            "nmg-2015.csv",
            [
                {"we_factor": "1.0", "boe39": "6", "dhousing": "1"},
                {"we_factor": "2.0", "boe39": "7", "dhousing": "2"},
            ],
        )
        try:
            wave = load_nmg_wave_csv(csv_path)
        finally:
            csv_path.unlink(missing_ok=True)
            csv_path.parent.rmdir()

        self.assertEqual(wave.wave_label, "2015")
        self.assertEqual(wave.survey_year, 2015)
        self.assertEqual(wave.row_count, 2)

    def test_load_nmg_wave_csv_rejects_2013_style_wave_without_boe39_values(self) -> None:
        csv_path = self._write_nmg_csv(
            "nmg-2013.csv",
            [
                {"we_factor": "1.0", "boe39": "", "dhousing": "1"},
                {"we_factor": "2.0", "boe39": "", "dhousing": "2"},
            ],
        )
        try:
            with self.assertRaisesRegex(ValueError, "does not contain valid weighted boe39 responses"):
                load_nmg_wave_csv(csv_path)
        finally:
            csv_path.unlink(missing_ok=True)
            csv_path.parent.rmdir()

    def test_build_survey_target_result_can_filter_owner_occupiers(self) -> None:
        csv_path = self._write_nmg_csv(
            "nmg-2024.csv",
            [
                {"we_factor": "1.0", "boe39": "6", "dhousing": "1"},
                {"we_factor": "1.0", "boe39": "6", "dhousing": "2"},
                {"we_factor": "1.0", "boe39": "9", "dhousing": "4"},
            ],
        )
        try:
            wave = load_nmg_wave_csv(csv_path)
        finally:
            csv_path.unlink(missing_ok=True)
            csv_path.parent.rmdir()

        result = build_survey_target_result(
            wave,
            SurveyTargetSpec(
                name="owner_occupiers",
                expectation_method_name="midpoint_exact",
                family_name="owner_occupier_cross_section",
                housing_codes=frozenset({"1", "2"}),
            ),
        )

        self.assertEqual(result.filtered_row_count, 2)
        self.assertAlmostEqual(result.expectation_mean, 0.035, places=12)

    def test_select_production_candidate_prefers_preferred_band_huber_default(self) -> None:
        admissible_ols_spec = HpaExpectationCandidateSpec(
            name="admissible_ols",
            survey_target_spec=SurveyTargetSpec(
                name="national_cross_section__midpoint_exact",
                expectation_method_name="midpoint_exact",
                family_name="national_cross_section",
            ),
            signal_method_name="annual_mean_annualised",
            category_key="A",
            regression_type="ols",
            anchor_policy_name="same_year_two_year_base",
        )
        preferred_huber_spec = HpaExpectationCandidateSpec(
            name="preferred_huber",
            survey_target_spec=SurveyTargetSpec(
                name="national_cross_section__midpoint_exact",
                expectation_method_name="midpoint_exact",
                family_name="national_cross_section",
            ),
            signal_method_name="annual_mean_annualised",
            category_key="A",
            regression_type="huber",
            anchor_policy_name="same_year_two_year_base",
        )
        admissible_ols = HpaExpectationCandidateResult(
            candidate_spec=admissible_ols_spec,
            factor=0.11,
            const=0.003,
            classification=classify_hpa_expectation_fit(0.11, 0.003),
            core_rmse=0.012,
            leave_one_out_rmse=0.020,
            legacy_distance=None,
            fit_points=tuple(),
        )
        preferred_huber = HpaExpectationCandidateResult(
            candidate_spec=preferred_huber_spec,
            factor=0.2887897073,
            const=-0.0059593352,
            classification=classify_hpa_expectation_fit(0.2887897073, -0.0059593352),
            core_rmse=0.0131822893,
            leave_one_out_rmse=0.0207210208,
            legacy_distance=None,
            fit_points=tuple(),
        )

        selection = select_production_candidate([admissible_ols, preferred_huber])

        self.assertEqual(selection.selected_result.candidate_spec.name, "preferred_huber")
        self.assertFalse(selection.complexity_override_applied)

    def test_rank_legacy_candidates_prefers_simpler_exact_precision_match(self) -> None:
        simpler_spec = HpaExpectationCandidateSpec(
            name="simpler_exact_match",
            survey_target_spec=SurveyTargetSpec(
                name="national_cross_section__midpoint_exact",
                expectation_method_name="midpoint_exact",
                family_name="national_cross_section",
            ),
            signal_method_name="rolling_quarter_cumulative",
            category_key="A",
            regression_type="ols",
            anchor_policy_name="explicit_rolling_quarter_pair",
        )
        more_complex_spec = HpaExpectationCandidateSpec(
            name="more_complex_exact_match",
            survey_target_spec=SurveyTargetSpec(
                name="owner_occupier_cross_section__midpoint_exact_cap35",
                expectation_method_name="midpoint_exact_cap35",
                family_name="owner_occupier_cross_section",
                housing_codes=frozenset({"1", "2"}),
            ),
            signal_method_name="rolling_quarter_cumulative",
            category_key="A",
            regression_type="ols",
            anchor_policy_name="explicit_rolling_quarter_pair",
        )
        simpler_result = HpaExpectationCandidateResult(
            candidate_spec=simpler_spec,
            factor=0.4402,
            const=-0.0066,
            classification=classify_hpa_expectation_fit(0.4402, -0.0066),
            core_rmse=0.01,
            leave_one_out_rmse=0.02,
            legacy_distance=0.0005,
            fit_points=tuple(),
        )
        more_complex_result = HpaExpectationCandidateResult(
            candidate_spec=more_complex_spec,
            factor=0.4407,
            const=-0.0067,
            classification=classify_hpa_expectation_fit(0.4407, -0.0067),
            core_rmse=0.009,
            leave_one_out_rmse=0.019,
            legacy_distance=0.0002,
            fit_points=tuple(),
        )

        ranked = rank_legacy_candidates([more_complex_result, simpler_result])

        self.assertEqual(ranked[0].candidate_spec.name, "simpler_exact_match")

    def test_rank_legacy_candidates_uses_diagnostic_rmse_to_break_exact_tie(self) -> None:
        first_spec = HpaExpectationCandidateSpec(
            name="exact_match_a",
            survey_target_spec=SurveyTargetSpec(
                name="national_cross_section__midpoint_exact",
                expectation_method_name="midpoint_exact",
                family_name="national_cross_section",
            ),
            signal_method_name="rolling_quarter_cumulative",
            category_key="A",
            regression_type="ols",
            anchor_policy_name="explicit_rolling_quarter_pair",
        )
        second_spec = HpaExpectationCandidateSpec(
            name="exact_match_b",
            survey_target_spec=SurveyTargetSpec(
                name="national_cross_section__midpoint_exact",
                expectation_method_name="midpoint_exact",
                family_name="national_cross_section",
            ),
            signal_method_name="rolling_quarter_cumulative",
            category_key="A",
            regression_type="ols",
            anchor_policy_name="explicit_rolling_quarter_pair",
        )
        first_result = HpaExpectationCandidateResult(
            candidate_spec=first_spec,
            factor=0.4402,
            const=-0.0066,
            classification=classify_hpa_expectation_fit(0.4402, -0.0066),
            core_rmse=0.01,
            leave_one_out_rmse=0.02,
            legacy_distance=0.0005,
            fit_points=tuple(),
        )
        second_result = HpaExpectationCandidateResult(
            candidate_spec=second_spec,
            factor=0.4409,
            const=-0.0067,
            classification=classify_hpa_expectation_fit(0.4409, -0.0067),
            core_rmse=0.011,
            leave_one_out_rmse=0.021,
            legacy_distance=0.0007,
            fit_points=tuple(),
        )

        ranked = rank_legacy_candidates(
            [first_result, second_result],
            diagnostic_rmse_by_candidate_name={
                "exact_match_a": 0.020,
                "exact_match_b": 0.010,
            },
        )

        self.assertEqual(ranked[0].candidate_spec.name, "exact_match_b")


if __name__ == "__main__":
    unittest.main()
