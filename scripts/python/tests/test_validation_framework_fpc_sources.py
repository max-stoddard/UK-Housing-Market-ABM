"""Tests for locked June 2024 FPC source evidence.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model import FPC_SOURCE_2024_BY_METRIC_ID as package_fpc_sources
from scripts.python.validation.model import TARGETS_BY_ID as package_targets_by_id
from scripts.python.validation.model.fpc_source_2024 import (
    FPC_SOURCE_2024_BY_METRIC_ID,
    SUPPORTED_FPC_METRIC_IDS,
    UNSUPPORTED_FPC_METRIC_IDS,
)
from scripts.python.validation.model.validation_catalog_2024 import TARGETS_BY_ID


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
                "core_hpiMean",
                "core_hpiStd",
                "core_hpiCyclePeriod",
                "rpi_mean",
                "household_owning_share",
                "household_renting_share",
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

    def test_target_catalog_uses_boe_metadata_for_full_year_macro_targets(self) -> None:
        self.assertEqual(TARGETS_BY_ID["core_debtToIncome"].label, "Household Debt to Income")
        self.assertAlmostEqual(TARGETS_BY_ID["core_priceToIncome"].target_band.lower, 4.847149441436771)
        self.assertAlmostEqual(TARGETS_BY_ID["core_housingTransactions"].target_band.lower, 82.43)
        self.assertEqual(TARGETS_BY_ID["core_advancesToFTB"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_advancesToFTB"].source_label, "UK Finance Household Finance Review 2024 Q4")
        self.assertEqual(TARGETS_BY_ID["core_advancesToFTB"].target_band.lower, 26.442)
        self.assertEqual(TARGETS_BY_ID["core_advancesToBTL"].source_label, "UK Finance BTL Mortgage Market Update 2024 (Q1-Q4)")
        self.assertEqual(TARGETS_BY_ID["core_advancesToBTL"].target_band.upper, 5.43)
        for metric_id in (
            "core_mortgageApprovals",
            "core_housingTransactions",
            "core_debtToIncome",
            "core_housePriceGrowth",
            "core_priceToIncome",
        ):
            self.assertIsNot(TARGETS_BY_ID[metric_id].source_metadata, FPC_SOURCE_2024_BY_METRIC_ID[metric_id])
            self.assertEqual(
                TARGETS_BY_ID[metric_id].source_metadata.source_document_path,
                "input-data-versions/validation-sources/2024/boe/housing-tools.xlsx",
            )

    def test_old_fpc_point_values_are_not_active_target_bands(self) -> None:
        self.assertNotEqual(TARGETS_BY_ID["core_mortgageApprovals"].target_band.lower, 57.0)
        self.assertNotEqual(TARGETS_BY_ID["core_mortgageApprovals"].target_band.upper, 63.0)
        self.assertNotEqual(TARGETS_BY_ID["core_housingTransactions"].target_band.lower, 84.2)
        self.assertNotEqual(TARGETS_BY_ID["core_debtToIncome"].target_band.lower, 125.0)
        self.assertNotEqual(TARGETS_BY_ID["core_priceToIncome"].target_band.lower, 5.4)
        self.assertNotEqual(TARGETS_BY_ID["core_housePriceGrowth"].target_band.lower, 0.0)

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

    def test_package_and_wrapper_exports_resolve_to_canonical_objects(self) -> None:
        self.assertIs(FPC_SOURCE_2024_BY_METRIC_ID, package_fpc_sources)
        self.assertIs(TARGETS_BY_ID, package_targets_by_id)


if __name__ == "__main__":
    unittest.main()
