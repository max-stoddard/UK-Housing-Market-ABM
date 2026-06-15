"""Tests for live SMM versus TuRBO output-calibration comparison runs.

@author: Max Stoddard
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from scripts.python.calibration.output.esmda import (
    BTL_CHOICE_INTENSITY,
    BTL_PROBABILITY_MULTIPLIER,
    MARKET_AVERAGE_PRICE_DECAY,
    PSYCHOLOGICAL_COST_OF_RENTING,
    SENSITIVITY_RENT_OR_PURCHASE,
)
from scripts.python.calibration.output.method_comparison import (
    _validate_args,
    build_arg_parser,
    run_method_comparison,
)
from scripts.python.calibration.output.validation_bridge import (
    FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
    MemberValidationResult,
)


class TestOutputMethodComparison(unittest.TestCase):
    def test_parser_defaults_to_full_scale_2011_live_comparison(self) -> None:
        args = build_arg_parser().parse_args(["--version", "v0", "--run-id", "comparison"])

        self.assertEqual(args.validation_year, 2011)
        self.assertEqual(args.validation_objective, FAMILY_AWARE_METRIC_LOSS_OBJECTIVE)
        self.assertEqual(args.seeds, "1,2,3,4,5,6,7,8,9,10")
        self.assertEqual(args.workers, 20)
        self.assertEqual(args.replicates, 5)
        self.assertEqual(args.evaluations, 480)
        self.assertEqual(args.checkpoint_evaluations, 240)
        self.assertEqual(args.n_steps, 3500)
        self.assertEqual(args.validation_window_start, 500)
        self.assertEqual(args.validation_window_end, 3500)
        self.assertEqual(args.smm_grid_profile, "carro-full")
        self.assertEqual(args.smm_grid_order, "random")
        self.assertEqual(args.turbo_initial_points, 40)
        self.assertEqual(args.live_plot_x_minor_step, None)
        self.assertEqual(args.live_plot_y_minor_step, None)
        self.assertEqual(args.live_plot_reference_x, None)
        self.assertEqual(args.live_plot_reference_x_label, None)
        self.assertEqual(args.live_plot_reference_y_loss, None)
        self.assertEqual(args.live_plot_reference_y_label, None)

    def test_parser_accepts_live_plot_reference_flags(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--version",
                "v0",
                "--run-id",
                "comparison",
                "--live-plot-x-minor-step",
                "5",
                "--live-plot-y-minor-step",
                "0.004",
                "--live-plot-reference-x",
                "40",
                "--live-plot-reference-x-label",
                "TuRBO exploratory Sobol period ends",
                "--live-plot-reference-y-loss",
                "0.5652252115924438",
                "--live-plot-reference-y-label",
                "v0 2011 validation loss",
            ]
        )

        self.assertEqual(args.live_plot_x_minor_step, 5.0)
        self.assertEqual(args.live_plot_y_minor_step, 0.004)
        self.assertEqual(args.live_plot_reference_x, 40.0)
        self.assertEqual(args.live_plot_reference_x_label, "TuRBO exploratory Sobol period ends")
        self.assertEqual(args.live_plot_reference_y_loss, 0.5652252115924438)
        self.assertEqual(args.live_plot_reference_y_label, "v0 2011 validation loss")

    def test_validation_rejects_invalid_live_plot_values(self) -> None:
        invalid_cases = [
            ("live_plot_x_minor_step", 0.0, "live-plot-x-minor-step must be positive"),
            ("live_plot_y_minor_step", -0.004, "live-plot-y-minor-step must be positive"),
            ("live_plot_reference_x", -1.0, "live-plot-reference-x must be non-negative"),
            ("live_plot_reference_y_loss", -0.1, "live-plot-reference-y-loss must be non-negative"),
        ]
        for attribute, value, expected_message in invalid_cases:
            with self.subTest(attribute=attribute):
                args = build_arg_parser().parse_args(["--version", "v0", "--run-id", "comparison"])
                setattr(args, attribute, value)

                with self.assertRaisesRegex(ValueError, expected_message):
                    _validate_args(args=args, seeds=(1, 2, 3, 4, 5, 6, 7, 8, 9, 10))

    def test_mocked_run_interleaves_methods_and_writes_live_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._write_source_config(repo_root)
            args = build_arg_parser().parse_args(
                [
                    "--version",
                    "v0",
                    "--run-id",
                    "comparison",
                    "--replicates",
                    "2",
                    "--evaluations",
                    "3",
                    "--checkpoint-evaluations",
                    "2",
                    "--seeds",
                    "1,2",
                    "--workers",
                    "4",
                    "--n-steps",
                    "1000",
                    "--validation-window-start",
                    "200",
                    "--validation-window-end",
                    "1000",
                    "--output-root",
                    "tmp/output-calibration",
                    "--live-plot-x-minor-step",
                    "5",
                    "--live-plot-y-minor-step",
                    "0.004",
                    "--live-plot-reference-x",
                    "40",
                    "--live-plot-reference-x-label",
                    "TuRBO exploratory Sobol period ends",
                    "--live-plot-reference-y-loss",
                    "0.5652252115924438",
                    "--live-plot-reference-y-label",
                    "v0 2011 validation loss",
                    "--no-plot",
                    "--delete-csv-after-metrics",
                ]
            )

            execute_calls: list[dict[str, object]] = []

            def fake_execute_seed_requests_for_members(**kwargs: object) -> list[SimpleNamespace]:
                execute_calls.append(dict(kwargs))
                return [
                    SimpleNamespace(
                        member_id=member_id,
                        seed=seed,
                        output_dir=f"{kwargs['output_root']}/member-{member_id}-seed-{seed}",
                        metrics={},
                        cached=False,
                    )
                    for member_id in range(len(kwargs["member_parameters"]))
                    for seed in kwargs["seeds"]
                ]

            def fake_build_member_validation_result(**kwargs: object) -> MemberValidationResult:
                version = str(kwargs["version"])
                iteration = int(kwargs["iteration"])
                member_id = int(kwargs["member_id"])
                method_penalty = 0.01 if "smm" in version else 0.0
                replicate = member_id // 1000
                evaluation = member_id % 1000
                loss = 1.0 - 0.05 * evaluation + method_penalty + 0.005 * replicate
                return self._member_result(
                    iteration=iteration,
                    member_id=member_id,
                    loss=loss,
                    parameters=dict(kwargs["parameters"]),
                )

            with (
                mock.patch("scripts.python.calibration.output.method_comparison.ensure_project_compiled"),
                mock.patch("scripts.python.calibration.output.method_comparison.resolve_was_data_root", return_value=repo_root),
                mock.patch(
                    "scripts.python.calibration.output.method_comparison.execute_seed_requests_for_members",
                    side_effect=fake_execute_seed_requests_for_members,
                ),
                mock.patch(
                    "scripts.python.calibration.output.method_comparison.build_member_validation_result",
                    side_effect=fake_build_member_validation_result,
                ),
                mock.patch(
                    "scripts.python.calibration.output.method_comparison.propose_turbo_candidates",
                    return_value=np.array([[0.5, 0.5, 0.5, 0.5, 0.5]], dtype=float),
                ),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = run_method_comparison(args, repo_root=repo_root)

            output_root = repo_root / "tmp" / "output-calibration" / "comparison" / "method-comparison"
            self.assertEqual(summary["evaluatedCandidates"], 12)
            self.assertEqual(summary["replicates"], 2)
            self.assertEqual(summary["evaluations"], 3)
            self.assertGreaterEqual(len(execute_calls), 6)
            self.assertTrue(any("turbo" in str(call["output_root"]) for call in execute_calls))
            self.assertTrue(any("smm" in str(call["output_root"]) for call in execute_calls))
            self.assertTrue((output_root / "method_convergence_live.csv").exists())
            self.assertTrue((output_root / "method_summary_live.csv").exists())
            self.assertTrue((output_root / "live.html").exists())
            self.assertTrue(
                (
                    output_root
                    / "candidate-requests"
                    / "turbo"
                    / "replicate-01"
                    / "eval-0001.json"
                ).exists()
            )
            self.assertTrue(
                (
                    output_root
                    / "candidate-requests"
                    / "smm-random-grid"
                    / "replicate-01"
                    / "eval-0001.json"
                ).exists()
            )
            with (output_root / "method_summary_live.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["method"] for row in rows}, {"TuRBO", "SMM random grid"})
            metadata = json.loads((output_root / "MethodComparisonMetadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["validationWindow"], {"startIndex": 200, "endIndex": 1000})
            self.assertEqual(
                metadata["livePlot"],
                {
                    "xMinorStep": 5.0,
                    "yMinorStep": 0.004,
                    "referenceX": 40.0,
                    "referenceXLabel": "TuRBO exploratory Sobol period ends",
                    "referenceYLoss": 0.5652252115924438,
                    "referenceYLabel": "v0 2011 validation loss",
                },
            )

    def _member_result(
        self,
        *,
        iteration: int,
        member_id: int,
        loss: float,
        parameters: dict[str, float],
    ) -> MemberValidationResult:
        return MemberValidationResult(
            iteration=iteration,
            member_id=member_id,
            parameters=parameters,
            summary={
                "overallCompositeLoss": loss,
                "metrics": [
                    {"metricId": "core_hpiStd", "requirement": "required", "status": "pass", "metricLoss": 0.1},
                    {"metricId": "core_hpiCyclePeriod", "requirement": "required", "status": "pass", "metricLoss": 0.1},
                    {"metricId": "core_hpiMean", "requirement": "required", "status": "pass", "metricLoss": 0.1},
                ],
            },
            observation_vector=(loss,),
            ranking_loss=loss,
            ranking_objective=FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
            normalized_source_movement=0.0,
            seed_results=(),
        )

    def _write_source_config(self, repo_root: Path) -> None:
        source_dir = repo_root / "input-data-versions" / "v0"
        source_dir.mkdir(parents=True)
        (source_dir / "config.properties").write_text(
            "PSYCHOLOGICAL_COST_OF_RENTING = 0.4\n"
            "SENSITIVITY_RENT_OR_PURCHASE = 0.001\n"
            "BTL_PROBABILITY_MULTIPLIER = 1.76\n"
            "BTL_CHOICE_INTENSITY = 100.0\n"
            "MARKET_AVERAGE_PRICE_DECAY = 0.5\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    unittest.main()
