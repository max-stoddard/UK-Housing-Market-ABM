"""Validation bridge for four-parameter output ES-MDA calibration.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from scripts.python.calibration.output.esmda import DEFAULT_PARAMETER_SPECS, ParameterSpec, normalized_source_movement
from scripts.python.validation.model.runner import build_validation_summary
from scripts.python.validation.model.scoring import resolve_loss_scale
from scripts.python.validation.model.validation_profiles import (
    VALIDATION_PROFILE_2024,
    VALIDATION_PROFILE_REFERENCE_V0_2011,
    ValidationProfile,
)

VALIDATION_YEAR_2011 = 2011
VALIDATION_YEAR_2024 = 2024
V0_2011_ALLOWED_SOURCE_VERSIONS = {"v0", "v0o", "v0oo"}


@dataclass(frozen=True)
class ValidationObservation:
    """One target-normalized validation observation used by ES-MDA."""

    metric_id: str
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


def build_validation_observations(profile: ValidationProfile) -> tuple[ValidationObservation, ...]:
    """Build target-normalized observations from the selected validation catalog."""

    observations: list[ValidationObservation] = []
    for metric in profile.target_catalog:
        if metric.requirement != "required":
            continue
        if metric.target_band is None:
            raise RuntimeError(f"Missing target band for required metric {metric.metric_id}")

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
        values.append(float(metric["seedMean"]) / observation.loss_scale)
    return tuple(values)


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
) -> MemberValidationResult:
    """Build a member-level validation summary without publishing tracked JSON."""

    summary = build_validation_summary(
        version=version,
        seed_results=seed_results,
        seeds=seeds,
        validation_profile=validation_profile,
    )
    vector = member_observation_vector(summary=summary, observations=observations)
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


def member_rank_key(member: MemberValidationResult) -> tuple[float, int, int, float]:
    """Rank final evaluated members by validation loss, status, and movement."""

    counts = required_metric_status_counts(member.summary)
    return (
        float(member.summary["overallCompositeLoss"]),
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
    "build_member_validation_result",
    "build_validation_observations",
    "group_seed_run_results_by_member",
    "member_observation_vector",
    "member_rank_key",
    "observation_error_covariance",
    "observation_vector",
    "required_metric_status_counts",
    "resolve_calibration_validation_profile",
    "summarize_validation_profile",
]
