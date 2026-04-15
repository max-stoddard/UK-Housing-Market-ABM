"""Deterministic scoring formulas for the 2024 validation framework.

@author: Max Stoddard
"""

from __future__ import annotations

from scripts.python.validation.model.schema import LossScaleBasis
from scripts.python.validation.model.validation_catalog_2024 import FAMILY_WEIGHTS


def compute_outside_distance(*, seed_mean: float, lower_bound: float, upper_bound: float) -> float:
    """Compute the distance from the mean to the nearest band edge."""

    band_width = upper_bound - lower_bound
    if band_width <= 0.0:
        raise ValueError("Target band width must be positive")
    if lower_bound <= seed_mean <= upper_bound:
        return 0.0
    return min(abs(seed_mean - lower_bound), abs(seed_mean - upper_bound))


def compute_normalized_distance(*, seed_mean: float, lower_bound: float, upper_bound: float) -> float:
    """Compute distance to the nearest band edge, normalized by band width."""

    band_width = upper_bound - lower_bound
    if band_width <= 0.0:
        raise ValueError("Target band width must be positive")
    return compute_outside_distance(
        seed_mean=seed_mean,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
    ) / band_width


def resolve_loss_scale(
    *,
    source_value: float | None,
    lower_bound: float,
    upper_bound: float,
) -> tuple[float, LossScaleBasis]:
    """Choose the auditably published denominator for loss normalization."""

    if source_value is not None and source_value > 0.0:
        return abs(source_value), "source_value"

    if lower_bound <= 0.0 < upper_bound:
        return upper_bound, "target_band_upper"

    midpoint = (lower_bound + upper_bound) / 2.0
    if midpoint > 0.0:
        return midpoint, "target_band_midpoint"

    if upper_bound > 0.0:
        return upper_bound, "target_band_upper"

    raise ValueError("Loss scale must be positive")


def normalize_by_loss_scale(*, raw_value: float, loss_scale: float) -> float:
    """Normalize a loss component by the selected cross-metric loss scale."""

    if loss_scale <= 0.0:
        raise ValueError("Loss scale must be positive")
    return raw_value / loss_scale


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
    loss_scale: float,
) -> float:
    """Compute the approved metric loss from distance, spread, and inside-rate."""

    normalized_distance = normalize_by_loss_scale(
        raw_value=compute_outside_distance(
            seed_mean=seed_mean,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        ),
        loss_scale=loss_scale,
    )
    normalized_iqr = normalize_by_loss_scale(
        raw_value=p75 - p25,
        loss_scale=loss_scale,
    )
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
