"""Deterministic scoring formulas for the 2024 validation framework.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from scripts.python.validation.model.schema import LossFamily, LossScaleBasis

ZERO_FLOOR_PENALTY = math.log(100.0)
METRIC_FLOOR = 1.0e-9
BOUNDED_SHARE_DOMAIN_WIDTH = 100.0


@dataclass(frozen=True)
class MetricLossAudit:
    """Scored validation loss plus the audit fields published with each metric."""

    metric_loss: float
    loss_family: LossFamily
    loss_transform: str
    loss_scale: float | None
    loss_scale_basis: LossScaleBasis
    additive_scale: float | None
    additive_scale_basis: LossScaleBasis
    normalized_distance: float
    normalized_iqr: float
    distance_component: float
    spread_component: float
    level_component: float
    inside_rate_component: float


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


def resolve_additive_scale(
    *,
    source_value: float | None,
    lower_bound: float,
    upper_bound: float,
    metric_floor: float = METRIC_FLOOR,
) -> tuple[float, LossScaleBasis]:
    """Choose the robust additive denominator for signed or fallback loss terms."""

    if metric_floor <= 0.0:
        raise ValueError("metric_floor must be positive")

    candidates: list[tuple[float, LossScaleBasis]] = []
    if source_value is not None:
        candidates.append((abs(source_value), "source_value"))
    candidates.extend(
        [
            (abs(lower_bound), "target_band_lower_abs"),
            (abs(upper_bound), "target_band_upper_abs"),
            ((upper_bound - lower_bound) / 2.0, "target_band_half_width"),
            (metric_floor, "metric_floor"),
        ]
    )
    scale, basis = max(candidates, key=lambda item: item[0])
    if scale <= 0.0:
        return metric_floor, "metric_floor"
    return scale, basis


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


def positive_level_distance(
    *,
    value: float,
    lower_bound: float,
    upper_bound: float,
    zero_floor_penalty: float = ZERO_FLOOR_PENALTY,
) -> float:
    """Compute symmetric multiplicative distance to a strictly positive target band."""

    if lower_bound <= 0.0 or upper_bound <= 0.0:
        raise ValueError("Positive-level loss requires a strictly positive target band")
    if lower_bound <= value <= upper_bound:
        return 0.0
    if value > upper_bound:
        return math.log(value / upper_bound)
    if value > 0.0:
        return math.log(lower_bound / value)
    return zero_floor_penalty


def compute_target_normalized_additive_metric_loss(
    *,
    seed_mean: float,
    p25: float,
    p75: float,
    lower_bound: float,
    upper_bound: float,
    inside_rate: float,
    loss_scale: float,
) -> float:
    """Compute the schema-3 additive metric loss retained for ES-MDA compatibility."""

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


def compute_metric_loss_audit(
    *,
    loss_family: LossFamily,
    seed_mean: float,
    p25: float,
    p75: float,
    lower_bound: float,
    upper_bound: float,
    inside_rate: float,
    source_value: float | None = None,
    zero_floor_penalty: float = ZERO_FLOOR_PENALTY,
    metric_floor: float = METRIC_FLOOR,
) -> MetricLossAudit:
    """Compute the schema-4 family-aware metric loss and audit fields."""

    inside_rate_component = 0.50 * (1.0 - inside_rate)

    if loss_family == "positive_level":
        distance_component = positive_level_distance(
            value=seed_mean,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            zero_floor_penalty=zero_floor_penalty,
        )
        if p25 > 0.0 and p75 > 0.0:
            normalized_iqr = max(0.0, math.log(p75 / p25))
            additive_scale = None
            additive_scale_basis: LossScaleBasis = "not_applicable"
            loss_transform = "log_ratio_to_target_band"
        else:
            additive_scale, additive_scale_basis = resolve_additive_scale(
                source_value=source_value,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
                metric_floor=metric_floor,
            )
            normalized_iqr = normalize_by_loss_scale(
                raw_value=max(0.0, p75 - p25),
                loss_scale=additive_scale,
            )
            loss_transform = "log_ratio_to_target_band_with_additive_spread_fallback"
        spread_component = 0.25 * normalized_iqr
        metric_loss = distance_component + spread_component + inside_rate_component
        return MetricLossAudit(
            metric_loss=metric_loss,
            loss_family=loss_family,
            loss_transform=loss_transform,
            loss_scale=None,
            loss_scale_basis="not_applicable",
            additive_scale=additive_scale,
            additive_scale_basis=additive_scale_basis,
            normalized_distance=distance_component,
            normalized_iqr=normalized_iqr,
            distance_component=distance_component,
            spread_component=spread_component,
            level_component=0.0,
            inside_rate_component=inside_rate_component,
        )

    if loss_family == "signed_additive":
        additive_scale, additive_scale_basis = resolve_additive_scale(
            source_value=source_value,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            metric_floor=metric_floor,
        )
        normalized_distance = normalize_by_loss_scale(
            raw_value=compute_outside_distance(
                seed_mean=seed_mean,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            ),
            loss_scale=additive_scale,
        )
        normalized_iqr = normalize_by_loss_scale(raw_value=max(0.0, p75 - p25), loss_scale=additive_scale)
        spread_component = 0.25 * normalized_iqr
        metric_loss = normalized_distance + spread_component + inside_rate_component
        return MetricLossAudit(
            metric_loss=metric_loss,
            loss_family=loss_family,
            loss_transform="additive_distance",
            loss_scale=additive_scale,
            loss_scale_basis=additive_scale_basis,
            additive_scale=additive_scale,
            additive_scale_basis=additive_scale_basis,
            normalized_distance=normalized_distance,
            normalized_iqr=normalized_iqr,
            distance_component=normalized_distance,
            spread_component=spread_component,
            level_component=0.0,
            inside_rate_component=inside_rate_component,
        )

    if loss_family == "bounded_low_is_better":
        if upper_bound <= 0.0:
            raise ValueError("Bounded low-is-better loss requires a positive upper bound")
        normalized_distance = max(seed_mean - upper_bound, 0.0) / upper_bound
        level_component = 0.25 * max(seed_mean, 0.0) / upper_bound
        normalized_iqr = max(0.0, p75 - p25) / upper_bound
        spread_component = 0.25 * normalized_iqr
        metric_loss = normalized_distance + level_component + spread_component + inside_rate_component
        return MetricLossAudit(
            metric_loss=metric_loss,
            loss_family=loss_family,
            loss_transform="bounded_low_is_better",
            loss_scale=upper_bound,
            loss_scale_basis="target_band_upper",
            additive_scale=None,
            additive_scale_basis="not_applicable",
            normalized_distance=normalized_distance,
            normalized_iqr=normalized_iqr,
            distance_component=normalized_distance,
            spread_component=spread_component,
            level_component=level_component,
            inside_rate_component=inside_rate_component,
        )

    if loss_family == "bounded_share":
        if lower_bound < 0.0 or upper_bound > 100.0:
            raise ValueError("Bounded-share loss requires percentage target bands within 0..100")
        if upper_bound <= lower_bound:
            raise ValueError("Bounded-share loss requires a positive target-band width")
        normalized_distance = compute_outside_distance(
            seed_mean=seed_mean,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
        ) / BOUNDED_SHARE_DOMAIN_WIDTH
        normalized_iqr = max(0.0, p75 - p25) / BOUNDED_SHARE_DOMAIN_WIDTH
        spread_component = 0.25 * normalized_iqr
        metric_loss = normalized_distance + spread_component + inside_rate_component
        return MetricLossAudit(
            metric_loss=metric_loss,
            loss_family=loss_family,
            loss_transform="bounded_share_domain_normalized_distance",
            loss_scale=BOUNDED_SHARE_DOMAIN_WIDTH,
            loss_scale_basis="bounded_share_domain_width",
            additive_scale=None,
            additive_scale_basis="not_applicable",
            normalized_distance=normalized_distance,
            normalized_iqr=normalized_iqr,
            distance_component=normalized_distance,
            spread_component=spread_component,
            level_component=0.0,
            inside_rate_component=inside_rate_component,
        )

    if loss_family == "diagnostic":
        raise ValueError("Diagnostic metrics are not scored")

    raise ValueError(f"Unsupported loss family: {loss_family}")


def compute_metric_loss(
    *,
    loss_family: LossFamily,
    seed_mean: float,
    p25: float,
    p75: float,
    lower_bound: float,
    upper_bound: float,
    inside_rate: float,
    source_value: float | None = None,
) -> float:
    """Compute the schema-4 family-aware metric loss."""

    return compute_metric_loss_audit(
        loss_family=loss_family,
        seed_mean=seed_mean,
        p25=p25,
        p75=p75,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        inside_rate=inside_rate,
        source_value=source_value,
    ).metric_loss


def compute_overall_composite_loss(
    *,
    metric_losses: Sequence[float],
    metric_weights: Sequence[float] | None = None,
) -> float:
    """Aggregate scored metrics into the overall composite loss."""

    if not metric_losses:
        raise ValueError("At least one scored metric loss is required")

    if metric_weights is None:
        metric_weights = [1.0] * len(metric_losses)
    if len(metric_losses) != len(metric_weights):
        raise ValueError("Metric losses and weights must have the same length")

    total_weight = float(sum(metric_weights))
    if total_weight <= 0.0:
        raise ValueError("Total metric weight must be positive")

    weighted_loss = sum(metric_loss * metric_weight for metric_loss, metric_weight in zip(metric_losses, metric_weights))
    return weighted_loss / total_weight
