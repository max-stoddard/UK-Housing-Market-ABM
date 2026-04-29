from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from scripts.python.calibration.btl.btl_survey_target import (
    DATASET_CHOICES,
    DEFAULT_MULTIPLIER,
    DEFAULT_DATASETS,
    FRS_INCOME_COLUMN,
    FRS_RENTAL_INCOME_COLUMN,
    FRS_SUBLET_COLUMN,
    FRS_WEIGHT_COLUMN,
    SURVEY_INDICATOR_COLUMN,
    SURVEY_INCOME_COLUMN,
    SURVEY_WEIGHT_COLUMN,
    WEIGHT_MODE_WEIGHTED,
    build_arg_parser,
    compute_equal_mass_percentile_table,
    compute_legacy_weak_percentile_table,
    prepare_frs_btl_target_rows,
    weighted_share,
)


class TestBtlSurveyTarget(unittest.TestCase):
    def test_parser_defaults_to_weighted_all_datasets_and_legacy_multiplier(self) -> None:
        args = build_arg_parser().parse_args([])

        self.assertEqual(args.datasets, DEFAULT_DATASETS)
        self.assertEqual(args.datasets.split(","), list(DATASET_CHOICES))
        self.assertEqual(args.weight_mode, WEIGHT_MODE_WEIGHTED)
        self.assertEqual(args.multiplier, DEFAULT_MULTIPLIER)
        self.assertIsNone(args.frs_household_csv)
        self.assertIsNone(args.frs_dictionary_txt)
        self.assertIsNone(args.output_json)
        self.assertIsNone(args.output_csv)

    def test_weighted_equal_mass_table_mean_matches_direct_share(self) -> None:
        income = pd.Series([10.0, 20.0, 30.0])
        indicator = pd.Series([0.0, 1.0, 1.0])
        weights = pd.Series([1.0, 1.0, 2.0])

        direct = weighted_share(indicator, weights)
        table = compute_equal_mass_percentile_table(
            income,
            indicator,
            weights,
            n_bins=2,
        )

        self.assertAlmostEqual(direct, 0.75)
        self.assertAlmostEqual(table["mean"], direct)
        self.assertAlmostEqual(table["equivalenceGap"], 0.0)

    def test_unweighted_legacy_path_reproduces_direct_share_on_equal_bins(self) -> None:
        income = pd.Series([1.0, 2.0, 3.0, 4.0])
        indicator = pd.Series([0.0, 1.0, 0.0, 1.0])
        weights = pd.Series(np.ones(4))

        direct = weighted_share(indicator, weights)
        equal_mass = compute_equal_mass_percentile_table(
            income,
            indicator,
            weights,
            n_bins=4,
        )
        legacy_weak = compute_legacy_weak_percentile_table(
            income,
            indicator,
            n_bins=4,
        )

        self.assertAlmostEqual(direct, 0.5)
        self.assertAlmostEqual(equal_mass["mean"], 0.5)
        self.assertAlmostEqual(legacy_weak["mean"], 0.5)
        self.assertEqual(legacy_weak["emptyBinCount"], 0)

    def test_frs_filtering_uses_sublet_subrent_and_not_hhrent(self) -> None:
        raw = pd.DataFrame(
            {
                FRS_WEIGHT_COLUMN: [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                FRS_INCOME_COLUMN: [100.0, 150.0, 200.0, 250.0, 300.0, 400.0],
                FRS_SUBLET_COLUMN: [2.0, 1.0, 1.0, 1.0, 9.0, 2.0],
                FRS_RENTAL_INCOME_COLUMN: ["A", 50.0, 0.0, -1.0, 0.0, "A"],
                "hhrent": [9999.0, 9999.0, 9999.0, 9999.0, 9999.0, 9999.0],
            }
        )

        prepared, diagnostics = prepare_frs_btl_target_rows(raw)

        self.assertEqual(len(prepared), 4)
        self.assertEqual(prepared[SURVEY_INDICATOR_COLUMN].tolist(), [0.0, 1.0, 0.0, 0.0])
        self.assertEqual(prepared[SURVEY_WEIGHT_COLUMN].tolist(), [1.0, 2.0, 3.0, 6.0])
        self.assertEqual(prepared[SURVEY_INCOME_COLUMN].tolist(), [5200.0, 5200.0, 10400.0, 20800.0])
        self.assertAlmostEqual(
            weighted_share(prepared[SURVEY_INDICATOR_COLUMN], prepared[SURVEY_WEIGHT_COLUMN]),
            1.0 / 6.0,
        )
        self.assertAlmostEqual(
            weighted_share(
                prepared[SURVEY_INDICATOR_COLUMN],
                pd.Series(np.ones(len(prepared))),
            ),
            0.25,
        )
        self.assertEqual(diagnostics["invalidSubletRows"], 1)
        self.assertEqual(diagnostics["invalidSubletterRentalIncomeRows"], 1)
        self.assertNotIn("hhrent", prepared.columns)

    def test_equal_mass_rejects_empty_input(self) -> None:
        with self.assertRaisesRegex(ValueError, "No valid observations"):
            compute_equal_mass_percentile_table([], [], [], n_bins=2)


if __name__ == "__main__":
    unittest.main()
