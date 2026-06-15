#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke tests for the paired cache benchmark shell harness."""

from __future__ import annotations

import subprocess
import unittest


class TestModelSpeedCachePairedHarness(unittest.TestCase):
    def test_help_documents_seed_repeat_and_pairing_options(self) -> None:
        result = subprocess.run(
            ["bash", "scripts/model/run-cache-paired-benchmark.sh", "--help"],
            check=False,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--seed", result.stdout)
        self.assertIn("--repeat", result.stdout)
        self.assertIn("--warmup-pairs", result.stdout)
        self.assertIn("--cache-off-root", result.stdout)
        self.assertIn("--cache-on-root", result.stdout)


if __name__ == "__main__":
    unittest.main()
