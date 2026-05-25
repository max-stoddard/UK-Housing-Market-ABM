#!/usr/bin/env python3
"""Run ES-MDA calibration for jointly output-calibrated parameters.

The historical module name is kept so existing reproduction commands continue
to work. Current campaigns use the five-parameter output ES-MDA parameter set.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from scripts.python.calibration.output.candidate_runs import (
    DEFAULT_OUTPUT_ROOT,
    EVIDENCE_DIR_TEMPLATE,
    create_output_version,
    execute_seed_requests_for_members,
    parse_config_parameters,
    parse_seed_list,
    resolve_repo_path,
    validate_version_name,
    write_json,
)
from scripts.python.calibration.output.esmda import (
    DEFAULT_PARAMETER_SPECS,
    OUTPUT_ESMDA_PARAMETER_NAMES,
    clip_transformed_ensemble_to_bounds,
    esmda_update,
    generate_initial_ensemble,
    make_alpha_schedule,
    parameter_dicts_to_transformed_matrix,
    snap_parameter_set,
    transformed_matrix_to_parameter_dicts,
)
from scripts.python.calibration.output.validation_bridge import (
    DEFAULT_VALIDATION_LOSS_ERROR_STD,
    DEFAULT_VALIDATION_OBJECTIVE,
    FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
    MemberValidationResult,
    TARGET_NORMALIZED_ADDITIVE_OBJECTIVE,
    build_member_validation_result,
    build_validation_observations,
    constrained_member_rank_key,
    group_seed_run_results_by_member,
    member_rank_key,
    observation_error_covariance,
    observation_vector,
    overall_composite_loss,
    resolve_calibration_validation_profile,
    summarize_validation_profile,
)
from scripts.python.calibration.output.workflow_helpers import (
    build_local_refinement_candidates,
    build_model_quality_warnings as _build_model_quality_warnings,
    find_baseline_member as _find_baseline_member,
    format_duration as _format_duration,
    guardrail_thresholds_payload as _guardrail_thresholds_payload,
    local_refinement_skipped_summary_payload as _local_refinement_skipped_summary_payload,
    local_refinement_summary_payload as _local_refinement_summary_payload,
    member_summary_payload as _member_summary_payload,
    select_guardrailed_member,
    select_local_refinement_seed_members,
    write_member_results_csv as _write_member_results_csv,
    write_parameter_sets_csv as _write_parameter_sets_csv,
)
from scripts.python.helpers.common.abm_policy_sweep import ensure_project_compiled, resolve_maven_bin
from scripts.python.helpers.common.paths import repo_root as default_repo_root
from scripts.python.validation.model.runner import resolve_was_data_root
from scripts.python.validation.model.schema import VALIDATION_WINDOW_END, VALIDATION_WINDOW_START

DEFAULT_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
DEFAULT_WORKERS = 20
DEFAULT_ENSEMBLE_SIZE = 40
DEFAULT_ASSIMILATION_STEPS = 4
DEFAULT_RNG_SEED = 20260502
DEFAULT_LOCAL_REFINEMENT_TOP_N = 12
DEFAULT_LOCAL_REFINEMENT_RADIUS = 1
DEFAULT_LOCAL_REFINEMENT_MAX_CANDIDATES = 120
WORKFLOW_SLUG = "five-parameter-esmda"
WORKFLOW_NAME = "five-parameter-esmda"
METADATA_FILENAME = "OutputParameterEsmdaMetadata.json"
SUMMARY_FILENAME = "OutputParameterEsmdaCalibrationSummary.json"
LEGACY_METADATA_FILENAME = "FourParameterEsmdaMetadata.json"
LEGACY_SUMMARY_FILENAME = "FourParameterEsmdaCalibrationSummary.json"
LOSS_HANDLING_NOTE = (
    "Validation metricLoss and overallCompositeLoss values are family-aware and unbounded; values greater than 1.0 "
    "are expected for severe misses and must not be clipped or treated as probabilities. ES-MDA can also run the "
    "old-compatible target-normalized additive objective for reproducibility."
)
def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        description="ES-MDA calibration for jointly output-calibrated housing-model parameters.",
    )
    parser.add_argument("--version", required=True, help="Source input-data version, for example v4.14o")
    parser.add_argument("--output-version", required=True, help="Output version to create, for example v4.14oo")
    parser.add_argument(
        "--validation-year",
        type=int,
        choices=(2011, 2024),
        default=2024,
        help="Validation target year/profile to use (default: 2024).",
    )
    parser.add_argument(
        "--validation-objective",
        choices=(FAMILY_AWARE_METRIC_LOSS_OBJECTIVE, TARGET_NORMALIZED_ADDITIVE_OBJECTIVE),
        default=DEFAULT_VALIDATION_OBJECTIVE,
        help=(
            "Validation objective used for ES-MDA assimilation and ranking "
            f"(default: {DEFAULT_VALIDATION_OBJECTIVE})."
        ),
    )
    parser.add_argument(
        "--validation-loss-error-std",
        type=float,
        default=DEFAULT_VALIDATION_LOSS_ERROR_STD,
        help=(
            "Diagonal observation standard deviation used when --validation-objective "
            f"{FAMILY_AWARE_METRIC_LOSS_OBJECTIVE} targets zero per-metric loss "
            f"(default: {DEFAULT_VALIDATION_LOSS_ERROR_STD})."
        ),
    )
    parser.add_argument(
        "--seeds",
        default=",".join(str(seed) for seed in DEFAULT_SEEDS),
        help="Comma-separated common-random-number seed block (default: 1,2,3,4,5,6,7,8).",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Maximum parallel seed workers.")
    parser.add_argument(
        "--ensemble-size",
        type=int,
        default=DEFAULT_ENSEMBLE_SIZE,
        help=f"ES-MDA ensemble size (default: {DEFAULT_ENSEMBLE_SIZE}).",
    )
    parser.add_argument(
        "--assimilation-steps",
        type=int,
        default=DEFAULT_ASSIMILATION_STEPS,
        help=f"Number of ES-MDA assimilations (default: {DEFAULT_ASSIMILATION_STEPS}).",
    )
    parser.add_argument("--rng-seed", type=int, default=DEFAULT_RNG_SEED)
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
    parser.add_argument(
        "--no-local-refinement",
        action="store_true",
        help="Skip snapped local refinement and promote the best guarded snapped ES-MDA candidate directly.",
    )
    parser.add_argument(
        "--local-refinement-top-n",
        type=int,
        default=DEFAULT_LOCAL_REFINEMENT_TOP_N,
        help=f"Number of best ES-MDA members to seed local snapped refinement (default: {DEFAULT_LOCAL_REFINEMENT_TOP_N}).",
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
        help="Write metadata and the deterministic initial ensemble without running Maven or creating a version.",
    )
    return parser


def run_calibration(args: argparse.Namespace, *, repo_root: Path | None = None) -> dict[str, object]:
    """Run or dry-run the output-parameter ES-MDA workflow."""

    resolved_repo_root = repo_root or default_repo_root()
    maven_bin = resolve_maven_bin(resolved_repo_root, args.maven_bin)
    version = validate_version_name(args.version)
    output_version = validate_version_name(args.output_version)
    seeds = parse_seed_list(args.seeds)
    _validate_execution_args(args=args, seeds=seeds)

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

    alphas = make_alpha_schedule(args.assimilation_steps)
    transformed_ensemble = generate_initial_ensemble(
        specs=DEFAULT_PARAMETER_SPECS,
        ensemble_size=args.ensemble_size,
        rng_seed=args.rng_seed,
    )
    # Keep the source vector in the evaluated ensemble so model-quality warnings
    # can compare against the actual source snapshot under the same seed block.
    transformed_ensemble[0, :] = parameter_dicts_to_transformed_matrix(
        [source_parameters],
        specs=DEFAULT_PARAMETER_SPECS,
    )[0, :]
    initial_parameters = transformed_matrix_to_parameter_dicts(
        transformed_ensemble,
        specs=DEFAULT_PARAMETER_SPECS,
    )

    metadata = _build_base_metadata(
        args=args,
        version=version,
        output_version=output_version,
        seeds=seeds,
        validation_profile=validation_profile,
        observations=observations,
        alphas=alphas,
        source_parameters=source_parameters,
        output_root=output_root,
        evidence_dir=evidence_dir,
    )
    _write_summary_artifacts(output_root, metadata, is_metadata=True)
    _write_parameter_sets_csv(output_root / "InitialEnsemble.csv", initial_parameters)

    if args.dry_run:
        summary = {
            **metadata,
            "dryRun": True,
            "createdOutputVersion": False,
            "initialEnsembleCsv": str(output_root / "InitialEnsemble.csv"),
        }
        _write_summary_artifacts(output_root, summary)
        return summary

    requested_output_dir = resolved_repo_root / "input-data-versions" / output_version
    if requested_output_dir.exists() and not args.overwrite_version:
        raise RuntimeError(f"Output version already exists: {requested_output_dir}")

    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "reproduce-command.sh").write_text(build_reproduce_command(args), encoding="utf-8")
    ensure_project_compiled(resolved_repo_root, maven_bin=maven_bin)
    was_data_root = resolve_was_data_root(repo_root=resolved_repo_root, explicit_root=None)

    all_member_results: list[MemberValidationResult] = []
    current_transformed_ensemble = transformed_ensemble
    baseline_member_for_ranking: MemberValidationResult | None = None
    started_at = time.monotonic()
    for iteration in range(args.assimilation_steps + 1):
        current_parameters = transformed_matrix_to_parameter_dicts(
            current_transformed_ensemble,
            specs=DEFAULT_PARAMETER_SPECS,
        )
        seed_run_results = execute_seed_requests_for_members(
            repo_root=resolved_repo_root,
            version=version,
            iteration=iteration,
            member_parameters=current_parameters,
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
        grouped_seed_results = group_seed_run_results_by_member(seed_run_results)
        iteration_member_results = [
            build_member_validation_result(
                version=version,
                iteration=iteration,
                member_id=member_id,
                parameters=current_parameters[member_id],
                seed_results=grouped_seed_results[member_id],
                seeds=seeds,
                validation_profile=validation_profile,
                observations=observations,
                source_parameters=source_parameters,
                validation_window_start=args.validation_window_start,
                validation_window_end=args.validation_window_end,
            )
            for member_id in range(len(current_parameters))
        ]
        all_member_results.extend(iteration_member_results)
        _write_member_results_csv(
            output_root / "members" / f"Iteration{iteration:02d}Members.csv",
            iteration_member_results,
        )
        _write_parameter_sets_csv(
            output_root / "parameters" / f"Iteration{iteration:02d}Parameters.csv",
            current_parameters,
        )

        if iteration == 0:
            baseline_member_for_ranking = _find_baseline_member(iteration_member_results)
        if baseline_member_for_ranking is None:
            best_iteration_member = min(iteration_member_results, key=member_rank_key)
        else:
            best_iteration_member = min(
                iteration_member_results,
                key=lambda member: constrained_member_rank_key(
                    member,
                    baseline_member=baseline_member_for_ranking,
                ),
            )
        elapsed = time.monotonic() - started_at
        print(
            "[output-esmda] "
            f"iteration={iteration + 1}/{args.assimilation_steps + 1} "
            f"bestMember={best_iteration_member.member_id} "
            f"rankLoss={best_iteration_member.ranking_loss:.6f} "
            f"schemaLoss={float(best_iteration_member.summary['overallCompositeLoss']):.6f} "
            f"elapsed={_format_duration(elapsed)}",
            flush=True,
        )

        if iteration < args.assimilation_steps:
            simulated_observations = np.array(
                [member.observation_vector for member in iteration_member_results],
                dtype=float,
            )
            current_transformed_ensemble = esmda_update(
                transformed_parameters=current_transformed_ensemble,
                simulated_observations=simulated_observations,
                observed_vector=observation_vector(observations),
                observation_error_covariance=observation_error_covariance(observations),
                alpha=float(alphas[iteration]),
                rng_seed=args.rng_seed + iteration + 1,
                perturb_observations=True,
            )
            current_transformed_ensemble = clip_transformed_ensemble_to_bounds(
                current_transformed_ensemble,
                specs=DEFAULT_PARAMETER_SPECS,
            )

    baseline_member = baseline_member_for_ranking or _find_baseline_member(all_member_results)
    if baseline_member is None:
        raise RuntimeError("Missing source baseline member from ES-MDA iteration 0 member 0")

    global_best_member = min(
        all_member_results,
        key=lambda member: constrained_member_rank_key(member, baseline_member=baseline_member),
    )
    unconstrained_lowest_loss_member = min(all_member_results, key=overall_composite_loss)
    local_seed_members = select_local_refinement_seed_members(
        all_member_results,
        baseline_member=baseline_member,
        top_n=args.local_refinement_top_n,
    )
    if not local_seed_members:
        warning = (
            "No ES-MDA member improved overallCompositeLoss without regressing core_hpiStd, "
            "core_hpiCyclePeriod, or core_hpiMean; local refinement was not run."
        )
        summary = {
            **metadata,
            "dryRun": False,
            "createdOutputVersion": False,
            "globalBest": _member_summary_payload(
                global_best_member,
                snap_parameter_set(global_best_member.parameters, specs=DEFAULT_PARAMETER_SPECS),
                baseline_member=baseline_member,
            ),
            "unconstrainedLowestLoss": _member_summary_payload(
                unconstrained_lowest_loss_member,
                snap_parameter_set(unconstrained_lowest_loss_member.parameters, specs=DEFAULT_PARAMETER_SPECS),
                baseline_member=baseline_member,
            ),
            "baseline": _member_summary_payload(
                baseline_member,
                baseline_member.parameters,
                baseline_member=baseline_member,
            ),
            "localRefinement": _local_refinement_skipped_summary_payload(
                args=args,
                all_member_results=all_member_results,
                baseline_member=baseline_member,
                skipped_reason=warning,
            ),
            "warnings": [warning],
            "finalValidationNote": "No output version was promoted because no ES-MDA member satisfied HPI constraints.",
        }
        _write_summary_artifacts(output_root, summary)
        _write_summary_artifacts(evidence_dir, summary)
        _write_member_results_csv(output_root / "AllEvaluatedMembers.csv", all_member_results)
        _write_member_results_csv(evidence_dir / "AllEvaluatedMembers.csv", all_member_results)
        raise RuntimeError(f"No ES-MDA member satisfied HPI-constrained ranking; see {SUMMARY_FILENAME}")

    local_candidates = build_local_refinement_candidates(
        [member.parameters for member in local_seed_members],
        radius=0 if args.no_local_refinement else args.local_refinement_radius,
        max_candidates=args.local_refinement_max_candidates,
    )
    local_iteration = args.assimilation_steps + 1
    print(
        "[output-esmda] "
        f"localRefinement={'disabled' if args.no_local_refinement else 'enabled'} "
        f"seedMembers={len(local_seed_members)} snappedCandidates={len(local_candidates)} "
        f"seedRuns={len(local_candidates) * len(seeds)} validationObjective={args.validation_objective}",
        flush=True,
    )
    local_seed_run_results = execute_seed_requests_for_members(
        repo_root=resolved_repo_root,
        version=version,
        iteration=local_iteration,
        member_parameters=local_candidates,
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
    local_grouped_seed_results = group_seed_run_results_by_member(local_seed_run_results)
    local_member_results = [
        build_member_validation_result(
            version=version,
            iteration=local_iteration,
            member_id=member_id,
            parameters=local_candidates[member_id],
            seed_results=local_grouped_seed_results[member_id],
            seeds=seeds,
            validation_profile=validation_profile,
            observations=observations,
            source_parameters=source_parameters,
            validation_window_start=args.validation_window_start,
            validation_window_end=args.validation_window_end,
        )
        for member_id in range(len(local_candidates))
    ]
    _write_member_results_csv(output_root / "members" / "LocalRefinementMembers.csv", local_member_results)
    _write_parameter_sets_csv(output_root / "parameters" / "LocalRefinementParameters.csv", local_candidates)

    promotion = select_guardrailed_member(
        candidates=local_member_results,
        baseline_member=baseline_member,
    )
    selected_member = promotion["promotedMember"]
    assert isinstance(selected_member, MemberValidationResult)
    selected_parameters = selected_member.parameters
    warnings = _build_model_quality_warnings(
        selected_member=selected_member,
        baseline_member=baseline_member,
    )
    if not promotion["accepted"]:
        warnings.append("No snapped local-refinement candidate improved total loss without HPI regression; output version was not created.")
        summary = {
            **metadata,
            "dryRun": False,
            "createdOutputVersion": False,
            "globalBest": _member_summary_payload(
                global_best_member,
                snap_parameter_set(global_best_member.parameters, specs=DEFAULT_PARAMETER_SPECS),
                baseline_member=baseline_member,
            ),
            "unconstrainedLowestLoss": _member_summary_payload(
                unconstrained_lowest_loss_member,
                snap_parameter_set(unconstrained_lowest_loss_member.parameters, specs=DEFAULT_PARAMETER_SPECS),
                baseline_member=baseline_member,
            ),
            "baseline": _member_summary_payload(
                baseline_member,
                baseline_member.parameters,
                baseline_member=baseline_member,
            ),
            "localRefinement": _local_refinement_summary_payload(
                args=args,
                baseline_member=baseline_member,
                local_seed_members=local_seed_members,
                local_candidates=local_candidates,
                local_member_results=local_member_results,
                promotion=promotion,
            ),
            "warnings": warnings,
            "finalValidationNote": (
                "No output version was promoted because every snapped candidate failed total-loss or HPI constraints."
            ),
        }
        _write_summary_artifacts(output_root, summary)
        _write_summary_artifacts(evidence_dir, summary)
        _write_member_results_csv(output_root / "AllEvaluatedMembers.csv", all_member_results)
        _write_member_results_csv(output_root / "LocalRefinementMembers.csv", local_member_results)
        _write_member_results_csv(evidence_dir / "AllEvaluatedMembers.csv", all_member_results)
        _write_member_results_csv(evidence_dir / "LocalRefinementMembers.csv", local_member_results)
        raise RuntimeError(f"No snapped local-refinement candidate satisfied HPI-constrained ranking; see {SUMMARY_FILENAME}")

    output_version_dir = create_output_version(
        repo_root=resolved_repo_root,
        source_version=version,
        output_version=output_version,
        selected_parameters=selected_parameters,
        overwrite=args.overwrite_version,
    )

    summary: dict[str, object] = {
        **metadata,
        "dryRun": False,
        "createdOutputVersion": True,
        "outputVersionDir": str(output_version_dir),
        "globalBest": _member_summary_payload(
            global_best_member,
            snap_parameter_set(global_best_member.parameters, specs=DEFAULT_PARAMETER_SPECS),
            baseline_member=baseline_member,
        ),
        "unconstrainedLowestLoss": _member_summary_payload(
            unconstrained_lowest_loss_member,
            snap_parameter_set(unconstrained_lowest_loss_member.parameters, specs=DEFAULT_PARAMETER_SPECS),
            baseline_member=baseline_member,
        ),
        "selected": _member_summary_payload(
            selected_member,
            selected_parameters,
            baseline_member=baseline_member,
        ),
        "baseline": _member_summary_payload(
            baseline_member,
            baseline_member.parameters,
            baseline_member=baseline_member,
        ),
        "localRefinement": _local_refinement_summary_payload(
            args=args,
            baseline_member=baseline_member,
            local_seed_members=local_seed_members,
            local_candidates=local_candidates,
            local_member_results=local_member_results,
            promotion=promotion,
        ),
        "warnings": warnings,
        "finalValidationNote": (
            "Selected HPI-constrained snapped parameters were written to the output version. "
            "Run input-data-versions/validate.sh before claiming release calibration validity."
        ),
    }
    _write_summary_artifacts(output_root, summary)
    _write_summary_artifacts(evidence_dir, summary)
    _write_member_results_csv(output_root / "AllEvaluatedMembers.csv", all_member_results)
    _write_member_results_csv(evidence_dir / "AllEvaluatedMembers.csv", all_member_results)
    _write_member_results_csv(evidence_dir / "LocalRefinementMembers.csv", local_member_results)
    return summary


def build_reproduce_command(args: argparse.Namespace) -> str:
    """Build a shell command that reproduces the requested workflow."""

    command = [
        "python3 -m scripts.python.calibration.output.output_parameter_esmda",
        f"--version {args.version}",
        f"--output-version {args.output_version}",
        f"--validation-year {args.validation_year}",
        f"--validation-objective {args.validation_objective}",
        f"--validation-loss-error-std {args.validation_loss_error_std}",
        f"--seeds {args.seeds}",
        f"--workers {args.workers}",
        f"--ensemble-size {args.ensemble_size}",
        f"--assimilation-steps {args.assimilation_steps}",
        f"--rng-seed {args.rng_seed}",
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
    if args.dry_run:
        command.append("--dry-run")
    return (" " + "\\" + "\n  ").join(command) + "\n"


def _write_summary_artifacts(path: Path, payload: Mapping[str, object], *, is_metadata: bool = False) -> None:
    """Write generic artifact names plus historical aliases for compatibility."""

    primary = METADATA_FILENAME if is_metadata else SUMMARY_FILENAME
    legacy = LEGACY_METADATA_FILENAME if is_metadata else LEGACY_SUMMARY_FILENAME
    write_json(path / primary, payload)
    write_json(path / legacy, payload)


def _validate_execution_args(*, args: argparse.Namespace, seeds: Sequence[int]) -> None:
    if args.workers <= 0:
        raise ValueError("workers must be positive")
    if args.ensemble_size <= 1:
        raise ValueError("ensemble-size must be greater than one")
    if args.assimilation_steps <= 0:
        raise ValueError("assimilation-steps must be positive")
    if args.validation_loss_error_std <= 0.0:
        raise ValueError("validation-loss-error-std must be positive")
    if args.workers < len(seeds):
        raise ValueError("workers must be at least the number of seeds for grouped candidate scheduling")
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
    validation_profile: object,
    observations: Sequence[object],
    alphas: np.ndarray,
    source_parameters: Mapping[str, float],
    output_root: Path,
    evidence_dir: Path,
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
        "assimilationTransform": observations[0].assimilation_transform if observations else None,
        "rankingObjective": args.validation_objective,
        "validationLossErrorStd": args.validation_loss_error_std,
        "guardrailThresholds": _guardrail_thresholds_payload(),
        "seeds": list(seeds),
        "workers": args.workers,
        "candidateParallelism": max(1, math.ceil(args.workers / len(seeds))),
        "ensembleSize": args.ensemble_size,
        "assimilationSteps": args.assimilation_steps,
        "rngSeed": args.rng_seed,
        "nSteps": args.n_steps,
        "validationWindow": {
            "startIndex": args.validation_window_start,
            "endIndex": args.validation_window_end,
        },
        "deleteCsvAfterMetrics": args.delete_csv_after_metrics,
        "alphaSchedule": [float(alpha) for alpha in alphas],
        "alphaScheduleCheckSumInverse": float(np.sum(1.0 / alphas)),
        "parameterSpecs": [asdict(spec) for spec in DEFAULT_PARAMETER_SPECS],
        "observations": [asdict(observation) for observation in observations],
        "outputRoot": str(output_root),
        "evidenceDir": str(evidence_dir),
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    run_calibration(args)


if __name__ == "__main__":
    main()
