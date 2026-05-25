"""Tests for the 2024 validation catalog review and reproducibility audit.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.python.validation.model.catalog_review_2024 import (
    build_live_review_data,
    extract_boe_housing_tools_values_2024,
    extract_frs_tenure_values_2024,
    extract_rpi_rebased_values,
    extract_spread_monthly_values_2024,
    load_ons_qwnd_snapshot,
    run_catalog_review,
)
from scripts.python.validation.model.validation_catalog_2024 import (
    FPC_SOURCE_2024_BY_METRIC_ID,
    MARKET_SOURCE_2024_BY_METRIC_ID,
    TARGETS_BY_ID,
)


class TestValidationCatalog2024Review(unittest.TestCase):
    def test_catalog_review_passes_with_complete_repo_local_sources(self) -> None:
        result = run_catalog_review()
        self.assertTrue(result.success, "\n".join(result.errors))

    def test_fpc_review_payload_matches_live_catalog_source_values(self) -> None:
        payload = build_live_review_data()["source_fpc_core_metrics"]
        for metric_id, reviewed in payload.items():
            source = FPC_SOURCE_2024_BY_METRIC_ID[metric_id]
            self.assertAlmostEqual(reviewed["raw_source_value"], source.raw_source_value or 0.0)
            self.assertAlmostEqual(reviewed["normalized_source_value"], source.normalized_source_value or 0.0)
            self.assertEqual(reviewed["source_as_of"], source.source_as_of)
            self.assertEqual(reviewed["mapping_status"], source.mapping_status)

    def test_ukf_advances_target_bands_recompute_with_locked_rounding_rule(self) -> None:
        payload = build_live_review_data()["source_ukf_advances_metrics"]
        self.assertEqual(build_live_review_data()["advances_target_tolerance"], 0.05)
        self.assertEqual(payload["core_advancesToFTB"]["target_band"], {"lower": 26.442, "upper": 29.225})
        self.assertEqual(payload["core_advancesToHM"]["target_band"], {"lower": 22.8, "upper": 25.2})
        self.assertEqual(payload["core_advancesToBTL"]["target_band"], {"lower": 4.913, "upper": 5.43})

    def test_hpi_review_payload_recomputes_rebased_and_cycle_metrics_from_local_source(self) -> None:
        payload = build_live_review_data()["source_market_hpi"]
        self.assertEqual(len(payload["index_sa_2024_values"]), 12)
        self.assertEqual(len(payload["rebased_index_sa_2024_values"]), 12)
        self.assertAlmostEqual(payload["rebased_index_sa_2024_values"][0], 1.0)
        self.assertAlmostEqual(payload["annual_mean"], 1.0196877121520707)
        self.assertEqual(
            payload["full_history_std_window"],
            {"start": "2005-01", "end": "2024-12", "count": 240},
        )
        self.assertAlmostEqual(payload["full_history_std"], 0.2766701944903836)
        self.assertAlmostEqual(payload["cycle_period_months"], 167.5)
        self.assertEqual(payload["hpi_target_tolerance"], 0.05)
        self.assertEqual(payload["mean_target_band"], {"lower": 0.9687033265444671, "upper": 1.0706720977596742})
        self.assertEqual(payload["std_target_band"], {"lower": 0.2628366847658644, "upper": 0.2905037042149028})
        self.assertEqual(payload["cycle_target_band"], {"lower": 159.125, "upper": 175.875})

    def test_spread_monthly_series_reads_twelve_2024_values_from_workbook(self) -> None:
        values = extract_spread_monthly_values_2024(
            Path("input-data-versions/validation-sources/2024/boe/housing-tools.xlsx")
        )
        self.assertEqual(len(values), 12)
        self.assertAlmostEqual(values[0], 0.5278707362670447)
        self.assertAlmostEqual(values[-1], 0.4538682238309004)

    def test_boe_housing_tools_core_series_read_expected_2024_windows_from_workbook(self) -> None:
        workbook_path = Path("input-data-versions/validation-sources/2024/boe/housing-tools.xlsx")
        cases = {
            "core_mortgageApprovals": ("4.Mortgage approvals", 12, 62.86358333333334, {"lower": 55.575, "upper": 68.073}),
            "core_housingTransactions": ("5.Housing transactions", 12, 91.23416666666667, {"lower": 82.43, "upper": 100.83}),
            "core_debtToIncome": (
                "3. Household debt to income",
                4,
                136.84725453089672,
                {"lower": 133.7791854721206, "upper": 139.0765196216166},
            ),
            "core_housePriceGrowth": (
                "6.House price growth",
                12,
                0.5421916778233726,
                {"lower": -0.675904021628948, "upper": 1.069161376545269},
            ),
            "core_priceToIncome": (
                "7.House prices disp. income",
                4,
                4.916288221210461,
                {"lower": 4.847149441436771, "upper": 4.956292571351748},
            ),
        }
        payload = build_live_review_data()["source_boe_housing_tools_core_metrics"]

        for metric_id, (sheet_name, expected_count, expected_mean, expected_band) in cases.items():
            values = extract_boe_housing_tools_values_2024(
                workbook_path,
                sheet_name=sheet_name,
                expected_count=expected_count,
            )
            self.assertEqual(len(values), expected_count, msg=metric_id)
            self.assertEqual(payload[metric_id]["value_count"], expected_count)
            self.assertAlmostEqual(payload[metric_id]["normalized_source_value"], expected_mean)
            self.assertEqual(payload[metric_id]["target_band"], expected_band)
            self.assertAlmostEqual(TARGETS_BY_ID[metric_id].source_metadata.normalized_source_value or 0.0, expected_mean)
            self.assertEqual(TARGETS_BY_ID[metric_id].target_band.lower, expected_band["lower"])
            self.assertEqual(TARGETS_BY_ID[metric_id].target_band.upper, expected_band["upper"])
            self.assertNotEqual(TARGETS_BY_ID[metric_id].source_metadata, FPC_SOURCE_2024_BY_METRIC_ID[metric_id])

    def test_oo_dti_review_uses_repo_local_ons_snapshot_and_local_source_reference(self) -> None:
        snapshot = load_ons_qwnd_snapshot(
            Path("input-data-versions/validation-sources/2024/ons/qwnd-household-gross-disposable-income-2023q2-2024q4.json")
        )
        self.assertEqual(snapshot["2023Q2"], 450301.0)
        self.assertEqual(snapshot["2024Q4"], 488902.0)

        oo_dti = MARKET_SOURCE_2024_BY_METRIC_ID["core_ooDebtToIncome"]
        self.assertTrue(
            any(
                reference.source_document_path
                == "input-data-versions/validation-sources/2024/ons/qwnd-household-gross-disposable-income-2023q2-2024q4.json"
                for reference in oo_dti.source_references
            )
        )

    def test_household_jsd_review_payload_locks_band_and_runtime_mapping(self) -> None:
        payload = build_live_review_data()["metric_definitions_household_jsd"]
        self.assertEqual(
            payload["income_distribution_jsd"],
            {
                "requirement": "required",
                "units": "JSD",
                "source_label": "WAS Round 8",
                "target_band": {"lower": 0.0, "upper": 0.12},
                "legacy_validation_module": "income_dist",
                "results_file_name": "MonthlyGrossEmploymentIncome-run1.csv",
            },
        )

    def test_catalog_assigns_explicit_loss_family_to_every_required_metric(self) -> None:
        expected_families = {
            "core_mortgageApprovals": "positive_level",
            "core_housingTransactions": "positive_level",
            "core_advancesToFTB": "positive_level",
            "core_advancesToHM": "positive_level",
            "core_advancesToBTL": "positive_level",
            "core_debtToIncome": "positive_level",
            "core_priceToIncome": "positive_level",
            "core_housePriceGrowth": "signed_additive",
            "core_hpiMean": "positive_level",
            "core_hpiStd": "positive_level",
            "core_hpiCyclePeriod": "positive_level",
            "rpi_mean": "positive_level",
            "household_owning_share": "bounded_share",
            "household_renting_share": "bounded_share",
            "core_ooDebtToIncome": "positive_level",
            "core_rentalYield": "positive_level",
            "core_interestRateSpread": "signed_additive",
            "income_distribution_jsd": "bounded_low_is_better",
            "housing_wealth_distribution_jsd": "bounded_low_is_better",
            "financial_wealth_distribution_jsd": "bounded_low_is_better",
        }
        self.assertEqual(
            {metric_id: TARGETS_BY_ID[metric_id].loss_family for metric_id in expected_families},
            expected_families,
        )

    def test_new_household_share_and_rpi_sources_recompute_from_retained_artifacts(self) -> None:
        tenure = extract_frs_tenure_values_2024(
            Path("input-data-versions/validation-sources/2024/frs/frs-2023-24-tenure-tables.xlsx")
        )
        self.assertEqual(tenure["household_owning_share"], 65.0)
        self.assertEqual(tenure["household_renting_share"], 19.0)

        rpi_values = extract_rpi_rebased_values(
            Path("input-data-versions/validation-sources/2024/ons-rpi/priceindexofprivaterentsukhistoricalseries-2025-03-26.xlsx"),
            year=2024,
        )
        self.assertEqual(len(rpi_values), 12)
        self.assertAlmostEqual(rpi_values[0], 1.0)
        self.assertAlmostEqual(sum(rpi_values) / len(rpi_values), 1.0404173774620358)
        self.assertAlmostEqual(max(rpi_values), 1.0820584689176576)


if __name__ == "__main__":
    unittest.main()
