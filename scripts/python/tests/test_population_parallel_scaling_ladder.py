#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the population parallel-scaling ladder benchmark.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.experiments.model import population_parallel_scaling_ladder


class TestPopulationParallelScalingLadder(unittest.TestCase):
    def test_build_plan_covers_each_population_once(self) -> None:
        plan = population_parallel_scaling_ladder.build_population_ladder_plan(
            populations=(5_000, 10_000),
            worker_counts=(1, 4),
            repeats=2,
            seed_count=40,
            ordering_seed=20260603,
        )

        self.assertEqual(len(plan), 2)
        self.assertEqual([entry.run_order_index for entry in plan], [1, 2])
        self.assertEqual([entry.target_population for entry in plan], [5_000, 10_000])
        self.assertEqual({entry.seed_count for entry in plan}, {40})
        self.assertEqual({entry.worker_counts for entry in plan}, {(1, 4)})
        self.assertEqual({entry.repeats for entry in plan}, {2})

    def test_dashboard_command_defaults_to_no_active_processor_count_override(self) -> None:
        entry = population_parallel_scaling_ladder.PopulationLadderPlanEntry(
            run_order_index=2,
            target_population=10_000,
            worker_counts=(1, 2, 4, 8),
            repeats=3,
            seed_count=40,
        )

        command = population_parallel_scaling_ladder.build_dashboard_command(
            entry,
            repo_root=Path("/repo"),
            output_root=Path("/out"),
            phase="full",
            confirm_expensive=True,
        )

        self.assertIn("--target-population", command)
        self.assertIn("10000", command)
        self.assertIn("--workers", command)
        self.assertIn("1,2,4,8", command)
        self.assertIn("--repeats", command)
        self.assertIn("3", command)
        self.assertIn("--seed-count", command)
        self.assertIn("40", command)
        self.assertIn("--policy-label", command)
        self.assertIn("default-no-apc-pop10000", command)
        self.assertNotIn("--java-option", command)
        self.assertNotIn("-XX:ActiveProcessorCount=1", command)

    def test_analyze_ladder_outputs_10k_worker_summary_with_requested_columns(self) -> None:
        rows = [
            _batch_row(repeat=1, population=5_000, workers=1, throughput=300.0),
            _batch_row(repeat=1, population=5_000, workers=2, throughput=510.0),
            _batch_row(repeat=1, population=10_000, workers=1, throughput=100.0),
            _batch_row(repeat=2, population=10_000, workers=1, throughput=120.0),
            _batch_row(repeat=1, population=10_000, workers=2, throughput=180.0),
            _batch_row(repeat=2, population=10_000, workers=2, throughput=200.0),
            _batch_row(repeat=1, population=10_000, workers=4, throughput=260.0),
            _batch_row(repeat=2, population=10_000, workers=4, throughput=300.0),
            _batch_row(repeat=1, population=20_000, workers=1, throughput=50.0),
            _batch_row(repeat=1, population=20_000, workers=2, throughput=80.0),
        ]

        analysis = population_parallel_scaling_ladder.analyze_population_worker_ladder(rows)

        table = analysis["tenk_worker_summary"]
        self.assertEqual(
            list(table[0]),
            [
                "workers",
                "tput",
                "tput_ci95_low",
                "tput_ci95_high",
                "speedup",
                "efficiency",
                "marginal_gain",
            ],
        )
        self.assertEqual([row["workers"] for row in table], [1, 2, 4])
        self.assertAlmostEqual(table[0]["tput"], 110.0)
        self.assertAlmostEqual(table[1]["tput"], 190.0)
        self.assertAlmostEqual(table[1]["speedup"], 190.0 / 110.0)
        self.assertAlmostEqual(table[1]["efficiency"], (190.0 / 110.0) / 2.0)
        self.assertAlmostEqual(table[1]["marginal_gain"], 80.0)
        self.assertAlmostEqual(table[2]["marginal_gain"], 45.0)
        self.assertIsNone(table[0]["marginal_gain"])

    def test_analyze_ladder_exports_usl_fit_rows_and_oversubscription_ratios(self) -> None:
        rows = []
        for repeat in (1, 2, 3):
            rows.extend(
                [
                    _batch_row(repeat=repeat, population=20_000, workers=1, throughput=40.0),
                    _batch_row(repeat=repeat, population=20_000, workers=2, throughput=76.0),
                    _batch_row(repeat=repeat, population=20_000, workers=4, throughput=135.0),
                    _batch_row(repeat=repeat, population=20_000, workers=20, throughput=300.0),
                    _batch_row(repeat=repeat, population=20_000, workers=24, throughput=288.0),
                    _batch_row(repeat=repeat, population=20_000, workers=32, throughput=260.0),
                ]
            )

        analysis = population_parallel_scaling_ladder.analyze_population_worker_ladder(rows)

        summary_row = analysis["summary_rows"][0]
        self.assertEqual(summary_row["target_population"], 20_000)
        self.assertAlmostEqual(summary_row["throughput_ratio_24_vs_20"], 288.0 / 300.0)
        self.assertAlmostEqual(summary_row["throughput_ratio_32_vs_20"], 260.0 / 300.0)
        self.assertIsNotNone(summary_row["contention_alpha"])
        self.assertIsNotNone(summary_row["coherency_beta"])
        self.assertIsNotNone(summary_row["r_squared"])
        self.assertEqual(summary_row["usl_included_workers"], "1,2,4,20,24,32")

        fit_rows = analysis["usl_fit_rows"]
        self.assertEqual({row["target_population"] for row in fit_rows}, {20_000})
        self.assertEqual([row["workers"] for row in fit_rows], [1, 2, 4, 20, 24, 32])
        self.assertTrue(all(row["fitted_throughput_per_hour"] is not None for row in fit_rows))
        self.assertTrue(all(row["included_in_fit"] for row in fit_rows))

    def test_main_analyze_writes_population_ladder_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batches_csv = root / "population_parallel_scaling_batches.csv"
            output_root = root / "out"
            _write_batches_csv(
                batches_csv,
                [
                    _batch_row(repeat=1, population=10_000, workers=1, throughput=100.0),
                    _batch_row(repeat=2, population=10_000, workers=1, throughput=120.0),
                    _batch_row(repeat=1, population=10_000, workers=2, throughput=180.0),
                    _batch_row(repeat=2, population=10_000, workers=2, throughput=200.0),
                ],
            )

            exit_code = population_parallel_scaling_ladder.main(
                ["analyze", "--batches-csv", str(batches_csv), "--output-root", str(output_root)]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_root / "population_parallel_scaling_results.csv").exists())
            self.assertTrue((output_root / "population_parallel_scaling_usl_fit.csv").exists())
            self.assertTrue((output_root / "population_parallel_scaling_summary.csv").exists())
            self.assertTrue((output_root / "population_parallel_scaling_summary.json").exists())
            self.assertTrue((output_root / "population_parallel_scaling_10k_worker_summary.csv").exists())
            summary = json.loads(
                (output_root / "population_parallel_scaling_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["target_populations"], [10_000])


def _batch_row(repeat: int, population: int, workers: int, throughput: float) -> dict[str, object]:
    return {
        "repeat_index": repeat,
        "run_order_index": repeat,
        "target_population": population,
        "workers": workers,
        "seed_count": 40,
        "status": "succeeded",
        "completed_child_count": 40,
        "failed_child_count": 0,
        "canceled_child_count": 0,
        "wall_clock_seconds": 40.0 / throughput * 3600.0,
        "throughput_runs_per_hour": throughput,
        "child_mean_wall_clock_seconds": 10.0,
        "child_median_wall_clock_seconds": 10.0,
        "child_p95_wall_clock_seconds": 10.0,
        "raw_json_path": "/tmp/raw.json",
    }


def _write_batches_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
