"""Tests for locked full-year 2024 market source evidence.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model import MARKET_SOURCE_2024_BY_METRIC_ID as package_market_sources
from scripts.python.validation.model.market_sources_2024 import (
    BOE_HOUSING_TOOLS_2024_VALUES_BY_METRIC_ID,
    HPI_2024_CYCLE_PERIOD_MONTHS,
    HPI_2024_REBASED_MEAN,
    HPI_2024_REBASED_STD,
    HPI_FULL_HISTORY_REBASED_STD,
    HPI_TARGET_TOLERANCE,
    INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS,
    MARKET_SOURCE_2024_BY_METRIC_ID,
    OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES,
    RENTAL_YIELD_2024_QUARTERLY_VALUES,
)
from scripts.python.validation.model.validation_catalog_2024 import TARGETS_BY_ID


class TestValidationFrameworkMarketSources(unittest.TestCase):
    def test_locked_market_source_means_match_reviewed_2024_values(self) -> None:
        hpi_mean = MARKET_SOURCE_2024_BY_METRIC_ID["core_hpiMean"]
        hpi_std = MARKET_SOURCE_2024_BY_METRIC_ID["core_hpiStd"]
        hpi_cycle = MARKET_SOURCE_2024_BY_METRIC_ID["core_hpiCyclePeriod"]
        spread = MARKET_SOURCE_2024_BY_METRIC_ID["core_interestRateSpread"]
        rental = MARKET_SOURCE_2024_BY_METRIC_ID["core_rentalYield"]
        oo_dti = MARKET_SOURCE_2024_BY_METRIC_ID["core_ooDebtToIncome"]
        mortgage = MARKET_SOURCE_2024_BY_METRIC_ID["core_mortgageApprovals"]
        transactions = MARKET_SOURCE_2024_BY_METRIC_ID["core_housingTransactions"]
        dti = MARKET_SOURCE_2024_BY_METRIC_ID["core_debtToIncome"]
        growth = MARKET_SOURCE_2024_BY_METRIC_ID["core_housePriceGrowth"]
        pti = MARKET_SOURCE_2024_BY_METRIC_ID["core_priceToIncome"]

        self.assertAlmostEqual(hpi_mean.normalized_source_value or 0.0, HPI_2024_REBASED_MEAN)
        self.assertAlmostEqual(hpi_std.normalized_source_value or 0.0, HPI_FULL_HISTORY_REBASED_STD)
        self.assertAlmostEqual(hpi_cycle.normalized_source_value or 0.0, HPI_2024_CYCLE_PERIOD_MONTHS)
        self.assertAlmostEqual(mortgage.normalized_source_value or 0.0, 62.86358333333334)
        self.assertAlmostEqual(transactions.normalized_source_value or 0.0, 91.23416666666667)
        self.assertAlmostEqual(dti.normalized_source_value or 0.0, 136.84725453089672)
        self.assertAlmostEqual(growth.normalized_source_value or 0.0, 0.5421916778233726)
        self.assertAlmostEqual(pti.normalized_source_value or 0.0, 4.916288221210461)
        self.assertAlmostEqual(spread.normalized_source_value or 0.0, 0.5411981033650148)
        self.assertAlmostEqual(rental.normalized_source_value or 0.0, 6.9275)
        self.assertAlmostEqual(oo_dti.normalized_source_value or 0.0, 78.79686928898442)

    def test_locked_boe_housing_tools_values_are_active_for_macro_targets(self) -> None:
        self.assertEqual(len(BOE_HOUSING_TOOLS_2024_VALUES_BY_METRIC_ID["core_mortgageApprovals"]), 12)
        self.assertEqual(len(BOE_HOUSING_TOOLS_2024_VALUES_BY_METRIC_ID["core_housingTransactions"]), 12)
        self.assertEqual(len(BOE_HOUSING_TOOLS_2024_VALUES_BY_METRIC_ID["core_debtToIncome"]), 4)
        self.assertEqual(len(BOE_HOUSING_TOOLS_2024_VALUES_BY_METRIC_ID["core_housePriceGrowth"]), 12)
        self.assertEqual(len(BOE_HOUSING_TOOLS_2024_VALUES_BY_METRIC_ID["core_priceToIncome"]), 4)

        for metric_id in (
            "core_mortgageApprovals",
            "core_housingTransactions",
            "core_debtToIncome",
            "core_housePriceGrowth",
            "core_priceToIncome",
        ):
            source = MARKET_SOURCE_2024_BY_METRIC_ID[metric_id]
            target = TARGETS_BY_ID[metric_id]
            self.assertEqual(source.source_document_path, "input-data-versions/validation-sources/2024/boe/housing-tools.xlsx")
            self.assertIs(target.source_metadata, source)

    def test_locked_quarterly_ranges_are_exposed_via_target_catalog(self) -> None:
        self.assertEqual(HPI_TARGET_TOLERANCE, 0.05)
        self.assertAlmostEqual(TARGETS_BY_ID["core_hpiMean"].target_band.lower, HPI_2024_REBASED_MEAN * (1.0 - HPI_TARGET_TOLERANCE))
        self.assertAlmostEqual(TARGETS_BY_ID["core_hpiMean"].target_band.upper, HPI_2024_REBASED_MEAN * (1.0 + HPI_TARGET_TOLERANCE))
        self.assertAlmostEqual(
            TARGETS_BY_ID["core_hpiStd"].target_band.lower,
            HPI_FULL_HISTORY_REBASED_STD * (1.0 - HPI_TARGET_TOLERANCE),
        )
        self.assertAlmostEqual(
            TARGETS_BY_ID["core_hpiStd"].target_band.upper,
            HPI_FULL_HISTORY_REBASED_STD * (1.0 + HPI_TARGET_TOLERANCE),
        )
        self.assertAlmostEqual(
            TARGETS_BY_ID["core_hpiCyclePeriod"].target_band.lower,
            HPI_2024_CYCLE_PERIOD_MONTHS * (1.0 - HPI_TARGET_TOLERANCE),
        )
        self.assertAlmostEqual(
            TARGETS_BY_ID["core_hpiCyclePeriod"].target_band.upper,
            HPI_2024_CYCLE_PERIOD_MONTHS * (1.0 + HPI_TARGET_TOLERANCE),
        )
        self.assertAlmostEqual(TARGETS_BY_ID["core_interestRateSpread"].target_band.lower, min(INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS))
        self.assertAlmostEqual(TARGETS_BY_ID["core_interestRateSpread"].target_band.upper, max(INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS))
        self.assertAlmostEqual(TARGETS_BY_ID["core_mortgageApprovals"].target_band.lower, 55.575)
        self.assertAlmostEqual(TARGETS_BY_ID["core_mortgageApprovals"].target_band.upper, 68.073)
        self.assertAlmostEqual(TARGETS_BY_ID["core_housingTransactions"].target_band.lower, 82.43)
        self.assertAlmostEqual(TARGETS_BY_ID["core_housingTransactions"].target_band.upper, 100.83)
        self.assertAlmostEqual(TARGETS_BY_ID["core_debtToIncome"].target_band.lower, 133.7791854721206)
        self.assertAlmostEqual(TARGETS_BY_ID["core_debtToIncome"].target_band.upper, 139.0765196216166)
        self.assertAlmostEqual(TARGETS_BY_ID["core_housePriceGrowth"].target_band.lower, -0.675904021628948)
        self.assertAlmostEqual(TARGETS_BY_ID["core_housePriceGrowth"].target_band.upper, 1.069161376545269)
        self.assertAlmostEqual(TARGETS_BY_ID["core_priceToIncome"].target_band.lower, 4.847149441436771)
        self.assertAlmostEqual(TARGETS_BY_ID["core_priceToIncome"].target_band.upper, 4.956292571351748)
        self.assertAlmostEqual(TARGETS_BY_ID["core_rentalYield"].target_band.lower, min(RENTAL_YIELD_2024_QUARTERLY_VALUES))
        self.assertAlmostEqual(TARGETS_BY_ID["core_rentalYield"].target_band.upper, max(RENTAL_YIELD_2024_QUARTERLY_VALUES))
        self.assertAlmostEqual(TARGETS_BY_ID["core_ooDebtToIncome"].target_band.lower, min(OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES))
        self.assertAlmostEqual(TARGETS_BY_ID["core_ooDebtToIncome"].target_band.upper, max(OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES))

    def test_updated_hpi_fixed_tolerance_metadata_does_not_reference_15_percent(self) -> None:
        for metric_id in ("core_hpiMean", "core_hpiStd", "core_hpiCyclePeriod"):
            source = TARGETS_BY_ID[metric_id].source_metadata
            metadata_text = f"{source.band_method or ''} {source.band_notes or ''}"
            self.assertIn("fixed_plus_minus_5pct", source.band_method or "")
            self.assertNotIn("15pct", metadata_text)
            self.assertNotIn("15%", metadata_text)
            self.assertNotIn("+/-15%", metadata_text)

    def test_target_catalog_promotes_market_source_metrics_to_required(self) -> None:
        self.assertEqual(TARGETS_BY_ID["core_hpiMean"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_hpiStd"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_hpiCyclePeriod"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_hpiMean"].units, "rebased index")
        self.assertEqual(TARGETS_BY_ID["core_hpiStd"].units, "rebased index")
        self.assertEqual(TARGETS_BY_ID["core_hpiCyclePeriod"].units, "months")
        self.assertEqual(TARGETS_BY_ID["core_ooDebtToIncome"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_rentalYield"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_interestRateSpread"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_interestRateSpread"].units, "percentage points")
        self.assertEqual(TARGETS_BY_ID["core_mortgageApprovals"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_housingTransactions"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_debtToIncome"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_housePriceGrowth"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_priceToIncome"].requirement, "required")

    def test_wrapper_reexports_canonical_market_mapping(self) -> None:
        self.assertIs(MARKET_SOURCE_2024_BY_METRIC_ID, package_market_sources)


if __name__ == "__main__":
    unittest.main()
