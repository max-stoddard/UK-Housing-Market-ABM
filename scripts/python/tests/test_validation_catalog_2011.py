"""Tests for the v0-only 2011 reference validation catalog.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model.validation_catalog_2011 import (
    HPI_2011_CYCLE_PERIOD_MONTHS,
    HPI_2011_REBASED_MEAN,
    HPI_2011_REBASED_STD,
    INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS,
    OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES,
    SOURCE_METADATA_2011_BY_METRIC_ID,
    TARGETS_BY_ID,
)


class TestValidationCatalog2011(unittest.TestCase):
    def test_locked_2011_source_values_match_tracked_bundle_derivations(self) -> None:
        self.assertAlmostEqual(
            SOURCE_METADATA_2011_BY_METRIC_ID["core_mortgageApprovals"].normalized_source_value or 0.0,
            49.28633333333333,
        )
        self.assertAlmostEqual(
            SOURCE_METADATA_2011_BY_METRIC_ID["core_debtToIncome"].normalized_source_value or 0.0,
            162.93794051498202,
        )
        self.assertAlmostEqual(
            SOURCE_METADATA_2011_BY_METRIC_ID["core_hpiMean"].normalized_source_value or 0.0,
            HPI_2011_REBASED_MEAN,
        )
        self.assertAlmostEqual(
            SOURCE_METADATA_2011_BY_METRIC_ID["core_hpiStd"].normalized_source_value or 0.0,
            HPI_2011_REBASED_STD,
        )
        self.assertAlmostEqual(
            SOURCE_METADATA_2011_BY_METRIC_ID["core_hpiCyclePeriod"].normalized_source_value or 0.0,
            HPI_2011_CYCLE_PERIOD_MONTHS,
        )
        self.assertAlmostEqual(
            SOURCE_METADATA_2011_BY_METRIC_ID["core_ooDebtToIncome"].normalized_source_value or 0.0,
            99.20166107684075,
        )

    def test_interest_rate_spread_band_uses_corrected_2011_quarterly_mean_range(self) -> None:
        spread = TARGETS_BY_ID["core_interestRateSpread"]

        self.assertAlmostEqual(spread.target_band.lower, min(INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS))
        self.assertAlmostEqual(spread.target_band.upper, max(INTEREST_RATE_SPREAD_2011_QUARTERLY_MEANS))
        self.assertEqual(len(spread.source_metadata.source_references), 4)
        self.assertIn("Q1=2.397573", spread.source_metadata.band_notes or "")
        self.assertIn("Q4=2.626825", spread.source_metadata.band_notes or "")

    def test_weaker_2011_metrics_are_labeled_as_secondary_source_proxies(self) -> None:
        for metric_id in ("core_advancesToFTB", "core_advancesToHM", "core_advancesToBTL", "core_rentalYield"):
            metric = TARGETS_BY_ID[metric_id]
            self.assertIn("Secondary-source proxy", metric.source_label)
            self.assertEqual(
                metric.source_metadata.band_method,
                "fixed_plus_minus_15pct_around_secondary_source_proxy",
            )

    def test_oo_dti_keeps_repo_local_ons_snapshot_reference(self) -> None:
        oo_dti = TARGETS_BY_ID["core_ooDebtToIncome"]

        self.assertAlmostEqual(oo_dti.target_band.lower, min(OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES))
        self.assertAlmostEqual(oo_dti.target_band.upper, max(OO_DEBT_TO_INCOME_2011_QUARTERLY_VALUES))
        self.assertTrue(
            any(
                reference.source_document_path
                == "input-data-versions/validation-sources/2011/ons/qwnd-household-gross-disposable-income-2010q2-2011q4.json"
                for reference in oo_dti.source_metadata.source_references
            )
        )


if __name__ == "__main__":
    unittest.main()
