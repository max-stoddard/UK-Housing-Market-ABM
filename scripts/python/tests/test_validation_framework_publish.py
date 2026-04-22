"""Tests for 2024 validation publication and runner plumbing.

@author: Max Stoddard
"""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.python.validation.model.runner import (
    build_validation_summary,
    resolve_was_data_root,
    run_validation_for_version,
    run_validation_seed,
)
from scripts.python.validation.model.publish import write_validation_summary
from scripts.python.validation.model.validation_profiles import resolve_validation_profile


class TestValidationFrameworkPublish(unittest.TestCase):
    def test_write_validation_summary_creates_dashboard_tracked_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            summary = {
                "version": "v-test",
                "schemaVersion": 3,
                "seeds": [1, 2, 3, 4, 5, 6, 7, 8],
                "overallCompositeLoss": 0.25,
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

    def test_run_validation_for_v0_keeps_tracked_summary_2024_and_writes_2011_reference_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            version_dir = repo_root / "input-data-versions" / "v0"
            version_dir.mkdir(parents=True)
            (version_dir / "config.properties").write_text("SEED = 1\n", encoding="utf-8")
            reference_output_dir = repo_root / "Results" / "v0-output"
            reference_output_dir.mkdir(parents=True)
            output_dir = repo_root / "tmp" / "validation" / "v0"

            with (
                patch(
                    "scripts.python.validation.model.runner.resolve_was_data_root",
                    return_value=repo_root,
                ),
                patch(
                    "scripts.python.validation.model.runner.run_snapshot_local_validation",
                    return_value=self._synthetic_seed_results(),
                ),
                patch(
                    "scripts.python.validation.model.runner._extract_seed_metrics",
                    return_value=self._synthetic_metrics(),
                ),
            ):
                summary = run_validation_for_version(
                    repo_root=repo_root,
                    version="v0",
                    seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                    output_dir=output_dir,
                )

            tracked_summary = json.loads(
                (repo_root / "input-data-versions" / "validation" / "v0.json").read_text(encoding="utf-8")
            )
            reference_summary = json.loads(
                (reference_output_dir / "reference-2011" / "validation_summary.json").read_text(encoding="utf-8")
            )
            tracked_reference_overlay = json.loads(
                (repo_root / "input-data-versions" / "validation-overlays" / "v0-2011.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(summary["validationTargetYear"], 2024)
            self.assertEqual(tracked_summary["validationTargetYear"], 2024)
            self.assertEqual(reference_summary["validationTargetYear"], 2011)
            self.assertEqual(tracked_reference_overlay["validationTargetYear"], 2011)
            self.assertEqual(reference_summary["artifactType"], "reference_overlay")
            self.assertEqual(tracked_reference_overlay["artifactType"], "reference_overlay")
            self.assertEqual(reference_summary["referenceSourceOutputDir"], "Results/v0-output")
            self.assertEqual(
                tracked_reference_overlay["overallCompositeLoss"],
                reference_summary["overallCompositeLoss"],
            )
            self.assertFalse((repo_root / "input-data-versions" / "validation" / "v0-reference-2011.json").exists())

    def test_run_validation_for_version_can_reuse_existing_output_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            version_dir = repo_root / "input-data-versions" / "v-test"
            version_dir.mkdir(parents=True)
            (version_dir / "config.properties").write_text("SEED = 1\n", encoding="utf-8")
            output_dir = repo_root / "tmp" / "validation" / "v-test"
            for seed in range(1, 9):
                (output_dir / f"seed-{seed}").mkdir(parents=True)

            with (
                patch(
                    "scripts.python.validation.model.runner.resolve_was_data_root",
                    return_value=repo_root,
                ),
                patch(
                    "scripts.python.validation.model.runner._extract_seed_metrics",
                    return_value=self._synthetic_metrics(),
                ) as extract_mock,
                patch(
                    "scripts.python.validation.model.runner.run_snapshot_local_validation",
                ) as run_mock,
            ):
                summary = run_validation_for_version(
                    repo_root=repo_root,
                    version="v-test",
                    seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                    output_dir=output_dir,
                    reuse_existing_output=True,
                )

            self.assertEqual(summary["version"], "v-test")
            self.assertEqual(extract_mock.call_count, 8)
            run_mock.assert_not_called()
            self.assertTrue((repo_root / "input-data-versions" / "validation" / "v-test.json").exists())

    def test_run_validation_for_version_can_reuse_cached_seed_results_and_backfill_missing_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            version_dir = repo_root / "input-data-versions" / "v-test"
            version_dir.mkdir(parents=True)
            (version_dir / "config.properties").write_text("SEED = 1\n", encoding="utf-8")
            output_dir = repo_root / "tmp" / "validation" / "v-test"
            output_dir.mkdir(parents=True)
            csv_lines = ["seed,metricId,value,outputDir"]
            for seed in range(1, 9):
                (output_dir / f"seed-{seed}").mkdir(parents=True)
                csv_lines.append(f"{seed},core_mortgageApprovals,60.0,{output_dir / f'seed-{seed}'}")
            (output_dir / "validation_seed_results.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")

            def fake_extract_seed_metrics(*, metric_ids: list[str], **_: object) -> dict[str, float]:
                metrics = self._synthetic_metrics()
                return {metric_id: metrics[metric_id] for metric_id in metric_ids}

            with (
                patch(
                    "scripts.python.validation.model.runner.resolve_was_data_root",
                    return_value=repo_root,
                ),
                patch(
                    "scripts.python.validation.model.runner._extract_seed_metrics",
                    side_effect=fake_extract_seed_metrics,
                ) as extract_mock,
            ):
                summary = run_validation_for_version(
                    repo_root=repo_root,
                    version="v-test",
                    seeds=[1, 2, 3, 4, 5, 6, 7, 8],
                    output_dir=output_dir,
                    reuse_existing_output=True,
                )

            self.assertEqual(summary["version"], "v-test")
            self.assertEqual(extract_mock.call_count, 8)
            self.assertNotIn("core_mortgageApprovals", extract_mock.call_args_list[0].kwargs["metric_ids"])

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

    def test_run_validation_seed_logs_java_start_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            version_dir = repo_root / "input-data-versions" / "v-test"
            version_dir.mkdir(parents=True)
            (version_dir / "config.properties").write_text("SEED = 1\n", encoding="utf-8")
            output_dir = repo_root / "tmp" / "validation" / "v-test"
            stdout = io.StringIO()

            with (
                patch(
                    "scripts.python.validation.model.runner.build_snapshot_local_config_text",
                    return_value="SEED = 3\n",
                ),
                patch(
                    "scripts.python.validation.model.runner.subprocess.run",
                    return_value=subprocess.CompletedProcess(args=["mvn"], returncode=0, stdout="ok"),
                ),
                patch(
                    "scripts.python.validation.model.runner._extract_seed_metrics",
                    return_value=self._synthetic_metrics(),
                ),
                redirect_stdout(stdout),
            ):
                result = run_validation_seed(
                    repo_root=repo_root,
                    version="v-test",
                    seed=3,
                    output_dir=output_dir,
                    maven_bin="mvn",
                    was_data_root=repo_root,
                    validation_profile=resolve_validation_profile("v-test"),
                )

            log_output = stdout.getvalue()
            self.assertEqual(result["seed"], 3)
            self.assertIn("[validation]", log_output)
            self.assertIn("version=v-test", log_output)
            self.assertIn("seed=3", log_output)
            self.assertIn("worker=MainThread", log_output)
            self.assertNotIn("start=", log_output)
            self.assertNotIn("maven=", log_output)
            self.assertNotIn("config=", log_output)
            self.assertNotIn("output_dir=", log_output)

    def test_build_validation_summary_rejects_missing_required_target_metadata(self) -> None:
        required_targets = {
            "core_mortgageApprovals": {
                "metric_id": "core_mortgageApprovals",
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
        self.assertEqual(metric["metricWeight"], 1.0)

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

    def test_build_validation_summary_uses_metric_only_composite_weighting(self) -> None:
        summary = build_validation_summary(
            version="v-test",
            seed_results=self._synthetic_seed_results(),
            seeds=[1, 2, 3, 4, 5, 6, 7, 8],
        )

        scored_metrics = [metric for metric in summary["metrics"] if metric["metricWeight"] == 1.0]
        expected_loss = sum(metric["metricLoss"] for metric in scored_metrics) / len(scored_metrics)
        self.assertAlmostEqual(summary["overallCompositeLoss"], expected_loss)

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

    def test_resolve_was_data_root_accepts_wave_3_only_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            was_file = repo_root / "private-datasets" / "was" / "was_wave_3_hhold_eul_final.dta"
            was_file.parent.mkdir(parents=True)
            was_file.write_text("header\n", encoding="utf-8")

            resolved = resolve_was_data_root(repo_root=repo_root, explicit_root=None)
            self.assertEqual(resolved, repo_root)

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
            "core_hpiMean": 1.02,
            "core_hpiStd": 0.0135,
            "core_hpiCyclePeriod": 170.0,
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

    def _synthetic_metrics(self) -> dict[str, float]:
        return self._synthetic_seed_results()[0]["metrics"]
