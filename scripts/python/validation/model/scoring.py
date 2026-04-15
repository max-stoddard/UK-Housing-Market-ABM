"""Deterministic scoring formulas for the 2024 validation framework.

@author: Max Stoddard
"""

from __future__ import annotations

from scripts.python.validation.model.validation_catalog_2024 import FAMILY_WEIGHTS


def compute_normalized_distance(*, seed_mean: float, lower_bound: float, upper_bound: float) -> float:
    """Compute distance to the nearest band edge, normalized by band width."""

    band_width = upper_bound - lower_bound
    if band_width <= 0.0:
        raise ValueError("Target band width must be positive")
    if lower_bound <= seed_mean <= upper_bound:
        return 0.0
    distance_to_band = min(abs(seed_mean - lower_bound), abs(seed_mean - upper_bound))
    return distance_to_band / band_width


def classify_metric_status(*, seed_mean: float, lower_bound: float, upper_bound: float, inside_rate: float) -> str:
    """Classify one metric according to the approved pass/warn/fail rules."""

    normalized_distance = compute_normalized_distance(
        seed_mean=seed_mean,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )
    if normalized_distance == 0.0 and inside_rate >= 0.75:
        return "pass"
    if normalized_distance <= 0.50 and inside_rate >= 0.50:
        return "warn"
    return "fail"


def compute_metric_loss(
    *,
    seed_mean: float,
    p25: float,
    p75: float,
    lower_bound: float,
    upper_bound: float,
    inside_rate: float,
) -> float:
    """Compute the approved metric loss from distance, spread, and inside-rate."""

    band_width = upper_bound - lower_bound
    if band_width <= 0.0:
        raise ValueError("Target band width must be positive")
    normalized_distance = compute_normalized_distance(
        seed_mean=seed_mean,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    )
    normalized_iqr = (p75 - p25) / band_width
    return normalized_distance + 0.25 * normalized_iqr + 0.50 * (1.0 - inside_rate)


def compute_overall_composite_loss(
    *,
    macro_credit_activity_loss: float,
    macro_prices_leverage_affordability_loss: float,
    household_distribution_realism_loss: float,
) -> float:
    """Aggregate the three scored families into the overall composite loss."""

    return (
        FAMILY_WEIGHTS["macro_credit_activity"] * macro_credit_activity_loss
        + FAMILY_WEIGHTS["macro_prices_leverage_affordability"] * macro_prices_leverage_affordability_loss
        + FAMILY_WEIGHTS["household_distribution_realism"] * household_distribution_realism_loss
    )
