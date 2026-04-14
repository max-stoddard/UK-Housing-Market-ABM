from __future__ import annotations

import unittest

from scripts.python.experiments.nmg.nmg_hpa_expectation_method_search import (
    CandidateEvaluation,
    build_arg_parser,
    rank_results,
    resolve_anchor_pairings,
)


class TestNmgHpaExpectationMethodSearch(unittest.TestCase):
    def test_parser_defaults_use_legacy_targets_and_2016_holdout(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "nmg-2014.csv",
                "nmg-2016.csv",
                "nmg-2024.csv",
                "pp.2012.csv",
                "pp-2018.csv",
                "pp-2024.csv",
            ]
        )

        self.assertEqual(args.config_path, "src/main/resources/config.properties")
        self.assertEqual(args.holdout_year, 2016)
        self.assertEqual(args.top_k, 20)

    def test_ranking_prefers_holdout_error_when_legacy_distance_ties(self) -> None:
        stronger_holdout = CandidateEvaluation(
            pairing_rule_name="previous_available",
            survey_method_name="midpoint_exact",
            signal_method_name="java_like_annualised",
            factor=0.44,
            const=-0.007,
            legacy_distance=0.01,
            holdout_year=2016,
            holdout_observed=0.04,
            holdout_predicted=0.041,
            simplicity_rank=0,
        )
        weaker_holdout = CandidateEvaluation(
            pairing_rule_name="nearest_available",
            survey_method_name="midpoint_exact_cap35",
            signal_method_name="annual_mean_cumulative",
            factor=0.44,
            const=-0.007,
            legacy_distance=0.01,
            holdout_year=2016,
            holdout_observed=0.04,
            holdout_predicted=0.05,
            simplicity_rank=2,
        )

        ranked = rank_results([weaker_holdout, stronger_holdout])

        self.assertEqual(ranked[0].signal_method_name, "java_like_annualised")
        self.assertEqual(ranked[1].signal_method_name, "annual_mean_cumulative")

    def test_ranking_prefers_simpler_methods_when_scores_tie(self) -> None:
        simpler = CandidateEvaluation(
            pairing_rule_name="previous_available",
            survey_method_name="midpoint_exact",
            signal_method_name="java_like_annualised",
            factor=0.43,
            const=-0.006,
            legacy_distance=0.02,
            holdout_year=2016,
            holdout_observed=0.04,
            holdout_predicted=0.042,
            simplicity_rank=0,
        )
        less_simple = CandidateEvaluation(
            pairing_rule_name="nearest_available",
            survey_method_name="midpoint_exact_cap35",
            signal_method_name="annual_mean_annualised",
            factor=0.43,
            const=-0.006,
            legacy_distance=0.02,
            holdout_year=2016,
            holdout_observed=0.04,
            holdout_predicted=0.042,
            simplicity_rank=1,
        )

        ranked = rank_results([less_simple, simpler])

        self.assertEqual(ranked[0].survey_method_name, "midpoint_exact")
        self.assertEqual(ranked[1].survey_method_name, "midpoint_exact_cap35")

    def test_resolve_anchor_pairings_supports_nearest_and_previous_available(self) -> None:
        available_years = [2011, 2012, 2018, 2022, 2023, 2024, 2025]

        self.assertEqual(
            resolve_anchor_pairings("nearest_available", available_years=available_years),
            {2014: 2012, 2016: 2018, 2024: 2024},
        )
        self.assertEqual(
            resolve_anchor_pairings("previous_available", available_years=available_years),
            {2014: 2012, 2016: 2012, 2024: 2024},
        )


if __name__ == "__main__":
    unittest.main()
