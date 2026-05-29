#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tests for the LTI quota response experiment workflow.

@author: Max Stoddard
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import warnings
from dataclasses import fields
from pathlib import Path
from unittest import mock

from scripts.python.experiments.model import lti_quota_response as lqr


class TestLtiQuotaResponse(unittest.TestCase):
    def _baseline_point(self) -> lqr.QuotaPoint:
        return next(
            point
            for point in lqr.build_quota_points(lqr.DEFAULT_QUOTA_VALUES, lqr.BASELINE_QUOTA)
            if point.is_baseline
        )

    def _run_request(self) -> lqr.RunRequest:
        return lqr.RunRequest(version="v0o7", seed=1, point=self._baseline_point())

    def _metric_values(self) -> dict[str, float]:
        return {metric_id: float(index + 1) for index, metric_id in enumerate(lqr.METRIC_IDS)}

    def _run_metrics_payload(self) -> dict[str, object]:
        return lqr.build_run_metrics_payload(
            request=self._run_request(),
            output_dir="tmp/lti-quota-response/v0o7/seed-1/quota_06_0p15",
            config_path="tmp/lti-quota-response/v0o7/seed-1/quota_06_0p15/config.properties",
            metrics=self._metric_values(),
            command=["./mvnw", "exec:java"],
            cached=False,
        )

    def _write_run_metrics(self, directory: Path, payload: dict[str, object]) -> Path:
        cache_path = directory / "run_metrics.json"
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        return cache_path

    def _aggregated_row(
        self,
        *,
        version: str = "v0o7",
        quota: float = 0.15,
        metric_id: str = "core_debtToIncome",
    ) -> lqr.AggregatedMetricRow:
        return lqr.AggregatedMetricRow(
            version=version,
            quota_label=str(quota),
            quota=quota,
            is_baseline=quota == lqr.BASELINE_QUOTA,
            metric_id=metric_id,
            raw_mean=100.0,
            raw_stdev=1.0,
            raw_ci_low=99.0,
            raw_ci_high=101.0,
            raw_n=10,
            delta_percent_mean=1.0,
            delta_percent_stdev=0.5,
            delta_percent_ci_low=0.5,
            delta_percent_ci_high=1.5,
            delta_percent_n=10,
        )

    class _RecordingAxis:
        def __init__(self) -> None:
            self.xticks: list[float] | None = None

        def plot(self, *args: object, **kwargs: object) -> None:
            return None

        def fill_between(self, *args: object, **kwargs: object) -> None:
            return None

        def axhline(self, *args: object, **kwargs: object) -> None:
            return None

        def set_xlabel(self, *args: object, **kwargs: object) -> None:
            return None

        def set_ylabel(self, *args: object, **kwargs: object) -> None:
            return None

        def set_xticks(self, ticks: list[float]) -> None:
            self.xticks = list(ticks)

        def grid(self, *args: object, **kwargs: object) -> None:
            return None

        def legend(self, *args: object, **kwargs: object) -> None:
            return None

    class _RecordingFigure:
        def __init__(self, *, fail_png: bool = False, fail_pdf: bool = False) -> None:
            self.fail_png = fail_png
            self.fail_pdf = fail_pdf
            self.saved_paths: list[Path] = []

        def tight_layout(self) -> None:
            return None

        def savefig(self, path: Path, **kwargs: object) -> None:
            if path.suffix == ".png" and self.fail_png:
                raise RuntimeError("png failed")
            if path.suffix == ".pdf" and self.fail_pdf:
                raise RuntimeError("pdf failed")
            self.saved_paths.append(path)

    def test_constants_match_design_contract(self) -> None:
        self.assertEqual(lqr.DEFAULT_VERSIONS, ("v0o7", "v5o3"))
        self.assertEqual(lqr.N_STEPS, 3500)
        self.assertEqual(lqr.METRIC_WINDOW, {"mode": "index_slice", "start_index": 500, "end_index": 3500})
        self.assertEqual(
            lqr.LTI_QUOTA_KEYS,
            (
                "CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB",
                "CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM",
            ),
        )
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_INITIAL_BASE_RATE"], "0.0510833333")
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_LTV_HARD_MAX_FTB"], "0.95")
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_LTV_HARD_MAX_HM"], "0.95")
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_LTV_HARD_MAX_BTL"], "0.85")
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_LTI_SOFT_MAX_FTB"], "4.5")
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_LTI_SOFT_MAX_HM"], "4.5")
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_LTI_MONTHS_TO_CHECK"], "12")
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_AFFORDABILITY_HARD_MAX"], "0.9999")
        self.assertEqual(lqr.POLICY_2024_OVERRIDES["CENTRAL_BANK_ICR_HARD_MIN"], "0")

    def test_metric_contract_includes_primary_and_secondary_metrics(self) -> None:
        self.assertEqual(lqr.METRIC_IDS, (
            "core_debtToIncome",
            "core_ooLTI",
            "core_advancesToFTB",
            "core_advancesToHM",
            "core_advancesToBTL",
        ))
        self.assertEqual(lqr.METRIC_DEFINITIONS["core_ooLTI"].file_name, "coreIndicator-ooLTI.csv")

    def test_select_metric_window_uses_500_to_3500_indices(self) -> None:
        values = list(range(0, 3501))

        self.assertEqual(lqr.select_metric_window(values), list(range(500, 3500)))

    def test_select_metric_window_raises_for_truncated_metric_series(self) -> None:
        values = list(range(0, 3499))

        with self.assertRaisesRegex(RuntimeError, "Expected at least 3500 metric values"):
            lqr.select_metric_window(values)

    def test_mean_rejects_non_finite_metric_values(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Non-finite metric value"):
            lqr._mean([1.0, float("nan")])

    def test_summary_rejects_non_finite_metric_values(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Non-finite metric value"):
            lqr._summary([1.0, float("inf")])

    def test_aggregate_run_metrics_rejects_non_finite_raw_values(self) -> None:
        run_metrics = [
            lqr.RunMetric("v0o7", 1, "0.15", 0.150, True, "core_debtToIncome", 100.0),
            lqr.RunMetric("v0o7", 1, "0.3", 0.300, False, "core_debtToIncome", float("nan")),
        ]

        with self.assertRaisesRegex(RuntimeError, "Non-finite metric value"):
            lqr.aggregate_run_metrics(run_metrics)

    def test_aggregate_percent_delta_uses_each_versions_own_baseline(self) -> None:
        run_metrics = [
            lqr.RunMetric("v0o7", 1, "0.15", 0.150, True, "core_debtToIncome", 100.0),
            lqr.RunMetric("v0o7", 1, "0.3", 0.300, False, "core_debtToIncome", 110.0),
            lqr.RunMetric("v5o3", 1, "0.15", 0.150, True, "core_debtToIncome", 200.0),
            lqr.RunMetric("v5o3", 1, "0.3", 0.300, False, "core_debtToIncome", 230.0),
        ]

        rows = lqr.aggregate_run_metrics(run_metrics)
        by_version_quota = {(row.version, row.quota_label): row for row in rows}

        self.assertAlmostEqual(by_version_quota[("v0o7", "0.3")].delta_percent_mean, 10.0)
        self.assertAlmostEqual(by_version_quota[("v5o3", "0.3")].delta_percent_mean, 15.0)
        self.assertAlmostEqual(by_version_quota[("v0o7", "0.15")].delta_percent_mean, 0.0)
        self.assertAlmostEqual(by_version_quota[("v5o3", "0.15")].delta_percent_mean, 0.0)

    def test_cli_defaults_match_design_contract(self) -> None:
        args = lqr.build_arg_parser().parse_args([])

        self.assertEqual(args.output_dir, "tmp/lti-quota-response")
        self.assertEqual(args.workers, 20)
        self.assertEqual(args.seeds, "1,2,3,4,5,6,7,8,9,10")
        self.assertEqual(args.maven_bin, None)
        self.assertFalse(args.force_rerun)
        self.assertFalse(args.plot_only)

    def test_parse_seed_list_rejects_duplicate_seeds(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Duplicate seed"):
            lqr.parse_seed_list("1,2,1")

    def test_parse_csv_floats_rejects_quota_values_outside_unit_interval(self) -> None:
        for raw in ("-0.001", "1.001"):
            with self.subTest(raw=raw), self.assertRaisesRegex(SystemExit, "between 0.0 and 1.0"):
                lqr.parse_csv_floats(raw)

    def test_parse_csv_floats_accepts_quota_bounds(self) -> None:
        self.assertEqual(lqr.parse_csv_floats("0,1"), [0.0, 1.0])

    def test_quota_point_fields_match_design_contract(self) -> None:
        self.assertEqual(
            [field.name for field in fields(lqr.QuotaPoint)],
            ["point_id", "point_index", "label", "quota", "is_baseline", "policy_overrides"],
        )

    def test_policy_grid_has_13_points_and_15pct_baseline(self) -> None:
        points = lqr.build_quota_points(lqr.DEFAULT_QUOTA_VALUES, lqr.BASELINE_QUOTA)

        self.assertEqual(len(points), 13)
        self.assertEqual(points[0].point_id, "quota_00_0")
        self.assertEqual(points[6].point_id, "quota_06_0p15")
        self.assertEqual([point.point_index for point in points], list(range(13)))
        self.assertEqual([point.quota for point in points], list(lqr.DEFAULT_QUOTA_VALUES))
        self.assertEqual([point.label for point in points], [
            "0", "0.025", "0.05", "0.075", "0.1", "0.125", "0.15",
            "0.175", "0.2", "0.225", "0.25", "0.275", "0.3",
        ])
        self.assertEqual([point.label for point in points if point.is_baseline], ["0.15"])
        for point in points:
            self.assertEqual(point.policy_overrides.keys(), lqr.POLICY_2024_OVERRIDES.keys())
            self.assertEqual(
                point.policy_overrides["CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB"],
                point.label,
            )
            self.assertEqual(
                point.policy_overrides["CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM"],
                point.label,
            )
            for key in set(lqr.POLICY_2024_OVERRIDES) - set(lqr.LTI_QUOTA_KEYS):
                self.assertEqual(point.policy_overrides[key], lqr.POLICY_2024_OVERRIDES[key])

    def test_policy_grid_raises_when_baseline_missing(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Baseline quota 0.15 was not present"):
            lqr.build_quota_points((0.0, 0.1, 0.2), lqr.BASELINE_QUOTA)

    def test_policy_grid_raises_when_multiple_values_match_baseline_tolerance(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Multiple baseline quota values"):
            lqr.build_quota_points((0.15, 0.1500000005), lqr.BASELINE_QUOTA)

    def test_policy_grid_rejects_exact_duplicate_quota_labels(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Duplicate quota label"):
            lqr.build_quota_points((0.15, 0.15), lqr.BASELINE_QUOTA)

    def test_policy_grid_rejects_near_duplicate_quota_labels_after_formatting(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Duplicate quota label"):
            lqr.build_quota_points((0.15, 0.150000000001), lqr.BASELINE_QUOTA)

    def test_load_valid_cached_run_metrics_accepts_exact_matching_payload(self) -> None:
        payload = self._run_metrics_payload()
        self.assertEqual(
            list(payload.keys()),
            [
                "experiment_id",
                "version",
                "seed",
                "quota_label",
                "quota",
                "point_id",
                "is_baseline",
                "policy_overrides",
                "n_steps",
                "metric_window",
                "metric_ids",
                "metrics",
                "output_dir",
                "config_path",
                "command",
                "cached",
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = self._write_run_metrics(Path(tmpdir), payload)

            cached_payload = lqr.load_valid_cached_run_metrics(
                cache_path,
                self._run_request(),
                lqr.METRIC_IDS,
            )

        expected_payload = dict(payload)
        expected_payload["cached"] = True
        self.assertEqual(cached_payload, expected_payload)

    def test_load_valid_cached_run_metrics_rejects_mismatched_metric_window(self) -> None:
        payload = self._run_metrics_payload()
        payload["metric_window"] = {"mode": "index_slice", "start_index": 0, "end_index": 3500}

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = self._write_run_metrics(Path(tmpdir), payload)

            cached_payload = lqr.load_valid_cached_run_metrics(
                cache_path,
                self._run_request(),
                lqr.METRIC_IDS,
            )

        self.assertIsNone(cached_payload)

    def test_load_valid_cached_run_metrics_rejects_mismatched_seed(self) -> None:
        payload = self._run_metrics_payload()
        payload["seed"] = 2

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = self._write_run_metrics(Path(tmpdir), payload)

            cached_payload = lqr.load_valid_cached_run_metrics(
                cache_path,
                self._run_request(),
                lqr.METRIC_IDS,
            )

        self.assertIsNone(cached_payload)

    def test_load_valid_cached_run_metrics_rejects_mismatched_quota(self) -> None:
        payload = self._run_metrics_payload()
        payload["quota"] = 0.200

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = self._write_run_metrics(Path(tmpdir), payload)

            cached_payload = lqr.load_valid_cached_run_metrics(
                cache_path,
                self._run_request(),
                lqr.METRIC_IDS,
            )

        self.assertIsNone(cached_payload)

    def test_load_valid_cached_run_metrics_rejects_mismatched_metric_ids(self) -> None:
        payload = self._run_metrics_payload()
        payload["metric_ids"] = list(reversed(lqr.METRIC_IDS))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = self._write_run_metrics(Path(tmpdir), payload)

            cached_payload = lqr.load_valid_cached_run_metrics(
                cache_path,
                self._run_request(),
                lqr.METRIC_IDS,
            )

        self.assertIsNone(cached_payload)

    def test_load_valid_cached_run_metrics_rejects_incomplete_metric_payload(self) -> None:
        payload = self._run_metrics_payload()
        metrics = self._metric_values()
        del metrics[lqr.METRIC_IDS[-1]]
        payload["metrics"] = metrics

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = self._write_run_metrics(Path(tmpdir), payload)

            cached_payload = lqr.load_valid_cached_run_metrics(
                cache_path,
                self._run_request(),
                lqr.METRIC_IDS,
            )

        self.assertIsNone(cached_payload)

    def test_load_valid_cached_run_metrics_marks_valid_cache_hit_as_cached_copy(self) -> None:
        payload = self._run_metrics_payload()

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = self._write_run_metrics(Path(tmpdir), payload)

            cached_payload = lqr.load_valid_cached_run_metrics(
                cache_path,
                self._run_request(),
                lqr.METRIC_IDS,
            )

        self.assertIsNotNone(cached_payload)
        self.assertFalse(payload["cached"])
        self.assertTrue(cached_payload["cached"])

        expected_payload = dict(payload)
        expected_payload["cached"] = True
        self.assertEqual(cached_payload, expected_payload)

    def test_load_valid_cached_run_metrics_rejects_invalid_metric_values(self) -> None:
        invalid_metric_values = [
            float("nan"),
            float("inf"),
            None,
            "1.0",
            True,
        ]

        for invalid_metric_value in invalid_metric_values:
            with self.subTest(invalid_metric_value=invalid_metric_value):
                payload = self._run_metrics_payload()
                metrics = self._metric_values()
                metrics[lqr.METRIC_IDS[0]] = invalid_metric_value
                payload["metrics"] = metrics

                with tempfile.TemporaryDirectory() as tmpdir:
                    cache_path = self._write_run_metrics(Path(tmpdir), payload)

                    cached_payload = lqr.load_valid_cached_run_metrics(
                        cache_path,
                        self._run_request(),
                        lqr.METRIC_IDS,
                    )

                self.assertIsNone(cached_payload)

    def test_execute_java_run_reruns_when_generated_config_is_stale(self) -> None:
        cached_metrics = self._metric_values()
        fresh_metrics = {metric_id: value + 10.0 for metric_id, value in cached_metrics.items()}

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo_root = root / "repo"
            output_root = root / "output"
            version_config_path = repo_root / "input-data-versions" / "v0o7" / "config.properties"
            version_config_path.parent.mkdir(parents=True)
            version_config_path.write_text("source config\n", encoding="utf-8")

            request = self._run_request()
            run_dir = output_root / "runs" / request.version / f"seed-{request.seed}" / request.point.point_id
            config_path = (
                output_root
                / "configs"
                / request.version
                / f"{request.point.point_id}-seed-{request.seed}.properties"
            )
            run_dir.mkdir(parents=True)
            config_path.parent.mkdir(parents=True)
            config_path.write_text("stale config\n", encoding="utf-8")
            self._write_run_metrics(
                run_dir,
                lqr.build_run_metrics_payload(
                    request=request,
                    output_dir=run_dir,
                    config_path=config_path,
                    metrics=cached_metrics,
                    command=["./mvnw", "exec:java"],
                    cached=False,
                ),
            )

            with mock.patch(
                "scripts.python.experiments.model.lti_quota_response.build_snapshot_local_config_text",
                return_value="fresh config\n",
            ), mock.patch(
                "scripts.python.experiments.model.lti_quota_response.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout=""),
            ) as run_mock, mock.patch(
                "scripts.python.experiments.model.lti_quota_response.extract_metrics_from_output",
                return_value=fresh_metrics,
            ) as extract_mock:
                metrics = lqr.execute_java_run(
                    repo_root=repo_root,
                    output_root=output_root,
                    request=request,
                    force_rerun=False,
                    maven_bin="./mvnw",
                )

            self.assertEqual(metrics, fresh_metrics)
            self.assertEqual(config_path.read_text(encoding="utf-8"), "fresh config\n")
            run_mock.assert_called_once()
            extract_mock.assert_called_once_with(run_dir)

    def test_execute_java_run_reruns_when_snapshot_local_input_is_newer_than_cache(self) -> None:
        cached_metrics = self._metric_values()
        fresh_metrics = {metric_id: value + 20.0 for metric_id, value in cached_metrics.items()}

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            repo_root = root / "repo"
            output_root = root / "output"
            version_dir = repo_root / "input-data-versions" / "v0o7"
            version_config_path = version_dir / "config.properties"
            snapshot_input_path = version_dir / "household-input.txt"
            version_dir.mkdir(parents=True)
            version_config_path.write_text("source config\n", encoding="utf-8")
            snapshot_input_path.write_text("newer snapshot-local input\n", encoding="utf-8")

            request = self._run_request()
            run_dir = output_root / "runs" / request.version / f"seed-{request.seed}" / request.point.point_id
            config_path = (
                output_root
                / "configs"
                / request.version
                / f"{request.point.point_id}-seed-{request.seed}.properties"
            )
            rendered_config = f'INPUT_FILE = "{snapshot_input_path}"\n'
            run_dir.mkdir(parents=True)
            config_path.parent.mkdir(parents=True)
            config_path.write_text(rendered_config, encoding="utf-8")
            cache_path = self._write_run_metrics(
                run_dir,
                lqr.build_run_metrics_payload(
                    request=request,
                    output_dir=run_dir,
                    config_path=config_path,
                    metrics=cached_metrics,
                    command=["./mvnw", "exec:java"],
                    cached=False,
                ),
            )

            base_time = 1_700_000_000
            os.utime(version_config_path, (base_time, base_time))
            os.utime(config_path, (base_time + 5, base_time + 5))
            os.utime(cache_path, (base_time + 10, base_time + 10))
            os.utime(snapshot_input_path, (base_time + 20, base_time + 20))

            with mock.patch(
                "scripts.python.experiments.model.lti_quota_response.build_snapshot_local_config_text",
                return_value=rendered_config,
            ), mock.patch(
                "scripts.python.experiments.model.lti_quota_response.subprocess.run",
                return_value=mock.Mock(returncode=0, stdout=""),
            ) as run_mock, mock.patch(
                "scripts.python.experiments.model.lti_quota_response.extract_metrics_from_output",
                return_value=fresh_metrics,
            ) as extract_mock:
                metrics = lqr.execute_java_run(
                    repo_root=repo_root,
                    output_root=output_root,
                    request=request,
                    force_rerun=False,
                    maven_bin="./mvnw",
                )

            self.assertEqual(metrics, fresh_metrics)
            run_mock.assert_called_once()
            extract_mock.assert_called_once_with(run_dir)

    def test_build_reproduce_command_shell_quotes_string_args(self) -> None:
        args = lqr.build_arg_parser().parse_args([
            "--output-dir", "tmp/lti quota response",
            "--seeds", "1,2",
            "--quota-values", "0.15,0.3",
            "--workers", "3",
            "--maven-bin", "/tmp/maven wrapper/mvnw",
        ])

        command = lqr.build_reproduce_command(args)

        self.assertIn("--output-dir 'tmp/lti quota response'", command)
        self.assertIn("--maven-bin '/tmp/maven wrapper/mvnw'", command)

    def test_plot_only_reads_aggregate_json_and_does_not_compile_or_run_java(self) -> None:
        rows = [
            lqr.AggregatedMetricRow(
                version="v0o7",
                quota_label="0.15",
                quota=0.15,
                is_baseline=True,
                metric_id="core_debtToIncome",
                raw_mean=100.0,
                raw_stdev=1.0,
                raw_ci_low=99.0,
                raw_ci_high=101.0,
                raw_n=10,
                delta_percent_mean=0.0,
                delta_percent_stdev=0.0,
                delta_percent_ci_low=0.0,
                delta_percent_ci_high=0.0,
                delta_percent_n=10,
            ),
            lqr.AggregatedMetricRow(
                version="v5o3",
                quota_label="0.15",
                quota=0.15,
                is_baseline=True,
                metric_id="core_debtToIncome",
                raw_mean=200.0,
                raw_stdev=1.0,
                raw_ci_low=199.0,
                raw_ci_high=201.0,
                raw_n=10,
                delta_percent_mean=0.0,
                delta_percent_stdev=0.0,
                delta_percent_ci_low=0.0,
                delta_percent_ci_high=0.0,
                delta_percent_n=10,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            lqr.write_aggregated_json(output_dir / "lti_quota_response_aggregated.json", rows)
            argv = ["lti_quota_response.py", "--output-dir", str(output_dir), "--plot-only"]
            with mock.patch.object(sys, "argv", argv), mock.patch(
                "scripts.python.experiments.model.lti_quota_response.ensure_project_compiled",
                side_effect=AssertionError("compile must not run in plot-only mode"),
            ), mock.patch(
                "scripts.python.experiments.model.lti_quota_response.execute_java_run",
                side_effect=AssertionError("java must not run in plot-only mode"),
            ):
                lqr.main()

            figure_path = output_dir / "core_debtToIncome_lti_quota_response.png"
            self.assertTrue(figure_path.exists())
            self.assertGreater(figure_path.stat().st_size, 0)

    def test_write_figures_uses_metric_rows_for_x_ticks(self) -> None:
        rows = [
            self._aggregated_row(version="v5o3", quota=0.225),
            self._aggregated_row(version="v0o7", quota=0.050),
            self._aggregated_row(version="v0o7", quota=0.175),
            self._aggregated_row(version="v5o3", quota=0.050),
        ]
        axis = self._RecordingAxis()
        figure = self._RecordingFigure()

        with tempfile.TemporaryDirectory() as tmp_dir, mock.patch.object(
            lqr.plt,
            "subplots",
            return_value=(figure, axis),
        ), mock.patch.object(lqr.plt, "close"):
            lqr.write_figures(Path(tmp_dir), rows)

        self.assertEqual(axis.xticks, [5.0, 17.5, 22.5])

    def test_write_figures_closes_figure_when_png_save_fails(self) -> None:
        axis = self._RecordingAxis()
        figure = self._RecordingFigure(fail_png=True)

        with tempfile.TemporaryDirectory() as tmp_dir, mock.patch.object(
            lqr.plt,
            "subplots",
            return_value=(figure, axis),
        ), mock.patch.object(lqr.plt, "close") as close_mock:
            with self.assertRaisesRegex(RuntimeError, "png failed"):
                lqr.write_figures(Path(tmp_dir), [self._aggregated_row()])

        close_mock.assert_called_once_with(figure)

    def test_write_figures_warns_when_pdf_save_fails(self) -> None:
        axis = self._RecordingAxis()
        figure = self._RecordingFigure(fail_pdf=True)

        with tempfile.TemporaryDirectory() as tmp_dir, mock.patch.object(
            lqr.plt,
            "subplots",
            return_value=(figure, axis),
        ), mock.patch.object(lqr.plt, "close"), warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            lqr.write_figures(Path(tmp_dir), [self._aggregated_row()])

        self.assertTrue(any("Could not save PDF figure" in str(item.message) for item in caught))
        self.assertTrue(any("pdf failed" in str(item.message) for item in caught))

    def test_main_run_path_compiles_once_writes_manifest_run_csv_and_aggregate_json(self) -> None:
        synthetic_metrics = {
            "core_debtToIncome": 100.0,
            "core_ooLTI": 4.4,
            "core_advancesToFTB": 12.0,
            "core_advancesToHM": 18.0,
            "core_advancesToBTL": 6.0,
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir) / "lti"
            argv = [
                "lti_quota_response.py",
                "--output-dir", str(output_dir),
                "--seeds", "1",
                "--quota-values", "0.15,0.3",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch(
                "scripts.python.experiments.model.lti_quota_response.ensure_project_compiled"
            ) as compile_mock, mock.patch(
                "scripts.python.experiments.model.lti_quota_response.execute_java_run",
                return_value=synthetic_metrics,
            ) as run_mock, mock.patch(
                "scripts.python.experiments.model.lti_quota_response.write_figures"
            ):
                lqr.main()

            compile_mock.assert_called_once()
            self.assertEqual(run_mock.call_count, 4)
            self.assertTrue((output_dir / "manifest.json").exists())
            self.assertTrue((output_dir / "lti_quota_response_runs.csv").exists())
            self.assertTrue((output_dir / "lti_quota_response_aggregated.csv").exists())
            self.assertTrue((output_dir / "lti_quota_response_aggregated.json").exists())


if __name__ == "__main__":
    unittest.main()
