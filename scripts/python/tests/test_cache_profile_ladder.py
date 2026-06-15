#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the rental-income cache profile analyzer.

@author: Max Stoddard
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.experiments.model import cache_profile_ladder


class TestCacheProfileLadder(unittest.TestCase):
    def test_load_profile_runs_reads_successful_child_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_a = root / "seed-1" / "output"
            output_b = root / "seed-2" / "output"
            output_a.mkdir(parents=True)
            output_b.mkdir(parents=True)
            _write_profile(output_a / "RentalIncomeCacheProfile-run1.json", seed=1, total_queries=10)
            _write_profile(output_b / "RentalIncomeCacheProfile-run1.json", seed=2, total_queries=20)
            raw_json = root / "parallel_scaling_raw.json"
            _write_raw_json(
                raw_json,
                [
                    _child(seed=1, output_path=output_a, status="succeeded", wall_clock_seconds=12.0),
                    _child(seed=2, output_path=output_b, status="succeeded", wall_clock_seconds=14.0),
                    _child(seed=3, output_path=root / "missing", status="failed", wall_clock_seconds=1.0),
                ],
            )

            rows = cache_profile_ladder.load_profile_runs(raw_json)

        self.assertEqual([row["seed"] for row in rows], [1, 2])
        self.assertEqual([row["total_queries"] for row in rows], [10, 20])
        self.assertEqual([row["wall_clock_seconds"] for row in rows], [12.0, 14.0])

    def test_analyze_profile_runs_aggregates_counts_and_rates(self) -> None:
        rows = [
            _profile_row(
                total_queries=10,
                clean_hits=8,
                dirty_recomputes=2,
                positive_contract_queries=6,
                positive_contract_clean_hits=4,
                positive_contract_dirty_queries=2,
                no_cache_equivalent_contract_scans=20,
                cached_contract_scans=6,
                invalidation_events=5,
                dirty_transitions=3,
                redundant_invalidations=2,
                contract_put_events=1,
                contract_replace_events=1,
                contract_remove_events=1,
                payment_state_events=2,
            ),
            _profile_row(
                total_queries=10,
                clean_hits=5,
                dirty_recomputes=5,
                positive_contract_queries=5,
                positive_contract_clean_hits=2,
                positive_contract_dirty_queries=3,
                no_cache_equivalent_contract_scans=10,
                cached_contract_scans=5,
                invalidation_events=4,
                dirty_transitions=4,
                redundant_invalidations=0,
                contract_put_events=2,
                contract_replace_events=0,
                contract_remove_events=1,
                payment_state_events=1,
            ),
        ]

        summary = cache_profile_ladder.analyze_profile_runs(rows)

        self.assertEqual(summary["run_count"], 2)
        self.assertEqual(summary["total_queries"], 20)
        self.assertEqual(summary["cached_contract_scans"], 11)
        self.assertEqual(summary["avoided_contract_scans"], 19)
        self.assertAlmostEqual(summary["hit_rate"], 13 / 20)
        self.assertAlmostEqual(summary["recompute_rate"], 7 / 20)
        self.assertAlmostEqual(summary["positive_contract_hit_rate"], 6 / 11)
        self.assertAlmostEqual(summary["positive_contract_recompute_rate"], 5 / 11)
        self.assertAlmostEqual(summary["avoided_scan_share"], 19 / 30)
        self.assertAlmostEqual(summary["redundant_invalidation_share"], 2 / 9)
        self.assertEqual(summary["invalidation_reason_counts"]["payment_state_events"], 3)

    def test_main_analyze_writes_profile_outputs_from_profile_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile_root = root / "profile"
            run_root = profile_root / "parallel-scaling" / "run-a"
            output = run_root / "batch-1" / "seed-1" / "output"
            output.mkdir(parents=True)
            _write_profile(output / "RentalIncomeCacheProfile-run1.json", seed=1, total_queries=10)
            _write_raw_json(run_root / "parallel_scaling_raw.json", [_child(seed=1, output_path=output)])
            analysis_root = root / "analysis"

            exit_code = cache_profile_ladder.main(
                ["analyze", "--profile-root", str(profile_root), "--output-root", str(analysis_root)]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue((analysis_root / "rental_income_cache_profile_runs.csv").exists())
            self.assertTrue((analysis_root / "rental_income_cache_profile_summary.csv").exists())
            summary_path = analysis_root / "rental_income_cache_profile_summary.json"
            self.assertTrue(summary_path.exists())
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["run_count"], 1)
            self.assertEqual(summary["total_queries"], 10)

    def test_load_profile_runs_resolves_outputs_after_result_root_is_moved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_profile_root = root / "worktree-profile"
            moved_profile_root = root / "main-profile"
            moved_output = moved_profile_root / "parallel-scaling" / "run-a" / "batch-1" / "seed-1" / "output"
            old_output = old_profile_root / "parallel-scaling" / "run-a" / "batch-1" / "seed-1" / "output"
            moved_output.mkdir(parents=True)
            _write_profile(moved_output / "RentalIncomeCacheProfile-run1.json", seed=1, total_queries=10)
            raw_json = moved_profile_root / "parallel-scaling" / "run-a" / "parallel_scaling_raw.json"
            _write_raw_json(raw_json, [_child(seed=1, output_path=old_output)])

            rows = cache_profile_ladder.load_profile_runs(raw_json)

        self.assertEqual(len(rows), 1)
        self.assertEqual(Path(rows[0]["output_path"]), moved_output)


