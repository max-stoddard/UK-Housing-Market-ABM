#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the combined cache and parallelisation speedup benchmark harness.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.experiments.model import combined_speedup_benchmark


class TestCombinedSpeedupBenchmark(unittest.TestCase):
    def test_build_block_plan_contains_each_factorial_cell_per_block(self) -> None:
        plan = combined_speedup_benchmark.build_block_plan(blocks=2, ordering_seed=20260529)

        self.assertEqual(len(plan), 8)
        self.assertEqual([entry.run_order_index for entry in plan], list(range(1, 9)))
        for block_index in (1, 2):
            block_entries = [entry for entry in plan if entry.block_index == block_index]
            self.assertCountEqual([entry.cell for entry in block_entries], ["A", "B", "C", "D"])
            self.assertEqual({entry.cell: entry.source_variant for entry in block_entries}["A"], "cache-off")
            self.assertEqual({entry.cell: entry.source_variant for entry in block_entries}["B"], "cache-on")
            self.assertEqual({entry.cell: entry.workers for entry in block_entries}["C"], 20)
            self.assertEqual({entry.cell: entry.workers for entry in block_entries}["D"], 20)

    def test_build_block_plan_is_seeded_and_does_not_tune_worker_count(self) -> None:
        left = combined_speedup_benchmark.build_block_plan(blocks=3, ordering_seed=11)
        right = combined_speedup_benchmark.build_block_plan(blocks=3, ordering_seed=11)
        changed = combined_speedup_benchmark.build_block_plan(blocks=3, ordering_seed=12)

        self.assertEqual([entry.cell for entry in left], [entry.cell for entry in right])
        self.assertNotEqual([entry.cell for entry in left], [entry.cell for entry in changed])
        self.assertEqual({entry.workers for entry in left if entry.parallel_enabled}, {20})

    def test_build_dashboard_command_uses_cell_source_workers_and_policy_label(self) -> None:
        entry = combined_speedup_benchmark.BenchmarkPlanEntry(
            block_index=3,
            run_order_index=9,
            cell="D",
            cache_enabled=True,
            parallel_enabled=True,
            source_variant="cache-on",
            workers=20,
        )

        command = combined_speedup_benchmark.build_dashboard_command(
            entry,
            repo_root=Path("/repo/cache-on"),
            output_root=Path("/repo/cache-on/tmp/_report/combined-speedup/cache-on/block003-D"),
        )

        self.assertEqual(command[:3], ["node", "--import", "tsx/esm"])
        self.assertIn("--repo-root", command)
        self.assertIn("/repo/cache-on", command)
        self.assertIn("--workers", command)
        self.assertIn("20", command)
        self.assertIn("--seed-count", command)
        self.assertIn("40", command)
        self.assertIn("--policy-label", command)
        self.assertIn("cache-on-w20-block003-D", command)
        self.assertIn("--java-option", command)
        self.assertIn("-XX:ActiveProcessorCount=1", command)
        self.assertIn("--confirm-expensive", command)

    def test_verify_seed_output_hashes_detects_cross_cell_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = []
            for cell in ("A", "B", "C", "D"):
                children = []
                for seed in (1, 2):
                    output_path = root / cell / f"seed-{seed}" / "output"
                    output_path.mkdir(parents=True)
                    value = "different\n" if cell == "D" and seed == 2 else "same\n"
                    (output_path / "CoreIndicators-run1.csv").write_text(value, encoding="utf-8")
                    (output_path / "Output-run1.csv").write_text("heavy file ignored\n", encoding="utf-8")
                    children.append({"seed": seed, "outputPath": str(output_path), "status": "succeeded"})
                records.append({"block_index": 1, "cell": cell, "children": children})

            with self.assertRaisesRegex(ValueError, "block 1 seed 2"):
                combined_speedup_benchmark.verify_seed_output_hashes(records)

    def test_verify_seed_output_hashes_accepts_matching_cross_cell_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            records = []
            for cell in ("A", "B", "C", "D"):
                children = []
                for seed in (1, 2):
                    output_path = root / cell / f"seed-{seed}" / "output"
                    output_path.mkdir(parents=True)
                    (output_path / "CoreIndicators-run1.csv").write_text(f"same-{seed}\n", encoding="utf-8")
                    children.append({"seed": seed, "outputPath": str(output_path), "status": "succeeded"})
                records.append({"block_index": 1, "cell": cell, "children": children})

            manifests = combined_speedup_benchmark.verify_seed_output_hashes(records)

        self.assertEqual(manifests["complete_blocks"], 1)
        self.assertEqual(manifests["checked_seed_count"], 2)

    def test_hash_output_tree_ignores_worktree_specific_config_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            left = root / "left"
            right = root / "right"
            left.mkdir()
            right.mkdir()
            (left / "config.properties").write_text('DATA_AGE = "/left/input-data-versions/v0/Age.csv"\n', encoding="utf-8")
            (right / "config.properties").write_text('DATA_AGE = "/right/input-data-versions/v0/Age.csv"\n', encoding="utf-8")
            (left / "CoreIndicators-run1.csv").write_text("same\n", encoding="utf-8")
            (right / "CoreIndicators-run1.csv").write_text("same\n", encoding="utf-8")

            self.assertEqual(
                combined_speedup_benchmark.hash_output_tree(left),
                combined_speedup_benchmark.hash_output_tree(right),
            )

    def test_analyze_blocks_reports_geometric_speedups(self) -> None:
        rows = [
            _batch_row(block=1, cell="A", throughput=100.0),
            _batch_row(block=1, cell="B", throughput=125.0),
            _batch_row(block=1, cell="C", throughput=300.0),
            _batch_row(block=1, cell="D", throughput=400.0),
            _batch_row(block=2, cell="A", throughput=200.0),
            _batch_row(block=2, cell="B", throughput=250.0),
            _batch_row(block=2, cell="C", throughput=600.0),
            _batch_row(block=2, cell="D", throughput=800.0),
        ]

        summary = combined_speedup_benchmark.analyze_blocks(rows)

        self.assertEqual(summary["complete_block_count"], 2)
        self.assertAlmostEqual(summary["effects"]["combined"]["estimate"], 4.0)
        self.assertAlmostEqual(summary["effects"]["cache_only"]["estimate"], 1.25)
        self.assertAlmostEqual(summary["effects"]["parallel_only"]["estimate"], 3.0)
        self.assertAlmostEqual(summary["effects"]["interaction"]["estimate"], 4.0 / (1.25 * 3.0))
        self.assertFalse(summary["headline_complete"])

    def test_main_analyze_only_writes_summary_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            batches_csv = root / "combined_speedup_batches.csv"
            output_root = root / "out"
            _write_batches_csv(
                batches_csv,
                [
                    _batch_row(block=1, cell="A", throughput=100.0),
                    _batch_row(block=1, cell="B", throughput=110.0),
                    _batch_row(block=1, cell="C", throughput=300.0),
                    _batch_row(block=1, cell="D", throughput=330.0),
                ],
            )

            exit_code = combined_speedup_benchmark.main(
                ["analyze", "--batches-csv", str(batches_csv), "--output-root", str(output_root)]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_root / "combined_speedup_results.csv").exists())
            self.assertTrue((output_root / "combined_speedup_blocks.csv").exists())
            self.assertTrue((output_root / "combined_speedup_summary.json").exists())
            self.assertTrue((output_root / "combined_speedup_factorial_model.json").exists())
            summary = json.loads((output_root / "combined_speedup_summary.json").read_text(encoding="utf-8"))
            self.assertAlmostEqual(summary["effects"]["combined"]["estimate"], 3.3)


def _batch_row(block: int, cell: str, throughput: float) -> dict[str, object]:
    workers = 1 if cell in {"A", "B"} else 20
    return {
        "block_index": block,
        "cell": cell,
        "cache_enabled": cell in {"B", "D"},
        "parallel_enabled": cell in {"C", "D"},
        "source_variant": "cache-on" if cell in {"B", "D"} else "cache-off",
        "workers": workers,
        "status": "succeeded",
        "completed_child_count": 40,
        "failed_child_count": 0,
        "canceled_child_count": 0,
        "wall_clock_seconds": 40.0 / throughput * 3600.0,
        "throughput_runs_per_hour": throughput,
    }


def _write_batches_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
