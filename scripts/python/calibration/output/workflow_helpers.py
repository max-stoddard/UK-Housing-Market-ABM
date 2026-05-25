"""Shared output-calibration workflow helpers.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Mapping, Sequence

from scripts.python.calibration.output.candidate_runs import parse_seed_list
from scripts.python.calibration.output.esmda import (
    DEFAULT_PARAMETER_SPECS,
    OUTPUT_ESMDA_PARAMETER_NAMES,
    ParameterSpec,
    snap_parameter_set,
)
from scripts.python.calibration.output.validation_bridge import (
    HPI_CONSTRAINED_METRIC_IDS,
    HPI_CONSTRAINED_RANK_EPSILON,
    MemberValidationResult,
    constrained_member_is_eligible,
    constrained_member_rank_key,
    hpi_metric_loss_deltas,
    hpi_metric_loss_regressions,
    member_rank_key,
    overall_composite_loss,
    required_metric_status_counts,
    total_loss_improvement,
)
from scripts.python.helpers.common.cli import format_float

DEFAULT_STRATEGIC_METRIC_DEGRADATION_TOLERANCE = 0.1
STRATEGIC_METRIC_IDS = (
    "core_advancesToBTL",
    "core_hpiMean",
    "core_hpiStd",
    "core_hpiCyclePeriod",
    "income_distribution_jsd",
    "housing_wealth_distribution_jsd",
    "financial_wealth_distribution_jsd",
)


def build_local_refinement_candidates(
    seed_parameter_sets: Sequence[Mapping[str, float]],
    *,
    radius: int,
    max_candidates: int,
) -> list[dict[str, float]]:
    """Build deduplicated snapped local candidates around good ES-MDA members."""

    if radius < 0:
        raise ValueError("radius must be non-negative")
    if max_candidates <= 0:
        raise ValueError("max_candidates must be positive")

    candidates: list[dict[str, float]] = []
    for raw_parameters in seed_parameter_sets:
        base = snap_parameter_set(raw_parameters, specs=DEFAULT_PARAMETER_SPECS)
        candidates.append(base)
        for spec in DEFAULT_PARAMETER_SPECS:
            step = _local_refinement_step(spec, base[spec.name])
            for offset in range(-radius, radius + 1):
                if offset == 0:
                    continue
                neighbour = dict(base)
                neighbour[spec.name] = spec.snap_value(base[spec.name] + offset * step)
                candidates.append(snap_parameter_set(neighbour, specs=DEFAULT_PARAMETER_SPECS))

    return _dedupe_parameter_sets(candidates)[:max_candidates]


def select_local_refinement_seed_members(
    member_results: Sequence[MemberValidationResult],
    *,
    baseline_member: MemberValidationResult,
    top_n: int,
) -> list[MemberValidationResult]:
    """Select only HPI-constrained eligible ES-MDA members for local refinement."""

    if top_n <= 0:
        raise ValueError("top_n must be positive")
    eligible_members = [
        member
        for member in member_results
        if constrained_member_is_eligible(member, baseline_member=baseline_member)
    ]
    return sorted(
        eligible_members,
        key=lambda member: constrained_member_rank_key(member, baseline_member=baseline_member),
    )[:top_n]


def _local_refinement_step(spec: object, value: float) -> float:
    snap = getattr(spec, "final_snap", None)
    if snap is not None:
        return float(snap)
    sigfigs = getattr(spec, "final_sigfigs", None)
    if sigfigs is not None:
        magnitude = max(abs(float(value)), getattr(spec, "lower", 0.0), 1.0e-12)
        return 10.0 ** (math.floor(math.log10(magnitude)) - int(sigfigs) + 1)
    return (float(getattr(spec, "prior_upper")) - float(getattr(spec, "prior_lower"))) / 20.0


def _dedupe_parameter_sets(parameter_sets: Sequence[Mapping[str, float]]) -> list[dict[str, float]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[dict[str, float]] = []
    for parameters in parameter_sets:
        snapped = snap_parameter_set(parameters, specs=DEFAULT_PARAMETER_SPECS)
        key = tuple(format_float(float(snapped[spec.name]), decimals=12) for spec in DEFAULT_PARAMETER_SPECS)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(snapped)
    return deduped


def write_parameter_sets_csv(path: Path, parameter_sets: Sequence[Mapping[str, float]]) -> None:
    rows = []
    for index, parameters in enumerate(parameter_sets):
        row: dict[str, object] = {"memberId": index}
        row.update({key: float(parameters[key]) for key in OUTPUT_ESMDA_PARAMETER_NAMES})
        rows.append(row)
    write_csv(path, rows)


def write_member_results_csv(path: Path, member_results: Sequence[MemberValidationResult]) -> None:
    rows = []
    for member in member_results:
        counts = required_metric_status_counts(member.summary)
        row: dict[str, object] = {
            "iteration": member.iteration,
            "memberId": member.member_id,
            "overallCompositeLoss": float(member.summary["overallCompositeLoss"]),
            "rankingLoss": member.ranking_loss,
            "rankingObjective": member.ranking_objective,
            "passCount": counts.get("pass", 0),
            "warnCount": counts.get("warn", 0),
            "failCount": counts.get("fail", 0),
            "normalizedSourceMovement": member.normalized_source_movement,
        }
        row.update({key: member.parameters[key] for key in OUTPUT_ESMDA_PARAMETER_NAMES})
        rows.append(row)
    write_csv(path, rows)


def write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def find_baseline_member(member_results: Sequence[MemberValidationResult]) -> MemberValidationResult | None:
    for member in member_results:
        if member.iteration == 0 and member.member_id == 0:
            return member
    return None


def build_model_quality_warnings(
    *,
    selected_member: MemberValidationResult,
    baseline_member: MemberValidationResult | None,
) -> list[str]:
    warnings: list[str] = []
    if baseline_member is None:
        return warnings

    selected_loss = selected_member.ranking_loss
    baseline_loss = baseline_member.ranking_loss
    if selected_loss >= baseline_loss:
        return warnings

    selected_metrics = metrics_by_id(selected_member.summary)
    baseline_metrics = metrics_by_id(baseline_member.summary)
    degraded = []
    for metric_id in STRATEGIC_METRIC_IDS:
        selected_metric = selected_metrics.get(metric_id)
        baseline_metric = baseline_metrics.get(metric_id)
        if selected_metric is None or baseline_metric is None:
            continue
        selected_metric_loss = selected_metric.get("metricLoss")
        baseline_metric_loss = baseline_metric.get("metricLoss")
        if selected_metric_loss is None or baseline_metric_loss is None:
            continue
        if float(selected_metric_loss) > float(baseline_metric_loss) + DEFAULT_STRATEGIC_METRIC_DEGRADATION_TOLERANCE:
            degraded.append(metric_id)
    if degraded:
        warnings.append(
            "Composite validation loss improved, but strategic metrics degraded materially: "
            + ", ".join(degraded)
        )
    return warnings


def select_guardrailed_member(
    *,
    candidates: Sequence[MemberValidationResult],
    baseline_member: MemberValidationResult,
) -> dict[str, object]:
    """Select the best snapped candidate that improves loss without HPI regression."""

    if not candidates:
        raise ValueError("At least one candidate is required")
    decisions = [
        _candidate_guardrail_decision(candidate=candidate, baseline_member=baseline_member)
        for candidate in candidates
    ]
    decisions_by_member = {int(decision["memberId"]): decision for decision in decisions}
    accepted_candidates = [
        candidate
        for candidate in candidates
        if bool(decisions_by_member[candidate.member_id]["accepted"])
    ]
    lowest_loss_candidate = min(candidates, key=overall_composite_loss)
    if accepted_candidates:
        promoted = min(
            accepted_candidates,
            key=lambda member: constrained_member_rank_key(member, baseline_member=baseline_member),
        )
        return {
            "accepted": True,
            "promotedMember": promoted,
            "lowestLossMember": lowest_loss_candidate,
            "decisions": decisions,
            "promotedDecision": decisions_by_member[promoted.member_id],
            "lowestLossDecision": decisions_by_member[lowest_loss_candidate.member_id],
            "lowestLossRejected": lowest_loss_candidate.member_id != promoted.member_id,
        }

    return {
        "accepted": False,
        "promotedMember": lowest_loss_candidate,
        "lowestLossMember": lowest_loss_candidate,
        "decisions": decisions,
        "promotedDecision": decisions_by_member[lowest_loss_candidate.member_id],
        "lowestLossDecision": decisions_by_member[lowest_loss_candidate.member_id],
        "lowestLossRejected": True,
    }


def _candidate_guardrail_decision(
    *,
    candidate: MemberValidationResult,
    baseline_member: MemberValidationResult,
) -> dict[str, object]:
    baseline_counts = required_metric_status_counts(baseline_member.summary)
    candidate_counts = required_metric_status_counts(candidate.summary)
    loss_improvement = total_loss_improvement(candidate, baseline_member=baseline_member)
    fail_count_increase = int(candidate_counts.get("fail", 0)) - int(baseline_counts.get("fail", 0))
    hpi_deltas = hpi_metric_loss_deltas(candidate, baseline_member=baseline_member)
    hpi_regressions = hpi_metric_loss_regressions(candidate, baseline_member=baseline_member)
    rejection_reasons: list[str] = []

    if not (loss_improvement > HPI_CONSTRAINED_RANK_EPSILON):
        rejection_reasons.append(
            f"overallCompositeLoss improvement {loss_improvement:.12f} is not positive"
        )
    if hpi_regressions:
        rejection_reasons.append(
            "HPI metric loss regressed versus baseline: "
            + ", ".join(f"{item['metricId']} ({item['delta']:+.12f})" for item in hpi_regressions)
        )

    return {
        "iteration": candidate.iteration,
        "memberId": candidate.member_id,
        "accepted": not rejection_reasons,
        "rejectionReasons": rejection_reasons,
        "lossImprovementVersusBaseline": loss_improvement,
        "baselineRankingLoss": baseline_member.ranking_loss,
        "candidateRankingLoss": candidate.ranking_loss,
        "baselineOverallCompositeLoss": overall_composite_loss(baseline_member),
        "candidateOverallCompositeLoss": overall_composite_loss(candidate),
        "rankingObjective": candidate.ranking_objective,
        "improvesTotalLoss": loss_improvement > HPI_CONSTRAINED_RANK_EPSILON,
        "hpiConstrainedEligible": not rejection_reasons,
        "hpiMetricLossDeltas": hpi_deltas,
        "hpiMetricLossRegressions": hpi_regressions,
        "failCountIncrease": fail_count_increase,
        "baselineStatusCounts": baseline_counts,
        "candidateStatusCounts": candidate_counts,
        "normalizedSourceMovement": candidate.normalized_source_movement,
        "rankKey": list(constrained_member_rank_key(candidate, baseline_member=baseline_member)),
    }


def guardrail_thresholds_payload() -> dict[str, object]:
    return {
        "requiredTotalLossImprovement": "overallCompositeLoss must improve versus iteration 0 member 0",
        "hpiRegressionTolerance": HPI_CONSTRAINED_RANK_EPSILON,
        "hpiConstrainedMetricIds": list(HPI_CONSTRAINED_METRIC_IDS),
        "rankKey": [
            "not improves_total_loss",
            "max(0, core_hpiStd_delta)",
            "max(0, core_hpiCyclePeriod_delta)",
            "max(0, core_hpiMean_delta)",
            "overallCompositeLoss",
            "fail_count",
            "warn_count",
            "normalized_source_movement",
        ],
        "rankingPrimaryObjective": (
            "lowest overallCompositeLoss among candidates that improve total loss and do not regress constrained "
            "HPI metric losses versus iteration 0 member 0"
        ),
        "nonHpiSignals": "fail count, warn count, and normalized source movement are rank tie-breakers, not hard gates",
    }


def metrics_by_id(summary: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    metrics = summary.get("metrics")
    if not isinstance(metrics, Sequence):
        return {}
    return {
        str(metric["metricId"]): metric
        for metric in metrics
        if isinstance(metric, Mapping) and "metricId" in metric
    }


def member_summary_payload(
    member: MemberValidationResult,
    selected_parameters: Mapping[str, float],
    *,
    baseline_member: MemberValidationResult | None = None,
) -> dict[str, object]:
    counts = required_metric_status_counts(member.summary)
    payload: dict[str, object] = {
        "iteration": member.iteration,
        "memberId": member.member_id,
        "parameters": {key: format_float(float(value), decimals=12) for key, value in selected_parameters.items()},
        "overallCompositeLoss": float(member.summary["overallCompositeLoss"]),
        "rankingLoss": member.ranking_loss,
        "rankingObjective": member.ranking_objective,
        "statusCounts": counts,
        "normalizedSourceMovement": member.normalized_source_movement,
        "rankKey": list(member_rank_key(member)),
    }
    if baseline_member is not None:
        payload.update(
            {
                "lossImprovementVersusBaseline": total_loss_improvement(member, baseline_member=baseline_member),
                "improvesTotalLoss": total_loss_improvement(member, baseline_member=baseline_member)
                > HPI_CONSTRAINED_RANK_EPSILON,
                "hpiConstrainedEligible": constrained_member_is_eligible(member, baseline_member=baseline_member),
                "hpiMetricLossDeltas": hpi_metric_loss_deltas(member, baseline_member=baseline_member),
                "hpiMetricLossRegressions": hpi_metric_loss_regressions(
                    member,
                    baseline_member=baseline_member,
                ),
                "rankKey": list(constrained_member_rank_key(member, baseline_member=baseline_member)),
            }
        )
    return payload


def local_refinement_summary_payload(
    *,
    args: argparse.Namespace,
    baseline_member: MemberValidationResult,
    local_seed_members: Sequence[MemberValidationResult],
    local_candidates: Sequence[Mapping[str, float]],
    local_member_results: Sequence[MemberValidationResult],
    promotion: Mapping[str, object],
) -> dict[str, object]:
    promoted_member = promotion["promotedMember"]
    lowest_loss_member = promotion["lowestLossMember"]
    assert isinstance(promoted_member, MemberValidationResult)
    assert isinstance(lowest_loss_member, MemberValidationResult)
    return {
        "enabled": not args.no_local_refinement,
        "seedTopN": args.local_refinement_top_n,
        "eligibleSeedMemberCount": len(local_seed_members),
        "seedMembers": [
            member_summary_payload(member, member.parameters, baseline_member=baseline_member)
            for member in local_seed_members
        ],
        "oneParameterNeighbourRadius": 0 if args.no_local_refinement else args.local_refinement_radius,
        "maxCandidates": args.local_refinement_max_candidates,
        "deduplicatedSnappedCandidateCount": len(local_candidates),
        "evaluatedCandidateCount": len(local_member_results),
        "seedRuns": len(local_candidates) * len(parse_seed_list(args.seeds)),
        "guardrailThresholds": guardrail_thresholds_payload(),
        "promotionAccepted": bool(promotion["accepted"]),
        "lowestLossRejected": bool(promotion["lowestLossRejected"]),
        "promoted": member_summary_payload(
            promoted_member,
            promoted_member.parameters,
            baseline_member=baseline_member,
        ),
        "lowestLoss": member_summary_payload(
            lowest_loss_member,
            lowest_loss_member.parameters,
            baseline_member=baseline_member,
        ),
        "promotedDecision": promotion["promotedDecision"],
        "lowestLossDecision": promotion["lowestLossDecision"],
        "candidateDecisions": promotion["decisions"],
    }


def local_refinement_skipped_summary_payload(
    *,
    args: argparse.Namespace,
    all_member_results: Sequence[MemberValidationResult],
    baseline_member: MemberValidationResult,
    skipped_reason: str,
) -> dict[str, object]:
    ranked_preview = sorted(
        all_member_results,
        key=lambda member: constrained_member_rank_key(member, baseline_member=baseline_member),
    )[: args.local_refinement_top_n]
    return {
        "enabled": not args.no_local_refinement,
        "seedTopN": args.local_refinement_top_n,
        "eligibleSeedMemberCount": 0,
        "seedMembers": [],
        "rankedPreview": [
            member_summary_payload(member, member.parameters, baseline_member=baseline_member)
            for member in ranked_preview
        ],
        "oneParameterNeighbourRadius": 0 if args.no_local_refinement else args.local_refinement_radius,
        "maxCandidates": args.local_refinement_max_candidates,
        "deduplicatedSnappedCandidateCount": 0,
        "evaluatedCandidateCount": 0,
        "seedRuns": 0,
        "guardrailThresholds": guardrail_thresholds_payload(),
        "promotionAccepted": False,
        "lowestLossRejected": False,
        "skippedReason": skipped_reason,
    }


def format_duration(seconds: float) -> str:
    rounded = max(0, int(round(seconds)))
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


__all__ = [
    "build_local_refinement_candidates",
    "build_model_quality_warnings",
    "find_baseline_member",
    "format_duration",
    "guardrail_thresholds_payload",
    "local_refinement_skipped_summary_payload",
    "local_refinement_summary_payload",
    "member_summary_payload",
    "select_guardrailed_member",
    "select_local_refinement_seed_members",
    "write_member_results_csv",
    "write_parameter_sets_csv",
]
