"""Tests for output-calibration convergence evidence exports.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.python.calibration.output.convergence import (
    _write_live_convergence_plot,
    build_best_so_far_rows,
    configure_matplotlib_environment,
    ensure_noninteractive_matplotlib_backend,
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

    def test_plotting_uses_noninteractive_backend_for_threaded_long_runs(self) -> None:
        backend = ensure_noninteractive_matplotlib_backend()

        self.assertEqual(backend.lower(), "agg")

    def test_matplotlib_environment_defaults_are_safe_for_terminal_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with mock.patch.dict(os.environ, {}, clear=True):
                config_dir = configure_matplotlib_environment(default_config_root=Path(tmp_dir))

                self.assertEqual(os.environ["MPLBACKEND"], "Agg")
                self.assertEqual(Path(os.environ["MPLCONFIGDIR"]), config_dir)
                self.assertTrue(config_dir.exists())

    def test_live_plot_options_add_minor_locators_and_dotted_reference_lines(self) -> None:
        import matplotlib.pyplot as plt
        from matplotlib.colors import to_hex
        from matplotlib.ticker import MultipleLocator

        with tempfile.TemporaryDirectory() as tmp_dir:
            plot_path = Path(tmp_dir) / "method_convergence_live.png"
            rows = [
                {
                    "method": "SMM random grid",
                    "evaluation": 1,
                    "medianBestSoFarLoss": 0.62,
                    "p25BestSoFarLoss": 0.61,
                    "p75BestSoFarLoss": 0.63,
                },
                {
                    "method": "SMM random grid",
                    "evaluation": 10,
                    "medianBestSoFarLoss": 0.58,
                    "p25BestSoFarLoss": 0.57,
                    "p75BestSoFarLoss": 0.59,
                },
                {
                    "method": "TuRBO",
                    "evaluation": 1,
                    "medianBestSoFarLoss": 0.6,
                    "p25BestSoFarLoss": 0.59,
                    "p75BestSoFarLoss": 0.61,
                },
                {
                    "method": "TuRBO",
                    "evaluation": 10,
                    "medianBestSoFarLoss": 0.56,
                    "p25BestSoFarLoss": 0.55,
                    "p75BestSoFarLoss": 0.57,
                },
            ]

            with mock.patch.object(plt, "close"):
                try:
                    _write_live_convergence_plot(
                        plot_path,
                        rows,
                        x_minor_step=5.0,
                        y_minor_step=0.004,
                        reference_x=40.0,
                        reference_x_label="TuRBO exploratory Sobol period ends",
                        reference_y_loss=0.5652252115924438,
                        reference_y_label="v0 2011 validation loss",
                    )
                except TypeError as exc:
                    self.fail(f"live plot options should be accepted: {exc}")

            axes = plt.gcf().axes[0]
            self.assertIsInstance(axes.xaxis.get_minor_locator(), MultipleLocator)
            self.assertIsInstance(axes.yaxis.get_minor_locator(), MultipleLocator)
            self.assertEqual(
                list(axes.xaxis.get_minor_locator().tick_values(0.0, 10.0)),
                [-5.0, 0.0, 5.0, 10.0, 15.0],
            )
            self.assertEqual(
                [round(value, 3) for value in axes.yaxis.get_minor_locator().tick_values(0.56, 0.568)],
                [0.556, 0.56, 0.564, 0.568, 0.572],
            )
            lines_by_label = {line.get_label(): line for line in axes.lines}
            x_reference = lines_by_label["TuRBO exploratory Sobol period ends"]
            y_reference = lines_by_label["v0 2011 validation loss"]
            method_colors = {
                to_hex(lines_by_label["SMM random grid"].get_color()).lower(),
                to_hex(lines_by_label["TuRBO"].get_color()).lower(),
            }
            reference_colors = {
                to_hex(x_reference.get_color()).lower(),
                to_hex(y_reference.get_color()).lower(),
            }

            self.assertEqual(x_reference.get_linestyle(), ":")
            self.assertEqual(y_reference.get_linestyle(), ":")
            self.assertNotEqual(to_hex(x_reference.get_color()).lower(), to_hex(y_reference.get_color()).lower())
            self.assertTrue(reference_colors.isdisjoint(method_colors))
            self.assertLessEqual(float(x_reference.get_alpha()), 0.5)
            self.assertLessEqual(float(y_reference.get_alpha()), 0.5)
            self.assertTrue(plot_path.exists())
            plt.close("all")

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
