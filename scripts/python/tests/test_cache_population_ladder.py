#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the rental-income cache population ladder benchmark.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.experiments.model import cache_population_ladder


class TestCachePopulationLadder(unittest.TestCase):
    def test_build_population_ladder_plan_pairs_cache_variants_per_population_block(self) -> None:
        plan = cache_population_ladder.build_population_ladder_plan(
            populations=(1_000, 5_000),
            blocks=2,
            ordering_seed=20260603,
        )

        self.assertEqual(len(plan), 8)
        self.assertEqual([entry.run_order_index for entry in plan], list(range(1, 9)))
        for block_index in (1, 2):
            for population in (1_000, 5_000):
                entries = [
                    entry
                    for entry in plan
                    if entry.block_index == block_index and entry.target_population == population
                ]
                self.assertCountEqual([entry.source_variant for entry in entries], ["cache-off", "cache-on"])
                self.assertEqual({entry.workers for entry in entries}, {20})
                self.assertEqual({entry.seed_count for entry in entries}, {40})

    def test_build_sequential_paired_plan_pairs_variants_per_population_seed(self) -> None:
        plan = cache_population_ladder.build_sequential_paired_plan(
            populations=(5_000, 10_000),
            seeds=(1, 2),
            ordering_seed=20260604,
        )

        self.assertEqual(len(plan), 8)
        self.assertEqual([entry.run_order_index for entry in plan], list(range(1, 9)))
        for population in (5_000, 10_000):
            for seed in (1, 2):
                entries = [entry for entry in plan if entry.target_population == population and entry.seed == seed]
                self.assertEqual(len(entries), 2)
                self.assertEqual(entries[0].pair_order_index, entries[1].pair_order_index)
                self.assertCountEqual([entry.source_variant for entry in entries], ["cache-off", "cache-on"])
                self.assertEqual(abs(entries[0].run_order_index - entries[1].run_order_index), 1)

    def test_build_sequential_paired_plan_is_deterministic_and_order_seed_sensitive(self) -> None:
        left = cache_population_ladder.build_sequential_paired_plan(
            populations=(5_000, 10_000),
            seeds=(1, 2, 3),
            ordering_seed=11,
        )
        right = cache_population_ladder.build_sequential_paired_plan(
            populations=(5_000, 10_000),
            seeds=(1, 2, 3),
            ordering_seed=11,
        )
        changed = cache_population_ladder.build_sequential_paired_plan(
            populations=(5_000, 10_000),
            seeds=(1, 2, 3),
            ordering_seed=12,
        )

        self.assertEqual([entry for entry in left], [entry for entry in right])
        self.assertNotEqual(
            [(entry.target_population, entry.seed, entry.source_variant) for entry in left],
            [(entry.target_population, entry.seed, entry.source_variant) for entry in changed],
        )

    def test_analyze_population_ladder_reports_paired_runtime_speedup(self) -> None:
        rows = [
            _batch_row(block=1, population=5_000, variant="cache-off", child_mean=10.0, throughput=360.0),
            _batch_row(block=1, population=5_000, variant="cache-on", child_mean=8.0, throughput=450.0),
            _batch_row(block=2, population=5_000, variant="cache-off", child_mean=20.0, throughput=180.0),
            _batch_row(block=2, population=5_000, variant="cache-on", child_mean=16.0, throughput=225.0),
            _batch_row(block=1, population=10_000, variant="cache-off", child_mean=25.0, throughput=144.0),
            _batch_row(block=1, population=10_000, variant="cache-on", child_mean=20.0, throughput=180.0),
        ]

        summary = cache_population_ladder.analyze_population_ladder(rows)

        self.assertEqual(summary["complete_population_block_count"], 3)
        by_population = {row["target_population"]: row for row in summary["population_summaries"]}
        self.assertAlmostEqual(by_population[5_000]["runtime_speedup"]["estimate"], 1.25)
        self.assertAlmostEqual(by_population[5_000]["throughput_speedup"]["estimate"], 1.25)
        self.assertEqual(by_population[5_000]["complete_blocks"], 2)
        self.assertEqual(by_population[10_000]["complete_blocks"], 1)

    def test_analyze_sequential_paired_runs_uses_seed_pairs_and_reports_incomplete_pairs(self) -> None:
        rows = [
            _sequential_row(5_000, 1, "cache-off", 10.0),
            _sequential_row(5_000, 1, "cache-on", 8.0),
            _sequential_row(5_000, 2, "cache-off", 20.0),
            _sequential_row(5_000, 2, "cache-on", 10.0),
            _sequential_row(10_000, 1, "cache-off", 30.0),
            _sequential_row(10_000, 1, "cache-on", 20.0),
            _sequential_row(10_000, 2, "cache-off", 40.0),
        ]

        summary = cache_population_ladder.analyze_sequential_paired_runs(rows)

        self.assertEqual(summary["complete_pair_count"], 3)
        self.assertEqual(summary["incomplete_pair_count"], 1)
        by_population = {row["target_population"]: row for row in summary["population_summaries"]}
        self.assertEqual(by_population[5_000]["complete_seed_pairs"], 2)
        self.assertAlmostEqual(by_population[5_000]["geometric_mean_speedup"], (1.25 * 2.0) ** 0.5)
        self.assertEqual(by_population[10_000]["complete_seed_pairs"], 1)
        self.assertEqual(summary["incomplete_pairs"][0]["seed"], 2)

    def test_recommend_sequential_seed_count_selects_largest_safe_n_with_buffer_and_floor(self) -> None:
        rows = [
            _sequential_row(5_000, 1, "cache-off", 13.0),
            _sequential_row(5_000, 1, "cache-on", 13.0),
            _sequential_row(10_000, 1, "cache-off", 28.0),
            _sequential_row(10_000, 1, "cache-on", 28.0),
            _sequential_row(20_000, 1, "cache-off", 55.0),
            _sequential_row(20_000, 1, "cache-on", 55.0),
            _sequential_row(35_000, 1, "cache-off", 97.0),
            _sequential_row(35_000, 1, "cache-on", 97.0),
            _sequential_row(50_000, 1, "cache-off", 159.0),
            _sequential_row(50_000, 1, "cache-on", 159.0),
        ]

        recommendation = cache_population_ladder.recommend_sequential_seed_count(
            rows,
            target_seed_count=40,
            max_hours=10.0,
            buffer_fraction=0.15,
            min_seed_count=25,
        )

        self.assertEqual(recommendation["recommended_seed_count"], 40)
        self.assertTrue(recommendation["launch_recommended"])
        self.assertGreater(recommendation["estimated_full_run_hours"], 7.5)
        self.assertLess(recommendation["estimated_full_run_hours_with_buffer"], 10.0)

    def test_recommend_sequential_seed_count_blocks_when_floor_is_not_safe(self) -> None:
        rows = [
            _sequential_row(5_000, 1, "cache-off", 900.0),
            _sequential_row(5_000, 1, "cache-on", 900.0),
            _sequential_row(10_000, 1, "cache-off", 900.0),
            _sequential_row(10_000, 1, "cache-on", 900.0),
        ]

        recommendation = cache_population_ladder.recommend_sequential_seed_count(
            rows,
            target_seed_count=40,
            max_hours=10.0,
            buffer_fraction=0.15,
            min_seed_count=25,
        )

        self.assertLess(recommendation["recommended_seed_count"], 25)
        self.assertFalse(recommendation["launch_recommended"])

    def test_main_analyze_writes_population_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batches_csv = root / "cache_population_ladder_batches.csv"
            output_root = root / "out"
            _write_batches_csv(
                batches_csv,
                [
                    _batch_row(block=1, population=5_000, variant="cache-off", child_mean=10.0, throughput=360.0),
                    _batch_row(block=1, population=5_000, variant="cache-on", child_mean=8.0, throughput=450.0),
                ],
            )

            exit_code = cache_population_ladder.main(
                ["analyze", "--batches-csv", str(batches_csv), "--output-root", str(output_root)]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_root / "cache_population_ladder_by_population.csv").exists())
            self.assertTrue((output_root / "cache_population_ladder_blocks.csv").exists())
            self.assertTrue((output_root / "cache_population_ladder_summary.json").exists())
            summary = json.loads(
                (output_root / "cache_population_ladder_summary.json").read_text(encoding="utf-8")
            )
            self.assertAlmostEqual(
                summary["population_summaries"][0]["runtime_speedup"]["estimate"],
                1.25,
            )


