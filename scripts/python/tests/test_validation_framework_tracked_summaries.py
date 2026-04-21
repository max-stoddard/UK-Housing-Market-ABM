"""Assertions over tracked 2024 validation summaries.

@author: Max Stoddard
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


class TestValidationFrameworkTrackedSummaries(unittest.TestCase):
    def test_all_tracked_summaries_score_new_required_metrics(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        version_dir = repo_root / "input-data-versions"
        validation_dir = version_dir / "validation"
        versions = sorted(
            [
                path.name
                for path in version_dir.iterdir()
                if path.is_dir() and path.name.startswith("v") and (path / "config.properties").exists()
            ],
            key=lambda version: [int(part) for part in version.removeprefix("v").split(".")],
        )
        required_metric_ids = {
            "core_advancesToFTB",
            "core_advancesToHM",
            "core_advancesToBTL",
            "core_hpiMean",
            "core_hpiStd",
            "core_hpiCyclePeriod",
            "core_interestRateSpread",
            "core_ooDebtToIncome",
            "core_rentalYield",
        }

        for version in versions:
            payload = json.loads((validation_dir / f"{version}.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["schemaVersion"], 3, msg=version)
            self.assertEqual(payload["seeds"], [1, 2, 3, 4, 5, 6, 7, 8], msg=version)
            self.assertNotIn("familySummaries", payload, msg=version)
            metrics_by_id = {metric["metricId"]: metric for metric in payload["metrics"]}
            self.assertEqual(required_metric_ids - set(metrics_by_id), set(), msg=version)

            for metric_id in required_metric_ids:
                metric = metrics_by_id[metric_id]
                self.assertNotEqual(metric["status"], "unsupported", msg=f"{version} {metric_id}")
                self.assertIsNotNone(metric["targetBand"], msg=f"{version} {metric_id}")
                self.assertIsNotNone(metric["insideRate"], msg=f"{version} {metric_id}")
                self.assertIsNotNone(metric["lossScale"], msg=f"{version} {metric_id}")
                self.assertIn(
                    metric["lossScaleBasis"],
                    {"source_value", "target_band_midpoint", "target_band_upper"},
                    msg=f"{version} {metric_id}",
                )
                self.assertIsNotNone(metric["metricLoss"], msg=f"{version} {metric_id}")
                self.assertEqual(metric["metricWeight"], 1.0, msg=f"{version} {metric_id}")
                self.assertNotIn("familyId", metric, msg=f"{version} {metric_id}")


if __name__ == "__main__":
    unittest.main()
