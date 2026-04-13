"""Tests for 2024 validation framework extractors.

@author: Max Stoddard
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.python.helpers.was.constants import WAS_NET_ANNUAL_RENTAL_INCOME
from scripts.python.validation.model.extractors import (
    HOUSEHOLD_DISTRIBUTION_SPECS,
    extract_core_indicator_mean,
    extract_household_jsd,
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
