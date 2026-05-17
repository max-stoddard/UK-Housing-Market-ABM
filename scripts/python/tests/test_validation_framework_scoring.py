"""Tests for the 2024 validation framework scoring rules.

@author: Max Stoddard
"""

from __future__ import annotations

import math
import unittest

from scripts.python.validation.model.scoring import (
    ZERO_FLOOR_PENALTY,
    classify_metric_status,
    compute_metric_loss,
    compute_metric_loss_audit,
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

    def test_positive_level_loss_is_symmetric_for_multiplicative_misses(self) -> None:
        over_loss = compute_metric_loss(
            loss_family="positive_level",
            seed_mean=300.0,
            p25=295.0,
            p75=305.0,
            lower_bound=90.0,
            upper_bound=100.0,
            inside_rate=0.0,
            source_value=95.0,
        )
        under_loss = compute_metric_loss(
            loss_family="positive_level",
            seed_mean=30.0,
            p25=29.5,
            p75=30.5,
            lower_bound=90.0,
            upper_bound=100.0,
            inside_rate=0.0,
            source_value=95.0,
        )
        self.assertAlmostEqual(over_loss, under_loss)

    def test_v419_btl_positive_level_loss_matches_expected_log_ratio(self) -> None:
        loss = compute_metric_loss(
            loss_family="positive_level",
            seed_mean=17.45106215277778,
            p25=17.17581777777778,
            p75=17.730475555555557,
            lower_bound=4.396,
            upper_bound=5.947,
            inside_rate=0.0,
            source_value=5.17125,
        )
        expected = math.log(17.45106215277778 / 5.947) + 0.25 * math.log(17.730475555555557 / 17.17581777777778) + 0.50
        self.assertAlmostEqual(loss, expected)
        self.assertAlmostEqual(loss, 1.5844592470279106)

    def test_positive_level_uses_zero_floor_penalty_for_nonpositive_means(self) -> None:
        audit = compute_metric_loss_audit(
            loss_family="positive_level",
            seed_mean=0.0,
            p25=-1.0,
            p75=1.0,
            lower_bound=4.0,
            upper_bound=6.0,
            inside_rate=0.0,
            source_value=5.0,
        )
        self.assertAlmostEqual(audit.distance_component, ZERO_FLOOR_PENALTY)
        self.assertEqual(audit.loss_transform, "log_ratio_to_target_band_with_additive_spread_fallback")
        self.assertAlmostEqual(audit.metric_loss, ZERO_FLOOR_PENALTY + 0.25 * (2.0 / 6.0) + 0.50)

    def test_signed_additive_handles_zero_crossing_bands(self) -> None:
        audit = compute_metric_loss_audit(
            loss_family="signed_additive",
            seed_mean=-3.0,
            p25=-3.5,
            p75=-2.5,
            lower_bound=-1.0,
            upper_bound=1.0,
            inside_rate=0.25,
            source_value=0.0,
        )
        self.assertEqual(audit.loss_transform, "additive_distance")
        self.assertAlmostEqual(audit.additive_scale or 0.0, 1.0)
        self.assertAlmostEqual(audit.metric_loss, 2.0 + 0.25 * 1.0 + 0.50 * 0.75)

    def test_bounded_low_is_better_rewards_lower_in_band_jsd(self) -> None:
        low = compute_metric_loss(
            loss_family="bounded_low_is_better",
            seed_mean=0.03,
            p25=0.02,
            p75=0.04,
            lower_bound=0.0,
            upper_bound=0.12,
            inside_rate=1.0,
        )
        high = compute_metric_loss(
            loss_family="bounded_low_is_better",
            seed_mean=0.10,
            p25=0.09,
            p75=0.11,
            lower_bound=0.0,
            upper_bound=0.12,
            inside_rate=1.0,
        )
        self.assertLess(low, high)
        self.assertAlmostEqual(low, 0.25 * (0.03 / 0.12) + 0.25 * (0.02 / 0.12))

    def test_bounded_share_loss_is_stable_at_zero_inside_band_and_hundred_percent(self) -> None:
        zero = compute_metric_loss_audit(
            loss_family="bounded_share",
            seed_mean=0.0,
            p25=0.0,
            p75=0.0,
            lower_bound=0.0,
            upper_bound=1.0,
            inside_rate=1.0,
        )
        inside = compute_metric_loss_audit(
            loss_family="bounded_share",
            seed_mean=65.0,
            p25=65.0,
            p75=65.0,
            lower_bound=64.5,
            upper_bound=65.5,
            inside_rate=1.0,
        )
        outside = compute_metric_loss_audit(
            loss_family="bounded_share",
            seed_mean=63.0,
            p25=63.0,
            p75=63.0,
            lower_bound=64.5,
            upper_bound=65.5,
            inside_rate=0.0,
        )
        hundred = compute_metric_loss_audit(
            loss_family="bounded_share",
            seed_mean=100.0,
            p25=100.0,
            p75=100.0,
            lower_bound=99.0,
            upper_bound=100.0,
            inside_rate=1.0,
        )

        self.assertEqual(zero.loss_transform, "bounded_share_domain_normalized_distance")
        self.assertEqual(zero.loss_scale_basis, "bounded_share_domain_width")
        self.assertAlmostEqual(zero.loss_scale or 0.0, 100.0)
        self.assertAlmostEqual(zero.metric_loss, 0.0)
        self.assertAlmostEqual(inside.metric_loss, 0.0)
        self.assertAlmostEqual(outside.metric_loss, (1.5 / 100.0) + 0.50)
        self.assertAlmostEqual(hundred.metric_loss, 0.0)

    def test_status_rules_remain_band_and_inside_rate_based(self) -> None:
        status = classify_metric_status(
            seed_mean=300.0,
            lower_bound=90.0,
            upper_bound=100.0,
            inside_rate=1.0,
        )
        self.assertEqual(status, "fail")

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