def _batch_row(block: int, population: int, variant: str, child_mean: float, throughput: float) -> dict[str, object]:
    cache_enabled = variant == "cache-on"
    return {
        "block_index": block,
        "run_order_index": block,
        "target_population": population,
        "cache_enabled": cache_enabled,
        "source_variant": variant,
        "workers": 20,
        "seed_count": 40,
        "status": "succeeded",
        "completed_child_count": 40,
        "failed_child_count": 0,
        "canceled_child_count": 0,
        "wall_clock_seconds": 40.0 / throughput * 3600.0,
        "throughput_runs_per_hour": throughput,
        "child_mean_wall_clock_seconds": child_mean,
        "child_median_wall_clock_seconds": child_mean,
        "child_p95_wall_clock_seconds": child_mean,
        "raw_json_path": "/tmp/raw.json",
    }


def _sequential_row(population: int, seed: int, variant: str, seconds: float, status: str = "succeeded") -> dict[str, object]:
    return {
        "pair_order_index": seed,
        "run_order_index": seed,
        "target_population": population,
        "seed": seed,
        "cache_enabled": variant == "cache-on",
        "source_variant": variant,
        "status": status,
        "run_wall_clock_seconds": seconds,
        "batch_wall_clock_seconds": seconds + 0.1,
        "raw_json_path": "/tmp/raw.json",
    }


def _write_batches_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
