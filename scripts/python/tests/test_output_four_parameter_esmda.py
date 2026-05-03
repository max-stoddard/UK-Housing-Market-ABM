"""Tests for the four-parameter output ES-MDA calibration workflow.

@author: Max Stoddard
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

from scripts.python.calibration.output.candidate_runs import (
    build_candidate_batches,
    create_output_version,
    parse_config_parameters,
    parse_seed_list,
    update_config_properties,
)
from scripts.python.calibration.output.esmda import (
    DEFAULT_PARAMETER_SPECS,
    MARKET_AVERAGE_PRICE_DECAY,
    PSYCHOLOGICAL_COST_OF_RENTING,
    SENSITIVITY_RENT_OR_PURCHASE,
    BTL_CHOICE_INTENSITY,
    ParameterSpec,
    esmda_update,
    generate_initial_ensemble,
    make_alpha_schedule,
    snap_parameter_set,
    transformed_matrix_to_parameter_dicts,
)
from scripts.python.calibration.output.four_parameter_esmda import (
    DEFAULT_ASSIMILATION_STEPS,
    DEFAULT_ENSEMBLE_SIZE,
    DEFAULT_RNG_SEED,
    LOSS_HANDLING_NOTE,
    build_arg_parser,
    run_calibration,
)
from scripts.python.calibration.output.validation_bridge import (
    MemberValidationResult,
    build_member_validation_result,
    build_validation_observations,
    observation_error_covariance,
    observation_vector,
    resolve_calibration_validation_profile,
    summarize_validation_profile,
)


class TestFourParameterEsmdaWorkflow(unittest.TestCase):
    def test_parser_defaults_to_four_seed_twenty_worker_esmda(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_arg_parser().parse_args([])

        args = build_arg_parser().parse_args(
            ["--version", "v4.14o", "--output-version", "v4.14oo"]
        )

        self.assertEqual(args.validation_year, 2024)
        self.assertEqual(args.seeds, "1,2,3,4")
        self.assertEqual(args.workers, 20)
        self.assertEqual(args.ensemble_size, DEFAULT_ENSEMBLE_SIZE)
        self.assertEqual(args.assimilation_steps, DEFAULT_ASSIMILATION_STEPS)
        self.assertEqual(args.rng_seed, DEFAULT_RNG_SEED)

    def test_parse_seed_list_requires_positive_seeds(self) -> None:
        self.assertEqual(parse_seed_list("1,2,4"), [1, 2, 4])
        for raw in ["", "0", "1,-2"]:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_seed_list(raw)

    def test_parameter_transforms_round_trip_inside_bounds(self) -> None:
        values = {
            PSYCHOLOGICAL_COST_OF_RENTING: 0.4,
            SENSITIVITY_RENT_OR_PURCHASE: 0.001,
            BTL_CHOICE_INTENSITY: 100.0,
            MARKET_AVERAGE_PRICE_DECAY: 0.5,
        }

        for spec in DEFAULT_PARAMETER_SPECS:
            transformed = spec.transform_value(values[spec.name])
            round_trip = spec.inverse_transform_value(transformed)
            self.assertAlmostEqual(round_trip, values[spec.name])
            self.assertGreaterEqual(round_trip, spec.lower)
            self.assertLessEqual(round_trip, spec.upper)

    def test_final_snapping_uses_practical_precision(self) -> None:
        snapped = snap_parameter_set(
            {
                PSYCHOLOGICAL_COST_OF_RENTING: 0.427,
                SENSITIVITY_RENT_OR_PURCHASE: 0.001234,
                BTL_CHOICE_INTENSITY: 124.0,
                MARKET_AVERAGE_PRICE_DECAY: 0.613,
            }
        )

        self.assertAlmostEqual(snapped[PSYCHOLOGICAL_COST_OF_RENTING], 0.45)
        self.assertAlmostEqual(snapped[SENSITIVITY_RENT_OR_PURCHASE], 0.0012)
        self.assertAlmostEqual(snapped[BTL_CHOICE_INTENSITY], 120.0)
        self.assertAlmostEqual(snapped[MARKET_AVERAGE_PRICE_DECAY], 0.62)

    def test_alpha_schedule_is_normalized(self) -> None:
        alphas = make_alpha_schedule(4)

        self.assertEqual(len(alphas), 4)
        self.assertTrue(np.all(alphas > 0.0))
        self.assertAlmostEqual(float(np.sum(1.0 / alphas)), 1.0)

    def test_initial_ensemble_generation_is_deterministic(self) -> None:
        first = generate_initial_ensemble(ensemble_size=8, rng_seed=123)
        second = generate_initial_ensemble(ensemble_size=8, rng_seed=123)
        different = generate_initial_ensemble(ensemble_size=8, rng_seed=124)

        np.testing.assert_allclose(first, second)
        self.assertFalse(np.allclose(first, different))
        params = transformed_matrix_to_parameter_dicts(first)
        self.assertEqual(len(params), 8)
        for parameter_set in params:
            for spec in DEFAULT_PARAMETER_SPECS:
                self.assertGreaterEqual(parameter_set[spec.name], spec.lower)
                self.assertLessEqual(parameter_set[spec.name], spec.upper)

    def test_esmda_update_moves_synthetic_linear_ensemble_toward_target(self) -> None:
        transformed_parameters = np.array([[0.0], [0.5], [1.0], [1.5]], dtype=float)
        simulated_observations = 2.0 * transformed_parameters
        observed = np.array([4.0], dtype=float)
        covariance = np.array([[0.01]], dtype=float)

        updated = esmda_update(
            transformed_parameters=transformed_parameters,
            simulated_observations=simulated_observations,
            observed_vector=observed,
            observation_error_covariance=covariance,
            alpha=4.0,
            rng_seed=1,
            perturb_observations=False,
        )

        old_mean_gap = abs(float(np.mean(transformed_parameters)) - 2.0)
        new_mean_gap = abs(float(np.mean(updated)) - 2.0)
        self.assertLess(new_mean_gap, old_mean_gap)

    def test_scheduler_groups_twenty_workers_into_five_four_seed_candidates(self) -> None:
        batches = build_candidate_batches(list(range(12)), seed_count=4, workers=20)

        self.assertEqual([len(batch) for batch in batches], [5, 5, 2])

    def test_validation_profiles_use_r8_for_2024_and_w3_for_2011_v0(self) -> None:
        profile_2024 = resolve_calibration_validation_profile(version="v4.14o", validation_year=2024)
        profile_2011 = resolve_calibration_validation_profile(version="v0o", validation_year=2011)

        self.assertEqual(summarize_validation_profile(profile_2024)["wasDataset"], "R8")
        self.assertEqual(summarize_validation_profile(profile_2011)["wasDataset"], "W3")
        with self.assertRaises(ValueError):
            resolve_calibration_validation_profile(version="v4.14o", validation_year=2011)

    def test_validation_observation_covariance_and_member_aggregation(self) -> None:
        profile = resolve_calibration_validation_profile(version="v4.14o", validation_year=2024)
        observations = build_validation_observations(profile)
        observed = observation_vector(observations)
        covariance = observation_error_covariance(observations)

        self.assertEqual(len(observations), 17)
        self.assertEqual(covariance.shape, (17, 17))
        self.assertTrue(np.all(np.diag(covariance) > 0.0))

        metrics = self._target_metric_values(profile)
        seed_results = [
            {"seed": seed, "outputDir": f"seed-{seed}", "metrics": metrics}
            for seed in (1, 2, 3, 4)
        ]
        member = build_member_validation_result(
            version="v4.14o",
            iteration=0,
            member_id=0,
            parameters=self._default_parameter_values(),
            seed_results=seed_results,
            seeds=[1, 2, 3, 4],
            validation_profile=profile,
            observations=observations,
            source_parameters=self._default_parameter_values(),
        )

        self.assertEqual(len(member.observation_vector), len(observed))
        self.assertLess(float(member.summary["overallCompositeLoss"]), 0.6)

    def test_config_parsing_and_update_are_limited_to_requested_keys(self) -> None:
        config = self._minimal_config_text()
        parsed = parse_config_parameters(config)
        updated = update_config_properties(
            config,
            {
                PSYCHOLOGICAL_COST_OF_RENTING: "0.45",
                SENSITIVITY_RENT_OR_PURCHASE: "0.0012",
            },
        )

        self.assertAlmostEqual(parsed[BTL_CHOICE_INTENSITY], 100.0)
        self.assertIn("PSYCHOLOGICAL_COST_OF_RENTING = 0.45", updated)
        self.assertIn("SENSITIVITY_RENT_OR_PURCHASE = 0.0012", updated)
        self.assertIn("BTL_PROBABILITY_MULTIPLIER = 0.435", updated)

    def test_create_output_version_updates_only_four_parameter_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            source_dir = repo_root / "input-data-versions" / "v4.14o"
            source_dir.mkdir(parents=True)
            (source_dir / "config.properties").write_text(self._minimal_config_text(), encoding="utf-8")
            (source_dir / "Other.csv").write_text("value\n", encoding="utf-8")

            output_dir = create_output_version(
                repo_root=repo_root,
                source_version="v4.14o",
                output_version="v4.14oo",
                selected_parameters={
                    PSYCHOLOGICAL_COST_OF_RENTING: 0.45,
                    SENSITIVITY_RENT_OR_PURCHASE: 0.0012,
                    BTL_CHOICE_INTENSITY: 120.0,
                    MARKET_AVERAGE_PRICE_DECAY: 0.62,
                },
                overwrite=False,
            )

            output_config = (output_dir / "config.properties").read_text(encoding="utf-8")
            self.assertIn("PSYCHOLOGICAL_COST_OF_RENTING = 0.45", output_config)
            self.assertIn("SENSITIVITY_RENT_OR_PURCHASE = 0.0012", output_config)
            self.assertIn("BTL_CHOICE_INTENSITY = 120", output_config)
            self.assertIn("MARKET_AVERAGE_PRICE_DECAY = 0.62", output_config)
            self.assertIn("BTL_PROBABILITY_MULTIPLIER = 0.435", output_config)
            self.assertTrue((output_dir / "Other.csv").exists())

    def test_cli_dry_run_writes_metadata_without_creating_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            source_dir = repo_root / "input-data-versions" / "v4.14o"
            source_dir.mkdir(parents=True)
            (source_dir / "config.properties").write_text(self._minimal_config_text(), encoding="utf-8")
            args = build_arg_parser().parse_args(
                [
                    "--version",
                    "v4.14o",
                    "--output-version",
                    "v4.14oo",
                    "--ensemble-size",
                    "8",
                    "--output-root",
                    "tmp/output-calibration",
                    "--dry-run",
                ]
            )

            summary = run_calibration(args, repo_root=repo_root)

            output_root = repo_root / "tmp" / "output-calibration" / "v4.14oo" / "four-parameter-esmda"
            summary_path = output_root / "FourParameterEsmdaCalibrationSummary.json"
            metadata = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertTrue(summary["dryRun"])
            self.assertTrue((output_root / "InitialEnsemble.csv").exists())
            self.assertFalse((repo_root / "input-data-versions" / "v4.14oo").exists())
            self.assertIn("unbounded", metadata["validationLossHandling"])
            self.assertIn("greater than 1.0", LOSS_HANDLING_NOTE)

    def test_single_assimilation_evaluates_initial_and_final_posterior(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            source_dir = repo_root / "input-data-versions" / "v4.14o"
            source_dir.mkdir(parents=True)
            (source_dir / "config.properties").write_text(self._minimal_config_text(), encoding="utf-8")
            args = build_arg_parser().parse_args(
                [
                    "--version",
                    "v4.14o",
                    "--output-version",
                    "v4.14oo",
                    "--ensemble-size",
                    "2",
                    "--assimilation-steps",
                    "1",
                    "--seeds",
                    "1",
                    "--workers",
                    "1",
                    "--output-root",
                    "tmp/output-calibration",
                ]
            )

            execute_iterations: list[int] = []

            def fake_execute_seed_requests_for_members(**kwargs: object) -> list[SimpleNamespace]:
                iteration = int(kwargs["iteration"])
                execute_iterations.append(iteration)
                member_count = len(kwargs["member_parameters"])
                return [
                    SimpleNamespace(
                        member_id=member_id,
                        seed=1,
                        output_dir=f"iteration-{iteration}-member-{member_id}",
                        metrics={},
                    )
                    for member_id in range(member_count)
                ]

            def fake_build_member_validation_result(**kwargs: object) -> MemberValidationResult:
                iteration = int(kwargs["iteration"])
                member_id = int(kwargs["member_id"])
                loss = 1.0 if iteration == 0 else 0.2 - 0.1 * member_id
                return MemberValidationResult(
                    iteration=iteration,
                    member_id=member_id,
                    parameters=dict(kwargs["parameters"]),
                    summary={
                        "overallCompositeLoss": loss,
                        "metrics": [
                            {
                                "metricId": "core_advancesToBTL",
                                "requirement": "required",
                                "status": "pass",
                                "metricLoss": loss,
                            }
                        ],
                    },
                    observation_vector=tuple(0.0 for _ in kwargs["observations"]),
                    normalized_source_movement=float(iteration) + member_id / 10.0,
                    seed_results=tuple(kwargs["seed_results"]),
                )

            with (
                mock.patch(
                    "scripts.python.calibration.output.four_parameter_esmda.ensure_project_compiled"
                ),
                mock.patch(
                    "scripts.python.calibration.output.four_parameter_esmda.resolve_was_data_root",
                    return_value=repo_root,
                ),
                mock.patch(
                    "scripts.python.calibration.output.four_parameter_esmda.execute_seed_requests_for_members",
                    side_effect=fake_execute_seed_requests_for_members,
                ),
                mock.patch(
                    "scripts.python.calibration.output.four_parameter_esmda.build_member_validation_result",
                    side_effect=fake_build_member_validation_result,
                ),
                mock.patch(
                    "scripts.python.calibration.output.four_parameter_esmda.esmda_update",
                    side_effect=lambda **kwargs: kwargs["transformed_parameters"],
                ) as update_mock,
                mock.patch(
                    "scripts.python.calibration.output.four_parameter_esmda.create_output_version",
                    return_value=repo_root / "input-data-versions" / "v4.14oo",
                ),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    summary = run_calibration(args, repo_root=repo_root)

            self.assertEqual(execute_iterations, [0, 1])
            self.assertEqual(update_mock.call_count, 1)
            self.assertEqual(summary["selected"]["iteration"], 1)
            self.assertEqual(summary["selected"]["memberId"], 1)

    def test_parameter_spec_rejects_invalid_log_bounds(self) -> None:
        with self.assertRaises(ValueError):
            ParameterSpec(
                name="BAD",
                lower=0.0,
                upper=1.0,
                prior_lower=0.1,
                prior_upper=0.9,
                transform="log10",
            )

    def _target_metric_values(self, profile: object) -> dict[str, float]:
        values: dict[str, float] = {}
        for metric_id, metric in profile.targets_by_id.items():
            if metric.target_band is None:
                values[metric_id] = 0.0
                continue
            source_value = metric.source_metadata.normalized_source_value if metric.source_metadata else None
            values[metric_id] = (
                float(source_value)
                if source_value is not None
                else (metric.target_band.lower + metric.target_band.upper) / 2.0
            )
        return values

    def _default_parameter_values(self) -> dict[str, float]:
        return {
            PSYCHOLOGICAL_COST_OF_RENTING: 0.4,
            SENSITIVITY_RENT_OR_PURCHASE: 0.001,
            BTL_CHOICE_INTENSITY: 100.0,
            MARKET_AVERAGE_PRICE_DECAY: 0.5,
        }

    def _minimal_config_text(self) -> str:
        return (
            "PSYCHOLOGICAL_COST_OF_RENTING = 0.4\n"
            "SENSITIVITY_RENT_OR_PURCHASE = 0.001\n"
            "BTL_PROBABILITY_MULTIPLIER = 0.435\n"
            "BTL_CHOICE_INTENSITY = 100.0\n"
            "MARKET_AVERAGE_PRICE_DECAY = 0.5\n"
        )


if __name__ == "__main__":
    unittest.main()
