#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the model-speed runtime histogram comparison plot.

@author: Max Stoddard
"""

from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.python.experiments.model import runtime_histogram_comparison


class TestRuntimeHistogramComparison(unittest.TestCase):
    def test_load_runtime_sample_uses_summary_mean_and_run_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "metric_summary": {"wall_clock_seconds": {"mean": 12.5}},
                        "runs": [
                            {"run_id": "run-001", "wall_clock_seconds": 11.0},
                            {"run_id": "run-002", "wall_clock_seconds": 14.0},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            sample = runtime_histogram_comparison.load_runtime_sample(
                summary_path,
                label="Default",
                color="#123456",
            )

        self.assertEqual(sample.label, "Default")
        self.assertEqual(sample.color, "#123456")
        self.assertEqual(sample.runtimes, [11.0, 14.0])
        self.assertEqual(sample.mean, 12.5)

    def test_load_runtime_sample_from_batches_filters_cache_flag_and_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            batches_path = Path(tmp) / "combined_speedup_batches.csv"
            batches_path.write_text(
                "\n".join(
                    [
                        "block_index,run_order_index,cell,cache_enabled,parallel_enabled,source_variant,workers,status,completed_child_count,failed_child_count,canceled_child_count,wall_clock_seconds,throughput_runs_per_hour,raw_json_path",
                        "1,1,A,False,False,cache-off,1,succeeded,40,0,0,747.59,192.6,/tmp/a.json",
                        "1,2,B,True,False,cache-on,1,succeeded,40,0,0,660.558,218.0,/tmp/b.json",
                        "2,3,A,False,False,cache-off,1,failed,39,1,0,700.0,0.0,/tmp/c.json",
                        "2,4,A,False,False,cache-off,1,succeeded,40,0,0,669.644,215.0,/tmp/d.json",
                        "2,5,C,False,True,cache-off,20,succeeded,40,0,0,113.979,1263.4,/tmp/e.json",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            sample = runtime_histogram_comparison.load_runtime_sample_from_batches_csv(
                batches_path,
                label="Cache-off 1 worker",
                color="#123456",
                cache_enabled=False,
                workers=1,
            )

        self.assertEqual(sample.label, "Cache-off 1 worker")
        self.assertEqual(sample.color, "#123456")
        self.assertEqual(sample.runtimes, [747.59, 669.644])
        self.assertAlmostEqual(sample.mean, (747.59 + 669.644) / 2.0)

    def test_load_seed_runtime_sample_from_batches_reads_successful_children(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cache_off_raw = tmp_path / "cache-off.json"
            cache_on_raw = tmp_path / "cache-on.json"
            cache_off_raw.write_text(
                json.dumps(
                    {
                        "batches": [
                            {
                                "children": [
                                    {"status": "succeeded", "wallClockSeconds": 10.0},
                                    {"status": "failed", "wallClockSeconds": 99.0},
                                    {"status": "succeeded", "wallClockSeconds": 11.5},
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            cache_on_raw.write_text(
                json.dumps(
                    {
                        "batches": [
                            {
                                "children": [
                                    {"status": "succeeded", "wallClockSeconds": 8.0},
                                    {"status": "succeeded", "wallClockSeconds": 9.25},
                                ]
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            batches_path = tmp_path / "combined_speedup_batches.csv"
            batches_path.write_text(
                "\n".join(
                    [
                        "block_index,run_order_index,cell,cache_enabled,parallel_enabled,source_variant,workers,status,completed_child_count,failed_child_count,canceled_child_count,wall_clock_seconds,throughput_runs_per_hour,raw_json_path",
                        f"1,1,A,False,False,cache-off,1,succeeded,2,1,0,747.59,192.6,{cache_off_raw}",
                        f"1,2,B,True,False,cache-on,1,succeeded,2,0,0,660.558,218.0,{cache_on_raw}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            sample = runtime_histogram_comparison.load_seed_runtime_sample_from_batches_csv(
                batches_path,
                label="Cache-off seeds",
                color="#123456",
                cache_enabled=False,
                workers=1,
            )

        self.assertEqual(sample.label, "Cache-off seeds")
        self.assertEqual(sample.color, "#123456")
        self.assertEqual(sample.runtimes, [10.0, 11.5])
        self.assertAlmostEqual(sample.mean, 10.75)

    def test_build_integer_second_bin_edges_rounds_outward(self) -> None:
        samples = [
            runtime_histogram_comparison.RuntimeSample("Default", "#123456", [42.8, 47.26], 45.27),
            runtime_histogram_comparison.RuntimeSample("Cache-enabled", "#654321", [39.48, 44.19], 41.83),
        ]

        edges = runtime_histogram_comparison.build_bin_edges(samples, bin_width=1.0)

        self.assertEqual(edges.tolist(), [39.0, 40.0, 41.0, 42.0, 43.0, 44.0, 45.0, 46.0, 47.0, 48.0])

    def test_write_runtime_histogram_creates_requested_format(self) -> None:
        if not runtime_histogram_comparison.HAS_MATPLOTLIB:
            self.skipTest("matplotlib is not installed")

        samples = [
            runtime_histogram_comparison.RuntimeSample("Default", "#4E79A7", [42.8, 43.4, 46.1, 47.3], 44.9),
            runtime_histogram_comparison.RuntimeSample("Cache-enabled", "#E15759", [39.5, 40.4, 42.2, 44.1], 41.6),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_paths = runtime_histogram_comparison.write_runtime_histogram(
                samples,
                output_dir=Path(tmp),
                basename="runtime-histogram",
                formats=("png",),
            )

            self.assertEqual(len(output_paths), 1)
            self.assertTrue(output_paths[0].exists())
            self.assertGreater(output_paths[0].stat().st_size, 0)

    def test_write_runtime_histograms_writes_panel_and_overlay_variants_by_default(self) -> None:
        if not runtime_histogram_comparison.HAS_MATPLOTLIB:
            self.skipTest("matplotlib is not installed")

        samples = [
            runtime_histogram_comparison.RuntimeSample("Default", "#4E79A7", [42.8, 43.4, 46.1, 47.3], 44.9),
            runtime_histogram_comparison.RuntimeSample("Cache-enabled", "#E15759", [39.5, 40.4, 42.2, 44.1], 41.6),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_paths = runtime_histogram_comparison.write_runtime_histograms(
                samples,
                output_dir=Path(tmp),
                basename="runtime-histogram",
                formats=("png",),
            )

            self.assertEqual(
                sorted(path.name for path in output_paths),
                ["runtime-histogram-overlay.png", "runtime-histogram.png"],
            )
            self.assertTrue(all(path.exists() for path in output_paths))

    def test_write_runtime_histograms_can_write_only_overlay_variant(self) -> None:
        if not runtime_histogram_comparison.HAS_MATPLOTLIB:
            self.skipTest("matplotlib is not installed")

        samples = [
            runtime_histogram_comparison.RuntimeSample("Default", "#4E79A7", [42.8, 43.4], 43.1),
            runtime_histogram_comparison.RuntimeSample("Cache-enabled", "#E15759", [39.5, 40.4], 40.0),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            output_paths = runtime_histogram_comparison.write_runtime_histograms(
                samples,
                output_dir=Path(tmp),
                basename="runtime-histogram",
                formats=("png",),
                layout="overlay",
            )

            self.assertEqual([path.name for path in output_paths], ["runtime-histogram-overlay.png"])

    def test_write_runtime_histogram_can_hide_per_run_markers(self) -> None:
        if not runtime_histogram_comparison.HAS_MATPLOTLIB:
            self.skipTest("matplotlib is not installed")

        samples = [
            runtime_histogram_comparison.RuntimeSample("Default", "#4E79A7", [42.8, 43.4], 43.1),
            runtime_histogram_comparison.RuntimeSample("Cache-enabled", "#E15759", [39.5, 40.4], 40.0),
        ]

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            runtime_histogram_comparison,
            "_plot_runtime_markers",
        ) as marker_plot:
            runtime_histogram_comparison.write_runtime_histogram(
                samples,
                output_dir=Path(tmp),
                basename="runtime-histogram",
                formats=("png",),
                show_markers=False,
            )

        marker_plot.assert_not_called()

    def test_markers_anchor_to_axis_line_and_cross_it_for_both_series(self) -> None:
        for layout in ("panels", "overlay"):
            y_min, y_max = runtime_histogram_comparison.marker_axis_y_span(layout)

            self.assertLess(y_min, 0.0)
            self.assertGreater(y_max, 0.0)
            self.assertAlmostEqual(abs(y_min), y_max)

    def test_legend_handles_include_series_colored_mean_lines(self) -> None:
        if not runtime_histogram_comparison.HAS_MATPLOTLIB:
            self.skipTest("matplotlib is not installed")

        samples = [
            runtime_histogram_comparison.RuntimeSample("Default", "#4E79A7", [42.8], 42.8),
            runtime_histogram_comparison.RuntimeSample("Cache-enabled", "#E15759", [39.5], 39.5),
        ]

        handles = runtime_histogram_comparison.build_legend_handles(samples)

        self.assertEqual([handle.get_label() for handle in handles], [
            "Default",
            "Cache-enabled",
            "Default mean",
            "Cache-enabled mean",
        ])
        self.assertEqual(handles[2].get_color(), "#4E79A7")
        self.assertEqual(handles[3].get_color(), "#E15759")

    def test_count_tick_step_scales_up_for_dense_histograms(self) -> None:
        self.assertEqual(runtime_histogram_comparison.count_tick_step(4.0), 1.0)
        self.assertEqual(runtime_histogram_comparison.count_tick_step(18.0), 2.0)
        self.assertEqual(runtime_histogram_comparison.count_tick_step(48.0), 5.0)
        self.assertEqual(runtime_histogram_comparison.count_tick_step(172.0), 20.0)

    def test_runtime_tick_step_stays_readable_for_subsecond_bin_widths(self) -> None:
        self.assertEqual(runtime_histogram_comparison.runtime_tick_step(0.5), 1.0)
        self.assertEqual(runtime_histogram_comparison.runtime_tick_step(1.0), 1.0)
        self.assertEqual(runtime_histogram_comparison.runtime_tick_step(2.0), 2.0)

    def test_main_keeps_default_legend_labels_for_batches_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batches_path = tmp_path / "combined_speedup_batches.csv"
            batches_path.write_text(
                "\n".join(
                    [
                        "block_index,run_order_index,cell,cache_enabled,parallel_enabled,source_variant,workers,status,completed_child_count,failed_child_count,canceled_child_count,wall_clock_seconds,throughput_runs_per_hour,raw_json_path",
                        "1,1,A,False,False,cache-off,1,succeeded,40,0,0,747.59,192.6,/tmp/a.json",
                        "1,2,B,True,False,cache-on,1,succeeded,40,0,0,660.558,218.0,/tmp/b.json",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            output_path = tmp_path / "runtime-histogram.png"

            with patch.object(
                runtime_histogram_comparison,
                "write_runtime_histograms",
                return_value=[output_path],
            ) as write_histograms:
                exit_code = runtime_histogram_comparison.main(
                    [
                        "--batches-csv",
                        str(batches_path),
                        "--output-dir",
                        str(tmp_path),
                        "--formats",
                        "png",
                    ]
                )

        self.assertEqual(exit_code, 0)
        samples = write_histograms.call_args.args[0]
        self.assertEqual([sample.label for sample in samples], ["Default", "Cache-enabled"])


if __name__ == "__main__":
    unittest.main()
