"""Tests for output-calibration convergence evidence exports.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.python.calibration.output.convergence import (
    build_best_so_far_rows,
    run_convergence_export,
)


class TestOutputCalibrationConvergence(unittest.TestCase):
    def test_best_so_far_rows_track_evaluation_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            member_csv = Path(tmp_dir) / "members.csv"
            self._write_member_csv(member_csv, [0.6, 0.5, 0.7, 0.45])

            rows = build_best_so_far_rows(method="TuRBO", member_csv=member_csv)

            self.assertEqual([row["evaluation"] for row in rows], [1, 2, 3, 4])
            self.assertEqual([row["bestEvaluation"] for row in rows], [1, 2, 2, 4])
            self.assertEqual([row["bestMemberId"] for row in rows], [0, 1, 1, 3])
            self.assertEqual([row["bestSoFarLoss"] for row in rows], [0.6, 0.5, 0.5, 0.45])

    def test_run_convergence_export_writes_combined_curve_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            turbo_csv = root / "turbo.csv"
            smm_csv = root / "smm.csv"
            output_dir = root / "out"
            self._write_member_csv(turbo_csv, [0.6, 0.5, 0.55])
            self._write_member_csv(smm_csv, [0.7, 0.65, 0.62])

            result = run_convergence_export(
                series={"TuRBO": turbo_csv, "SMM grid": smm_csv},
                output_dir=output_dir,
                baseline_loss=0.58,
                baseline_label="Original model",
                target_loss=0.50,
                target_label="TuRBO Optimised Model",
                write_plot=False,
            )

            self.assertEqual(result["summaryRows"][0]["method"], "TuRBO")
            self.assertEqual(result["summaryRows"][0]["bestEvaluation"], 2)
            self.assertAlmostEqual(result["summaryRows"][0]["bestLoss"], 0.5)
            self.assertEqual(result["summaryRows"][1]["method"], "SMM grid")
            self.assertEqual(result["summaryRows"][1]["bestEvaluation"], 3)
            self.assertEqual(result["comparison"]["baselineLabel"], "Original model")
            self.assertAlmostEqual(result["comparison"]["baselineLoss"], 0.58)
            self.assertEqual(result["comparison"]["targetLabel"], "TuRBO Optimised Model")
            self.assertAlmostEqual(result["comparison"]["targetLoss"], 0.50)
            self.assertEqual(result["summaryRows"][0]["firstEvaluationBeatingBaseline"], 2)
            self.assertEqual(result["summaryRows"][0]["firstEvaluationBeatingTarget"], 2)
            self.assertEqual(result["summaryRows"][1]["firstEvaluationBeatingBaseline"], None)
            self.assertEqual(result["summaryRows"][1]["firstEvaluationBeatingTarget"], None)
            self.assertFalse(result["summaryRows"][1]["beatsTarget"])
            self.assertTrue((output_dir / "method_convergence.csv").exists())
            self.assertTrue((output_dir / "method_summary.csv").exists())
            self.assertTrue((output_dir / "method_comparison.json").exists())
            with (output_dir / "method_convergence.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 6)
            self.assertEqual(rows[0]["method"], "TuRBO")
            self.assertEqual(rows[-1]["method"], "SMM grid")

    def _write_member_csv(self, path: Path, losses: list[float]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["iteration", "memberId", "overallCompositeLoss", "rankingLoss", "rankingObjective"],
            )
            writer.writeheader()
            for member_id, loss in enumerate(losses):
                writer.writerow(
                    {
                        "iteration": member_id // 2,
                        "memberId": member_id,
                        "overallCompositeLoss": loss,
                        "rankingLoss": loss,
                        "rankingObjective": "family_aware_metric_loss",
                    }
                )


if __name__ == "__main__":
    unittest.main()
