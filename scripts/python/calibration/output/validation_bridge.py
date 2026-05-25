"""Validation bridge for output ES-MDA calibration.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Sequence

import numpy as np

from scripts.python.calibration.output.esmda import DEFAULT_PARAMETER_SPECS, ParameterSpec, normalized_source_movement
from scripts.python.validation.model.runner import build_validation_summary
from scripts.python.validation.model.scoring import (
    compute_overall_composite_loss,
    compute_target_normalized_additive_metric_loss,
    resolve_loss_scale,
)
from scripts.python.validation.model.validation_profiles import (
    VALIDATION_PROFILE_2024,
    VALIDATION_PROFILE_REFERENCE_V0_2011,
    ValidationProfile,
)

VALIDATION_YEAR_2011 = 2011
VALIDATION_YEAR_2024 = 2024
V0_2011_ALLOWED_SOURCE_VERSIONS = {"v0", "v0o", "v0oo", "v0o1", "v0o2", "v0o3", "v0o6"}
FAMILY_AWARE_METRIC_LOSS_OBJECTIVE = "family_aware_metric_loss"
TARGET_NORMALIZED_ADDITIVE_OBJECTIVE = "target_normalized_additive"
DEFAULT_VALIDATION_OBJECTIVE = FAMILY_AWARE_METRIC_LOSS_OBJECTIVE
DEFAULT_VALIDATION_LOSS_ERROR_STD = 1.0
HPI_CONSTRAINED_METRIC_IDS = ("core_hpiStd", "core_hpiCyclePeriod", "core_hpiMean")
HPI_CONSTRAINED_RANK_EPSILON = 1.0e-12
ValidationObjective = Literal["family_aware_metric_loss", "target_normalized_additive"]


@dataclass(frozen=True)
class ValidationObservation:
    """One validation observation used by ES-MDA."""

    metric_id: str
    validation_objective: str
    assimilation_transform: str
    observed_value: float
    loss_scale: float
    loss_scale_basis: str
    normalized_observed_value: float
    normalized_error_std: float
    target_lower: float
    target_upper: float


@dataclass(frozen=True)
class MemberValidationResult:
    """Aggregated validation result for one ensemble member."""

    iteration: int
    member_id: int
    parameters: dict[str, float]
    summary: dict[str, object]
    observation_vector: tuple[float, ...]
    ranking_loss: float
    ranking_objective: str
    normalized_source_movement: float
    seed_results: tuple[dict[str, object], ...]


def resolve_calibration_validation_profile(*, version: str, validation_year: int) -> ValidationProfile:
    """Resolve the calibration validation profile and enforce v0-only 2011 mode."""

    if validation_year == VALIDATION_YEAR_2024:
        return VALIDATION_PROFILE_2024
    if validation_year == VALIDATION_YEAR_2011:
        normalized = version.strip().lower()
        if normalized not in V0_2011_ALLOWED_SOURCE_VERSIONS:
            raise ValueError(
                "2011 output calibration is restricted to v0-family versions "
                f"{sorted(V0_2011_ALLOWED_SOURCE_VERSIONS)} by default"
            )
        return VALIDATION_PROFILE_REFERENCE_V0_2011
    raise ValueError("validation_year must be 2011 or 2024")


def build_validation_observations(
    profile: ValidationProfile,
    *,
    validation_objective: ValidationObjective = DEFAULT_VALIDATION_OBJECTIVE,
    validation_loss_error_std: float = DEFAULT_VALIDATION_LOSS_ERROR_STD,
) -> tuple[ValidationObservation, ...]:
    """Build observations from the selected validation catalog and ES-MDA objective."""

    if validation_objective not in {FAMILY_AWARE_METRIC_LOSS_OBJECTIVE, TARGET_NORMALIZED_ADDITIVE_OBJECTIVE}:
        raise ValueError(f"Unsupported validation objective: {validation_objective}")
    if validation_loss_error_std <= 0.0:
        raise ValueError("validation_loss_error_std must be positive")

    observations: list[ValidationObservation] = []
    for metric in profile.target_catalog:
        if metric.requirement != "required":
            continue
        if metric.target_band is None:
            raise RuntimeError(f"Missing target band for required metric {metric.metric_id}")

        if validation_objective == FAMILY_AWARE_METRIC_LOSS_OBJECTIVE:
            observations.append(
                ValidationObservation(
                    metric_id=metric.metric_id,
                    validation_objective=validation_objective,
                    assimilation_transform="schema4_metric_loss",
                    observed_value=0.0,
                    loss_scale=1.0,
                    loss_scale_basis="not_applicable",
                    normalized_observed_value=0.0,
                    normalized_error_std=validation_loss_error_std,
                    target_lower=metric.target_band.lower,
                    target_upper=metric.target_band.upper,
                )
            )
            continue

        source_value = metric.source_metadata.normalized_source_value if metric.source_metadata else None
        observed_value = (
            float(source_value)
            if source_value is not None
            else (metric.target_band.lower + metric.target_band.upper) / 2.0
        )
        loss_scale, loss_scale_basis = resolve_loss_scale(
            source_value=source_value,
            lower_bound=metric.target_band.lower,
            upper_bound=metric.target_band.upper,
        )
        normalized_half_width = (metric.target_band.upper - metric.target_band.lower) / (2.0 * loss_scale)
        observations.append(
            ValidationObservation(
                metric_id=metric.metric_id,
                validation_objective=validation_objective,
                assimilation_transform="target_normalized_additive",
                observed_value=observed_value,
                loss_scale=loss_scale,
                loss_scale_basis=loss_scale_basis,
                normalized_observed_value=observed_value / loss_scale,
                normalized_error_std=max(normalized_half_width, 1.0e-3),
                target_lower=metric.target_band.lower,
                target_upper=metric.target_band.upper,
            )
        )

    if not observations:
        raise RuntimeError("No required validation observations found")
    return tuple(observations)


def observation_vector(observations: Sequence[ValidationObservation]) -> np.ndarray:
    """Return normalized observed values for ES-MDA."""

    return np.array([observation.normalized_observed_value for observation in observations], dtype=float)


def observation_error_covariance(observations: Sequence[ValidationObservation]) -> np.ndarray:
    """Return diagonal target-band-derived covariance for normalized observations."""

    variances = [observation.normalized_error_std**2 for observation in observations]
    return np.diag(np.array(variances, dtype=float))


def member_observation_vector(
    *,
    summary: Mapping[str, object],
    observations: Sequence[ValidationObservation],
) -> tuple[float, ...]:
    """Extract normalized seed-mean outputs from a validation summary."""

    metrics = summary.get("metrics")
    if not isinstance(metrics, Sequence):
        raise RuntimeError("Validation summary is missing metrics")
    metrics_by_id = {
        str(metric["metricId"]): metric
        for metric in metrics
        if isinstance(metric, Mapping) and "metricId" in metric
    }
    values: list[float] = []
    for observation in observations:
        metric = metrics_by_id.get(observation.metric_id)
        if metric is None:
            raise RuntimeError(f"Missing validation metric {observation.metric_id}")
        if observation.validation_objective == FAMILY_AWARE_METRIC_LOSS_OBJECTIVE:
            metric_loss = metric.get("metricLoss")
            if metric_loss is None:
                raise RuntimeError(f"Missing metricLoss for validation metric {observation.metric_id}")
            values.append(float(metric_loss))
        else:
            values.append(float(metric["seedMean"]) / observation.loss_scale)
    return tuple(values)


def target_normalized_additive_composite_loss(
    *,
    summary: Mapping[str, object],
    observations: Sequence[ValidationObservation],
) -> float:
    """Compute the old-compatible additive composite used by the ES-MDA compatibility objective."""

    metrics = summary.get("metrics")
    if not isinstance(metrics, Sequence):
        raise RuntimeError("Validation summary is missing metrics")
    metrics_by_id = {
        str(metric["metricId"]): metric
        for metric in metrics
        if isinstance(metric, Mapping) and "metricId" in metric
    }
    metric_losses: list[float] = []
    metric_weights: list[float] = []
    for observation in observations:
        metric = metrics_by_id.get(observation.metric_id)
        if metric is None:
            raise RuntimeError(f"Missing validation metric {observation.metric_id}")
        inside_rate = metric.get("insideRate")
        if inside_rate is None:
            raise RuntimeError(f"Missing insideRate for validation metric {observation.metric_id}")
        metric_losses.append(
            compute_target_normalized_additive_metric_loss(
                seed_mean=float(metric["seedMean"]),
                p25=float(metric["p25"]),
                p75=float(metric["p75"]),
                lower_bound=observation.target_lower,
                upper_bound=observation.target_upper,
                inside_rate=float(inside_rate),
                loss_scale=observation.loss_scale,
            )
        )
        metric_weights.append(float(metric.get("metricWeight") or 1.0))
    return compute_overall_composite_loss(metric_losses=metric_losses, metric_weights=metric_weights)


def ranking_loss_for_summary(
    *,
    summary: Mapping[str, object],
    observations: Sequence[ValidationObservation],
) -> tuple[float, str]:
    """Return the objective-specific scalar used to rank ES-MDA members."""

    objective = observations[0].validation_objective if observations else DEFAULT_VALIDATION_OBJECTIVE
    if objective == TARGET_NORMALIZED_ADDITIVE_OBJECTIVE:
        return (
            target_normalized_additive_composite_loss(summary=summary, observations=observations),
            TARGET_NORMALIZED_ADDITIVE_OBJECTIVE,
        )
    return float(summary["overallCompositeLoss"]), FAMILY_AWARE_METRIC_LOSS_OBJECTIVE


def build_member_validation_result(
    *,
    version: str,
    iteration: int,
    member_id: int,
    parameters: Mapping[str, float],
    seed_results: Sequence[dict[str, object]],
    seeds: Sequence[int],
    validation_profile: ValidationProfile,
    observations: Sequence[ValidationObservation],
    source_parameters: Mapping[str, float],
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
    validation_window_start: int | None = None,
    validation_window_end: int | None = None,
) -> MemberValidationResult:
    """Build a member-level validation summary without publishing tracked JSON."""

    summary = build_validation_summary(
        version=version,
        seed_results=seed_results,
        seeds=seeds,
        validation_profile=validation_profile,
        window_start=validation_window_start,
        window_end=validation_window_end,
    )
    vector = member_observation_vector(summary=summary, observations=observations)
    ranking_loss, ranking_objective = ranking_loss_for_summary(summary=summary, observations=observations)
    movement = normalized_source_movement(
        source_parameters=source_parameters,
        candidate_parameters=parameters,
        specs=specs,
    )
    return MemberValidationResult(
        iteration=iteration,
        member_id=member_id,
        parameters={str(key): float(value) for key, value in parameters.items()},
        summary=summary,
        observation_vector=vector,
        ranking_loss=ranking_loss,
        ranking_objective=ranking_objective,
        normalized_source_movement=movement,
        seed_results=tuple(seed_results),
    )


def group_seed_run_results_by_member(seed_run_results: Sequence[object]) -> dict[int, list[dict[str, object]]]:
    """Convert SeedRunResult objects into validation runner seed-result shape."""

    grouped: dict[int, list[dict[str, object]]] = {}
    for result in seed_run_results:
        member_id = int(getattr(result, "member_id"))
        grouped.setdefault(member_id, []).append(
            {
                "seed": int(getattr(result, "seed")),
                "outputDir": str(getattr(result, "output_dir")),
                "metrics": dict(getattr(result, "metrics")),
            }
        )

    return {
        member_id: sorted(seed_results, key=lambda item: int(item["seed"]))
        for member_id, seed_results in grouped.items()
    }


def required_metric_status_counts(summary: Mapping[str, object]) -> dict[str, int]:
    """Count required metric statuses from a validation summary."""

    counts = {"pass": 0, "warn": 0, "fail": 0, "unsupported": 0}
    metrics = summary.get("metrics")
    if not isinstance(metrics, Sequence):
        raise RuntimeError("Validation summary is missing metrics")
    for metric in metrics:
        if not isinstance(metric, Mapping):
            continue
        if metric.get("requirement") != "required":
            continue
        status = str(metric.get("status"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def summary_metrics_by_id(summary: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    """Return validation metrics keyed by metric id."""

    metrics = summary.get("metrics")
    if not isinstance(metrics, Sequence):
        raise RuntimeError("Validation summary is missing metrics")
    return {
        str(metric["metricId"]): metric
        for metric in metrics
        if isinstance(metric, Mapping) and "metricId" in metric
    }


def overall_composite_loss(member: MemberValidationResult) -> float:
    """Return the schema overall composite loss for constrained selection."""

    return float(member.summary["overallCompositeLoss"])


def total_loss_improvement(
    member: MemberValidationResult,
    *,
    baseline_member: MemberValidationResult,
) -> float:
    """Return positive loss improvement versus the source baseline."""

    return overall_composite_loss(baseline_member) - overall_composite_loss(member)


def hpi_metric_loss_deltas(
    member: MemberValidationResult,
    *,
    baseline_member: MemberValidationResult,
) -> dict[str, float]:
    """Return constrained HPI metric-loss deltas versus the source baseline."""

    candidate_metrics = summary_metrics_by_id(member.summary)
    baseline_metrics = summary_metrics_by_id(baseline_member.summary)
    deltas: dict[str, float] = {}
    for metric_id in HPI_CONSTRAINED_METRIC_IDS:
        candidate_metric = candidate_metrics.get(metric_id)
        baseline_metric = baseline_metrics.get(metric_id)
        if candidate_metric is None:
            raise RuntimeError(f"Missing validation metric {metric_id} for candidate member {member.member_id}")
        if baseline_metric is None:
            raise RuntimeError(f"Missing validation metric {metric_id} for baseline member {baseline_member.member_id}")
        candidate_loss = candidate_metric.get("metricLoss")
        baseline_loss = baseline_metric.get("metricLoss")
        if candidate_loss is None:
            raise RuntimeError(f"Missing metricLoss for validation metric {metric_id} on candidate member {member.member_id}")
        if baseline_loss is None:
            raise RuntimeError(f"Missing metricLoss for validation metric {metric_id} on baseline member {baseline_member.member_id}")
        deltas[metric_id] = float(candidate_loss) - float(baseline_loss)
    return deltas


def hpi_metric_loss_regressions(
    member: MemberValidationResult,
    *,
    baseline_member: MemberValidationResult,
) -> list[dict[str, float | str]]:
    """Return constrained HPI metric regressions beyond floating-point tolerance."""

    candidate_metrics = summary_metrics_by_id(member.summary)
    baseline_metrics = summary_metrics_by_id(baseline_member.summary)
    regressions: list[dict[str, float | str]] = []
    for metric_id, delta in hpi_metric_loss_deltas(member, baseline_member=baseline_member).items():
        if delta <= HPI_CONSTRAINED_RANK_EPSILON:
            continue
        regressions.append(
            {
                "metricId": metric_id,
                "baselineMetricLoss": float(baseline_metrics[metric_id]["metricLoss"]),
                "candidateMetricLoss": float(candidate_metrics[metric_id]["metricLoss"]),
                "delta": delta,
            }
        )
    return regressions


def constrained_member_is_eligible(
    member: MemberValidationResult,
    *,
    baseline_member: MemberValidationResult,
) -> bool:
    """Return whether a member improves total loss without HPI regression."""

    if total_loss_improvement(member, baseline_member=baseline_member) <= HPI_CONSTRAINED_RANK_EPSILON:
        return False
    return not hpi_metric_loss_regressions(member, baseline_member=baseline_member)


def constrained_member_rank_key(
    member: MemberValidationResult,
    *,
    baseline_member: MemberValidationResult,
) -> tuple[bool, float, float, float, float, int, int, float]:
    """Rank members by total-loss improvement and HPI non-regression first."""

    counts = required_metric_status_counts(member.summary)
    hpi_deltas = hpi_metric_loss_deltas(member, baseline_member=baseline_member)
    return (
        not (total_loss_improvement(member, baseline_member=baseline_member) > HPI_CONSTRAINED_RANK_EPSILON),
        max(0.0, hpi_deltas["core_hpiStd"]),
        max(0.0, hpi_deltas["core_hpiCyclePeriod"]),
        max(0.0, hpi_deltas["core_hpiMean"]),
        overall_composite_loss(member),
        int(counts.get("fail", 0)),
        int(counts.get("warn", 0)),
        member.normalized_source_movement,
    )


def member_rank_key(member: MemberValidationResult) -> tuple[float, int, int, float]:
    """Rank members by validation loss, status, and movement."""

    counts = required_metric_status_counts(member.summary)
    return (
        member.ranking_loss,
        int(counts.get("fail", 0)),
        int(counts.get("warn", 0)),
        member.normalized_source_movement,
    )


def summarize_validation_profile(profile: ValidationProfile) -> dict[str, object]:
    """Return metadata proving the selected year uses the intended WAS dataset."""

    return {
        "profileId": profile.profile_id,
        "validationTargetYear": profile.validation_target_year,
        "wasDataset": profile.was_dataset,
        "metricCount": len(profile.target_catalog),
        "requiredMetricCount": sum(1 for metric in profile.target_catalog if metric.requirement == "required"),
    }


__all__ = [
    "MemberValidationResult",
    "ValidationObservation",
    "DEFAULT_VALIDATION_LOSS_ERROR_STD",
    "DEFAULT_VALIDATION_OBJECTIVE",
    "FAMILY_AWARE_METRIC_LOSS_OBJECTIVE",
    "HPI_CONSTRAINED_METRIC_IDS",
    "HPI_CONSTRAINED_RANK_EPSILON",
    "TARGET_NORMALIZED_ADDITIVE_OBJECTIVE",
    "build_member_validation_result",
    "build_validation_observations",
    "constrained_member_is_eligible",
    "constrained_member_rank_key",
    "group_seed_run_results_by_member",
    "hpi_metric_loss_deltas",
    "hpi_metric_loss_regressions",
    "member_observation_vector",
    "member_rank_key",
    "observation_error_covariance",
    "observation_vector",
    "overall_composite_loss",
    "ranking_loss_for_summary",
    "required_metric_status_counts",
    "resolve_calibration_validation_profile",
    "summary_metrics_by_id",
    "summarize_validation_profile",
    "target_normalized_additive_composite_loss",
    "total_loss_improvement",
]
