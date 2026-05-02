"""Tests for BTL output multiplier calibration helpers.

@author: Max Stoddard
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from scripts.python.calibration.output.btl_probability_multiplier import (
    BTL_PROBABILITY_MULTIPLIER,
    DEFAULT_COARSE_MAX,
    DEFAULT_COARSE_MIN,
    DEFAULT_COARSE_STEP,
    DEFAULT_PRECISION,
    CandidateSummary,
    SeedRunResult,
    build_arg_parser,
    build_candidate_grid,
    build_fine_candidate_grid,
    build_search_diagnostics,
    build_run_overrides,
    config_text_hash,
    create_output_version,
    extract_rental_income_positive_share,
    load_cached_seed_result,
    select_best_candidate,
    snap_to_precision,
    update_config_property,
    validate_version_name,
)


class TestOutputBtlProbabilityMultiplier(unittest.TestCase):
    def test_parser_requires_explicit_versions(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                build_arg_parser().parse_args([])

        args = build_arg_parser().parse_args(
            ["--version", "v4.14", "--output-version", "v4.14o"]
        )

        self.assertEqual(args.version, "v4.14")
        self.assertEqual(args.output_version, "v4.14o")
        self.assertEqual(args.precision, DEFAULT_PRECISION)
        self.assertEqual(args.seeds, "1,2,3,4")
        self.assertEqual(args.workers, 20)
        self.assertEqual(args.coarse_min, DEFAULT_COARSE_MIN)
        self.assertEqual(args.coarse_max, DEFAULT_COARSE_MAX)
        self.assertEqual(args.coarse_step, DEFAULT_COARSE_STEP)

    def test_validate_version_name_accepts_snapshot_versions_only(self) -> None:
        self.assertEqual(validate_version_name("v4.14o"), "v4.14o")

        for invalid_version in [
            "validation",
            "tmp",
            "calibration-evidence",
            "../v4.14o",
            "v4.14o/child",
        ]:
            with self.subTest(version=invalid_version):
                with self.assertRaises(ValueError):
                    validate_version_name(invalid_version)

    def test_precision_controls_fine_grid_and_snapping(self) -> None:
        coarse = build_candidate_grid(0.05, 2.0, 0.05)
        fine = build_fine_candidate_grid(
            best_coarse=0.9,
            lower_bound=0.8,
            upper_bound=1.0,
            radius=0.01,
            precision=0.005,
        )

        self.assertEqual(len(coarse), 40)
        self.assertEqual(round(coarse[0], 3), 0.05)
        self.assertEqual(round(coarse[-1], 3), 2.0)
        self.assertNotIn(2.05, [round(value, 3) for value in coarse])
        self.assertEqual(
            [round(value, 3) for value in fine],
            [0.89, 0.895, 0.9, 0.905, 0.91],
        )
        self.assertAlmostEqual(snap_to_precision(1.7624, 0.005), 1.76)
        self.assertAlmostEqual(snap_to_precision(1.7625, 0.005), 1.765)

    def test_rental_income_share_uses_t_ge_200_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "MonthlyGrossRentalIncome-run1.csv"
            path.write_text(
                "\n".join(
                    [
                        "100; 10.0; 0.0",
                        "200; 0.0; 5.0; 10.0",
                        "212; 0.0; 0.0; 4.0",
                        "2000; 2.0; 0.0",
                        "2004; 10.0; 10.0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            share = extract_rental_income_positive_share(path)

        expected = ((2.0 / 3.0) + (1.0 / 3.0) + (1.0 / 2.0)) / 3.0
        self.assertAlmostEqual(share, expected)

    def test_select_best_candidate_uses_primary_gap_only(self) -> None:
        worse_diagnostics_better_gap = self._summary(
            multiplier=1.2,
            target_gap=0.001,
            active_btl_share_mean=0.5,
            btl_stock_fraction_mean=0.5,
        )
        better_diagnostics_worse_gap = self._summary(
            multiplier=1.1,
            target_gap=0.002,
            active_btl_share_mean=0.01,
            btl_stock_fraction_mean=0.01,
        )
        tied_lower_multiplier = self._summary(multiplier=1.0, target_gap=0.001)

        selected = select_best_candidate(
            [
                worse_diagnostics_better_gap,
                better_diagnostics_worse_gap,
                tied_lower_multiplier,
            ]
        )

        self.assertEqual(selected.multiplier, 1.0)

    def test_search_diagnostics_flags_boundary_and_target_miss(self) -> None:
        coarse = [
            self._summary(multiplier=0.05, rental_income_positive_share_mean=0.06),
            self._summary(multiplier=0.1, rental_income_positive_share_mean=0.07),
        ]
        fine = [
            self._summary(multiplier=0.05, rental_income_positive_share_mean=0.06),
            self._summary(multiplier=0.055, rental_income_positive_share_mean=0.061),
        ]

        diagnostics = build_search_diagnostics(
            coarse_summaries=coarse,
            fine_summaries=fine,
            best_coarse=coarse[0],
            best_fine=fine[0],
            target=0.05,
        )

        self.assertFalse(diagnostics["coarse"]["targetBracketed"])
        self.assertTrue(diagnostics["coarse"]["selectedOnLowerBoundary"])
        self.assertFalse(diagnostics["fine"]["targetBracketed"])
        self.assertTrue(diagnostics["fine"]["selectedOnLowerBoundary"])
        self.assertTrue(diagnostics["promotedWithWarnings"])
        self.assertTrue(
            any("do not bracket" in warning for warning in diagnostics["warnings"])
        )

    def test_cache_load_requires_matching_config_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.properties"
            config_path.write_text("BTL_PROBABILITY_MULTIPLIER = 0.5\n", encoding="utf-8")
            output_dir = root / "run"
            output_dir.mkdir()
            (output_dir / "MonthlyGrossRentalIncome-run1.csv").write_text("200; 1.0\n", encoding="utf-8")
            (output_dir / "Output-run1.csv").write_text("Model time; TotalPopulation; nActiveBTL; nBTL; BTLStockFraction\n", encoding="utf-8")
            config_hash = config_text_hash(config_path.read_text(encoding="utf-8"))
            metrics_path = output_dir / "btl_multiplier_metrics.json"
            result = SeedRunResult(
                stage="coarse",
                multiplier=0.5,
                seed=1,
                output_dir=str(output_dir),
                config_path=str(config_path),
                config_hash=config_hash,
                cached=False,
                rental_income_positive_share=0.1,
                active_btl_share=0.2,
                latent_btl_share=0.3,
                btl_stock_fraction=0.4,
            )
            metrics_path.write_text(json.dumps(asdict(result)), encoding="utf-8")

            cached = load_cached_seed_result(
                metrics_path,
                expected_stage="coarse",
                expected_multiplier=0.5,
                expected_seed=1,
                expected_config_hash=config_hash,
            )
            stale = load_cached_seed_result(
                metrics_path,
                expected_stage="coarse",
                expected_multiplier=0.5,
                expected_seed=1,
                expected_config_hash=config_text_hash("different\n"),
            )

        self.assertIsNotNone(cached)
        self.assertTrue(cached.cached if cached is not None else False)
        self.assertIsNone(stale)

    def test_config_update_only_changes_multiplier(self) -> None:
        config = (
            'DATA_BTL_PROBABILITY = "src/main/resources/BTLProbabilityPerIncomePercentileBin-R8.csv"\n'
            "BTL_PROBABILITY_MULTIPLIER = 1.76\n"
            "BTL_CHOICE_INTENSITY = 100.0\n"
        )

        updated = update_config_property(config, BTL_PROBABILITY_MULTIPLIER, "1.235")

        self.assertIn("BTL_PROBABILITY_MULTIPLIER = 1.235", updated)
        self.assertIn(
            'DATA_BTL_PROBABILITY = "src/main/resources/BTLProbabilityPerIncomePercentileBin-R8.csv"',
            updated,
        )
        self.assertIn("BTL_CHOICE_INTENSITY = 100.0", updated)

    def test_create_output_version_copies_source_and_updates_multiplier_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            source_dir = repo_root / "input-data-versions" / "v4.14"
            source_dir.mkdir(parents=True)
            (source_dir / "config.properties").write_text(
                'DATA_BTL_PROBABILITY = "src/main/resources/BTLProbabilityPerIncomePercentileBin-R8.csv"\n'
                "BTL_PROBABILITY_MULTIPLIER = 1.76\n",
                encoding="utf-8",
            )
            (source_dir / "BTLProbabilityPerIncomePercentileBin-R8.csv").write_text(
                "0,0.01,0.1\n",
                encoding="utf-8",
            )

            output_dir = create_output_version(
                repo_root=repo_root,
                source_version="v4.14",
                output_version="v4.14o",
                selected_multiplier=1.235,
                overwrite=False,
            )

            output_config = (output_dir / "config.properties").read_text(encoding="utf-8")
            self.assertIn("BTL_PROBABILITY_MULTIPLIER = 1.235", output_config)
            self.assertIn("WAS Round 8 positive-gross-rental-income", output_config)
            self.assertIn("0.0515255103048705", output_config)
            self.assertIn("Selected BTL_PROBABILITY_MULTIPLIER = 1.235", output_config)
            self.assertIn(
                'DATA_BTL_PROBABILITY = "src/main/resources/BTLProbabilityPerIncomePercentileBin-R8.csv"',
                output_config,
            )
            self.assertTrue((output_dir / "BTLProbabilityPerIncomePercentileBin-R8.csv").exists())

    def test_create_output_version_rejects_self_overwrite_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            source_dir = repo_root / "input-data-versions" / "v4.14"
            source_dir.mkdir(parents=True)
            config_path = source_dir / "config.properties"
            config_path.write_text(
                "BTL_PROBABILITY_MULTIPLIER = 1.76\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                create_output_version(
                    repo_root=repo_root,
                    source_version="v4.14",
                    output_version="v4.14",
                    selected_multiplier=1.235,
                    overwrite=True,
                )

            self.assertTrue(config_path.exists())

    def test_create_output_version_rejects_invalid_output_before_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            source_dir = repo_root / "input-data-versions" / "v4.14"
            invalid_output_dir = repo_root / "input-data-versions" / "validation"
            source_dir.mkdir(parents=True)
            invalid_output_dir.mkdir()
            config_path = source_dir / "config.properties"
            config_path.write_text(
                "BTL_PROBABILITY_MULTIPLIER = 1.76\n",
                encoding="utf-8",
            )
            marker_path = invalid_output_dir / "marker.txt"
            marker_path.write_text("do not delete\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                create_output_version(
                    repo_root=repo_root,
                    source_version="v4.14",
                    output_version="validation",
                    selected_multiplier=1.235,
                    overwrite=True,
                )

            self.assertTrue(config_path.exists())
            self.assertTrue(marker_path.exists())

    def test_run_overrides_force_required_model_settings(self) -> None:
        overrides = build_run_overrides(multiplier=1.235, seed=4)

        self.assertEqual(overrides["SEED"], "4")
        self.assertEqual(overrides["N_STEPS"], "2000")
        self.assertEqual(overrides["recordRentalIncome"], "true")
        self.assertEqual(overrides["recordCoreIndicators"], "true")
        self.assertEqual(overrides["BTL_PROBABILITY_MULTIPLIER"], "1.235")

    def _summary(
        self,
        *,
        multiplier: float,
        target_gap: float = 0.0,
        rental_income_positive_share_mean: float | None = None,
        active_btl_share_mean: float = 0.0,
        btl_stock_fraction_mean: float = 0.0,
    ) -> CandidateSummary:
        mean_share = (
            0.05 + target_gap
            if rental_income_positive_share_mean is None
            else rental_income_positive_share_mean
        )
        return CandidateSummary(
            stage="fine",
            multiplier=multiplier,
            target=0.05,
            target_gap=abs(mean_share - 0.05),
            rental_income_positive_share_mean=mean_share,
            rental_income_positive_share_stdev=0.0,
            active_btl_share_mean=active_btl_share_mean,
            latent_btl_share_mean=0.0,
            btl_stock_fraction_mean=btl_stock_fraction_mean,
            seed_count=4,
            seeds=(1, 2, 3, 4),
        )


if __name__ == "__main__":
    unittest.main()
