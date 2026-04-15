"""Tests for locked 2024 UK Finance source evidence.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model import UKF_SOURCE_2024_BY_METRIC_ID as package_ukf_sources
from scripts.python.validation.model.ukf_source_2024 import UKF_SOURCE_2024_BY_METRIC_ID
from scripts.python.validation.model.validation_catalog_2024 import TARGETS_BY_ID


class TestValidationFrameworkUkfSources(unittest.TestCase):
    def test_locked_ukf_values_capture_derived_monthly_means(self) -> None:
        ftb = UKF_SOURCE_2024_BY_METRIC_ID["core_advancesToFTB"]
        hm = UKF_SOURCE_2024_BY_METRIC_ID["core_advancesToHM"]
        btl = UKF_SOURCE_2024_BY_METRIC_ID["core_advancesToBTL"]

        self.assertEqual(ftb.raw_source_value, 334000.0)
        self.assertAlmostEqual(ftb.normalized_source_value or 0.0, 27.833333333333332)
        self.assertEqual(hm.raw_source_value, 288000.0)
        self.assertAlmostEqual(hm.normalized_source_value or 0.0, 24.0)
        self.assertEqual(btl.raw_source_value, 62055.0)
        self.assertAlmostEqual(btl.normalized_source_value or 0.0, 5.17125)

    def test_btl_metric_exposes_all_four_quarterly_references(self) -> None:
        btl = UKF_SOURCE_2024_BY_METRIC_ID["core_advancesToBTL"]
        self.assertEqual(len(btl.source_references), 4)
        self.assertEqual(
            [reference.raw_source_value for reference in btl.source_references],
            [12422.0, 14955.0, 16410.0, 18268.0],
        )
        self.assertTrue(all(reference.source_page == 2 for reference in btl.source_references))

    def test_target_catalog_promotes_advances_metrics_to_required_with_exact_bands(self) -> None:
        self.assertEqual(TARGETS_BY_ID["core_advancesToFTB"].requirement, "required")
        self.assertEqual(TARGETS_BY_ID["core_advancesToFTB"].target_band.lower, 23.658)
        self.assertEqual(TARGETS_BY_ID["core_advancesToFTB"].target_band.upper, 32.008)
        self.assertEqual(TARGETS_BY_ID["core_advancesToHM"].target_band.lower, 20.4)
        self.assertEqual(TARGETS_BY_ID["core_advancesToHM"].target_band.upper, 27.6)
        self.assertEqual(TARGETS_BY_ID["core_advancesToBTL"].target_band.lower, 4.396)
        self.assertEqual(TARGETS_BY_ID["core_advancesToBTL"].target_band.upper, 5.947)

    def test_wrapper_reexports_canonical_ukf_mapping(self) -> None:
        self.assertIs(UKF_SOURCE_2024_BY_METRIC_ID, package_ukf_sources)


if __name__ == "__main__":
    unittest.main()
