"""Tests for locked June 2024 FPC source evidence.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model.fpc_source_2024 import (
    FPC_SOURCE_2024_BY_METRIC_ID,
    SUPPORTED_FPC_METRIC_IDS,
    UNSUPPORTED_FPC_METRIC_IDS,
)
from scripts.python.validation.model.targets_2024 import TARGETS_BY_ID


class TestValidationFrameworkFpcSources(unittest.TestCase):
    def test_locked_support_matrix_matches_june_2024_source(self) -> None:
        self.assertEqual(
            SUPPORTED_FPC_METRIC_IDS,
            (
                "core_mortgageApprovals",
                "core_housingTransactions",
                "core_debtToIncome",
                "core_housePriceGrowth",
                "core_priceToIncome",
                "core_interestRateSpread",
            ),
        )
        self.assertEqual(
            UNSUPPORTED_FPC_METRIC_IDS,
            (
                "core_advancesToFTB",
                "core_advancesToHM",
                "core_advancesToBTL",
                "core_ooDebtToIncome",
                "core_rentalYield",
            ),
        )

    def test_locked_official_values_capture_raw_and_comparison_units(self) -> None:
        mortgage = FPC_SOURCE_2024_BY_METRIC_ID["core_mortgageApprovals"]
        self.assertEqual(mortgage.source_indicator_label, "Mortgage approvals")
        self.assertEqual(mortgage.raw_source_value, 61325.0)
        self.assertEqual(mortgage.normalized_source_value, 61.325)
        self.assertEqual(mortgage.source_as_of, "Mar 2024")

    def test_target_catalog_uses_locked_fpc_metadata(self) -> None:
        self.assertEqual(TARGETS_BY_ID["core_debtToIncome"].label, "Household Debt to Income")
        self.assertEqual(TARGETS_BY_ID["core_priceToIncome"].target_band.lower, 5.4)
        self.assertEqual(TARGETS_BY_ID["core_housingTransactions"].target_band.lower, 84.2)
        self.assertEqual(TARGETS_BY_ID["core_advancesToFTB"].requirement, "diagnostic")
        self.assertIsNone(TARGETS_BY_ID["core_advancesToFTB"].target_band)
        self.assertNotEqual(
            TARGETS_BY_ID["core_mortgageApprovals"].source_label,
            "Official 2024 macro indicator target",
        )

    def test_supported_bands_contain_normalized_official_values(self) -> None:
        for metric_id in (
            "core_mortgageApprovals",
            "core_housingTransactions",
            "core_debtToIncome",
            "core_housePriceGrowth",
            "core_priceToIncome",
        ):
            metric = TARGETS_BY_ID[metric_id]
            source = metric.source_metadata
            self.assertIsNotNone(metric.target_band)
            self.assertIsNotNone(source)
            self.assertIsNotNone(source.normalized_source_value)
            self.assertLessEqual(metric.target_band.lower, source.normalized_source_value)
            self.assertGreaterEqual(metric.target_band.upper, source.normalized_source_value)


if __name__ == "__main__":
    unittest.main()
