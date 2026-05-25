"""Tests for the output-parameter TuRBO calibration workflow.

@author: Max Stoddard
"""

from __future__ import annotations

import contextlib
import io
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from scripts.python.calibration.output.esmda import (
    BTL_CHOICE_INTENSITY,
    BTL_PROBABILITY_MULTIPLIER,
    DEFAULT_PARAMETER_SPECS,
    MARKET_AVERAGE_PRICE_DECAY,
    PSYCHOLOGICAL_COST_OF_RENTING,
    SENSITIVITY_RENT_OR_PURCHASE,
)
from scripts.python.calibration.output.turbo_core import (
    TurboState,
    default_failure_tolerance,
    estimate_objective_noise_variance,
    generate_initial_normalized_design,
    hpi_regression_penalty,
    load_turbo_dependencies,
    normalized_points_to_parameter_dicts,
    optimizer_score,
    parameter_dicts_to_normalized_points,
    resolve_candidate_batch_size,
    update_turbo_state,
)
from scripts.python.calibration.output.output_parameter_turbo import build_arg_parser, run_calibration
from scripts.python.calibration.output.validation_bridge import (
    FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
    MemberValidationResult,
)


class TestOutputParameterTurboCore(unittest.TestCase):
    def test_parser_defaults_to_2011_twenty_worker_turbo(self) -> None:
        args = build_arg_parser().parse_args(["--version", "v0", "--output-version", "v0o7"])

        self.assertEqual(args.validation_year, 2011)
        self.assertEqual(args.validation_objective, FAMILY_AWARE_METRIC_LOSS_OBJECTIVE)
        self.assertEqual(args.seeds, "1,2,3,4,5,6,7,8,9,10")
        self.assertEqual(args.workers, 20)
        self.assertEqual(args.initial_points, 20)
        self.assertEqual(args.max_evaluations, 120)
        self.assertIsNone(args.candidate_batch_size)
        self.assertFalse(args.evidence_only)

    def test_normalized_points_round_trip_through_parameter_dicts(self) -> None:
        normalized = np.array([[0.0, 0.25, 0.5, 0.75, 1.0]], dtype=float)

        parameter_sets = normalized_points_to_parameter_dicts(normalized)
        round_trip = parameter_dicts_to_normalized_points(parameter_sets)

        self.assertEqual(len(parameter_sets), 1)
        for spec in DEFAULT_PARAMETER_SPECS:
            self.assertGreaterEqual(parameter_sets[0][spec.name], spec.lower)
            self.assertLessEqual(parameter_sets[0][spec.name], spec.upper)
        np.testing.assert_allclose(round_trip, normalized, rtol=1.0e-12, atol=1.0e-12)

    def test_normalized_mapping_rejects_bad_shape_and_out_of_bounds_values(self) -> None:
        with self.assertRaisesRegex(ValueError, "shape"):
            normalized_points_to_parameter_dicts(np.array([0.5, 0.5]))
        with self.assertRaisesRegex(ValueError, r"\[0, 1\]"):
            normalized_points_to_parameter_dicts(np.array([[0.0, 0.0, 0.0, 0.0, 1.1]]))

    def test_initial_design_is_deterministic_for_fixed_seed(self) -> None:
        first = generate_initial_normalized_design(initial_points=7, dimensions=5, rng_seed=123)
        second = generate_initial_normalized_design(initial_points=7, dimensions=5, rng_seed=123)
        different = generate_initial_normalized_design(initial_points=7, dimensions=5, rng_seed=124)

        self.assertEqual(first.shape, (7, 5))
        self.assertTrue(np.all(first >= 0.0))
        self.assertTrue(np.all(first <= 1.0))
        np.testing.assert_allclose(first, second)
        self.assertFalse(np.allclose(first, different))

    def test_candidate_batch_default_uses_worker_seed_capacity(self) -> None:
        self.assertEqual(resolve_candidate_batch_size(requested=None, workers=20, seed_count=10), 2)
        self.assertEqual(resolve_candidate_batch_size(requested=1, workers=20, seed_count=10), 1)

    def test_candidate_batch_rejects_requests_above_worker_seed_capacity(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceeds available worker capacity"):
            resolve_candidate_batch_size(requested=3, workers=20, seed_count=10)
        with self.assertRaisesRegex(ValueError, "workers must be at least"):
            resolve_candidate_batch_size(requested=None, workers=2, seed_count=3)

    def test_hpi_penalty_is_zero_for_non_positive_constrained_deltas(self) -> None:
        baseline = self._member_result(member_id=0, loss=1.0)
        candidate = self._member_result(
            member_id=1,
            loss=0.8,
            hpi_std_loss=0.05,
            hpi_cycle_loss=0.1,
            hpi_mean_loss=0.0,
        )

        self.assertEqual(hpi_regression_penalty(candidate, baseline_member=baseline), 0.0)
        score, raw_loss, penalty = optimizer_score(candidate, baseline_member=baseline)
        self.assertEqual(raw_loss, 0.8)
        self.assertEqual(penalty, 0.0)
        self.assertEqual(score, -0.8)

    def test_hpi_penalty_is_positive_for_constrained_hpi_regressions(self) -> None:
        baseline = self._member_result(member_id=0, loss=1.0)
        candidate = self._member_result(
            member_id=1,
            loss=0.7,
            hpi_std_loss=0.2,
            hpi_cycle_loss=0.15,
            hpi_mean_loss=0.1,
        )

        penalty = hpi_regression_penalty(candidate, baseline_member=baseline, penalty_weight=2.0)
        score, raw_loss, scored_penalty = optimizer_score(
            candidate,
            baseline_member=baseline,
            penalty_weight=2.0,
        )

        self.assertAlmostEqual(penalty, 0.3)
        self.assertEqual(raw_loss, 0.7)
        self.assertAlmostEqual(scored_penalty, 0.3)
        self.assertAlmostEqual(score, -1.0)

    def test_noise_variance_uses_sample_variance_divided_by_seed_count_and_floor(self) -> None:
        variance = estimate_objective_noise_variance([1.0, 2.0, 3.0], seed_count=3, floor=1.0e-6)

        self.assertAlmostEqual(variance, 1.0 / 3.0)
        self.assertEqual(estimate_objective_noise_variance([2.0], seed_count=1, floor=0.25), 0.25)
        self.assertEqual(estimate_objective_noise_variance([2.0, 2.0], seed_count=2, floor=0.25), 0.25)

    def test_dependency_loader_reports_missing_packages_without_import_time_requirement(self) -> None:
        with mock.patch(
            "scripts.python.calibration.output.turbo_core.importlib.import_module",
            side_effect=ModuleNotFoundError("missing"),
        ):
            with self.assertRaisesRegex(RuntimeError, "torch, botorch, gpytorch"):
                load_turbo_dependencies()

    def test_turbo_state_updates_success_failure_length_and_restart(self) -> None:
        improved = update_turbo_state(
            TurboState(length=0.8, best_score=1.0),
            batch_best_score=2.0,
            batch_evaluation_count=2,
            success_tolerance=1,
            failure_tolerance=2,
            length_max=1.6,
        )
        failed = update_turbo_state(
            improved,
            batch_best_score=1.5,
            batch_evaluation_count=2,
            success_tolerance=2,
            failure_tolerance=1,
            length_min=0.5**7,
        )
        restarted = update_turbo_state(
            TurboState(length=0.02, best_score=10.0),
            batch_best_score=9.0,
            batch_evaluation_count=1,
            failure_tolerance=1,
            length_min=0.02,
        )

        self.assertEqual(default_failure_tolerance(dimensions=5, batch_size=2), math.ceil(5.0 / 2.0))
        self.assertEqual(improved.length, 1.6)
        self.assertEqual(improved.best_score, 2.0)
        self.assertEqual(improved.evaluated_candidate_count, 2)
        self.assertEqual(failed.length, 0.8)
        self.assertTrue(restarted.restart_triggered)

    def test_mocked_no_promotion_campaign_stops_before_creating_output_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._write_source_config(repo_root)
            args = self._campaign_args(evidence_only=False)

            with self._patched_campaign_dependencies(repo_root, member_builder=self._no_promotion_member):
                with (
                    contextlib.redirect_stdout(io.StringIO()),
                    self.assertRaisesRegex(RuntimeError, "No TuRBO member satisfied HPI-constrained ranking"),
                ):
                    run_calibration(args, repo_root=repo_root)

            output_root = repo_root / "tmp" / "output-calibration" / "v0o7" / "five-parameter-turbo"
            self.assertTrue((output_root / "OutputParameterTurboCalibrationSummary.json").exists())
            self.assertFalse((repo_root / "input-data-versions" / "v0o7").exists())

    def test_mocked_accepted_evidence_only_campaign_writes_artifacts_without_output_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._write_source_config(repo_root)
            args = self._campaign_args(evidence_only=True)

            with self._patched_campaign_dependencies(repo_root, member_builder=self._accepted_member) as patches:
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = run_calibration(args, repo_root=repo_root)

            output_root = repo_root / "tmp" / "output-calibration" / "v0o7" / "five-parameter-turbo"
            self.assertFalse(summary["createdOutputVersion"])
            self.assertTrue(summary["evidenceOnly"])
            self.assertTrue(summary["localRefinement"]["promotionAccepted"])
            patches["create_output_version"].assert_not_called()
            self.assertTrue((output_root / "OutputParameterTurboCalibrationSummary.json").exists())
            self.assertTrue((output_root / "TurboEvaluatedMembers.csv").exists())
            self.assertTrue((output_root / "LocalRefinementMembers.csv").exists())

    def test_mocked_accepted_promotion_campaign_creates_output_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            self._write_source_config(repo_root)
            args = self._campaign_args(evidence_only=False)

            with self._patched_campaign_dependencies(repo_root, member_builder=self._accepted_member) as patches:
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = run_calibration(args, repo_root=repo_root)

            self.assertTrue(summary["createdOutputVersion"])
            patches["create_output_version"].assert_called_once()
            self.assertEqual(summary["selected"]["hpiConstrainedEligible"], True)

    def _member_result(
        self,
        *,
        member_id: int,
        loss: float,
        parameters: dict[str, float] | None = None,
        hpi_std_loss: float = 0.1,
        hpi_cycle_loss: float = 0.1,
        hpi_mean_loss: float = 0.1,
    ) -> MemberValidationResult:
        return MemberValidationResult(
            iteration=0,
            member_id=member_id,
            parameters=parameters or {
                PSYCHOLOGICAL_COST_OF_RENTING: 0.4,
                SENSITIVITY_RENT_OR_PURCHASE: 0.001,
                BTL_PROBABILITY_MULTIPLIER: 1.63,
                BTL_CHOICE_INTENSITY: 100.0,
                MARKET_AVERAGE_PRICE_DECAY: 0.5,
            },
            summary={
                "overallCompositeLoss": loss,
                "metrics": [
                    {"metricId": "core_hpiStd", "requirement": "required", "status": "pass", "metricLoss": hpi_std_loss},
                    {
                        "metricId": "core_hpiCyclePeriod",
                        "requirement": "required",
                        "status": "pass",
                        "metricLoss": hpi_cycle_loss,
                    },
                    {"metricId": "core_hpiMean", "requirement": "required", "status": "pass", "metricLoss": hpi_mean_loss},
                ],
            },
            observation_vector=(loss,),
            ranking_loss=loss,
            ranking_objective=FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
            normalized_source_movement=0.0,
            seed_results=(),
        )

    def _campaign_args(self, *, evidence_only: bool) -> object:
        argv = [
            "--version",
            "v0",
            "--output-version",
            "v0o7",
            "--seeds",
            "1",
            "--workers",
            "1",
            "--candidate-batch-size",
            "1",
            "--initial-points",
            "1",
            "--max-evaluations",
            "1",
            "--output-root",
            "tmp/output-calibration",
            "--evidence-dir",
            "tmp/output-calibration/evidence-output-five-parameter-turbo-v0o7",
            "--local-refinement-top-n",
            "1",
            "--local-refinement-radius",
            "0",
            "--local-refinement-max-candidates",
            "2",
            "--n-steps",
            "1000",
            "--validation-window-start",
            "200",
            "--validation-window-end",
            "1000",
            "--delete-csv-after-metrics",
        ]
        if evidence_only:
            argv.append("--evidence-only")
        return build_arg_parser().parse_args(argv)

    def _write_source_config(self, repo_root: Path) -> None:
        source_dir = repo_root / "input-data-versions" / "v0"
        source_dir.mkdir(parents=True)
        (source_dir / "config.properties").write_text(
            "PSYCHOLOGICAL_COST_OF_RENTING = 0.4\n"
            "SENSITIVITY_RENT_OR_PURCHASE = 0.001\n"
            "BTL_PROBABILITY_MULTIPLIER = 1.63\n"
            "BTL_CHOICE_INTENSITY = 100.0\n"
            "MARKET_AVERAGE_PRICE_DECAY = 0.5\n",
            encoding="utf-8",
        )

    def _fake_seed_results(self, **kwargs: object) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                member_id=member_id,
                seed=seed,
                output_dir=f"iter-{kwargs['iteration']}-member-{member_id}-seed-{seed}",
                metrics={},
            )
            for member_id in range(len(kwargs["member_parameters"]))
            for seed in kwargs["seeds"]
        ]

    def _no_promotion_member(self, **kwargs: object) -> MemberValidationResult:
        iteration = int(kwargs["iteration"])
        member_id = int(kwargs["member_id"])
        if iteration == 0:
            return self._member_result(member_id=member_id, loss=1.0)
        if member_id == 0:
            return self._member_result(member_id=member_id, loss=1.2, parameters=dict(kwargs["parameters"]))
        return self._member_result(
            member_id=member_id,
            loss=0.8,
            hpi_std_loss=0.2,
            parameters=dict(kwargs["parameters"]),
        )

    def _accepted_member(self, **kwargs: object) -> MemberValidationResult:
        iteration = int(kwargs["iteration"])
        member_id = int(kwargs["member_id"])
        if iteration == 0:
            return self._member_result(member_id=member_id, loss=1.0)
        loss = 0.8 if iteration == 1 else 0.7
        return self._member_result(member_id=member_id, loss=loss, parameters=dict(kwargs["parameters"]))

    def _patched_campaign_dependencies(self, repo_root: Path, *, member_builder: object) -> object:
        fake_dependencies = SimpleNamespace(
            torch=SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False), __version__="test"),
            botorch=SimpleNamespace(__version__="test"),
            gpytorch=SimpleNamespace(__version__="test"),
            versions={"torch": "test", "botorch": "test", "gpytorch": "test"},
        )
        patches = {
            "ensure_project_compiled": mock.patch(
                "scripts.python.calibration.output.output_parameter_turbo.ensure_project_compiled"
            ),
            "resolve_was_data_root": mock.patch(
                "scripts.python.calibration.output.output_parameter_turbo.resolve_was_data_root",
                return_value=repo_root,
            ),
            "load_turbo_dependencies": mock.patch(
                "scripts.python.calibration.output.output_parameter_turbo.load_turbo_dependencies",
                return_value=fake_dependencies,
            ),
            "propose_turbo_candidates": mock.patch(
                "scripts.python.calibration.output.output_parameter_turbo.propose_turbo_candidates",
                return_value=np.array([[0.5, 0.5, 0.5, 0.5, 0.5]], dtype=float),
            ),
            "execute_seed_requests_for_members": mock.patch(
                "scripts.python.calibration.output.output_parameter_turbo.execute_seed_requests_for_members",
                side_effect=self._fake_seed_results,
            ),
            "build_member_validation_result": mock.patch(
                "scripts.python.calibration.output.output_parameter_turbo.build_member_validation_result",
                side_effect=member_builder,
            ),
            "create_output_version": mock.patch(
                "scripts.python.calibration.output.output_parameter_turbo.create_output_version",
                return_value=repo_root / "input-data-versions" / "v0o7",
            ),
        }
        return _PatchGroup(patches)


class _PatchGroup:
    def __init__(self, patches: dict[str, object]) -> None:
        self._patches = patches
        self._started: dict[str, object] = {}

    def __enter__(self) -> dict[str, object]:
        self._started = {name: patcher.start() for name, patcher in self._patches.items()}
        return self._started

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        for patcher in reversed(list(self._patches.values())):
            patcher.stop()


if __name__ == "__main__":
    unittest.main()
