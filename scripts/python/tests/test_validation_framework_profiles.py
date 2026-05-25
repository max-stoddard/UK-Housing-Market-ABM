"""Tests for version-gated validation-profile resolution.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model.validation_catalog_2024 import TARGETS_BY_ID as TARGETS_BY_ID_2024
from scripts.python.validation.model.validation_profiles import (
    resolve_reference_validation_profile,
    resolve_validation_profile,
)


class TestValidationFrameworkProfiles(unittest.TestCase):
    def test_resolve_validation_profile_keeps_all_tracked_versions_on_2024(self) -> None:
        v0_profile = resolve_validation_profile("v0")
        latest_profile = resolve_validation_profile("v4.1")

        self.assertEqual(v0_profile.validation_target_year, 2024)
        self.assertEqual(v0_profile.was_dataset, "R8")
        self.assertEqual(latest_profile.validation_target_year, 2024)
        self.assertEqual(latest_profile.was_dataset, "R8")

    def test_resolve_reference_validation_profile_routes_only_v0_family_to_2011_overlay(self) -> None:
        v0_profile = resolve_reference_validation_profile("v0")
        v0o_profile = resolve_reference_validation_profile("v0o")
        v0oo_profile = resolve_reference_validation_profile("v0oo")
        v0o1_profile = resolve_reference_validation_profile("v0o1")
        v0o2_profile = resolve_reference_validation_profile("v0o2")
        v0o3_profile = resolve_reference_validation_profile("v0o3")
        v0o6_profile = resolve_reference_validation_profile("v0o6")
        latest_profile = resolve_reference_validation_profile("v4.1")

        self.assertIsNotNone(v0_profile)
        self.assertEqual(v0_profile.validation_target_year, 2011)
        self.assertEqual(v0_profile.was_dataset, "W3")
        self.assertIs(v0o_profile, v0_profile)
        self.assertIs(v0oo_profile, v0_profile)
        self.assertIs(v0o1_profile, v0_profile)
        self.assertIs(v0o2_profile, v0_profile)
        self.assertIs(v0o3_profile, v0_profile)
        self.assertIs(v0o6_profile, v0_profile)
        self.assertIsNone(latest_profile)

    def test_v0_reference_profile_preserves_metric_ids_while_switching_household_reference_wave(self) -> None:
        v0_profile = resolve_reference_validation_profile("v0")
        assert v0_profile is not None

        self.assertEqual(set(v0_profile.targets_by_id), set(TARGETS_BY_ID_2024))
        self.assertEqual(v0_profile.targets_by_id["income_distribution_jsd"].source_label, "WAS Wave 3")
        self.assertEqual(v0_profile.targets_by_id["housing_wealth_distribution_jsd"].source_label, "WAS Wave 3")
        self.assertEqual(v0_profile.targets_by_id["financial_wealth_distribution_jsd"].source_label, "WAS Wave 3")
        self.assertNotEqual(
            v0_profile.targets_by_id["core_mortgageApprovals"].source_label,
            TARGETS_BY_ID_2024["core_mortgageApprovals"].source_label,
        )
        self.assertNotIn("core_hpiStd", v0_profile.output_series_trailing_months_by_metric)
        self.assertEqual(v0_profile.output_series_trailing_months_by_metric["core_hpiCyclePeriod"], 525)


if __name__ == "__main__":
    unittest.main()