def _write_raw_json(path: Path, children: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "runId": "test-run",
                "batches": [
                    {
                        "batchId": "batch-1",
                        "status": "succeeded",
                        "wallClockSeconds": 20.0,
                        "completedChildCount": len(
                            [child for child in children if child["status"] == "succeeded"]
                        ),
                        "failedChildCount": len([child for child in children if child["status"] == "failed"]),
                        "canceledChildCount": 0,
                        "throughputRunsPerHour": 3600.0,
                        "children": children,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _child(
    *,
    seed: int,
    output_path: Path,
    status: str = "succeeded",
    wall_clock_seconds: float = 12.0,
) -> dict[str, object]:
    return {
        "batchId": "batch-1",
        "taskId": f"task-{seed}",
        "seed": seed,
        "workerIndex": seed % 20,
        "status": status,
        "wallClockSeconds": wall_clock_seconds,
        "configPath": str(output_path.parent / "config" / "config.properties"),
        "outputPath": str(output_path),
    }


def _write_profile(path: Path, *, seed: int, total_queries: int) -> None:
    profile = _profile_row(total_queries=total_queries)
    profile.update({"n_simulation": 1, "seed": seed, "target_population": 20000, "n_steps": 2000})
    path.write_text(json.dumps(profile), encoding="utf-8")


def _profile_row(**overrides: int | float | str) -> dict[str, int | float | str]:
    row: dict[str, int | float | str] = {
        "schema_version": 1,
        "n_simulation": 1,
        "seed": 1,
        "target_population": 20000,
        "n_steps": 2000,
        "total_queries": 10,
        "clean_hits": 7,
        "dirty_queries": 3,
        "positive_contract_queries": 5,
        "positive_contract_clean_hits": 3,
        "positive_contract_dirty_queries": 2,
        "dirty_recomputes": 3,
        "no_cache_equivalent_contract_scans": 20,
        "cached_contract_scans": 5,
        "avoided_contract_scans": 15,
        "max_contracts_scanned_per_recompute": 2,
        "invalidation_events": 4,
        "dirty_transitions": 3,
        "redundant_invalidations": 1,
        "contract_put_events": 1,
        "contract_replace_events": 0,
        "contract_remove_events": 1,
        "payment_state_events": 2,
        "hit_rate": 0.7,
        "recompute_rate": 0.3,
        "positive_contract_hit_rate": 0.6,
        "positive_contract_recompute_rate": 0.4,
        "avoided_scan_share": 0.75,
        "mean_contracts_per_query": 2.0,
        "mean_contracts_per_recompute": 5 / 3,
    }
    row.update(overrides)
    return row


if __name__ == "__main__":
    unittest.main()
