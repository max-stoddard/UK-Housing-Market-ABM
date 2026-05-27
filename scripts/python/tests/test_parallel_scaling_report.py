#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for parallel scaling report analysis helpers.

@author: Max Stoddard
"""

from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

from scripts.python.experiments.model import parallel_scaling_report


def _batch(
    *,
    batch_id: str,
    workers: int,
    wall_clock_seconds: float,
    status: str = "success",
    child_seconds: list[float] | None = None,
    completed_runs: int | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "batchId": batch_id,
        "workers": workers,
        "status": status,
        "wallClockSeconds": wall_clock_seconds,
    }
    if child_seconds is not None:
        row["children"] = [
            {"childId": f"{batch_id}-{index}", "status": "success", "wallClockSeconds": seconds}
            for index, seconds in enumerate(child_seconds)
        ]
    if completed_runs is not None:
        row["completedRuns"] = completed_runs
    return row


class TestParallelScalingReport(unittest.TestCase):
    def test_throughput_summaries_and_speedup_efficiency(self) -> None:
        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batchResults": [
                    _batch(batch_id="w1-r1", workers=1, wall_clock_seconds=3600.0, child_seconds=[600.0]),
                    _batch(batch_id="w1-r2", workers=1, wall_clock_seconds=1800.0, child_seconds=[900.0]),
                    _batch(batch_id="w2-r1", workers=2, wall_clock_seconds=2400.0, child_seconds=[400.0, 500.0]),
                    _batch(batch_id="w2-r2", workers=2, wall_clock_seconds=2400.0, child_seconds=[450.0, 550.0]),
                    _batch(
                        batch_id="w4-r1",
                        workers=4,
                        wall_clock_seconds=3200.0,
                        child_seconds=[700.0, 710.0, 720.0, 730.0],
                    ),
                    _batch(
                        batch_id="w4-r2",
                        workers=4,
                        wall_clock_seconds=3200.0,
                        child_seconds=[740.0, 750.0, 760.0, 770.0],
                    ),
                ]
            }
        )

        one_worker = self._row_for(analysis, 1)
        two_workers = self._row_for(analysis, 2)
        four_workers = self._row_for(analysis, 4)

        self.assertEqual(one_worker["successful_repeats"], 2)
        self.assertAlmostEqual(one_worker["mean_throughput_per_hour"], 1.5)
        self.assertAlmostEqual(two_workers["mean_throughput_per_hour"], 3.0)
        self.assertAlmostEqual(two_workers["speedup_vs_1_worker"], 2.0)
        self.assertAlmostEqual(two_workers["scaling_efficiency"], 1.0)
        self.assertAlmostEqual(four_workers["mean_throughput_per_hour"], 4.5)
        self.assertAlmostEqual(four_workers["speedup_vs_1_worker"], 3.0)
        self.assertAlmostEqual(four_workers["scaling_efficiency"], 0.75)
        self.assertAlmostEqual(two_workers["child_wall_clock_mean_seconds"], 475.0)
        self.assertAlmostEqual(two_workers["child_wall_clock_median_seconds"], 475.0)
        self.assertAlmostEqual(two_workers["child_wall_clock_p95_seconds"], 542.5)

    def test_confidence_intervals_require_at_least_two_successful_repeats(self) -> None:
        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batches": [
                    _batch(batch_id="w1-r1", workers=1, wall_clock_seconds=3600.0, completed_runs=1),
                    _batch(batch_id="w1-r2", workers=1, wall_clock_seconds=1800.0, completed_runs=1),
                    _batch(batch_id="w8-r1", workers=8, wall_clock_seconds=900.0, completed_runs=4),
                ]
            }
        )

        one_worker = self._row_for(analysis, 1)
        eight_workers = self._row_for(analysis, 8)

        self.assertIsNotNone(one_worker["throughput_ci95_low"])
        self.assertIsNotNone(one_worker["throughput_ci95_high"])
        self.assertIsNone(eight_workers["throughput_ci95_low"])
        self.assertIsNone(eight_workers["throughput_ci95_high"])

    def test_planned_batch_csv_child_count_fields_drive_throughput(self) -> None:
        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batches": [
                    {
                        "batch_id": "w6-r1",
                        "workers": 6,
                        "status": "success",
                        "wall_clock_seconds": 1800.0,
                        "completed_child_count": 3,
                        "failed_child_count": 2,
                        "canceled_child_count": 1,
                    },
                    {
                        "batchId": "w6-r2",
                        "workers": 6,
                        "status": "success",
                        "wallClockSeconds": 900.0,
                        "completedChildCount": 3,
                        "failedChildCount": 0,
                        "canceledChildCount": 0,
                    },
                ]
            }
        )

        row = self._row_for(analysis, 6)
        self.assertEqual(row["successful_repeats"], 2)
        self.assertAlmostEqual(row["mean_throughput_per_hour"], 9.0)

    def test_throughput_field_is_only_used_when_count_or_duration_is_unavailable(self) -> None:
        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batches": [
                    {
                        "batch_id": "w3-r1",
                        "workers": 3,
                        "status": "success",
                        "wall_clock_seconds": 3600.0,
                        "completed_child_count": 4,
                        "throughput_runs_per_hour": 999.0,
                    },
                    {
                        "batchId": "w3-r2",
                        "workers": 3,
                        "status": "success",
                        "throughputRunsPerHour": 6.0,
                    },
                ]
            }
        )

        row = self._row_for(analysis, 3)
        self.assertEqual(row["successful_repeats"], 2)
        self.assertAlmostEqual(row["mean_throughput_per_hour"], 5.0)

    def test_failed_and_canceled_batches_are_excluded_from_analysis(self) -> None:
        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batches": [
                    _batch(batch_id="w1-r1", workers=1, wall_clock_seconds=3600.0, completed_runs=1),
                    _batch(batch_id="w16-r1", workers=16, wall_clock_seconds=120.0, status="failed", completed_runs=32),
                    _batch(batch_id="w24-r1", workers=24, wall_clock_seconds=120.0, status="canceled", completed_runs=48),
                ]
            }
        )

        self.assertEqual([row["workers"] for row in analysis["worker_summaries"]], [1])
        self.assertEqual(len(analysis["successful_batches"]), 1)

    def test_saturating_regression_uses_only_workers_up_to_20(self) -> None:
        core_batches = [
            _batch(batch_id="w1-r1", workers=1, wall_clock_seconds=3600.0, completed_runs=12),
            _batch(batch_id="w8-r1", workers=8, wall_clock_seconds=3600.0, completed_runs=70),
            _batch(batch_id="w20-r1", workers=20, wall_clock_seconds=3600.0, completed_runs=100),
        ]
        oversubscribed_batches = [
            _batch(batch_id="w24-r1", workers=24, wall_clock_seconds=3600.0, completed_runs=500),
            _batch(batch_id="w32-r1", workers=32, wall_clock_seconds=3600.0, completed_runs=800),
        ]
        analysis = parallel_scaling_report.analyze_raw_payload({"batches": core_batches + oversubscribed_batches})
        core_analysis = parallel_scaling_report.analyze_raw_payload({"batches": core_batches})

        regression = analysis["regression"]
        core_regression = core_analysis["regression"]
        self.assertTrue(regression["valid"])
        self.assertEqual(regression["model_name"], "saturating_exponential")
        self.assertEqual(regression["included_workers"], [1, 8, 20])
        self.assertEqual(regression["n"], 3)
        self.assertGreater(regression["asymptote"], 100.0)
        self.assertGreater(regression["k"], 0.0)
        self.assertEqual(set(regression["fitted_values"]), {"1", "8", "20", "24", "32"})
        for workers in (1, 8, 20, 24, 32):
            fitted_value = regression["fitted_values"][str(workers)]
            self.assertEqual(fitted_value["workers"], workers)
            self.assertEqual(fitted_value["extrapolation"], workers > 20)
            expected = regression["asymptote"] * (1.0 - math.exp(-regression["k"] * workers))
            self.assertAlmostEqual(fitted_value["fitted_throughput_per_hour"], expected)

        self.assertAlmostEqual(regression["asymptote"], core_regression["asymptote"])
        self.assertAlmostEqual(regression["k"], core_regression["k"])
        self.assertAlmostEqual(regression["r_squared"], core_regression["r_squared"])

    def test_saturating_regression_can_report_negative_r_squared(self) -> None:
        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batches": [
                    _batch(batch_id="w1-r1", workers=1, wall_clock_seconds=3600.0, completed_runs=100),
                    _batch(batch_id="w8-r1", workers=8, wall_clock_seconds=3600.0, completed_runs=20),
                    _batch(batch_id="w20-r1", workers=20, wall_clock_seconds=3600.0, completed_runs=10),
                ]
            }
        )

        regression = analysis["regression"]
        self.assertTrue(regression["valid"])
        self.assertIsNotNone(regression["r_squared"])
        self.assertLess(regression["r_squared"], 0.0)

    def test_saturating_regression_r_squared_is_none_for_zero_variance_inputs(self) -> None:
        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batches": [
                    _batch(batch_id="w1-r1", workers=1, wall_clock_seconds=3600.0, completed_runs=50),
                    _batch(batch_id="w8-r1", workers=8, wall_clock_seconds=3600.0, completed_runs=50),
                    _batch(batch_id="w20-r1", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
                ]
            }
        )

        regression = analysis["regression"]
        self.assertTrue(regression["valid"])
        self.assertIsNone(regression["r_squared"])

    def test_oversubscription_comparisons_for_24_and_32_against_20(self) -> None:
        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batches": [
                    _batch(batch_id="w1-r1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
                    _batch(batch_id="w20-r1", workers=20, wall_clock_seconds=3600.0, completed_runs=100),
                    _batch(batch_id="w24-r1", workers=24, wall_clock_seconds=3600.0, completed_runs=90),
                    _batch(batch_id="w32-r1", workers=32, wall_clock_seconds=3600.0, completed_runs=80),
                ]
            }
        )

        comparisons = analysis["summary"]["oversubscription_comparisons"]
        self.assertAlmostEqual(comparisons["24"]["throughput_ratio_vs_20"], 0.9)
        self.assertAlmostEqual(comparisons["24"]["throughput_delta_vs_20"], -10.0)
        self.assertAlmostEqual(comparisons["32"]["throughput_ratio_vs_20"], 0.8)
        self.assertAlmostEqual(comparisons["32"]["throughput_delta_vs_20"], -20.0)

    def test_plot_smoke_output_writes_non_empty_pngs(self) -> None:
        if not parallel_scaling_report.HAS_MATPLOTLIB:
            self.skipTest("matplotlib is unavailable")

        analysis = parallel_scaling_report.analyze_raw_payload(
            {
                "batches": [
                    _batch(batch_id="w1-r1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
                    _batch(batch_id="w2-r1", workers=2, wall_clock_seconds=3600.0, completed_runs=19),
                    _batch(batch_id="w20-r1", workers=20, wall_clock_seconds=3600.0, completed_runs=100),
                    _batch(batch_id="w24-r1", workers=24, wall_clock_seconds=3600.0, completed_runs=90),
                ]
            }
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir)
            parallel_scaling_report.write_report_outputs(analysis, output_root)

            for filename in (
                "parallel_scaling_results.csv",
                "parallel_scaling_summary.json",
                "parallel_scaling_regression.json",
                "parallel_scaling_throughput.png",
                "parallel_scaling_batch_time.png",
            ):
                path = output_root / filename
                self.assertTrue(path.exists(), filename)
                self.assertGreater(path.stat().st_size, 0, filename)

    def _row_for(self, analysis: dict[str, object], workers: int) -> dict[str, object]:
        summaries = analysis["worker_summaries"]
        self.assertIsInstance(summaries, list)
        for row in summaries:
            self.assertIsInstance(row, dict)
            if row["workers"] == workers:
                return row
        raise AssertionError(f"Missing summary for {workers} workers")


if __name__ == "__main__":
    unittest.main()
