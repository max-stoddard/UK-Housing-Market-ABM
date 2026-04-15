"""Tests for locked full-year 2024 market source evidence.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model import MARKET_SOURCE_2024_BY_METRIC_ID as package_market_sources
from scripts.python.validation.model.market_sources_2024 import (
    INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS,
    MARKET_SOURCE_2024_BY_METRIC_ID,
    OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES,
    RENTAL_YIELD_2024_QUARTERLY_VALUES,
)
from scripts.python.validation.model.validation_catalog_2024 import TARGETS_BY_ID


class TestValidationFrameworkMarketSources(unittest.TestCase):
    def test_locked_market_source_means_match_reviewed_2024_values(self) -> None:
        spread = MARKET_SOURCE_2024_BY_METRIC_ID["core_interestRateSpread"]
        rental = MARKET_SOURCE_2024_BY_METRIC_ID["core_rentalYield"]
        oo_dti = MARKET_SOURCE_2024_BY_METRIC_ID["core_ooDebtToIncome"]

        self.assertAlmostEqual(spread.normalized_source_value or 0.0, 0.5411981033650148)
        self.assertAlmostEqual(rental.normalized_source_value or 0.0, 6.9275)
        self.assertAlmostEqual(oo_dti.normalized_source_value or 0.0, 78.79686928898442)

    def test_locked_quarterly_ranges_are_exposed_via_target_catalog(self) -> None:
        self.assertAlmostEqual(TARGETS_BY_ID["core_interestRateSpread"].target_band.lower, min(INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS))
        self.assertAlmostEqual(TARGETS_BY_ID["core_interestRateSpread"].target_band.upper, max(INTEREST_RATE_SPREAD_2024_QUARTERLY_MEANS))
        self.assertAlmostEqual(TARGETS_BY_ID["core_rentalYield"].target_band.lower, min(RENTAL_YIELD_2024_QUARTERLY_VALUES))
        self.assertAlmostEqual(TARGETS_BY_ID["core_rentalYield"].target_band.upper, max(RENTAL_YIELD_2024_QUARTERLY_VALUES))
        self.assertAlmostEqual(TARGETS_BY_ID["core_ooDebtToIncome"].target_band.lower, min(OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES))
        self.assertAlmostEqual(TARGETS_BY_ID["core_ooDebtToIncome"].target_band.upper, max(OO_DEBT_TO_INCOME_2024_QUARTERLY_VALUES))

    def test_target_catalog_promotes_market_source_metrics_to_required(self) -> None:
        self.assertEqual(TARGETS_BY_ID["core_ooDebtToIncome"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_rentalYield"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_interestRateSpread"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_interestRateSpread"].units, "percentage points")

    def test_wrapper_reexports_canonical_market_mapping(self) -> None:
        self.assertIs(MARKET_SOURCE_2024_BY_METRIC_ID, package_market_sources)


if __name__ == "__main__":
    unittest.main()
