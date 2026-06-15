#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for the seed-1 paired cache benchmark helper."""

from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from scripts.model import model_speed


class TestModelSpeedCachePairedBenchmark(unittest.TestCase):
    def test_build_cache_paired_run_plan_balances_warmups_and_measured_pairs(self) -> None:
        plan = model_speed.build_cache_paired_run_plan(
            seed=1,
            repeat=40,
            warmup_pairs=3,
            ordering_seed=20260603,
        )

        self.assertEqual(len(plan), 86)
        self.assertEqual([entry.run_order_index for entry in plan], list(range(1, 87)))
        self.assertEqual(sum(1 for entry in plan if entry.phase == "warmup"), 6)
        self.assertEqual(sum(1 for entry in plan if entry.phase == "measured"), 80)
        self.assertEqual({entry.seed for entry in plan}, {1})

        for phase, expected_pair_count in (("warmup", 3), ("measured", 40)):
            phase_entries = [entry for entry in plan if entry.phase == phase]
            self.assertEqual(
                sorted({entry.pair_index for entry in phase_entries}),
                list(range(1, expected_pair_count + 1)),
            )
            for pair_index in range(1, expected_pair_count + 1):
                pair_entries = [entry for entry in phase_entries if entry.pair_index == pair_index]
                self.assertEqual(len(pair_entries), 2)
                self.assertCountEqual([entry.variant for entry in pair_entries], ["cache-off", "cache-on"])
                self.assertEqual(abs(pair_entries[0].run_order_index - pair_entries[1].run_order_index), 1)

    def test_build_cache_paired_run_plan_is_deterministic_and_order_seed_sensitive(self) -> None:
        left = model_speed.build_cache_paired_run_plan(seed=1, repeat=8, warmup_pairs=2, ordering_seed=11)
        right = model_speed.build_cache_paired_run_plan(seed=1, repeat=8, warmup_pairs=2, ordering_seed=11)
        changed = model_speed.build_cache_paired_run_plan(seed=1, repeat=8, warmup_pairs=2, ordering_seed=12)

        self.assertEqual(left, right)
        self.assertNotEqual(
            [(entry.phase, entry.pair_index, entry.variant) for entry in left],
            [(entry.phase, entry.pair_index, entry.variant) for entry in changed],
        )

    def test_write_cache_paired_run_plan_uses_unix_line_endings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "run-plan.tsv"
            model_speed.write_cache_paired_run_plan(
                model_speed.build_cache_paired_run_plan(
                    seed=1,
                    repeat=2,
                    warmup_pairs=1,
                    ordering_seed=20260603,
                ),
                output,
            )

            raw_bytes = output.read_bytes()

        self.assertNotIn(b"\r\n", raw_bytes)
        self.assertTrue(raw_bytes.endswith(b"\n"))

    def test_cache_paired_summary_excludes_warmups_and_reports_paired_speedup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            matched_a = _manifest(root, "matched-a.sha256", "a" * 64)
            matched_b = _manifest(root, "matched-b.sha256", "a" * 64)
            rows = [
                _row("warmup", 1, "cache-off", 100.0, matched_a),
                _row("warmup", 1, "cache-on", 1.0, matched_b),
                _row("measured", 1, "cache-off", 10.0, matched_a),
                _row("measured", 1, "cache-on", 5.0, matched_b),
                _row("measured", 2, "cache-off", 20.0, matched_a),
                _row("measured", 2, "cache-on", 10.0, matched_b),
            ]

            summary = model_speed.analyze_cache_paired_runs(rows)

        self.assertEqual(summary["status"], "PASS")
        self.assertEqual(summary["run_count"], 4)
        self.assertEqual(summary["warmup_rows_ignored"], 2)
        self.assertEqual(summary["complete_pair_count"], 2)
        self.assertAlmostEqual(summary["speedup"]["geometric_mean"], 2.0)
        self.assertEqual(summary["output_hash_comparison"]["status"], "PASS")
        self.assertEqual(summary["output_hash_comparison"]["mismatched_pair_count"], 0)

    def test_cache_paired_summary_fails_on_manifest_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache_off_manifest = _manifest(root, "off.sha256", "a" * 64)
            cache_on_manifest = _manifest(root, "on.sha256", "b" * 64)
            summary = model_speed.analyze_cache_paired_runs(
                [
                    _row("measured", 1, "cache-off", 10.0, cache_off_manifest),
                    _row("measured", 1, "cache-on", 9.0, cache_on_manifest),
                ]
            )

        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["output_hash_comparison"]["status"], "FAIL")
        self.assertEqual(summary["output_hash_comparison"]["mismatched_pair_count"], 1)
        self.assertEqual(summary["output_hash_comparison"]["mismatches"][0]["pair_index"], 1)

    def test_cache_paired_summary_cli_returns_nonzero_for_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            runs_tsv = root / "measured-runs.tsv"
            output = root / "paired-summary.json"
            cache_off_manifest = _manifest(root, "off.sha256", "a" * 64)
            cache_on_manifest = _manifest(root, "on.sha256", "b" * 64)
            _write_runs_tsv(
                runs_tsv,
                [
                    _row("measured", 1, "cache-off", 10.0, cache_off_manifest),
                    _row("measured", 1, "cache-on", 9.0, cache_on_manifest),
                ],
            )

            return_code = model_speed.cache_paired_summary(
                Namespace(runs_tsv=str(runs_tsv), output=str(output), expected_repeat=1, expected_seed=1)
            )
            payload = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(return_code, 1)
        self.assertEqual(payload["status"], "FAIL")


def _manifest(root: Path, name: str, digest: str) -> Path:
    path = root / name
    path.write_text(f"{digest}  Output-run1.csv\n", encoding="utf-8")
    return path


def _row(phase: str, pair_index: int, variant: str, seconds: float, manifest_path: Path) -> dict[str, object]:
    return {
        "phase": phase,
        "variant": variant,
        "pair_index": pair_index,
        "run_order_index": pair_index * 2,
        "seed": 1,
        "run_id": f"{phase}-{pair_index:03d}-{variant}",
        "wall_clock_seconds": seconds,
        "model_computing_seconds": seconds - 0.5,
        "seconds_per_household_month": seconds / (20_000 * 2_000),
        "output_bytes": 1234,
        "max_rss_kb": 100_000,
        "user_cpu_seconds": seconds - 0.2,
        "system_cpu_seconds": 0.2,
        "gc_pause_count": 1,
        "gc_pause_time_ms_total": 2.5,
        "config_path": "/tmp/config.properties",
        "output_dir": "/tmp/output",
        "stdout_log": "/tmp/stdout.log",
        "time_file": "/tmp/time.txt",
        "manifest_path": str(manifest_path),
    }


def _write_runs_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    headers = [
        "phase",
        "variant",
        "pair_index",
        "run_order_index",
        "seed",
        "run_id",
        *model_speed.BENCHMARK_NUMERIC_KEYS,
        "config_path",
        "output_dir",
        "stdout_log",
        "time_file",
        "manifest_path",
    ]
    with path.open("w", encoding="utf-8") as handle:
        handle.write("\t".join(headers) + "\n")
        for row in rows:
            handle.write("\t".join(str(row.get(header, "")) for header in headers) + "\n")


if __name__ == "__main__":
    unittest.main()
