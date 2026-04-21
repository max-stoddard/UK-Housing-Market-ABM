#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for model-speed manifest contracts under widened output sets."""

from __future__ import annotations

from argparse import Namespace
import tempfile
import unittest
from pathlib import Path

from scripts.model import model_speed


class TestModelSpeedManifestContract(unittest.TestCase):
    def test_write_manifest_sorts_widened_output_file_sets_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "run"
            output_dir.mkdir()
            (output_dir / "Output-run1.csv").write_text("output\n", encoding="utf-8")
            (output_dir / "HouseholdMicroData-run1.csv").write_text("micro\n", encoding="utf-8")
            nested = output_dir / "metadata"
            nested.mkdir()
            (nested / "summary.json").write_text("{}\n", encoding="utf-8")
            manifest_path = Path(tmp_dir) / "model-output.sha256"

            return_code = model_speed.write_manifest(
                Namespace(output_dir=str(output_dir), manifest_path=str(manifest_path))
            )

            self.assertEqual(return_code, 0)
            rel_paths = [
                line.split("  ", 1)[1]
                for line in manifest_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                rel_paths,
                [
                    "HouseholdMicroData-run1.csv",
                    "Output-run1.csv",
                    "metadata/summary.json",
                ],
            )

    def test_exact_compare_reports_extra_opt_in_outputs_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            baseline_manifest = Path(tmp_dir) / "baseline.sha256"
            candidate_manifest = Path(tmp_dir) / "candidate.sha256"
            report_path = Path(tmp_dir) / "exact-report.md"

            baseline_manifest.write_text(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  Output-run1.csv\n",
                encoding="utf-8",
            )
            candidate_manifest.write_text(
                "\n".join(
                    [
                        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa  Output-run1.csv",
                        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb  HouseholdMicroData-run1.csv",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            return_code = model_speed.exact_compare(
                Namespace(
                    baseline_manifest=str(baseline_manifest),
                    candidate_manifest=str(candidate_manifest),
                    report_path=str(report_path),
                )
            )

            self.assertEqual(return_code, 1)
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("status: FAIL", report)
            self.assertIn("Extra files:", report)
            self.assertIn("- HouseholdMicroData-run1.csv", report)


if __name__ == "__main__":
    unittest.main()
