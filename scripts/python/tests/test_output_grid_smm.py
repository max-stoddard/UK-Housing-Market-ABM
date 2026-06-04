"""Tests for restartable output-parameter grid SMM calibration.

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

from scripts.python.calibration.output.esmda import (
    BTL_CHOICE_INTENSITY,
    BTL_PROBABILITY_MULTIPLIER,
    MARKET_AVERAGE_PRICE_DECAY,
    PSYCHOLOGICAL_COST_OF_RENTING,
    SENSITIVITY_RENT_OR_PURCHASE,
)
from scripts.python.calibration.output.grid_smm import (
    WORKFLOW_SLUG,
    build_arg_parser,
    build_carro_three_level_candidates,
    build_reproduce_command,
    run_grid_smm,
)
from scripts.python.calibration.output.validation_bridge import (
    FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
    MemberValidationResult,
)


class TestOutputGridSmm(unittest.TestCase):
    def test_carro_three_level_grid_is_centered_on_original_selected_values(self) -> None:
        candidates = build_carro_three_level_candidates()

        self.assertEqual(len(candidates), 243)
        self.assertEqual(candidates[0].member_id, 0)
        self.assertEqual(candidates[0].center_distance, 0)
        self.assertEqual(
            candidates[0].parameters,
            {
                PSYCHOLOGICAL_COST_OF_RENTING: 0.4,
                SENSITIVITY_RENT_OR_PURCHASE: 0.001,
                BTL_PROBABILITY_MULTIPLIER: 1.76,
                BTL_CHOICE_INTENSITY: 100.0,
                MARKET_AVERAGE_PRICE_DECAY: 0.5,
            },
        )
        self.assertIn(
            {
                PSYCHOLOGICAL_COST_OF_RENTING: 0.3,
                SENSITIVITY_RENT_OR_PURCHASE: 0.0003162,
                BTL_PROBABILITY_MULTIPLIER: 1.72,
                BTL_CHOICE_INTENSITY: 31.62,
                MARKET_AVERAGE_PRICE_DECAY: 0.3,
            },
            [candidate.parameters for candidate in candidates],
        )
        self.assertIn(
            {
                PSYCHOLOGICAL_COST_OF_RENTING: 0.5,
                SENSITIVITY_RENT_OR_PURCHASE: 0.003162,
                BTL_PROBABILITY_MULTIPLIER: 1.8,
                BTL_CHOICE_INTENSITY: 316.2,
                MARKET_AVERAGE_PRICE_DECAY: 0.7,
            },
            [candidate.parameters for candidate in candidates],
        )

    def test_carro_three_level_grid_uses_deterministic_center_out_order(self) -> None:
        candidates = build_carro_three_level_candidates()

        distances = [candidate.center_distance for candidate in candidates]
        self.assertEqual(distances, sorted(distances))
        self.assertEqual(sum(1 for distance in distances if distance == 0), 1)
        self.assertEqual(sum(1 for distance in distances if distance == 1), 10)
        self.assertEqual([candidate.member_id for candidate in candidates], list(range(243)))

    def test_parser_defaults_to_restartable_2011_smm_grid(self) -> None:
        args = build_arg_parser().parse_args(["--version", "v0", "--run-id", "v0-smm-grid"])

        self.assertEqual(args.validation_year, 2011)
        self.assertEqual(args.validation_objective, FAMILY_AWARE_METRIC_LOSS_OBJECTIVE)
        self.assertEqual(args.seeds, "1,2,3,4,5,6,7,8,9,10")
        self.assertEqual(args.workers, 20)
        self.assertEqual(args.grid_profile, "carro-three-level")
        self.assertFalse(args.force_rerun)
        self.assertFalse(args.delete_csv_after_metrics)

    def test_reproduce_command_includes_approved_2011_grid_smm_shape(self) -> None:
        args = build_arg_parser().parse_args(
            [
                "--version",
                "v0",
                "--run-id",
                "v0-smm-grid-2011-carro-3level",
                "--validation-year",
                "2011",
                "--validation-objective",
                "family_aware_metric_loss",
                "--validation-loss-error-std",
                "1.0",
                "--seeds",
                "1,2,3,4,5,6,7,8,9,10",
                "--workers",
                "20",
                "--grid-profile",
                "carro-three-level",
                "--n-steps",
                "3500",
                "--validation-window-start",
                "500",
                "--validation-window-end",
                "3500",
                "--output-root",
                "tmp/output-calibration",
                "--evidence-dir",
                "input-data-versions/calibration-evidence/output-grid-smm-v0-2011-carro-3level",
                "--delete-csv-after-metrics",
            ]
        )

        command = build_reproduce_command(args)

        self.assertIn("--version v0", command)
        self.assertIn("--run-id v0-smm-grid-2011-carro-3level", command)
        self.assertIn("--validation-year 2011", command)
        self.assertIn("--validation-objective family_aware_metric_loss", command)
        self.assertIn("--seeds 1,2,3,4,5,6,7,8,9,10", command)
        self.assertIn("--workers 20", command)
        self.assertIn("--grid-profile carro-three-level", command)
        self.assertIn("--n-steps 3500", command)
        self.assertIn("--validation-window-start 500", command)
        self.assertIn("--validation-window-end 3500", command)
        self.assertIn("--delete-csv-after-metrics", command)

    def test_dry_run_writes_candidate_grid_and_metadata_without_model_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._write_source_config(repo_root)
            args = build_arg_parser().parse_args(
                [
                    "--version",
                    "v0",
                    "--run-id",
                    "v0-smm-grid",
                    "--output-root",
                    "tmp/output-calibration",
                    "--dry-run",
                ]
            )

            summary = run_grid_smm(args, repo_root=repo_root)

            output_root = repo_root / "tmp" / "output-calibration" / "v0-smm-grid" / WORKFLOW_SLUG
            metadata = json.loads((output_root / "OutputGridSmmMetadata.json").read_text(encoding="utf-8"))
            with (output_root / "GridCandidates.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(summary["dryRun"])
            self.assertEqual(len(rows), 243)
            self.assertEqual(rows[0]["centerDistance"], "0")
            self.assertTrue(metadata["restartable"])
            self.assertEqual(metadata["candidateCount"], 243)
            self.assertFalse((repo_root / "input-data-versions" / "v0-smm-grid").exists())

    def test_mocked_run_evaluates_grid_once_and_reports_cache_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._write_source_config(repo_root)
            args = build_arg_parser().parse_args(
                [
                    "--version",
                    "v0",
                    "--run-id",
                    "v0-smm-grid",
                    "--seeds",
                    "1,2",
                    "--workers",
                    "2",
                    "--max-candidates",
                    "3",
                    "--output-root",
                    "tmp/output-calibration",
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
                        output_dir=f"member-{member_id}-seed-{seed}",
                        metrics={},
                        cached=member_id == 0,
                    )
                    for member_id in range(len(kwargs["member_parameters"]))
                    for seed in kwargs["seeds"]
                ]

            def fake_build_member_validation_result(**kwargs: object) -> MemberValidationResult:
                member_id = int(kwargs["member_id"])
                loss = {0: 1.0, 1: 0.8, 2: 0.9}[member_id]
                return MemberValidationResult(
                    iteration=int(kwargs["iteration"]),
                    member_id=member_id,
                    parameters=dict(kwargs["parameters"]),
                    summary={
                        "overallCompositeLoss": loss,
                        "metrics": [
                            {
                                "metricId": "core_hpiStd",
                                "requirement": "required",
                                "status": "pass",
                                "metricLoss": 0.1,
                            },
                            {
                                "metricId": "core_hpiCyclePeriod",
                                "requirement": "required",
                                "status": "pass",
                                "metricLoss": 0.1,
                            },
                            {
                                "metricId": "core_hpiMean",
                                "requirement": "required",
                                "status": "pass",
                                "metricLoss": 0.1,
                            },
                        ],
                    },
                    observation_vector=(loss,),
                    ranking_loss=loss,
                    ranking_objective=str(kwargs["observations"][0].validation_objective),
                    normalized_source_movement=float(member_id),
                    seed_results=tuple(kwargs["seed_results"]),
                )

            with (
                mock.patch("scripts.python.calibration.output.grid_smm.ensure_project_compiled"),
                mock.patch("scripts.python.calibration.output.grid_smm.resolve_was_data_root", return_value=repo_root),
                mock.patch(
                    "scripts.python.calibration.output.grid_smm.execute_seed_requests_for_members",
                    side_effect=fake_execute_seed_requests_for_members,
                ),
                mock.patch(
                    "scripts.python.calibration.output.grid_smm.build_member_validation_result",
                    side_effect=fake_build_member_validation_result,
                ),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = run_grid_smm(args, repo_root=repo_root)

            output_root = repo_root / "tmp" / "output-calibration" / "v0-smm-grid" / WORKFLOW_SLUG
            self.assertEqual(len(execute_calls), 1)
            self.assertEqual(execute_calls[0]["iteration"], 0)
            self.assertEqual(len(execute_calls[0]["member_parameters"]), 3)
            self.assertFalse(execute_calls[0]["force_rerun"])
            self.assertTrue(execute_calls[0]["delete_csv_after_metrics"])
            self.assertEqual(summary["best"]["memberId"], 1)
            self.assertEqual(summary["seedRunCount"], 6)
            self.assertEqual(summary["cachedSeedRunCount"], 2)
            self.assertTrue((output_root / "SmmEvaluatedMembers.csv").exists())
            self.assertTrue((output_root / "OutputGridSmmCalibrationSummary.json").exists())

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
