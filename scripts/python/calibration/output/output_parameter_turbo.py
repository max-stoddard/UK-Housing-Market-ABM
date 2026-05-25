#!/usr/bin/env python3
"""Run TuRBO-1 calibration for jointly output-calibrated parameters.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import time
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from scripts.python.calibration.output.candidate_runs import (
    DEFAULT_OUTPUT_ROOT,
    create_output_version,
    execute_seed_requests_for_members,
    parse_config_parameters,
    parse_seed_list,
    resolve_repo_path,
    validate_version_name,
    write_json,
)
from scripts.python.calibration.output.esmda import DEFAULT_PARAMETER_SPECS, OUTPUT_ESMDA_PARAMETER_NAMES
from scripts.python.calibration.output.turbo_core import (
    DEFAULT_HPI_PENALTY_WEIGHT,
    DEFAULT_INITIAL_POINTS,
    DEFAULT_MAX_EVALUATIONS,
    DEFAULT_NOISE_VARIANCE_FLOOR,
    DEFAULT_RNG_SEED,
    DEFAULT_SUCCESS_TOLERANCE,
    DEFAULT_TRUST_REGION_LENGTH,
    DEFAULT_TRUST_REGION_LENGTH_MAX,
    DEFAULT_TRUST_REGION_LENGTH_MIN,
    TurboState,
    default_failure_tolerance,
    estimate_objective_noise_variance,
    generate_initial_normalized_design,
    load_turbo_dependencies,
    normalized_points_to_parameter_dicts,
    optimizer_score,
    parameter_dicts_to_normalized_points,
    propose_turbo_candidates,
    resolve_candidate_batch_size,
    select_torch_device,
    update_turbo_state,
)
from scripts.python.calibration.output.validation_bridge import (
    DEFAULT_VALIDATION_LOSS_ERROR_STD,
    FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
    TARGET_NORMALIZED_ADDITIVE_OBJECTIVE,
    MemberValidationResult,
    build_member_validation_result,
    build_validation_observations,
    group_seed_run_results_by_member,
    overall_composite_loss,
    resolve_calibration_validation_profile,
    summarize_validation_profile,
)
from scripts.python.calibration.output.workflow_helpers import (
    build_local_refinement_candidates,
    build_model_quality_warnings,
    find_baseline_member,
    format_duration,
    guardrail_thresholds_payload,
    local_refinement_skipped_summary_payload,
    local_refinement_summary_payload,
    member_summary_payload,
    select_guardrailed_member,
    select_local_refinement_seed_members,
    write_member_results_csv,
    write_parameter_sets_csv,
)
from scripts.python.helpers.common.abm_policy_sweep import ensure_project_compiled, resolve_maven_bin
from scripts.python.helpers.common.paths import repo_root as default_repo_root
from scripts.python.validation.model.runner import resolve_was_data_root
from scripts.python.validation.model.schema import VALIDATION_WINDOW_END, VALIDATION_WINDOW_START

DEFAULT_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
DEFAULT_WORKERS = 20
DEFAULT_LOCAL_REFINEMENT_TOP_N = 12
DEFAULT_LOCAL_REFINEMENT_RADIUS = 1
DEFAULT_LOCAL_REFINEMENT_MAX_CANDIDATES = 120
WORKFLOW_SLUG = "five-parameter-turbo"
WORKFLOW_NAME = "five-parameter-turbo"
EVIDENCE_DIR_TEMPLATE = "input-data-versions/calibration-evidence/output-five-parameter-turbo-{output_version}"
METADATA_FILENAME = "OutputParameterTurboMetadata.json"
SUMMARY_FILENAME = "OutputParameterTurboCalibrationSummary.json"
LOSS_HANDLING_NOTE = (
    "TuRBO optimizes an HPI-penalized score while retaining raw family-aware validation loss. "
    "Promotion still uses the unchanged guardrail contract: overallCompositeLoss must improve versus "
    "iteration 0 member 0 and constrained HPI metric losses must not regress."
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        description="TuRBO-1 calibration for jointly output-calibrated housing-model parameters.",
    )
    parser.add_argument("--version", required=True, help="Source input-data version, for example v0")
    parser.add_argument("--output-version", required=True, help="Output version to create, for example v0o7")
    parser.add_argument(
        "--validation-year",
        type=int,
        choices=(2011, 2024),
        default=2011,
        help="Validation target year/profile to use (default: 2011).",
    )
    parser.add_argument(
        "--validation-objective",
        choices=(FAMILY_AWARE_METRIC_LOSS_OBJECTIVE, TARGET_NORMALIZED_ADDITIVE_OBJECTIVE),
        default=FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
        help="Validation objective used for TuRBO scoring and ranking.",
    )
    parser.add_argument(
        "--validation-loss-error-std",
        type=float,
        default=DEFAULT_VALIDATION_LOSS_ERROR_STD,
        help="Diagonal observation standard deviation used for family-aware validation loss.",
    )
    parser.add_argument(
        "--seeds",
        default=",".join(str(seed) for seed in DEFAULT_SEEDS),
        help="Comma-separated common-random-number seed block (default: 1..10).",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Maximum parallel seed workers.")
    parser.add_argument("--candidate-batch-size", type=int, default=None)
    parser.add_argument("--initial-points", type=int, default=DEFAULT_INITIAL_POINTS)
    parser.add_argument("--max-evaluations", type=int, default=DEFAULT_MAX_EVALUATIONS)
    parser.add_argument("--rng-seed", type=int, default=DEFAULT_RNG_SEED)
    parser.add_argument("--hpi-penalty-weight", type=float, default=DEFAULT_HPI_PENALTY_WEIGHT)
    parser.add_argument("--noise-variance-floor", type=float, default=DEFAULT_NOISE_VARIANCE_FLOOR)
    parser.add_argument("--turbo-length", type=float, default=DEFAULT_TRUST_REGION_LENGTH)
    parser.add_argument("--turbo-length-min", type=float, default=DEFAULT_TRUST_REGION_LENGTH_MIN)
    parser.add_argument("--turbo-length-max", type=float, default=DEFAULT_TRUST_REGION_LENGTH_MAX)
    parser.add_argument("--success-tolerance", type=int, default=DEFAULT_SUCCESS_TOLERANCE)
    parser.add_argument("--failure-tolerance", type=int, default=None)
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument(
        "--n-steps",
        type=int,
        default=None,
        help="Optional N_STEPS override for candidate model runs; omitted keeps the snapshot config value.",
    )
    parser.add_argument(
        "--validation-window-start",
        type=int,
        default=VALIDATION_WINDOW_START,
        help=f"Metric extraction window start index (default: {VALIDATION_WINDOW_START}).",
    )
    parser.add_argument(
        "--validation-window-end",
        type=int,
        default=VALIDATION_WINDOW_END,
        help=f"Metric extraction window end index, exclusive for time series (default: {VALIDATION_WINDOW_END}).",
    )
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Transient output root (default: {DEFAULT_OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="Retained evidence directory. Defaults to input-data-versions/calibration-evidence/...<output-version>.",
    )
    parser.add_argument("--maven-bin", default=None, help="Maven executable override (default: repo-local ./mvnw).")
    parser.add_argument("--force-rerun", action="store_true", help="Ignore cached per-seed metric JSON.")
    parser.add_argument(
        "--delete-csv-after-metrics",
        action="store_true",
        help="After each seed's metrics are safely cached, delete generated run CSV outputs from that seed directory.",
    )
    parser.add_argument("--overwrite-version", action="store_true", help="Replace an existing output version folder.")
    parser.add_argument("--no-local-refinement", action="store_true", help="Promote only from snapped global members.")
    parser.add_argument(
        "--local-refinement-top-n",
        type=int,
        default=DEFAULT_LOCAL_REFINEMENT_TOP_N,
        help=f"Number of best TuRBO members to seed local snapped refinement (default: {DEFAULT_LOCAL_REFINEMENT_TOP_N}).",
    )
    parser.add_argument(
        "--local-refinement-radius",
        type=int,
        default=DEFAULT_LOCAL_REFINEMENT_RADIUS,
        help=f"One-parameter snapped neighbour radius for local refinement (default: {DEFAULT_LOCAL_REFINEMENT_RADIUS}).",
    )
    parser.add_argument(
        "--local-refinement-max-candidates",
        type=int,
        default=DEFAULT_LOCAL_REFINEMENT_MAX_CANDIDATES,
        help=f"Maximum deduplicated snapped local candidates to evaluate (default: {DEFAULT_LOCAL_REFINEMENT_MAX_CANDIDATES}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write metadata and deterministic initial design without running Maven or creating a version.",
    )
    return parser


def run_calibration(args: argparse.Namespace, *, repo_root: Path | None = None) -> dict[str, object]:
    """Run or dry-run the output-parameter TuRBO workflow."""

    resolved_repo_root = repo_root or default_repo_root()
    maven_bin = resolve_maven_bin(resolved_repo_root, args.maven_bin)
    version = validate_version_name(args.version)
    output_version = validate_version_name(args.output_version)
    seeds = parse_seed_list(args.seeds)
    candidate_batch_size = resolve_candidate_batch_size(
        requested=args.candidate_batch_size,
        workers=args.workers,
        seed_count=len(seeds),
    )
    _validate_execution_args(args=args, seeds=seeds, candidate_batch_size=candidate_batch_size)

    validation_profile = resolve_calibration_validation_profile(
        version=version,
        validation_year=args.validation_year,
    )
    observations = build_validation_observations(
        validation_profile,
        validation_objective=args.validation_objective,
        validation_loss_error_std=args.validation_loss_error_std,
    )
    source_config_path = resolved_repo_root / "input-data-versions" / version / "config.properties"
    if not source_config_path.exists():
        raise RuntimeError(f"Missing source version config: {source_config_path}")
    source_parameters = parse_config_parameters(source_config_path.read_text(encoding="utf-8"))

    output_root = resolve_repo_path(resolved_repo_root, args.output_root) / output_version / WORKFLOW_SLUG
    evidence_dir = (
        resolve_repo_path(resolved_repo_root, args.evidence_dir)
        if args.evidence_dir
        else resolved_repo_root / EVIDENCE_DIR_TEMPLATE.format(output_version=output_version)
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "reproduce-command.sh").write_text(build_reproduce_command(args), encoding="utf-8")

    dependencies = load_turbo_dependencies()
    device = select_torch_device(dependencies.torch)
    initial_normalized = generate_initial_normalized_design(
        initial_points=args.initial_points,
        dimensions=len(DEFAULT_PARAMETER_SPECS),
        rng_seed=args.rng_seed,
    )
    source_normalized = parameter_dicts_to_normalized_points([source_parameters])
    initial_normalized = _replace_source_equivalent_points(
        initial_normalized,
        source_normalized=source_normalized[0],
        rng_seed=args.rng_seed + 1,
    )
    initial_parameters = normalized_points_to_parameter_dicts(initial_normalized)

    metadata = _build_base_metadata(
        args=args,
        version=version,
        output_version=output_version,
        seeds=seeds,
        candidate_batch_size=candidate_batch_size,
        validation_profile=validation_profile,
        observations=observations,
        source_parameters=source_parameters,
        output_root=output_root,
        evidence_dir=evidence_dir,
        device=device,
        dependency_versions=dependencies.versions,
    )
    _write_summary_artifacts(output_root, metadata, is_metadata=True)
    write_parameter_sets_csv(output_root / "InitialDesign.csv", initial_parameters)

    if args.dry_run:
        summary = {
            **metadata,
            "dryRun": True,
            "createdOutputVersion": False,
            "initialDesignCsv": str(output_root / "InitialDesign.csv"),
        }
        _write_summary_artifacts(output_root, summary)
        return summary

    requested_output_dir = resolved_repo_root / "input-data-versions" / output_version
    if requested_output_dir.exists() and not (args.overwrite_version or args.evidence_only):
        raise RuntimeError(f"Output version already exists: {requested_output_dir}")

    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "reproduce-command.sh").write_text(build_reproduce_command(args), encoding="utf-8")
    write_parameter_sets_csv(evidence_dir / "InitialDesign.csv", initial_parameters)
    _write_summary_artifacts(evidence_dir, metadata, is_metadata=True)

    ensure_project_compiled(resolved_repo_root, maven_bin=maven_bin)
    was_data_root = resolve_was_data_root(repo_root=resolved_repo_root, explicit_root=None)

    started_at = time.monotonic()
    baseline_seed_run_results = execute_seed_requests_for_members(
        repo_root=resolved_repo_root,
        version=version,
        iteration=0,
        member_parameters=[source_parameters],
        seeds=seeds,
        output_root=output_root,
        maven_bin=maven_bin,
        force_rerun=args.force_rerun,
        validation_profile=validation_profile,
        was_data_root=was_data_root,
        workers=args.workers,
        delete_csv_after_metrics=args.delete_csv_after_metrics,
        n_steps=args.n_steps,
        validation_window_start=args.validation_window_start,
        validation_window_end=args.validation_window_end,
    )
    baseline_grouped = group_seed_run_results_by_member(baseline_seed_run_results)
    baseline_member = build_member_validation_result(
        version=version,
        iteration=0,
        member_id=0,
        parameters=source_parameters,
        seed_results=baseline_grouped[0],
        seeds=seeds,
        validation_profile=validation_profile,
        observations=observations,
        source_parameters=source_parameters,
        validation_window_start=args.validation_window_start,
        validation_window_end=args.validation_window_end,
    )
    baseline_member = find_baseline_member([baseline_member]) or baseline_member
    baseline_score, baseline_raw_loss, baseline_penalty = optimizer_score(
        baseline_member,
        baseline_member=baseline_member,
        penalty_weight=args.hpi_penalty_weight,
    )

    all_global_members: list[MemberValidationResult] = [baseline_member]
    train_x_rows: list[np.ndarray] = [source_normalized[0]]
    train_y_rows: list[list[float]] = [[baseline_score]]
    train_yvar_rows: list[list[float]] = [[args.noise_variance_floor]]
    score_rows: list[dict[str, object]] = [
        _score_row(
            member=baseline_member,
            optimizer_score_value=baseline_score,
            raw_validation_loss=baseline_raw_loss,
            hpi_penalty=baseline_penalty,
            observation_noise_variance=args.noise_variance_floor,
        )
    ]
    state_history: list[dict[str, object]] = []

    initial_members, evaluated_initial, initial_score_rows, initial_yvar = _evaluate_candidates(
        repo_root=resolved_repo_root,
        version=version,
        iteration=1,
        normalized_points=initial_normalized,
        seeds=seeds,
        output_root=output_root,
        maven_bin=maven_bin,
        force_rerun=args.force_rerun,
        validation_profile=validation_profile,
        was_data_root=was_data_root,
        workers=args.workers,
        delete_csv_after_metrics=args.delete_csv_after_metrics,
        n_steps=args.n_steps,
        validation_window_start=args.validation_window_start,
        validation_window_end=args.validation_window_end,
        observations=observations,
        source_parameters=source_parameters,
        baseline_member=baseline_member,
        hpi_penalty_weight=args.hpi_penalty_weight,
        noise_variance_floor=args.noise_variance_floor,
    )
    all_global_members.extend(initial_members)
    train_x_rows.extend(evaluated_initial)
    train_y_rows.extend([[float(row["optimizerScore"])] for row in initial_score_rows])
    train_yvar_rows.extend(initial_yvar)
    score_rows.extend(initial_score_rows)

    best_score = max(float(row[0]) for row in train_y_rows)
    state = TurboState(
        length=args.turbo_length,
        best_score=best_score,
        evaluated_candidate_count=len(initial_members),
    )
    state_history.append(_state_payload(state, iteration=1))
    _write_progress_artifacts(
        output_root=output_root,
        evidence_dir=evidence_dir,
        metadata=metadata,
        summary={
            **metadata,
            "dryRun": False,
            "createdOutputVersion": False,
            "evidenceOnly": args.evidence_only,
            "turboStateHistory": state_history,
            "scoreRows": score_rows,
            "elapsed": format_duration(time.monotonic() - started_at),
        },
        global_members=all_global_members,
    )

    failure_tolerance = (
        args.failure_tolerance
        if args.failure_tolerance is not None
        else default_failure_tolerance(dimensions=len(DEFAULT_PARAMETER_SPECS), batch_size=candidate_batch_size)
    )
    iteration = 2
    while state.evaluated_candidate_count < args.max_evaluations and not state.restart_triggered:
        remaining = args.max_evaluations - state.evaluated_candidate_count
        batch_size = min(candidate_batch_size, remaining)
        proposed = propose_turbo_candidates(
            train_x=np.asarray(train_x_rows, dtype=float),
            train_y=np.asarray(train_y_rows, dtype=float),
            train_yvar=np.asarray(train_yvar_rows, dtype=float),
            state=state,
            batch_size=batch_size,
            rng_seed=args.rng_seed + iteration,
            dependencies=dependencies,
            device=device,
        )
        batch_members, evaluated_points, batch_score_rows, batch_yvar = _evaluate_candidates(
            repo_root=resolved_repo_root,
            version=version,
            iteration=iteration,
            normalized_points=proposed,
            seeds=seeds,
            output_root=output_root,
            maven_bin=maven_bin,
            force_rerun=args.force_rerun,
            validation_profile=validation_profile,
            was_data_root=was_data_root,
            workers=args.workers,
            delete_csv_after_metrics=args.delete_csv_after_metrics,
            n_steps=args.n_steps,
            validation_window_start=args.validation_window_start,
            validation_window_end=args.validation_window_end,
            observations=observations,
            source_parameters=source_parameters,
            baseline_member=baseline_member,
            hpi_penalty_weight=args.hpi_penalty_weight,
            noise_variance_floor=args.noise_variance_floor,
        )
        all_global_members.extend(batch_members)
        train_x_rows.extend(evaluated_points)
        train_y_rows.extend([[float(row["optimizerScore"])] for row in batch_score_rows])
        train_yvar_rows.extend(batch_yvar)
        score_rows.extend(batch_score_rows)
        state = update_turbo_state(
            state,
            batch_best_score=max(float(row["optimizerScore"]) for row in batch_score_rows),
            batch_evaluation_count=len(batch_members),
            success_tolerance=args.success_tolerance,
            failure_tolerance=failure_tolerance,
            length_min=args.turbo_length_min,
            length_max=args.turbo_length_max,
        )
        state_history.append(_state_payload(state, iteration=iteration))
        _write_progress_artifacts(
            output_root=output_root,
            evidence_dir=evidence_dir,
            metadata=metadata,
            summary={
                **metadata,
                "dryRun": False,
                "createdOutputVersion": False,
                "evidenceOnly": args.evidence_only,
                "turboStateHistory": state_history,
                "scoreRows": score_rows,
                "elapsed": format_duration(time.monotonic() - started_at),
            },
            global_members=all_global_members,
        )
        iteration += 1

    global_best_member = min(
        all_global_members,
        key=lambda member: member_summary_payload(
            member,
            member.parameters,
            baseline_member=baseline_member,
        )["rankKey"],
    )
    unconstrained_lowest_loss_member = min(all_global_members, key=overall_composite_loss)
    local_seed_members = select_local_refinement_seed_members(
        all_global_members,
        baseline_member=baseline_member,
        top_n=args.local_refinement_top_n,
    )
    if not local_seed_members:
        warning = (
            "No TuRBO member improved overallCompositeLoss without regressing core_hpiStd, "
            "core_hpiCyclePeriod, or core_hpiMean; local refinement was not run."
        )
        summary = {
            **metadata,
            "dryRun": False,
            "createdOutputVersion": False,
            "evidenceOnly": args.evidence_only,
            "globalBest": member_summary_payload(global_best_member, global_best_member.parameters, baseline_member=baseline_member),
            "unconstrainedLowestLoss": member_summary_payload(
                unconstrained_lowest_loss_member,
                unconstrained_lowest_loss_member.parameters,
                baseline_member=baseline_member,
            ),
            "baseline": member_summary_payload(baseline_member, baseline_member.parameters, baseline_member=baseline_member),
            "localRefinement": local_refinement_skipped_summary_payload(
                args=args,
                all_member_results=all_global_members,
                baseline_member=baseline_member,
                skipped_reason=warning,
            ),
            "turboStateHistory": state_history,
            "scoreRows": score_rows,
            "warnings": [warning],
            "finalValidationNote": "No output version was promoted because no TuRBO member satisfied HPI constraints.",
            "deleteCsvAfterMetrics": args.delete_csv_after_metrics,
        }
        _write_progress_artifacts(
            output_root=output_root,
            evidence_dir=evidence_dir,
            metadata=metadata,
            summary=summary,
            global_members=all_global_members,
        )
        raise RuntimeError(f"No TuRBO member satisfied HPI-constrained ranking; see {SUMMARY_FILENAME}")

    local_candidates = build_local_refinement_candidates(
        [member.parameters for member in local_seed_members],
        radius=0 if args.no_local_refinement else args.local_refinement_radius,
        max_candidates=args.local_refinement_max_candidates,
    )
    local_iteration = iteration
    local_normalized = parameter_dicts_to_normalized_points(local_candidates)
    local_member_results, _, local_score_rows, _ = _evaluate_candidates(
        repo_root=resolved_repo_root,
        version=version,
        iteration=local_iteration,
        normalized_points=local_normalized,
        seeds=seeds,
        output_root=output_root,
        maven_bin=maven_bin,
        force_rerun=args.force_rerun,
        validation_profile=validation_profile,
        was_data_root=was_data_root,
        workers=args.workers,
        delete_csv_after_metrics=args.delete_csv_after_metrics,
        n_steps=args.n_steps,
        validation_window_start=args.validation_window_start,
        validation_window_end=args.validation_window_end,
        observations=observations,
        source_parameters=source_parameters,
        baseline_member=baseline_member,
        hpi_penalty_weight=args.hpi_penalty_weight,
        noise_variance_floor=args.noise_variance_floor,
    )
    score_rows.extend(local_score_rows)
    promotion = select_guardrailed_member(
        candidates=local_member_results,
        baseline_member=baseline_member,
    )
    selected_member = promotion["promotedMember"]
    assert isinstance(selected_member, MemberValidationResult)
    selected_parameters = selected_member.parameters
    warnings = build_model_quality_warnings(
        selected_member=selected_member,
        baseline_member=baseline_member,
    )
    all_evaluated_members = [*all_global_members, *local_member_results]

    if not promotion["accepted"]:
        warnings.append("No snapped local-refinement candidate improved total loss without HPI regression; output version was not created.")
        summary = _final_summary(
            metadata=metadata,
            args=args,
            created_output_version=False,
            output_version_dir=None,
            baseline_member=baseline_member,
            global_best_member=global_best_member,
            unconstrained_lowest_loss_member=unconstrained_lowest_loss_member,
            selected_member=selected_member,
            local_seed_members=local_seed_members,
            local_candidates=local_candidates,
            local_member_results=local_member_results,
            promotion=promotion,
            warnings=warnings,
            state_history=state_history,
            score_rows=score_rows,
            final_note="No output version was promoted because every snapped candidate failed total-loss or HPI constraints.",
        )
        _write_final_artifacts(output_root, evidence_dir, metadata, summary, all_global_members, local_member_results, all_evaluated_members)
        raise RuntimeError(f"No snapped local-refinement candidate satisfied HPI-constrained ranking; see {SUMMARY_FILENAME}")

    output_version_dir: Path | None = None
    created_output_version = False
    if not args.evidence_only:
        output_version_dir = create_output_version(
            repo_root=resolved_repo_root,
            source_version=version,
            output_version=output_version,
            selected_parameters=selected_parameters,
            overwrite=args.overwrite_version,
        )
        created_output_version = True

    summary = _final_summary(
        metadata=metadata,
        args=args,
        created_output_version=created_output_version,
        output_version_dir=output_version_dir,
        baseline_member=baseline_member,
        global_best_member=global_best_member,
        unconstrained_lowest_loss_member=unconstrained_lowest_loss_member,
        selected_member=selected_member,
        local_seed_members=local_seed_members,
        local_candidates=local_candidates,
        local_member_results=local_member_results,
        promotion=promotion,
        warnings=warnings,
        state_history=state_history,
        score_rows=score_rows,
        final_note=(
            "Selected HPI-constrained snapped parameters were accepted. "
            "Evidence-only mode skipped output-version creation."
            if args.evidence_only
            else "Selected HPI-constrained snapped parameters were written to the output version."
        ),
    )
    _write_final_artifacts(output_root, evidence_dir, metadata, summary, all_global_members, local_member_results, all_evaluated_members)
    return summary


def _evaluate_candidates(
    *,
    repo_root: Path,
    version: str,
    iteration: int,
    normalized_points: np.ndarray,
    seeds: Sequence[int],
    output_root: Path,
    maven_bin: str,
    force_rerun: bool,
    validation_profile: object,
    was_data_root: Path,
    workers: int,
    delete_csv_after_metrics: bool,
    n_steps: int | None,
    validation_window_start: int,
    validation_window_end: int,
    observations: Sequence[object],
    source_parameters: Mapping[str, float],
    baseline_member: MemberValidationResult,
    hpi_penalty_weight: float,
    noise_variance_floor: float,
) -> tuple[list[MemberValidationResult], list[np.ndarray], list[dict[str, object]], list[list[float]]]:
    parameter_sets = normalized_points_to_parameter_dicts(normalized_points)
    seed_run_results = execute_seed_requests_for_members(
        repo_root=repo_root,
        version=version,
        iteration=iteration,
        member_parameters=parameter_sets,
        seeds=seeds,
        output_root=output_root,
        maven_bin=maven_bin,
        force_rerun=force_rerun,
        validation_profile=validation_profile,
        was_data_root=was_data_root,
        workers=workers,
        delete_csv_after_metrics=delete_csv_after_metrics,
        n_steps=n_steps,
        validation_window_start=validation_window_start,
        validation_window_end=validation_window_end,
    )
    grouped_seed_results = group_seed_run_results_by_member(seed_run_results)
    member_results: list[MemberValidationResult] = []
    score_rows: list[dict[str, object]] = []
    train_yvar_rows: list[list[float]] = []
    for member_id, parameters in enumerate(parameter_sets):
        member = build_member_validation_result(
            version=version,
            iteration=iteration,
            member_id=member_id,
            parameters=parameters,
            seed_results=grouped_seed_results[member_id],
            seeds=seeds,
            validation_profile=validation_profile,
            observations=observations,
            source_parameters=source_parameters,
            validation_window_start=validation_window_start,
            validation_window_end=validation_window_end,
        )
        single_seed_members = [
            build_member_validation_result(
                version=version,
                iteration=iteration,
                member_id=member_id,
                parameters=parameters,
                seed_results=[seed_result],
                seeds=[int(seed_result["seed"])],
                validation_profile=validation_profile,
                observations=observations,
                source_parameters=source_parameters,
                validation_window_start=validation_window_start,
                validation_window_end=validation_window_end,
            )
            for seed_result in grouped_seed_results[member_id]
        ]
        per_seed_losses = [overall_composite_loss(single_seed_member) for single_seed_member in single_seed_members]
        score, raw_loss, penalty = optimizer_score(
            member,
            baseline_member=baseline_member,
            penalty_weight=hpi_penalty_weight,
        )
        noise_variance = estimate_objective_noise_variance(
            per_seed_losses,
            seed_count=len(seeds),
            floor=noise_variance_floor,
        )
        member_results.append(member)
        score_rows.append(
            _score_row(
                member=member,
                optimizer_score_value=score,
                raw_validation_loss=raw_loss,
                hpi_penalty=penalty,
                observation_noise_variance=noise_variance,
            )
        )
        train_yvar_rows.append([noise_variance])
    return member_results, [np.asarray(row, dtype=float) for row in normalized_points], score_rows, train_yvar_rows


def build_reproduce_command(args: argparse.Namespace) -> str:
    """Build a shell command that reproduces the requested workflow."""

    command = [
        "python3 -m scripts.python.calibration.output.output_parameter_turbo",
        f"--version {args.version}",
        f"--output-version {args.output_version}",
        f"--validation-year {args.validation_year}",
        f"--validation-objective {args.validation_objective}",
        f"--validation-loss-error-std {args.validation_loss_error_std}",
        f"--seeds {args.seeds}",
        f"--workers {args.workers}",
        f"--candidate-batch-size {args.candidate_batch_size}" if args.candidate_batch_size is not None else None,
        f"--initial-points {args.initial_points}",
        f"--max-evaluations {args.max_evaluations}",
        f"--rng-seed {args.rng_seed}",
        f"--hpi-penalty-weight {args.hpi_penalty_weight}",
        f"--noise-variance-floor {args.noise_variance_floor}",
        f"--turbo-length {args.turbo_length}",
        f"--turbo-length-min {args.turbo_length_min}",
        f"--turbo-length-max {args.turbo_length_max}",
        f"--success-tolerance {args.success_tolerance}",
        f"--failure-tolerance {args.failure_tolerance}" if args.failure_tolerance is not None else None,
        f"--validation-window-start {args.validation_window_start}",
        f"--validation-window-end {args.validation_window_end}",
        f"--output-root {args.output_root}",
    ]
    if args.n_steps is not None:
        command.append(f"--n-steps {args.n_steps}")
    if args.evidence_dir:
        command.append(f"--evidence-dir {args.evidence_dir}")
    if args.maven_bin:
        command.append(f"--maven-bin {args.maven_bin}")
    if args.force_rerun:
        command.append("--force-rerun")
    if args.delete_csv_after_metrics:
        command.append("--delete-csv-after-metrics")
    if args.overwrite_version:
        command.append("--overwrite-version")
    if args.no_local_refinement:
        command.append("--no-local-refinement")
    command.extend(
        [
            f"--local-refinement-top-n {args.local_refinement_top_n}",
            f"--local-refinement-radius {args.local_refinement_radius}",
            f"--local-refinement-max-candidates {args.local_refinement_max_candidates}",
        ]
    )
    if args.evidence_only:
        command.append("--evidence-only")
    if args.dry_run:
        command.append("--dry-run")
    return (" " + "\\" + "\n  ").join(item for item in command if item is not None) + "\n"


def _validate_execution_args(*, args: argparse.Namespace, seeds: Sequence[int], candidate_batch_size: int) -> None:
    if args.workers <= 0:
        raise ValueError("workers must be positive")
    if args.initial_points <= 0:
        raise ValueError("initial-points must be positive")
    if args.max_evaluations < args.initial_points:
        raise ValueError("max-evaluations must be greater than or equal to initial-points")
    if args.validation_loss_error_std <= 0.0:
        raise ValueError("validation-loss-error-std must be positive")
    if args.hpi_penalty_weight < 0.0:
        raise ValueError("hpi-penalty-weight must be non-negative")
    if args.noise_variance_floor <= 0.0:
        raise ValueError("noise-variance-floor must be positive")
    if args.turbo_length <= 0.0:
        raise ValueError("turbo-length must be positive")
    if args.turbo_length_min <= 0.0:
        raise ValueError("turbo-length-min must be positive")
    if args.turbo_length_max < args.turbo_length:
        raise ValueError("turbo-length-max must be greater than or equal to turbo-length")
    if args.success_tolerance <= 0:
        raise ValueError("success-tolerance must be positive")
    if args.failure_tolerance is not None and args.failure_tolerance <= 0:
        raise ValueError("failure-tolerance must be positive")
    if args.workers < len(seeds):
        raise ValueError("workers must be at least the number of seeds")
    if candidate_batch_size > args.workers // len(seeds):
        raise ValueError("candidate-batch-size exceeds available worker capacity")
    if args.local_refinement_top_n <= 0:
        raise ValueError("local-refinement-top-n must be positive")
    if args.local_refinement_radius < 0:
        raise ValueError("local-refinement-radius must be non-negative")
    if args.local_refinement_max_candidates <= 0:
        raise ValueError("local-refinement-max-candidates must be positive")
    if args.validation_window_start < 0:
        raise ValueError("validation-window-start must be non-negative")
    if args.validation_window_end <= args.validation_window_start:
        raise ValueError("validation-window-end must be greater than validation-window-start")
    if args.n_steps is not None:
        if args.n_steps <= 0:
            raise ValueError("n-steps must be positive")
        if args.validation_window_end > args.n_steps:
            raise ValueError("validation-window-end must be less than or equal to n-steps")


def _build_base_metadata(
    *,
    args: argparse.Namespace,
    version: str,
    output_version: str,
    seeds: Sequence[int],
    candidate_batch_size: int,
    validation_profile: object,
    observations: Sequence[object],
    source_parameters: Mapping[str, float],
    output_root: Path,
    evidence_dir: Path,
    device: str,
    dependency_versions: Mapping[str, str],
) -> dict[str, object]:
    return {
        "workflow": WORKFLOW_NAME,
        "sourceVersion": version,
        "outputVersion": output_version,
        "parameters": list(OUTPUT_ESMDA_PARAMETER_NAMES),
        "sourceParameters": dict(source_parameters),
        "validationProfile": summarize_validation_profile(validation_profile),
        "validationLossHandling": LOSS_HANDLING_NOTE,
        "validationObjective": args.validation_objective,
        "rankingObjective": "hpi_penalized_family_aware_metric_loss",
        "validationLossErrorStd": args.validation_loss_error_std,
        "guardrailThresholds": guardrail_thresholds_payload(),
        "seeds": list(seeds),
        "workers": args.workers,
        "candidateBatchSize": candidate_batch_size,
        "initialPoints": args.initial_points,
        "maxEvaluations": args.max_evaluations,
        "rngSeed": args.rng_seed,
        "nSteps": args.n_steps,
        "validationWindow": {
            "startIndex": args.validation_window_start,
            "endIndex": args.validation_window_end,
        },
        "deleteCsvAfterMetrics": args.delete_csv_after_metrics,
        "evidenceOnly": args.evidence_only,
        "hpiPenaltyWeight": args.hpi_penalty_weight,
        "noiseVarianceFloor": args.noise_variance_floor,
        "turboSettings": {
            "length": args.turbo_length,
            "lengthMin": args.turbo_length_min,
            "lengthMax": args.turbo_length_max,
            "successTolerance": args.success_tolerance,
            "failureTolerance": args.failure_tolerance,
        },
        "device": device,
        "dependencyVersions": dict(dependency_versions),
        "parameterSpecs": [asdict(spec) for spec in DEFAULT_PARAMETER_SPECS],
        "observations": [asdict(observation) for observation in observations],
        "outputRoot": str(output_root),
        "evidenceDir": str(evidence_dir),
    }


def _replace_source_equivalent_points(normalized_points: np.ndarray, *, source_normalized: np.ndarray, rng_seed: int) -> np.ndarray:
    points = np.asarray(normalized_points, dtype=float).copy()
    rng = np.random.default_rng(rng_seed)
    source_key = tuple(round(float(value), 12) for value in source_normalized)
    for row_index, row in enumerate(points):
        if tuple(round(float(value), 12) for value in row) == source_key:
            points[row_index] = rng.random(points.shape[1])
    return points


def _score_row(
    *,
    member: MemberValidationResult,
    optimizer_score_value: float,
    raw_validation_loss: float,
    hpi_penalty: float,
    observation_noise_variance: float,
) -> dict[str, object]:
    return {
        "iteration": member.iteration,
        "memberId": member.member_id,
        "optimizerScore": optimizer_score_value,
        "rawValidationLoss": raw_validation_loss,
        "hpiPenalty": hpi_penalty,
        "observationNoiseVariance": observation_noise_variance,
        "overallCompositeLoss": overall_composite_loss(member),
    }


def _state_payload(state: TurboState, *, iteration: int) -> dict[str, object]:
    return {
        "iteration": iteration,
        "length": state.length,
        "successCounter": state.success_counter,
        "failureCounter": state.failure_counter,
        "restartTriggered": state.restart_triggered,
        "bestScore": state.best_score,
        "evaluatedCandidateCount": state.evaluated_candidate_count,
    }


def _write_summary_artifacts(path: Path, payload: Mapping[str, object], *, is_metadata: bool = False) -> None:
    write_json(path / (METADATA_FILENAME if is_metadata else SUMMARY_FILENAME), payload)


def _write_progress_artifacts(
    *,
    output_root: Path,
    evidence_dir: Path,
    metadata: Mapping[str, object],
    summary: Mapping[str, object],
    global_members: Sequence[MemberValidationResult],
) -> None:
    _write_summary_artifacts(output_root, metadata, is_metadata=True)
    _write_summary_artifacts(evidence_dir, metadata, is_metadata=True)
    _write_summary_artifacts(output_root, summary)
    _write_summary_artifacts(evidence_dir, summary)
    write_member_results_csv(output_root / "TurboEvaluatedMembers.csv", global_members)
    write_member_results_csv(evidence_dir / "TurboEvaluatedMembers.csv", global_members)


def _final_summary(
    *,
    metadata: Mapping[str, object],
    args: argparse.Namespace,
    created_output_version: bool,
    output_version_dir: Path | None,
    baseline_member: MemberValidationResult,
    global_best_member: MemberValidationResult,
    unconstrained_lowest_loss_member: MemberValidationResult,
    selected_member: MemberValidationResult,
    local_seed_members: Sequence[MemberValidationResult],
    local_candidates: Sequence[Mapping[str, float]],
    local_member_results: Sequence[MemberValidationResult],
    promotion: Mapping[str, object],
    warnings: Sequence[str],
    state_history: Sequence[Mapping[str, object]],
    score_rows: Sequence[Mapping[str, object]],
    final_note: str,
) -> dict[str, object]:
    summary: dict[str, object] = {
        **metadata,
        "dryRun": False,
        "createdOutputVersion": created_output_version,
        "evidenceOnly": args.evidence_only,
        "globalBest": member_summary_payload(global_best_member, global_best_member.parameters, baseline_member=baseline_member),
        "unconstrainedLowestLoss": member_summary_payload(
            unconstrained_lowest_loss_member,
            unconstrained_lowest_loss_member.parameters,
            baseline_member=baseline_member,
        ),
        "selected": member_summary_payload(selected_member, selected_member.parameters, baseline_member=baseline_member),
        "baseline": member_summary_payload(baseline_member, baseline_member.parameters, baseline_member=baseline_member),
        "localRefinement": local_refinement_summary_payload(
            args=args,
            baseline_member=baseline_member,
            local_seed_members=local_seed_members,
            local_candidates=local_candidates,
            local_member_results=local_member_results,
            promotion=promotion,
        ),
        "turboStateHistory": list(state_history),
        "scoreRows": list(score_rows),
        "warnings": list(warnings),
        "finalValidationNote": final_note,
        "deleteCsvAfterMetrics": args.delete_csv_after_metrics,
    }
    if output_version_dir is not None:
        summary["outputVersionDir"] = str(output_version_dir)
    return summary


def _write_final_artifacts(
    output_root: Path,
    evidence_dir: Path,
    metadata: Mapping[str, object],
    summary: Mapping[str, object],
    global_members: Sequence[MemberValidationResult],
    local_members: Sequence[MemberValidationResult],
    all_members: Sequence[MemberValidationResult],
) -> None:
    _write_progress_artifacts(
        output_root=output_root,
        evidence_dir=evidence_dir,
        metadata=metadata,
        summary=summary,
        global_members=global_members,
    )
    write_member_results_csv(output_root / "LocalRefinementMembers.csv", local_members)
    write_member_results_csv(evidence_dir / "LocalRefinementMembers.csv", local_members)
    write_member_results_csv(output_root / "AllEvaluatedMembers.csv", all_members)
    write_member_results_csv(evidence_dir / "AllEvaluatedMembers.csv", all_members)


def main() -> None:
    args = build_arg_parser().parse_args()
    run_calibration(args)


if __name__ == "__main__":
    main()
