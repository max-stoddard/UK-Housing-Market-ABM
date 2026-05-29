#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for parallel scaling report analysis helpers.

@author: Max Stoddard
"""

from __future__ import annotations

import json
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


def _raw_payload(
    label: str,
    batches: list[dict[str, object]],
    java_options: list[str] | None = None,
) -> dict[str, object]:
    return {
        "runId": f"run-{label.lower()}",
        "workload": {
            "policyLabel": label,
            "javaOptions": java_options or [],
            "snapshot": "v0",
            "baseMode": "core-minimal-20k-s1",
            "targetPopulation": 5000,
            "nSteps": 2000,
            "seedCount": 40,
            "workerCounts": [1, 20],
            "repeats": 3,
            "orderingSeed": 20260527,
            "phase": "full",
        },
        "batches": batches,
    }


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

    def test_amdahl_regression_uses_only_workers_up_to_20(self) -> None:
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
        self.assertEqual(regression["model_name"], "amdahl")
        self.assertEqual(regression["included_workers"], [1, 8, 20])
        self.assertEqual(regression["n"], 3)
        self.assertEqual(regression["baseline_throughput_per_hour"], 12.0)
        self.assertGreaterEqual(regression["parallel_fraction"], 0.0)
        self.assertLessEqual(regression["parallel_fraction"], 1.0)
        self.assertEqual(set(regression["fitted_values"]), {"1", "8", "20", "24", "32"})
        for workers in (1, 8, 20, 24, 32):
            fitted_value = regression["fitted_values"][str(workers)]
            self.assertEqual(fitted_value["workers"], workers)
            self.assertEqual(fitted_value["extrapolation"], workers > 20)
            parallel_fraction = regression["parallel_fraction"]
            expected = regression["baseline_throughput_per_hour"] / (
                1.0 - parallel_fraction + parallel_fraction / workers
            )
            self.assertAlmostEqual(fitted_value["fitted_throughput_per_hour"], expected)

        self.assertAlmostEqual(regression["baseline_throughput_per_hour"], core_regression["baseline_throughput_per_hour"])
        self.assertAlmostEqual(regression["parallel_fraction"], core_regression["parallel_fraction"])
        self.assertAlmostEqual(regression["r_squared"], core_regression["r_squared"])

    def test_cached_default_regression_keeps_twenty_worker_training_cutoff(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        raw_json = (
            repo_root
            / "tmp"
            / "_report"
            / "parallel-scaling"
            / "parallel-scaling-20260527T181156Z-765a3a1a"
            / "parallel_scaling_raw.json"
        )
        if not raw_json.exists():
            self.skipTest(f"cached parallel scaling raw JSON is not available: {raw_json}")

        analysis = parallel_scaling_report.analyze_raw_payload(parallel_scaling_report.read_raw_results(raw_json))

        self.assertEqual(analysis["regression"]["model_name"], "amdahl")
        self.assertEqual(analysis["regression"]["included_workers"], [1, 2, 4, 8, 12, 16, 20])

    def test_extra_raw_json_merge_adds_compatible_default_batches(self) -> None:
        primary = _raw_payload(
            "Default",
            [
                _batch(batch_id="base-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
                _batch(batch_id="base-w8", workers=8, wall_clock_seconds=3600.0, completed_runs=70),
                _batch(batch_id="base-w16", workers=16, wall_clock_seconds=3600.0, completed_runs=90),
                _batch(batch_id="base-w20", workers=20, wall_clock_seconds=3600.0, completed_runs=100),
            ],
        )
        del primary["workload"]["policyLabel"]
        del primary["workload"]["javaOptions"]
        extra = _raw_payload(
            "default",
            [
                _batch(batch_id="extra-w8", workers=8, wall_clock_seconds=3600.0, completed_runs=80),
                _batch(batch_id="extra-w16", workers=16, wall_clock_seconds=3600.0, completed_runs=95),
            ],
        )
        extra["workload"]["workerCounts"] = [8, 16]
        extra["workload"]["repeats"] = 3
        extra["workload"]["orderingSeed"] = 12345

        merged = parallel_scaling_report.merge_extra_raw_payloads(primary, [extra])
        analysis = parallel_scaling_report.analyze_raw_payload(merged)

        self.assertEqual(analysis["summary"]["raw_batch_count"], 6)
        self.assertEqual(self._row_for(analysis, 8)["successful_repeats"], 2)
        self.assertEqual(self._row_for(analysis, 16)["successful_repeats"], 2)
        self.assertEqual(analysis["regression"]["included_workers"], [1, 8, 16, 20])

    def test_extra_raw_json_merge_rejects_non_default_or_mismatched_payloads(self) -> None:
        primary = _raw_payload(
            "Default",
            [_batch(batch_id="base-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10)],
        )
        custom_extra = _raw_payload(
            "custom",
            [_batch(batch_id="custom-w8", workers=8, wall_clock_seconds=3600.0, completed_runs=80)],
        )
        mismatched_extra = _raw_payload(
            "default",
            [_batch(batch_id="extra-w8", workers=8, wall_clock_seconds=3600.0, completed_runs=80)],
        )
        mismatched_extra["workload"]["nSteps"] = 3000

        with self.assertRaisesRegex(ValueError, "Default"):
            parallel_scaling_report.merge_extra_raw_payloads(primary, [custom_extra])
        with self.assertRaisesRegex(ValueError, "n_steps"):
            parallel_scaling_report.merge_extra_raw_payloads(primary, [mismatched_extra])
        with self.assertRaisesRegex(TypeError, "mapping-style"):
            parallel_scaling_report.merge_extra_raw_payloads(primary, [[custom_extra]])

    def test_amdahl_regression_can_report_negative_r_squared(self) -> None:
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

    def test_amdahl_regression_r_squared_is_none_for_zero_variance_inputs(self) -> None:
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

    def test_comparison_headline_metrics(self) -> None:
        default = _raw_payload(
            "Default",
            [
                _batch(batch_id="d-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
                _batch(batch_id="d-w20", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
            ],
        )
        apc1 = _raw_payload(
            "APC1",
            [
                _batch(batch_id="a-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=12),
                _batch(batch_id="a-w20", workers=20, wall_clock_seconds=3600.0, completed_runs=66),
            ],
            ["-XX:ActiveProcessorCount=1"],
        )

        comparison = parallel_scaling_report.analyze_comparison(default, apc1)
        headlines = comparison["headline_metrics"]
        self.assertAlmostEqual(headlines["default_20_worker_speedup"], 5.0)
        self.assertAlmostEqual(headlines["apc1_20_worker_speedup"], 5.5)
        self.assertAlmostEqual(headlines["apc1_20_vs_default_20_throughput_ratio"], 1.32)
        self.assertEqual(headlines["default_best"]["workers"], 20)
        self.assertEqual(headlines["apc1_best"]["workers"], 20)

    def test_comparison_rejects_mismatched_workload_metadata(self) -> None:
        batches = [
            _batch(batch_id="w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
            _batch(batch_id="w20", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
        ]
        default = _raw_payload("Default", batches)
        apc1 = _raw_payload("APC1", batches, ["-XX:ActiveProcessorCount=1"])
        apc1["workload"]["nSteps"] = 3000
        apc1["workload"]["orderingSeed"] = 12345

        with self.assertRaisesRegex(ValueError, "n_steps"):
            parallel_scaling_report.analyze_comparison(default, apc1)
        with self.assertRaisesRegex(ValueError, "ordering_seed"):
            parallel_scaling_report.analyze_comparison(default, apc1)

    def test_comparison_rejects_missing_required_workload_metadata(self) -> None:
        batches = [
            _batch(batch_id="w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
            _batch(batch_id="w20", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
        ]
        default = _raw_payload("Default", batches)
        apc1 = _raw_payload("APC1", batches, ["-XX:ActiveProcessorCount=1"])
        del default["workload"]["nSteps"]
        del apc1["workload"]["nSteps"]
        del apc1["workload"]["orderingSeed"]

        with self.assertRaisesRegex(ValueError, "missing.*default.*n_steps"):
            parallel_scaling_report.analyze_comparison(default, apc1)
        with self.assertRaisesRegex(ValueError, "missing.*comparison.*ordering_seed"):
            parallel_scaling_report.analyze_comparison(default, apc1)

    def test_comparison_rejects_swapped_policy_roles(self) -> None:
        batches = [
            _batch(batch_id="w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
            _batch(batch_id="w20", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
        ]
        default = _raw_payload("APC1", batches, ["-XX:ActiveProcessorCount=1"])
        apc1 = _raw_payload("Default", batches)

        with self.assertRaisesRegex(ValueError, "default.*APC1"):
            parallel_scaling_report.analyze_comparison(default, apc1)

    def test_comparison_rejects_non_apc1_comparison_policy(self) -> None:
        batches = [
            _batch(batch_id="w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
            _batch(batch_id="w20", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
        ]
        default = _raw_payload("Default", batches)
        comparison_payload = _raw_payload("Custom", batches)

        with self.assertRaisesRegex(ValueError, "comparison.*APC1"):
            parallel_scaling_report.analyze_comparison(default, comparison_payload)

    def test_comparison_rejects_label_only_apc1_without_jvm_option(self) -> None:
        batches = [
            _batch(batch_id="w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
            _batch(batch_id="w20", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
        ]
        default = _raw_payload("Default", batches)
        comparison_payload = _raw_payload("APC1", batches)

        with self.assertRaisesRegex(ValueError, "comparison.*APC1"):
            parallel_scaling_report.analyze_comparison(default, comparison_payload)

    def test_comparison_accepts_zero_ordering_seed_metadata(self) -> None:
        default = _raw_payload(
            "Default",
            [
                _batch(batch_id="d-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
                _batch(batch_id="d-w20", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
            ],
        )
        apc1 = _raw_payload(
            "APC1",
            [
                _batch(batch_id="a-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=12),
                _batch(batch_id="a-w20", workers=20, wall_clock_seconds=3600.0, completed_runs=66),
            ],
            ["-XX:ActiveProcessorCount=1"],
        )
        default["workload"]["orderingSeed"] = 0
        apc1["workload"]["orderingSeed"] = 0

        comparison = parallel_scaling_report.analyze_comparison(default, apc1)

        self.assertEqual(comparison["default"]["metadata"]["ordering_seed"], 0)
        self.assertEqual(comparison["comparison"]["metadata"]["ordering_seed"], 0)

    def test_comparison_apc1_label_falls_back_to_java_option(self) -> None:
        default = _raw_payload(
            "Default",
            [_batch(batch_id="d-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10)],
        )
        comparison_payload = _raw_payload(
            "",
            [_batch(batch_id="a-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=12)],
            ["-XX:ActiveProcessorCount=1"],
        )
        del comparison_payload["workload"]["policyLabel"]

        comparison = parallel_scaling_report.analyze_comparison(default, comparison_payload)

        self.assertEqual(comparison["comparison"]["label"], "APC1")

    def test_comparison_fit_line_always_spans_one_to_twenty_workers(self) -> None:
        class FakeAxis:
            def __init__(self) -> None:
                self.x_values: list[float] | None = None

            def plot(self, x_values: list[float], *_args: object, **_kwargs: object) -> None:
                self.x_values = x_values

        axis = FakeAxis()

        parallel_scaling_report._plot_amdahl_fit(
            axis,
            regression={"valid": True, "baseline_throughput_per_hour": 10.0, "parallel_fraction": 0.8},
            color="#000000",
            label="fit",
        )

        self.assertIsNotNone(axis.x_values)
        self.assertAlmostEqual(axis.x_values[0], 1.0)
        self.assertAlmostEqual(axis.x_values[-1], 20.0)

    def test_single_run_throughput_plot_limits_ideal_line_extends_fit_and_sets_grid(self) -> None:
        class FakeLocator:
            def __init__(self, base: float) -> None:
                self.base = base

        class FakeAxisScale:
            def __init__(self) -> None:
                self.major_locator: FakeLocator | None = None
                self.minor_locator: FakeLocator | None = None

            def set_major_locator(self, locator: FakeLocator) -> None:
                self.major_locator = locator

            def set_minor_locator(self, locator: FakeLocator) -> None:
                self.minor_locator = locator

        class FakeFigure:
            def tight_layout(self) -> None:
                pass

            def savefig(self, *_args: object, **_kwargs: object) -> None:
                pass

        class FakeAxis:
            def __init__(self) -> None:
                self.plot_calls: list[dict[str, object]] = []
                self.axvline_calls: list[dict[str, object]] = []
                self.text_calls: list[dict[str, object]] = []
                self.xaxis = FakeAxisScale()
                self.yaxis = FakeAxisScale()
                self.xlim_kwargs: dict[str, object] | None = None
                self.grid_calls: list[dict[str, object]] = []
                self.axisbelow: bool | None = None

            def errorbar(self, *_args: object, **_kwargs: object) -> None:
                pass

            def plot(self, x_values: list[float], y_values: list[float], **kwargs: object) -> None:
                self.plot_calls.append({"x_values": x_values, "y_values": y_values, **kwargs})

            def axvline(self, *args: object, **kwargs: object) -> None:
                self.axvline_calls.append({"args": args, **kwargs})

            def text(self, *args: object, **kwargs: object) -> None:
                self.text_calls.append({"args": args, **kwargs})

            def set_xlabel(self, *_args: object, **_kwargs: object) -> None:
                pass

            def set_ylabel(self, *_args: object, **_kwargs: object) -> None:
                pass

            def set_xlim(self, **kwargs: object) -> None:
                self.xlim_kwargs = kwargs

            def grid(self, *_args: object, **kwargs: object) -> None:
                self.grid_calls.append(kwargs)

            def set_axisbelow(self, value: bool) -> None:
                self.axisbelow = value

            def legend(self) -> None:
                pass

        class FakePlot:
            def __init__(self, axis: FakeAxis) -> None:
                self.axis = axis

            def subplots(self, *_args: object, **_kwargs: object) -> tuple[FakeFigure, FakeAxis]:
                return FakeFigure(), self.axis

            def close(self, *_args: object, **_kwargs: object) -> None:
                pass

        axis = FakeAxis()
        original_plt = parallel_scaling_report.plt
        had_locator = hasattr(parallel_scaling_report, "MultipleLocator")
        original_locator = getattr(parallel_scaling_report, "MultipleLocator", None)
        parallel_scaling_report.plt = FakePlot(axis)
        parallel_scaling_report.MultipleLocator = FakeLocator
        try:
            parallel_scaling_report._write_throughput_plot(
                Path("unused.png"),
                [
                    {
                        "workers": 1,
                        "mean_throughput_per_hour": 10.0,
                        "throughput_ci95_low": None,
                        "throughput_ci95_high": None,
                    },
                    {
                        "workers": 20,
                        "mean_throughput_per_hour": 50.0,
                        "throughput_ci95_low": None,
                        "throughput_ci95_high": None,
                    },
                    {
                        "workers": 24,
                        "mean_throughput_per_hour": 48.0,
                        "throughput_ci95_low": None,
                        "throughput_ci95_high": None,
                    },
                    {
                        "workers": 32,
                        "mean_throughput_per_hour": 45.0,
                        "throughput_ci95_low": None,
                        "throughput_ci95_high": None,
                    },
                ],
                {"valid": True, "baseline_throughput_per_hour": 10.0, "parallel_fraction": 0.8},
            )
        finally:
            parallel_scaling_report.plt = original_plt
            if had_locator:
                parallel_scaling_report.MultipleLocator = original_locator
            else:
                delattr(parallel_scaling_report, "MultipleLocator")

        ideal_line = next(call for call in axis.plot_calls if call["label"] == "Ideal linear")
        fit_line = next(call for call in axis.plot_calls if str(call["label"]).startswith("Amdahl fit"))
        self.assertEqual(ideal_line["x_values"], [1, 20])
        self.assertAlmostEqual(fit_line["x_values"][0], 1.0)
        self.assertAlmostEqual(fit_line["x_values"][-1], 32.0)
        self.assertEqual(fit_line["label"], "Amdahl fit (≤ 20 workers)")
        self.assertEqual(axis.xlim_kwargs, {"left": 0})
        self.assertEqual(axis.axvline_calls[0]["label"], "Hardware limit: 20 logical processors")
        self.assertEqual(axis.text_calls[0]["args"][2], "20 cores")
        self.assertEqual(axis.xaxis.major_locator.base if axis.xaxis.major_locator else None, 5)
        self.assertEqual(axis.xaxis.minor_locator.base if axis.xaxis.minor_locator else None, 1)
        self.assertEqual(axis.yaxis.major_locator.base if axis.yaxis.major_locator else None, 2000)
        self.assertEqual(axis.yaxis.minor_locator.base if axis.yaxis.minor_locator else None, 400)
        self.assertEqual(axis.axisbelow, True)
        self.assertTrue(any(call.get("which") == "major" for call in axis.grid_calls))
        self.assertTrue(any(call.get("which") == "minor" for call in axis.grid_calls))

    def test_main_merges_extra_raw_json_for_single_run_reports(self) -> None:
        if not parallel_scaling_report.HAS_MATPLOTLIB:
            self.skipTest("matplotlib is unavailable")

        primary = _raw_payload(
            "Default",
            [
                _batch(batch_id="base-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
                _batch(batch_id="base-w8", workers=8, wall_clock_seconds=3600.0, completed_runs=70),
                _batch(batch_id="base-w16", workers=16, wall_clock_seconds=3600.0, completed_runs=90),
                _batch(batch_id="base-w20", workers=20, wall_clock_seconds=3600.0, completed_runs=100),
            ],
        )
        extra = _raw_payload(
            "default",
            [
                _batch(batch_id="extra-w8", workers=8, wall_clock_seconds=3600.0, completed_runs=80),
                _batch(batch_id="extra-w16", workers=16, wall_clock_seconds=3600.0, completed_runs=95),
            ],
        )
        extra["workload"]["workerCounts"] = [8, 16]

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            primary_path = root / "primary.json"
            extra_path = root / "extra.json"
            output_root = root / "report"
            primary_path.write_text(json.dumps(primary), encoding="utf-8")
            extra_path.write_text(json.dumps(extra), encoding="utf-8")

            exit_code = parallel_scaling_report.main(
                [
                    "--raw-json",
                    str(primary_path),
                    "--extra-raw-json",
                    str(extra_path),
                    "--output-root",
                    str(output_root),
                ]
            )

            summary = json.loads((output_root / "parallel_scaling_summary.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(summary["raw_batch_count"], 6)

    def test_missing_markdown_metric_values_render_as_na(self) -> None:
        self.assertEqual(parallel_scaling_report._format_multiplier(None), "n/a")
        self.assertEqual(parallel_scaling_report._format_percent(None), "n/a")
        self.assertEqual(parallel_scaling_report._format_number(None), "n/a")

    def test_missing_markdown_best_worker_counts_render_as_na(self) -> None:
        comparison = {
            "headline_metrics": {
                "default_20_worker_speedup": None,
                "apc1_20_worker_speedup": None,
                "apc1_20_vs_default_20_throughput_uplift_percent": None,
                "apc1_20_vs_default_20_throughput_ratio": None,
                "default_best": None,
                "apc1_best": None,
            },
            "default": {"metadata": {}},
            "comparison": {"metadata": {}},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "summary.md"
            parallel_scaling_report._write_comparison_markdown(path, comparison)

            markdown = path.read_text(encoding="utf-8")

        self.assertIn("Default best observed throughput: n/a runs/hour at n/a workers", markdown)
        self.assertIn("APC1 best observed throughput: n/a runs/hour at n/a workers", markdown)

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

    def test_comparison_smoke_output_writes_expected_artifacts(self) -> None:
        if not parallel_scaling_report.HAS_MATPLOTLIB:
            self.skipTest("matplotlib is unavailable")

        default = _raw_payload(
            "Default",
            [
                _batch(batch_id="d-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=10),
                _batch(batch_id="d-w20", workers=20, wall_clock_seconds=3600.0, completed_runs=50),
                _batch(batch_id="d-w24", workers=24, wall_clock_seconds=3600.0, completed_runs=48),
                _batch(batch_id="d-w32", workers=32, wall_clock_seconds=3600.0, completed_runs=42),
            ],
        )
        apc1 = _raw_payload(
            "APC1",
            [
                _batch(batch_id="a-w1", workers=1, wall_clock_seconds=3600.0, completed_runs=12),
                _batch(batch_id="a-w20", workers=20, wall_clock_seconds=3600.0, completed_runs=66),
                _batch(batch_id="a-w24", workers=24, wall_clock_seconds=3600.0, completed_runs=63),
                _batch(batch_id="a-w32", workers=32, wall_clock_seconds=3600.0, completed_runs=60),
            ],
            ["-XX:ActiveProcessorCount=1"],
        )
        comparison = parallel_scaling_report.analyze_comparison(default, apc1)

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir)
            parallel_scaling_report.write_comparison_outputs(comparison, output_root)

            for filename in (
                "parallel_scaling_comparison_results.csv",
                "parallel_scaling_comparison_summary.json",
                "parallel_scaling_comparison_regression.json",
                "parallel_scaling_throughput_comparison.png",
                "parallel_scaling_apc1_summary.md",
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
