"""Tests for cached validation-loss weight sensitivity analysis.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.python.validation.model.loss_weight_sensitivity import (
    CURRENT_WEIGHT_LABEL,
    MetricComponents,
    METRIC_DELTA_COLORBAR_SHRINK,
    METRIC_DELTA_COLORBAR_LABEL,
    METRIC_DELTA_SIGN_COLORS,
    OPTIMISED_MODEL_LABEL,
    ORIGINAL_MODEL_LABEL,
    RANK_STABILITY_DECIMALS,
    RANK_STABILITY_COLORMAP,
    SIGN_HEATMAP_BOUNDARIES,
    SIGN_HEATMAP_COLORMAP,
    SIGN_HEATMAP_TICK_LABELS,
    SIGN_HEATMAP_TICKS,
    TOTAL_LOSS_COLORBAR_LABEL,
    TOTAL_LOSS_HEATMAP_COLORMAP,
    TOTAL_LOSS_SIGNIFICANT_FIGURES,
    WeightSpec,
    compare_summaries,
    default_weight_grid,
    group_separator_top_y,
    kendall_tau,
    load_summary,
    format_heatmap_label,
    metric_display_label,
    metric_components_from_summary_metric,
    rank_stability_rows,
    rescore_metric_loss,
    sign_score,
    run_analysis,
    sign_label,
    spearman_correlation,
    validate_expected_summary,
    weight_axis_spec,
)


class TestValidationLossWeightSensitivity(unittest.TestCase):
    def _summary(self, version: str, first_loss: float, second_loss: float) -> dict[str, object]:
        return {
            "version": version,
            "validationTargetYear": 2011,
            "seeds": list(range(1, 11)),
            "window": {"startIndex": 500, "endIndex": 3500},
            "overallCompositeLoss": (first_loss + second_loss) / 2,
            "metrics": [
                {
                    "metricId": "metric_a",
                    "label": "Metric A",
                    "requirement": "required",
                    "metricWeight": 1.0,
                    "distanceComponent": first_loss,
                    "insideRateComponent": 0.0,
                    "spreadComponent": 0.0,
                    "levelComponent": 0.0,
                    "normalizedIqr": 0.0,
                    "metricLoss": first_loss,
                },
                {
                    "metricId": "metric_b",
                    "label": "Metric B",
                    "requirement": "required",
                    "metricWeight": 1.0,
                    "distanceComponent": second_loss,
                    "insideRateComponent": 0.0,
                    "spreadComponent": 0.0,
                    "levelComponent": 0.0,
                    "normalizedIqr": 0.0,
                    "metricLoss": second_loss,
                },
            ],
        }

    def test_default_grid_excludes_central_only_and_preserves_approved_ordering(self) -> None:
        grid = default_weight_grid()
        pairs = [(weight.reliability, weight.dispersion_shape) for weight in grid]

        self.assertEqual(
            pairs,
            [
                (0.25, 0.125),
                (0.5, 0.125),
                (0.5, 0.25),
                (0.5, 0.375),
                (0.75, 0.125),
                (0.75, 0.25),
                (0.75, 0.375),
                (0.75, 0.5),
            ],
        )
        self.assertEqual(len(grid), 8)
        self.assertEqual({weight.reliability for weight in grid}, {0.25, 0.5, 0.75})
        self.assertEqual({weight.dispersion_shape for weight in grid}, {0.125, 0.25, 0.375, 0.5})
        self.assertIn(CURRENT_WEIGHT_LABEL, [weight.label for weight in grid])
        self.assertEqual(
            next(weight for weight in grid if weight.label == CURRENT_WEIGHT_LABEL),
            WeightSpec(label=CURRENT_WEIGHT_LABEL, reliability=0.5, dispersion_shape=0.25),
        )
        for weight in grid:
            self.assertEqual(weight.central, 1.0)
            self.assertGreater(weight.reliability, 0.0)
            self.assertGreater(weight.dispersion_shape, 0.0)
            self.assertGreater(weight.reliability, weight.dispersion_shape)
            self.assertLess(weight.reliability, weight.central)

    def test_heatmaps_use_colourblind_safer_colormaps(self) -> None:
        self.assertEqual(TOTAL_LOSS_HEATMAP_COLORMAP, "RdBu_r")
        self.assertEqual(RANK_STABILITY_COLORMAP, "Blues")

    def test_metric_delta_heatmap_uses_ternary_sign_colormap(self) -> None:
        self.assertEqual(SIGN_HEATMAP_COLORMAP, "validation_delta_sign")
        self.assertEqual(METRIC_DELTA_SIGN_COLORS, ("#2166AC", "#B2182B"))
        self.assertEqual(SIGN_HEATMAP_BOUNDARIES, (-1.5, 0.0, 1.5))
        self.assertEqual(SIGN_HEATMAP_TICKS, (-1, 1))
        self.assertEqual(SIGN_HEATMAP_TICK_LABELS, ("Improved", "Regressed"))
        self.assertEqual(METRIC_DELTA_COLORBAR_SHRINK, 0.35)

    def test_plot_labels_use_academic_model_names(self) -> None:
        self.assertEqual(ORIGINAL_MODEL_LABEL, "The original model")
        self.assertEqual(OPTIMISED_MODEL_LABEL, "The optimised model")
        self.assertEqual(METRIC_DELTA_COLORBAR_LABEL, "Optimised vs original model loss delta (%)")
        self.assertEqual(TOTAL_LOSS_COLORBAR_LABEL, "Optimised vs original model loss delta (%)")
        self.assertNotIn("v0", METRIC_DELTA_COLORBAR_LABEL)
        self.assertNotIn("v0o7", METRIC_DELTA_COLORBAR_LABEL)
        self.assertNotIn("v0", TOTAL_LOSS_COLORBAR_LABEL)
        self.assertNotIn("v0o7", TOTAL_LOSS_COLORBAR_LABEL)

    def test_metric_display_label_uses_report_abbreviations(self) -> None:
        self.assertEqual(metric_display_label("core_priceToIncome", "House Price to Household Disposable Income"), "House PIR")
        self.assertEqual(metric_display_label("core_debtToIncome", "Household Debt to Income"), "HH DTI")
        self.assertEqual(metric_display_label("core_ooDebtToIncome", "Owner-Occupier Debt to Income"), "OO DTI")
        self.assertEqual(
            metric_display_label("income_distribution_jsd", "Income Distribution Realism"),
            "Income Realism",
        )
        self.assertEqual(metric_display_label("unknown_metric", "Verbose Label"), "Verbose Label")

    def test_heatmap_label_formats_rounded_zero_as_plain_zero(self) -> None:
        self.assertEqual(format_heatmap_label(-0.0001, decimals=2), "0")
        self.assertEqual(format_heatmap_label(0.0001, decimals=2), "0")
        self.assertEqual(format_heatmap_label(-0.014, decimals=2), "-0.01")
        self.assertEqual(format_heatmap_label(0.126, decimals=2), "0.13")
        self.assertEqual(format_heatmap_label(-0.0001, decimals=1, suffix="%"), "0%")
        self.assertEqual(format_heatmap_label(-3.84, decimals=1, suffix="%"), "-3.8%")

    def test_heatmap_label_can_include_explicit_delta_signs(self) -> None:
        self.assertEqual(format_heatmap_label(2.5, decimals=1, suffix="%", signed=True), "+2.5%")
        self.assertEqual(format_heatmap_label(-8.04, decimals=1, suffix="%", signed=True), "-8.0%")
        self.assertEqual(format_heatmap_label(0.0001, decimals=1, suffix="%", signed=True), "0%")

    def test_heatmap_label_can_format_significant_figures(self) -> None:
        self.assertEqual(format_heatmap_label(-5.7, significant_figures=3, suffix="%", signed=True), "-5.70%")
        self.assertEqual(format_heatmap_label(-8.1, significant_figures=3, suffix="%", signed=True), "-8.10%")
        self.assertEqual(format_heatmap_label(12.44, significant_figures=3, suffix="%", signed=True), "+12.4%")
        self.assertEqual(format_heatmap_label(0.0, significant_figures=3, suffix="%", signed=True), "0%")

    def test_figure_annotation_precision_matches_academic_exports(self) -> None:
        self.assertEqual(RANK_STABILITY_DECIMALS, 3)
        self.assertEqual(TOTAL_LOSS_SIGNIFICANT_FIGURES, 3)

    def test_weight_axis_spec_groups_dispersion_ticks_by_reliability(self) -> None:
        labels = [weight.label for weight in default_weight_grid()]

        spec = weight_axis_spec(labels)

        self.assertEqual(
            spec.dispersion_labels,
            ("0.125", "0.125", "0.25\n(current)", "0.375", "0.125", "0.25", "0.375", "0.5"),
        )
        self.assertEqual(
            [(group.start, group.end, group.center, group.label) for group in spec.reliability_groups],
            [(0, 0, 0.0, "0.25"), (1, 3, 2.0, "0.5"), (4, 7, 5.5, "0.75")],
        )
        self.assertEqual(spec.separator_positions, (0.5, 3.5))
        self.assertEqual(spec.current_index, 2)

    def test_group_separator_top_extension_scales_for_short_heatmaps(self) -> None:
        self.assertAlmostEqual(group_separator_top_y(row_count=2), -0.56)
        self.assertAlmostEqual(group_separator_top_y(row_count=20), -0.85)

    def test_sign_score_makes_loss_direction_primary(self) -> None:
        self.assertEqual(sign_score(-0.02), -1)
        self.assertEqual(sign_score(0.02), 1)
        self.assertEqual(sign_score(1.0e-13), 0)

    def test_positive_metric_reconstructs_raw_components(self) -> None:
        metric = {
            "metricId": "core_test",
            "requirement": "required",
            "metricWeight": 1.0,
            "distanceComponent": 0.2,
            "insideRateComponent": 0.25,
            "spreadComponent": 0.1,
            "levelComponent": 0.0,
            "normalizedIqr": 0.4,
            "metricLoss": 0.55,
        }

        components = metric_components_from_summary_metric(metric)

        self.assertEqual(
            components,
            MetricComponents(
                metric_id="core_test",
                central_distance=0.2,
                reliability_raw=0.5,
                dispersion_shape_raw=0.4,
                metric_weight=1.0,
            ),
        )
        self.assertAlmostEqual(
            rescore_metric_loss(components, WeightSpec(label="r075-d0125", reliability=0.75, dispersion_shape=0.125)),
            0.625,
        )

    def test_jsd_level_component_is_treated_as_secondary_shape(self) -> None:
        metric = {
            "metricId": "income_distribution_jsd",
            "requirement": "required",
            "metricWeight": 1.0,
            "distanceComponent": 0.0,
            "insideRateComponent": 0.0,
            "spreadComponent": 0.05,
            "levelComponent": 0.2,
            "normalizedIqr": 0.2,
            "metricLoss": 0.25,
        }

        components = metric_components_from_summary_metric(metric)

        self.assertAlmostEqual(components.central_distance, 0.0)
        self.assertAlmostEqual(components.reliability_raw, 0.0)
        self.assertAlmostEqual(components.dispersion_shape_raw, 1.0)
        self.assertAlmostEqual(
            rescore_metric_loss(components, WeightSpec(label="current", reliability=0.5, dispersion_shape=0.25)),
            0.25,
        )
        self.assertAlmostEqual(
            rescore_metric_loss(components, WeightSpec(label="low-shape", reliability=0.5, dispersion_shape=0.125)),
            0.125,
        )

    def test_validate_expected_summary_rejects_mismatched_cache_metadata(self) -> None:
        payload = {
            "version": "v0",
            "validationTargetYear": 2011,
            "seeds": [1, 2, 3],
            "window": {"startIndex": 500, "endIndex": 3500},
            "metrics": [],
        }

        with self.assertRaisesRegex(ValueError, "expected seeds"):
            validate_expected_summary(payload, expected_version="v0")

    def test_load_summary_reads_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "summary.json"
            path.write_text(json.dumps({"version": "v0"}), encoding="utf-8")

            self.assertEqual(load_summary(path), {"version": "v0"})

    def test_sign_label_uses_small_tolerance(self) -> None:
        self.assertEqual(sign_label(-0.1), "improved")
        self.assertEqual(sign_label(0.1), "regressed")
        self.assertEqual(sign_label(1.0e-13), "tied")

    def test_compare_summaries_reports_candidate_lower_across_weights(self) -> None:
        baseline = self._summary("v0", first_loss=0.8, second_loss=0.6)
        candidate = self._summary("v0o7", first_loss=0.4, second_loss=0.5)
        comparison = compare_summaries(
            baseline=baseline,
            candidate=candidate,
            weights=[WeightSpec(label="central-only", reliability=0.0, dispersion_shape=0.0)],
        )

        self.assertEqual(len(comparison.weight_rows), 1)
        self.assertAlmostEqual(comparison.weight_rows[0]["baselineLoss"], 0.7)
        self.assertAlmostEqual(comparison.weight_rows[0]["candidateLoss"], 0.45)
        self.assertEqual(comparison.weight_rows[0]["candidateLower"], True)
        self.assertEqual(comparison.metric_delta_by_weight[0]["metricLabel"], "Metric A")
        self.assertAlmostEqual(comparison.metric_delta_by_weight[0]["lossPctDelta"], -50.0)
        self.assertEqual(comparison.metric_delta_stability[0]["metricId"], "metric_a")
        self.assertEqual(comparison.metric_delta_stability[0]["stableSign"], True)

    def test_compare_summaries_reports_zero_percent_delta_for_zero_loss_tie(self) -> None:
        baseline = self._summary("v0", first_loss=0.0, second_loss=0.6)
        candidate = self._summary("v0o7", first_loss=0.0, second_loss=0.5)
        comparison = compare_summaries(
            baseline=baseline,
            candidate=candidate,
            weights=[WeightSpec(label="central-only", reliability=0.0, dispersion_shape=0.0)],
        )

        self.assertEqual(comparison.metric_delta_by_weight[0]["metricId"], "metric_a")
        self.assertEqual(comparison.metric_delta_by_weight[0]["lossPctDelta"], 0.0)

    def test_rank_correlations_are_exact_for_identical_ordering(self) -> None:
        self.assertAlmostEqual(spearman_correlation([3.0, 2.0, 1.0], [6.0, 5.0, 4.0]), 1.0)
        self.assertAlmostEqual(kendall_tau([3.0, 2.0, 1.0], [6.0, 5.0, 4.0]), 1.0)
        self.assertAlmostEqual(kendall_tau([3.0, 2.0, 1.0], [4.0, 5.0, 6.0]), -1.0)

    def test_rank_stability_rows_report_worst_metric_overlap(self) -> None:
        components_by_version = {
            "v0": [
                MetricComponents("metric_a", 3.0, 0.0, 0.0, 1.0),
                MetricComponents("metric_b", 2.0, 0.0, 0.0, 1.0),
                MetricComponents("metric_c", 1.0, 0.0, 0.0, 1.0),
            ]
        }
        rows = rank_stability_rows(
            components_by_version=components_by_version,
            weights=[
                WeightSpec(label=CURRENT_WEIGHT_LABEL, reliability=0.5, dispersion_shape=0.25),
                WeightSpec(label="central-only", reliability=0.0, dispersion_shape=0.0),
            ],
            worst_n=2,
        )

        self.assertEqual(rows[0]["version"], "v0")
        self.assertEqual(rows[0]["weightLabel"], CURRENT_WEIGHT_LABEL)
        self.assertAlmostEqual(rows[0]["spearman"], 1.0)
        self.assertEqual(rows[0]["worstNOverlap"], 2)
        self.assertEqual(rows[1]["weightLabel"], "central-only")

    def test_run_analysis_writes_expected_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            baseline_path = root / "v0.json"
            candidate_path = root / "v0o7.json"
            output_dir = root / "out"
            baseline_path.write_text(json.dumps(self._summary("v0", 0.8, 0.6)), encoding="utf-8")
            candidate_path.write_text(json.dumps(self._summary("v0o7", 0.4, 0.5)), encoding="utf-8")

            result = run_analysis(
                baseline_path=baseline_path,
                candidate_path=candidate_path,
                output_dir=output_dir,
            )

            self.assertTrue((output_dir / "weight_summary.csv").exists())
            self.assertTrue((output_dir / "metric_delta_by_weight.csv").exists())
            self.assertTrue((output_dir / "metric_delta_stability.csv").exists())
            self.assertTrue((output_dir / "rank_stability.csv").exists())
            self.assertTrue((output_dir / "report.md").exists())
            (output_dir / "metric_delta_sign_heatmap.pdf").write_text("stale", encoding="utf-8")
            (output_dir / "metric_delta_sign_heatmap.png").write_text("stale", encoding="utf-8")
            run_analysis(
                baseline_path=baseline_path,
                candidate_path=candidate_path,
                output_dir=output_dir,
            )
            for stem in ("total_loss_heatmap", "metric_delta_heatmap", "rank_stability_heatmap"):
                for suffix in (".pdf", ".png"):
                    figure_path = output_dir / f"{stem}{suffix}"
                    self.assertTrue(figure_path.exists(), msg=figure_path)
                    self.assertGreater(figure_path.stat().st_size, 0, msg=figure_path)
            self.assertFalse((output_dir / "metric_delta_sign_heatmap.pdf").exists())
            self.assertFalse((output_dir / "metric_delta_sign_heatmap.png").exists())
            with (output_dir / "weight_summary.csv").open(encoding="utf-8", newline="") as handle:
                weight_labels = [row["weightLabel"] for row in csv.DictReader(handle)]
            self.assertNotIn("central-only", weight_labels)
            with (output_dir / "rank_stability.csv").open(encoding="utf-8", newline="") as handle:
                rank_labels = [row["weightLabel"] for row in csv.DictReader(handle)]
            self.assertIn(CURRENT_WEIGHT_LABEL, rank_labels)
            self.assertEqual(result.weight_rows[0]["candidateLower"], True)


if __name__ == "__main__":
    unittest.main()
