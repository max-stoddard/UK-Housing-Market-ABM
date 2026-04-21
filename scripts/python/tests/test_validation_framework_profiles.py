"""Tests for version-gated validation-profile resolution.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model.validation_catalog_2024 import TARGETS_BY_ID as TARGETS_BY_ID_2024
from scripts.python.validation.model.validation_profiles import resolve_validation_profile


class TestValidationFrameworkProfiles(unittest.TestCase):
    def test_resolve_validation_profile_routes_v0_to_2011_and_later_versions_to_2024(self) -> None:
        v0_profile = resolve_validation_profile("v0")
        latest_profile = resolve_validation_profile("v4.1")

        self.assertEqual(v0_profile.validation_target_year, 2011)
        self.assertEqual(v0_profile.was_dataset, "W3")
        self.assertEqual(latest_profile.validation_target_year, 2024)
        self.assertEqual(latest_profile.was_dataset, "R8")

    def test_v0_profile_preserves_metric_ids_while_switching_household_reference_wave(self) -> None:
        v0_profile = resolve_validation_profile("v0")

        self.assertEqual(set(v0_profile.targets_by_id), set(TARGETS_BY_ID_2024))
        self.assertEqual(v0_profile.targets_by_id["income_distribution_jsd"].source_label, "WAS Wave 3")
        self.assertEqual(v0_profile.targets_by_id["housing_wealth_distribution_jsd"].source_label, "WAS Wave 3")
        self.assertEqual(v0_profile.targets_by_id["financial_wealth_distribution_jsd"].source_label, "WAS Wave 3")
        self.assertEqual(
            v0_profile.targets_by_id["core_mortgageApprovals"].source_label,
            TARGETS_BY_ID_2024["core_mortgageApprovals"].source_label,
        )


if __name__ == "__main__":
    unittest.main()
