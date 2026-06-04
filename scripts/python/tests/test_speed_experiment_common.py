#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for shared model-speed experiment helpers.

@author: Max Stoddard
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.experiments.model import speed_experiment_common


class TestSpeedExperimentCommon(unittest.TestCase):
    def test_build_parallel_scaling_command_uses_common_dashboard_shape(self) -> None:
        command = speed_experiment_common.build_parallel_scaling_command(
            repo_root=Path("/repo/cache-on"),
            output_root=Path("/repo/out"),
            target_population=20_000,
            workers=20,
            seed_count=40,
            policy_label="cache-on-pop20000-block003",
            phase="full",
            java_options=("-Xmx6g",),
            confirm_expensive=True,
        )

        self.assertEqual(command[:3], ["node", "--import", "tsx/esm"])
        self.assertIn("--repo-root", command)
        self.assertIn("/repo/cache-on", command)
        self.assertIn("--target-population", command)
        self.assertIn("20000", command)
        self.assertIn("--workers", command)
        self.assertIn("20", command)
        self.assertIn("--seed-count", command)
        self.assertIn("40", command)
        self.assertIn("--java-option", command)
        self.assertIn("-Xmx6g", command)
        self.assertIn("--confirm-expensive", command)

    def test_build_parallel_scaling_command_can_pass_explicit_seeds(self) -> None:
        command = speed_experiment_common.build_parallel_scaling_command(
            repo_root=Path("/repo/cache-on"),
            output_root=Path("/repo/out"),
            target_population=5_000,
            workers=1,
            seed_count=1,
            seeds=(17,),
            policy_label="cache-on-pop5000-seed17-pair001",
            phase="full",
            confirm_expensive=True,
        )

        self.assertIn("--seeds", command)
        self.assertIn("17", command)
        self.assertIn("--seed-count", command)
        self.assertIn("1", command)
        self.assertIn("--workers", command)
        self.assertIn("1", command)

    def test_load_parallel_scaling_batch_extracts_child_runtime_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            raw_json = Path(tmp) / "parallel_scaling_raw.json"
            raw_json.write_text(
                json.dumps(
                    {
                        "batches": [
                            {
                                "status": "succeeded",
                                "wallClockSeconds": 20.0,
                                "completedChildCount": 3,
                                "failedChildCount": 0,
                                "canceledChildCount": 0,
                                "throughputRunsPerHour": 540.0,
                                "children": [
                                    {"status": "succeeded", "wallClockSeconds": 10.0},
                                    {"status": "failed", "wallClockSeconds": 99.0},
                                    {"status": "succeeded", "wallClockSeconds": 14.0},
                                    {"status": "succeeded", "wallClockSeconds": 12.0},
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            batch = speed_experiment_common.load_single_parallel_scaling_batch(raw_json)

        self.assertEqual(batch.status, "succeeded")
        self.assertEqual(batch.wall_clock_seconds, 20.0)
        self.assertEqual(batch.completed_child_count, 3)
        self.assertEqual(batch.child_wall_clock_seconds, [10.0, 14.0, 12.0])
        self.assertAlmostEqual(batch.child_mean_wall_clock_seconds, 12.0)
        self.assertAlmostEqual(batch.child_median_wall_clock_seconds, 12.0)
        self.assertAlmostEqual(batch.child_p95_wall_clock_seconds, 14.0)

    def test_effect_summary_reports_geometric_estimate_and_ci(self) -> None:
        summary = speed_experiment_common.effect_summary([1.0, 1.1, 1.2])

        self.assertEqual(summary["n"], 3)
        self.assertGreater(summary["estimate"], 1.0)
        self.assertLess(summary["lower_95_ci"], summary["estimate"])
        self.assertGreater(summary["upper_95_ci"], summary["estimate"])


if __name__ == "__main__":
    unittest.main()
