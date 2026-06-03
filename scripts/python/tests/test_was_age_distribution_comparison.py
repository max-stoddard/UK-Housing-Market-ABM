from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from scripts.python.experiments.was import age_gross_income_joint_dist_comparison
from scripts.python.experiments.was import age_distribution_comparison
from scripts.python.experiments.was.age_gross_income_joint_dist_comparison import (
    _gross_income_stats_from_age_conditional,
)
from scripts.python.experiments.was.age_distribution_comparison import (
    _split_final_bin_uniform,
)
from scripts.python.helpers.was.experiments import get_input_version_file


class TestWasAgeDistributionComparison(unittest.TestCase):
    def test_legacy_round8_final_bin_75_85_is_split_to_95(self) -> None:
        distribution = pd.DataFrame(
            [
                {"lower_edge": 65.0, "upper_edge": 75.0, "probability": 0.2},
                {"lower_edge": 75.0, "upper_edge": 85.0, "probability": 0.1},
            ]
        )

        actual = _split_final_bin_uniform(distribution)
        expected = pd.DataFrame(
            [
                {"lower_edge": 65.0, "upper_edge": 75.0, "probability": 0.2},
                {"lower_edge": 75.0, "upper_edge": 85.0, "probability": 0.05},
                {"lower_edge": 85.0, "upper_edge": 95.0, "probability": 0.05},
            ]
        )
        assert_frame_equal(actual.reset_index(drop=True), expected)

    def test_new_round8_final_bin_75_95_is_left_unchanged(self) -> None:
        distribution = pd.DataFrame(
            [
                {"lower_edge": 65.0, "upper_edge": 75.0, "probability": 0.2},
                {"lower_edge": 75.0, "upper_edge": 95.0, "probability": 0.1},
            ]
        )

        actual = _split_final_bin_uniform(distribution)
        assert_frame_equal(actual.reset_index(drop=True), distribution)

    def test_age_density_values_are_not_divided_by_bin_width_again(self) -> None:
        distribution = pd.DataFrame(
            [
                {"lower_edge": 0.0, "upper_edge": 10.0, "probability": 0.05},
                {"lower_edge": 10.0, "upper_edge": 30.0, "probability": 0.025},
            ]
        )

        actual = age_distribution_comparison._normalized_age_density(distribution)

        np.testing.assert_allclose(
            actual.to_numpy(),
            np.asarray([0.05, 0.025]),
        )
        self.assertAlmostEqual(
            age_distribution_comparison._age_density_integral(distribution),
            1.0,
        )

    def test_density_weighted_age_stats_use_density_times_bin_width(self) -> None:
        distribution = pd.DataFrame(
            [
                {"lower_edge": 0.0, "upper_edge": 10.0, "probability": 0.05},
                {"lower_edge": 10.0, "upper_edge": 30.0, "probability": 0.025},
            ]
        )

        mean, variance, skew = age_distribution_comparison._density_weighted_mean_variance_skew(
            distribution
        )

        self.assertAlmostEqual(mean, 12.5)
        self.assertAlmostEqual(variance, 56.25)
        self.assertAlmostEqual(skew, 0.0)

    def test_input_version_file_resolves_checked_in_distribution(self) -> None:
        path = get_input_version_file(
            age_distribution_comparison.__file__,
            "v5o3",
            "Age15-FRS-2023-24-Weighted.csv",
        )

        self.assertTrue(
            path.endswith(
                "input-data-versions/v5o3/Age15-FRS-2023-24-Weighted.csv"
            )
        )
        self.assertTrue(Path(path).exists())

    def test_gross_income_stats_are_weighted_by_age_distribution(self) -> None:
        age_distribution = pd.DataFrame(
            [
                {"lower_edge": 0.0, "upper_edge": 10.0, "probability": 0.05},
                {"lower_edge": 10.0, "upper_edge": 30.0, "probability": 0.025},
            ]
        )
        income_edges = np.log(np.asarray([10.0, 20.0, 40.0]))
        conditional_grid = np.asarray(
            [
                [0.25, 0.75],
                [1.0, 0.0],
            ]
        )

        stats = _gross_income_stats_from_age_conditional(
            age_distribution,
            income_edges,
            conditional_grid,
        )

        income_midpoints = np.exp((income_edges[:-1] + income_edges[1:]) / 2.0)
        probabilities = np.asarray(
            [
                0.5 * 0.25,
                0.5 * 0.75,
                0.5 * 1.0,
                0.5 * 0.0,
            ]
        )
        values = np.asarray(
            [
                income_midpoints[0],
                income_midpoints[1],
                income_midpoints[0],
                income_midpoints[1],
            ]
        )
        expected_mean = float(probabilities @ values)
        expected_variance = float(probabilities @ (values - expected_mean) ** 2)

        self.assertAlmostEqual(stats["mean"], expected_mean)
        self.assertAlmostEqual(stats["variance"], expected_variance)

    def test_age_summary_rows_use_source_dataset_labels_and_target_years(self) -> None:
        rows = age_distribution_comparison._build_version_comparison_rows(
            {"mean": 1.0, "stddev": 2.0, "skew": 3.0},
            {"mean": 2.0, "stddev": 4.0, "skew": 6.0},
        )

        self.assertEqual(rows[0]["dataset"], "WAS Wave 3")
        self.assertEqual(rows[0]["period"], "2011 target year")
        self.assertEqual(rows[1]["dataset"], "FRS 2023-24")
        self.assertEqual(rows[1]["period"], "2024 target year")
        self.assertEqual(rows[2]["dataset"], "Percent diff. (2024 vs 2011)")
        self.assertEqual(rows[2]["period"], "--")

    def test_income_summary_rows_use_source_dataset_labels_and_target_years(self) -> None:
        rows = age_gross_income_joint_dist_comparison._build_version_comparison_rows(
            {"mean": 1.0, "stddev": 2.0, "skew": 3.0},
            {"mean": 2.0, "stddev": 4.0, "skew": 6.0},
        )

        self.assertEqual(rows[0]["dataset"], "WAS Wave 3")
        self.assertEqual(rows[0]["period"], "2011 target year")
        self.assertEqual(rows[1]["dataset"], "FRS 2023-24")
        self.assertEqual(rows[1]["period"], "2024 target year")
        self.assertEqual(rows[2]["dataset"], "Percent diff. (2024 vs 2011)")
        self.assertEqual(rows[2]["period"], "--")

    def test_income_plot_labels_omit_input_version_prefixes(self) -> None:
        age_distribution = pd.DataFrame(
            [
                {"lower_edge": 20.0, "upper_edge": 30.0, "probability": 0.05},
                {"lower_edge": 30.0, "upper_edge": 50.0, "probability": 0.025},
            ]
        )
        age_edges = np.asarray([20.0, 30.0, 50.0])
        income_edges = np.log(np.asarray([10000.0, 20000.0, 40000.0]))
        conditional_grid = np.asarray(
            [
                [0.25, 0.75],
                [1.0, 0.0],
            ]
        )

        with tempfile.TemporaryDirectory() as output_dir:
            with mock.patch(
                "sys.argv",
                [
                    "age_gross_income_joint_dist_comparison.py",
                    "--output-dir",
                    output_dir,
                ],
            ), mock.patch.object(
                age_gross_income_joint_dist_comparison,
                "read_binned_distribution",
                return_value=age_distribution,
            ), mock.patch.object(
                age_gross_income_joint_dist_comparison,
                "read_joint_distribution_grid",
                return_value=(age_edges, income_edges, conditional_grid),
            ), mock.patch.object(
                age_gross_income_joint_dist_comparison.plt,
                "show",
            ):
                age_gross_income_joint_dist_comparison.main()
                figure = age_gross_income_joint_dist_comparison.plt.gcf()

        try:
            labels = [
                line.get_label()
                for axis in figure.axes
                for line in axis.lines
            ]

            self.assertIn("WAS Wave 3 (2011 target year)", labels)
            self.assertIn("FRS 2023-24 (2024 target year)", labels)
            self.assertNotIn("v0 WAS Wave 3 (2011 target year)", labels)
            self.assertNotIn("v5o3 FRS 2023-24 (2024 target year)", labels)
        finally:
            age_gross_income_joint_dist_comparison.plt.close(figure)


if __name__ == "__main__":
    unittest.main()
