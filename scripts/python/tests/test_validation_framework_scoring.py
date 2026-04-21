"""Tests for the 2024 validation framework scoring rules.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model.scoring import (
    classify_metric_status,
    compute_metric_loss,
    compute_overall_composite_loss,
    resolve_loss_scale,
)


class TestValidationFrameworkScoring(unittest.TestCase):
    def test_pass_requires_inside_band_and_inside_rate_at_least_three_quarters(self) -> None:
        status = classify_metric_status(
            seed_mean=100.0,
            lower_bound=95.0,
            upper_bound=105.0,
            inside_rate=0.75,
        )
        self.assertEqual(status, "pass")

    def test_warn_allows_small_distance_and_moderate_inside_rate(self) -> None:
        status = classify_metric_status(
            seed_mean=108.0,
            lower_bound=95.0,
            upper_bound=105.0,
            inside_rate=0.50,
        )
        self.assertEqual(status, "warn")

    def test_metric_loss_uses_target_level_normalization(self) -> None:
        loss = compute_metric_loss(
            seed_mean=110.0,
            p25=108.0,
            p75=112.0,
            lower_bound=95.0,
            upper_bound=105.0,
            inside_rate=0.25,
            loss_scale=100.0,
        )
        self.assertAlmostEqual(loss, 0.05 + 0.25 * 0.04 + 0.50 * 0.75)

    def test_loss_scale_prefers_positive_source_value(self) -> None:
        scale, basis = resolve_loss_scale(source_value=27.833, lower_bound=23.658, upper_bound=32.008)
        self.assertAlmostEqual(scale, 27.833)
        self.assertEqual(basis, "source_value")

    def test_loss_scale_falls_back_to_target_band_midpoint(self) -> None:
        scale, basis = resolve_loss_scale(source_value=None, lower_bound=4.0, upper_bound=10.0)
        self.assertAlmostEqual(scale, 7.0)
        self.assertEqual(basis, "target_band_midpoint")

    def test_loss_scale_uses_target_band_upper_for_zero_anchored_bands(self) -> None:
        scale, basis = resolve_loss_scale(source_value=None, lower_bound=0.0, upper_bound=0.12)
        self.assertAlmostEqual(scale, 0.12)
        self.assertEqual(basis, "target_band_upper")

    def test_overall_loss_is_weighted_mean_of_metric_losses(self) -> None:
        loss = compute_overall_composite_loss(
            metric_losses=[0.2, 0.4, 0.6],
            metric_weights=[1.0, 1.0, 1.0],
        )
        self.assertAlmostEqual(loss, 0.4)
