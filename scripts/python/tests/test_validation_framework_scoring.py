"""Tests for the 2024 validation framework scoring rules.

@author: Max Stoddard
"""

from __future__ import annotations

import unittest

from scripts.python.validation.model.scoring import (
    classify_metric_status,
    compute_metric_loss,
    compute_overall_composite_loss,
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

    def test_metric_loss_uses_distance_iqr_and_inside_rate(self) -> None:
        loss = compute_metric_loss(
            seed_mean=110.0,
            p25=108.0,
            p75=112.0,
            lower_bound=95.0,
            upper_bound=105.0,
            inside_rate=0.25,
        )
        self.assertAlmostEqual(loss, 0.5 + 0.25 * 0.4 + 0.50 * 0.75)

    def test_overall_loss_weights_macro_and_household_families(self) -> None:
        loss = compute_overall_composite_loss(
            macro_credit_activity_loss=0.2,
            macro_prices_leverage_affordability_loss=0.4,
            household_distribution_realism_loss=0.6,
        )
        self.assertAlmostEqual(loss, 0.45)
