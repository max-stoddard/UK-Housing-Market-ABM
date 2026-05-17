"""Tests for 2024 validation framework extractors.

@author: Max Stoddard
"""

from __future__ import annotations

import math
import statistics
import tempfile
import unittest
from pathlib import Path

from scripts.python.helpers.was.config import ROUND_8_DATA, WAVE_3_DATA
from scripts.python.helpers.was.constants import WAS_NET_ANNUAL_RENTAL_INCOME
from scripts.python.validation.model.extractors import (
    HOUSEHOLD_DISTRIBUTION_SPECS,
    extract_core_indicator_mean,
    extract_household_metric_from_results,
    extract_household_jsd,
    extract_household_share_from_results,
    extract_household_status_share,
    extract_output_series_cycle_period,
    extract_output_series_metric_from_results,
    extract_rebased_output_series_mean,
    extract_rebased_output_series_std,
)


class TestValidationFrameworkExtractors(unittest.TestCase):
    def test_extract_core_indicator_mean_uses_periods_200_to_2000(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "coreIndicator-mortgageApprovals.csv"
            values = [10.0] * 200 + [20.0] * 1800 + [999.0] * 5
            path.write_text("\n".join(str(value) for value in values), encoding="utf-8")
            self.assertAlmostEqual(extract_core_indicator_mean(path), 20.0)

    def test_extract_core_indicator_mean_can_scale_counts_to_thousands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "coreIndicator-mortgageApprovals.csv"
            values = [1_000.0] * 200 + [52_000.0] * 1800
            path.write_text("\n".join(str(value) for value in values), encoding="utf-8")
            self.assertAlmostEqual(extract_core_indicator_mean(path, scale=0.001), 52.0)

    def test_extract_core_indicator_mean_honors_explicit_long_run_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "coreIndicator-mortgageApprovals.csv"
            values = [10.0] * 500 + [30.0] * 3000 + [999.0] * 5
            path.write_text("\n".join(str(value) for value in values), encoding="utf-8")
            self.assertAlmostEqual(
                extract_core_indicator_mean(path, window_start=500, window_end=3500),
                30.0,
            )

    def test_extract_rebased_output_series_mean_uses_first_window_value_as_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "Output-run1.csv"
            sale_hpi_values = [99.0] * 200 + [2.0] + [4.0] * 1799 + [999.0] * 5
            path.write_text(
                "Sale HPI\n" + "\n".join(str(value) for value in sale_hpi_values) + "\n",
                encoding="utf-8",
            )
            expected_mean = (1.0 + 1799.0 * 2.0) / 1800.0
            self.assertAlmostEqual(
                extract_rebased_output_series_mean(path, column_name="Sale HPI"),
                expected_mean,
            )

    def test_extract_rebased_output_series_std_uses_population_std_after_rebasing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "Output-run1.csv"
            sale_hpi_values = [77.0] * 200 + [2.0, 4.0, 6.0] * 600 + [888.0] * 5
            path.write_text(
                "Sale HPI\n" + "\n".join(str(value) for value in sale_hpi_values) + "\n",
                encoding="utf-8",
            )
            rebased_window = [1.0, 2.0, 3.0] * 600
            self.assertAlmostEqual(
                extract_rebased_output_series_std(path, column_name="Sale HPI"),
                statistics.pstdev(rebased_window),
            )

    def test_extract_output_series_cycle_period_detects_locked_fft_peak(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "Output-run1.csv"
            values = []
            for month in range(2005):
                values.append(2.0 + 0.2 * math.sin((2.0 * math.pi * month) / 120.0))
            path.write_text(
                "Sale HPI\n" + "\n".join(f"{value:.12f}" for value in values) + "\n",
                encoding="utf-8",
            )
            self.assertAlmostEqual(
                extract_output_series_cycle_period(path, column_name="Sale HPI"),
                120.0,
                delta=6.0,
            )

    def test_extract_output_series_cycle_period_can_use_trailing_2011_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "Output-run1.csv"
            values = []
            for month in range(200):
                values.append(2.0)
            for month in range(1275):
                values.append(2.0 + 0.2 * math.sin((2.0 * math.pi * month) / 60.0))
            for month in range(525):
                values.append(2.0 + 0.2 * math.sin((2.0 * math.pi * month) / 120.0))
            for month in range(5):
                values.append(2.0)
            path.write_text(
                "Sale HPI\n" + "\n".join(f"{value:.12f}" for value in values) + "\n",
                encoding="utf-8",
            )
            self.assertAlmostEqual(
                extract_output_series_cycle_period(
                    path,
                    column_name="Sale HPI",
                    trailing_months=525,
                ),
                120.0,
                delta=10.0,
            )

    def test_extract_rpi_mean_reads_rental_hpi_from_output_series(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            results_dir = Path(tmp_dir)
            rental_hpi_values = [99.0] * 200 + [2.0] + [4.0] * 1799 + [999.0] * 5
            (results_dir / "Output-run1.csv").write_text(
                "Rental HPI\n" + "\n".join(str(value) for value in rental_hpi_values) + "\n",
                encoding="utf-8",
            )
            expected_mean = (1.0 + 1799.0 * 2.0) / 1800.0
            self.assertAlmostEqual(
                extract_output_series_metric_from_results(metric_id="rpi_mean", results_dir=results_dir),
                expected_mean,
            )

    def test_extract_household_status_share_averages_snapshot_shares(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "HousingStatus-run1.csv"
            path.write_text(
                "199;2;2;2;2\n"
                "996;2;2;1;0\n"
                "1008;2;1;1;1\n"
                "2001;1;1;1;1\n",
                encoding="utf-8",
            )
            self.assertAlmostEqual(extract_household_status_share(path, status_value=2), 37.5)
            self.assertAlmostEqual(extract_household_status_share(path, status_value=1), 50.0)

    def test_extract_household_status_share_honors_explicit_exclusive_window_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "HousingStatus-run1.csv"
            path.write_text(
                "499;2;2;2;2\n"
                "500;2;2;1;1\n"
                "3499;2;1;1;1\n"
                "3500;2;2;2;2\n",
                encoding="utf-8",
            )
            self.assertAlmostEqual(
                extract_household_status_share(
                    path,
                    status_value=2,
                    window_start=500,
                    window_end=3500,
                ),
                37.5,
            )

    def test_extract_household_share_from_results_uses_housing_status_metric_specs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            results_dir = Path(tmp_dir)
            (results_dir / "HousingStatus-run1.csv").write_text(
                "996;2;2;1;0\n"
                "1008;2;1;1;1\n",
                encoding="utf-8",
            )
            self.assertAlmostEqual(
                extract_household_share_from_results(metric_id="household_owning_share", results_dir=results_dir),
                37.5,
            )
            self.assertAlmostEqual(
                extract_household_share_from_results(metric_id="household_renting_share", results_dir=results_dir),
                50.0,
            )

    def test_extract_household_jsd_returns_zero_for_identical_histograms(self) -> None:
        jsd = extract_household_jsd(
            model_values=[1_000.0, 2_000.0, 4_000.0],
            target_values=[1_000.0, 2_000.0, 4_000.0],
            target_weights=[1.0, 1.0, 1.0],
            bin_edges=[500.0, 1_500.0, 3_000.0, 5_000.0],
        )
        self.assertAlmostEqual(jsd, 0.0)

    def test_income_distribution_spec_includes_net_rental_income_for_non_rent_derivation(self) -> None:
        income_spec = HOUSEHOLD_DISTRIBUTION_SPECS["income_distribution_jsd"]
        self.assertIn(WAS_NET_ANNUAL_RENTAL_INCOME, income_spec.use_columns)

    def test_extract_household_metric_honors_explicit_was_dataset_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            results_dir = root / "Results" / "dataset-selection"
            results_dir.mkdir(parents=True)
            (results_dir / "MonthlyGrossEmploymentIncome-run1.csv").write_text(
                "1000;100.0;200.0;300.0\n",
                encoding="utf-8",
            )

            self._write_income_was_fixture(
                root=root,
                dataset=WAVE_3_DATA,
                incomes=[1_200.0, 2_400.0, 3_600.0],
            )
            self._write_income_was_fixture(
                root=root,
                dataset=ROUND_8_DATA,
                incomes=[8_000.0, 12_000.0, 16_000.0],
            )

            w3_jsd = extract_household_metric_from_results(
                metric_id="income_distribution_jsd",
                results_dir=results_dir,
                was_data_root=root,
                was_dataset=WAVE_3_DATA,
            )
            r8_jsd = extract_household_metric_from_results(
                metric_id="income_distribution_jsd",
                results_dir=results_dir,
                was_data_root=root,
                was_dataset=ROUND_8_DATA,
            )

            self.assertAlmostEqual(w3_jsd, 0.0)
            self.assertGreater(r8_jsd, 0.0)

    def _write_income_was_fixture(self, *, root: Path, dataset: str, incomes: list[float]) -> None:
        if dataset == WAVE_3_DATA:
            relative_path = "private-datasets/was/was_wave_3_hhold_eul_final.dta"
            header = [
                "w3xswgt",
                "DVTotGIRw3",
                "DVTotNIRw3",
                "DVGrsRentAmtAnnualw3_aggr",
                "DVNetRentAmtAnnualw3_aggr",
            ]
        else:
            relative_path = "private-datasets/was/was_round_8_hhold_eul_may_2025.privdata"
            header = [
                "R8xshhwgt",
                "DVTotGIRR8",
                "DVTotInc_BHCR8",
                "DVGrsRentAmtAnnualR8_aggr",
                "DVNetRentAmtAnnualR8_aggr",
            ]

        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        separator = "," if dataset == WAVE_3_DATA else "\t"
        rows = [separator.join(header)]
        for income in incomes:
            rows.append(separator.join(["1.0", str(income), str(0.8 * income), "0.0", "0.0"]))
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
