"""Tests for the 2024 validation catalog review and reproducibility audit.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.python.validation.model.catalog_review_2024 import (
    build_live_review_data,
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
        self.assertEqual(payload["core_advancesToFTB"]["target_band"], {"lower": 23.658, "upper": 32.008})
        self.assertEqual(payload["core_advancesToHM"]["target_band"], {"lower": 20.4, "upper": 27.6})
        self.assertEqual(payload["core_advancesToBTL"]["target_band"], {"lower": 4.396, "upper": 5.947})

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
        self.assertEqual(payload["mean_target_band"], {"lower": 0.86673455532926, "upper": 1.172640868974881})
        self.assertEqual(payload["std_target_band"], {"lower": 0.23516966531682607, "upper": 0.3181707236639411})
        self.assertEqual(payload["cycle_target_band"], {"lower": 142.375, "upper": 192.62499999999997})

    def test_spread_monthly_series_reads_twelve_2024_values_from_workbook(self) -> None:
        values = extract_spread_monthly_values_2024(
            Path("input-data-versions/validation-sources/2024/boe/housing-tools.xlsx")
        )
        self.assertEqual(len(values), 12)
        self.assertAlmostEqual(values[0], 0.5278707362670447)
        self.assertAlmostEqual(values[-1], 0.4538682238309004)

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


if __name__ == "__main__":
    unittest.main()
