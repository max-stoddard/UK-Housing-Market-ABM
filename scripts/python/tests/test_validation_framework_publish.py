"""Tests for 2024 validation publication and runner plumbing.

@author: Max Stoddard
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.python.validation.model.runner import (
    build_validation_summary,
    resolve_was_data_root,
    run_validation_for_version,
)
from scripts.python.validation.model.publish import write_validation_summary


class TestValidationFrameworkPublish(unittest.TestCase):
    def test_write_validation_summary_creates_dashboard_tracked_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            summary = {
                "version": "v-test",
                "schemaVersion": 2,
                "seeds": [1, 2, 3, 4, 5, 6, 7, 8],
                "overallCompositeLoss": 0.25,
                "familySummaries": [],
                "metrics": [],
            }
            output_path = write_validation_summary(repo_root=repo_root, summary=summary)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], "v-test")
            self.assertEqual(output_path.as_posix(), f"{repo_root.as_posix()}/input-data-versions/validation/v-test.json")

    def test_run_validation_for_version_writes_transient_and_tracked_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            version_dir = repo_root / "input-data-versions" / "v-test"
            version_dir.mkdir(parents=True)
            (version_dir / "config.properties").write_text("SEED = 1\n", encoding="utf-8")
            output_dir = repo_root / "tmp" / "validation" / "v-test"

            with patch(
                "scripts.python.validation.model.runner.run_snapshot_local_validation",
                return_value=self._synthetic_seed_results(),
            ):
                summary = run_validation_for_version(
                    repo_root=repo_root,
                    version="v-test",
                    seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                    output_dir=output_dir,
                )

            self.assertEqual(summary["version"], "v-test")
            self.assertTrue((output_dir / "validation_summary.json").exists())
            self.assertTrue((output_dir / "validation_metrics.csv").exists())
            self.assertTrue((output_dir / "validation_seed_results.csv").exists())
            self.assertTrue((output_dir / "validation_summary.md").exists())
            self.assertTrue((repo_root / "input-data-versions" / "validation" / "v-test.json").exists())

    def test_run_validation_for_version_requires_all_eight_canonical_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            version_dir = repo_root / "input-data-versions" / "v-test"
            version_dir.mkdir(parents=True)
            (version_dir / "config.properties").write_text("SEED = 1\n", encoding="utf-8")

            with patch(
                "scripts.python.validation.model.runner.run_snapshot_local_validation",
                return_value=self._synthetic_seed_results()[:-1],
            ):
                with self.assertRaisesRegex(ValueError, "8/8 successful seeds"):
                    run_validation_for_version(
                        repo_root=repo_root,
                        version="v-test",
                        seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                        output_dir=repo_root / "tmp" / "validation" / "v-test",
                    )

    def test_build_validation_summary_rejects_missing_required_target_metadata(self) -> None:
        required_targets = {
            "core_mortgageApprovals": {
                "metric_id": "core_mortgageApprovals",
                "family_id": "macro_credit_activity",
            }
        }
        with self.assertRaisesRegex(RuntimeError, "Missing target metadata"):
            build_validation_summary(
                version="v-test",
                seed_results=[
                    {
                        "seed": 1,
                        "metrics": {"core_mortgageApprovals": 60.0},
                    }
                ]
                * 8,
                seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                targets_by_id=required_targets,
            )

    def test_build_validation_summary_emits_source_provenance_fields(self) -> None:
        summary = build_validation_summary(
            version="v-test",
            seed_results=self._synthetic_seed_results(),
            seeds=[1, 2, 3, 4, 5, 6, 7, 8],
        )
        metric = next(item for item in summary["metrics"] if item["metricId"] == "core_mortgageApprovals")
        self.assertEqual(metric["sourceIndicatorLabel"], "Mortgage approvals")
        self.assertEqual(metric["rawSourceValue"], 61325.0)
        self.assertEqual(metric["sourceValue"], 61.325)
        self.assertEqual(metric["mappingStatus"], "exact_match")

    def test_build_validation_summary_scores_ukf_backed_advances_metrics(self) -> None:
        summary = build_validation_summary(
            version="v-test",
            seed_results=self._synthetic_seed_results(),
            seeds=[1, 2, 3, 4, 5, 6, 7, 8],
        )
        metric = next(item for item in summary["metrics"] if item["metricId"] == "core_advancesToBTL")
        self.assertEqual(metric["sourceLabel"], "UK Finance BTL Mortgage Market Update 2024 (Q1-Q4)")
        self.assertEqual(metric["status"], "fail")
        self.assertEqual(metric["targetBand"], {"lower": 4.396, "upper": 5.947})
        self.assertEqual(len(metric["sourceReferences"]), 4)
        self.assertIsNotNone(metric["metricLoss"])
        self.assertAlmostEqual(metric["lossScale"], 5.17125)
        self.assertEqual(metric["lossScaleBasis"], "source_value")

    def test_market_source_metrics_are_scored_once_required_bands_exist(self) -> None:
        summary = build_validation_summary(
            version="v-test",
            seed_results=self._synthetic_seed_results(),
            seeds=[1, 2, 3, 4, 5, 6, 7, 8],
        )
        oo_dti = next(item for item in summary["metrics"] if item["metricId"] == "core_ooDebtToIncome")
        rental = next(item for item in summary["metrics"] if item["metricId"] == "core_rentalYield")
        spread = next(item for item in summary["metrics"] if item["metricId"] == "core_interestRateSpread")

        self.assertEqual(oo_dti["status"], "fail")
        self.assertEqual(rental["status"], "fail")
        self.assertEqual(spread["status"], "fail")
        self.assertEqual(spread["units"], "percentage points")
        self.assertEqual(len(rental["sourceReferences"]), 4)
        self.assertEqual(len(spread["sourceReferences"]), 4)
        self.assertIsNotNone(oo_dti["metricLoss"])
        self.assertIsNotNone(rental["metricLoss"])
        self.assertIsNotNone(spread["metricLoss"])
        self.assertEqual(oo_dti["lossScaleBasis"], "source_value")
        self.assertEqual(rental["lossScaleBasis"], "source_value")
        self.assertEqual(spread["lossScaleBasis"], "source_value")
        self.assertEqual(len(oo_dti["sourceReferences"]), 5)
        self.assertEqual(
            oo_dti["sourceReferences"][-1]["sourceDocumentPath"],
            "input-data-versions/validation-sources/2024/ons/qwnd-household-gross-disposable-income-2023q2-2024q4.json",
        )

    def test_build_validation_summary_preserves_statuses_while_publishing_loss_scale_audit_fields(self) -> None:
        summary = build_validation_summary(
            version="v-test",
            seed_results=self._synthetic_seed_results(),
            seeds=[1, 2, 3, 4, 5, 6, 7, 8],
        )

        mortgage_approvals = next(item for item in summary["metrics"] if item["metricId"] == "core_mortgageApprovals")
        financial_wealth = next(
            item for item in summary["metrics"] if item["metricId"] == "financial_wealth_distribution_jsd"
        )

        self.assertEqual(mortgage_approvals["status"], "pass")
        self.assertEqual(financial_wealth["status"], "pass")
        self.assertEqual(mortgage_approvals["lossScaleBasis"], "source_value")
        self.assertEqual(financial_wealth["lossScaleBasis"], "target_band_upper")
        self.assertAlmostEqual(financial_wealth["lossScale"], 0.12)

    def test_resolve_was_data_root_uses_parent_checkout_when_worktree_lacks_private_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            worktree_root = project_root / ".worktrees" / "validation-framework-2024"
            worktree_root.mkdir(parents=True)
            was_file = project_root / "private-datasets" / "was" / "was_round_8_hhold_eul_may_2025.privdata"
            was_file.parent.mkdir(parents=True)
            was_file.write_text("header\n", encoding="utf-8")

            resolved = resolve_was_data_root(repo_root=worktree_root, explicit_root=None)
            self.assertEqual(resolved, project_root)

    def _synthetic_seed_results(self) -> list[dict[str, object]]:
        metrics = {
            "core_mortgageApprovals": 60.0,
            "core_housingTransactions": 94.0,
            "core_advancesToFTB": 20.0,
            "core_advancesToHM": 28.0,
            "core_advancesToBTL": 9.0,
            "core_debtToIncome": 135.0,
            "core_priceToIncome": 8.0,
            "core_housePriceGrowth": 1.0,
            "core_ooDebtToIncome": 110.0,
            "core_rentalYield": 4.0,
            "core_interestRateSpread": 1.5,
            "income_distribution_jsd": 0.05,
            "housing_wealth_distribution_jsd": 0.06,
            "financial_wealth_distribution_jsd": 0.07,
        }
        return [
            {
                "seed": seed,
                "outputDir": f"/tmp/seed-{seed}",
                "metrics": metrics,
            }
            for seed in range(1, 9)
        ]
