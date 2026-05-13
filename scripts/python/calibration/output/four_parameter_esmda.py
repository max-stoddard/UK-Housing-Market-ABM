#!/usr/bin/env python3
"""Run ES-MDA calibration for four output-calibrated parameters.

The workflow is deliberately separate from ``btl_probability_multiplier.py`` so
``vX.Xo`` and ``vX.Xoo`` can remain distinct output-calibration stages.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
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
    FOUR_PARAMETER_NAMES,
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
    group_seed_run_results_by_member,
    member_rank_key,
    observation_error_covariance,
    observation_vector,
    required_metric_status_counts,
    resolve_calibration_validation_profile,
    summarize_validation_profile,
)
from scripts.python.helpers.common.abm_policy_sweep import ensure_project_compiled, resolve_maven_bin
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import repo_root as default_repo_root
from scripts.python.validation.model.runner import resolve_was_data_root

DEFAULT_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8)
DEFAULT_WORKERS = 20
DEFAULT_ENSEMBLE_SIZE = 40
DEFAULT_ASSIMILATION_STEPS = 4
DEFAULT_RNG_SEED = 20260502
DEFAULT_LOCAL_REFINEMENT_TOP_N = 12
DEFAULT_LOCAL_REFINEMENT_RADIUS = 1
DEFAULT_LOCAL_REFINEMENT_MAX_CANDIDATES = 120
DEFAULT_REQUIRED_LOSS_IMPROVEMENT = 1.0e-3
DEFAULT_MATERIAL_LOSS_IMPROVEMENT = 2.0e-2
DEFAULT_STRATEGIC_METRIC_DEGRADATION_TOLERANCE = 0.1
DEFAULT_EXCESSIVE_MOVEMENT_THRESHOLD = 1.0
DEFAULT_BOUNDARY_LOSS_IMPROVEMENT = 5.0e-2
LOSS_HANDLING_NOTE = (
    "Validation metricLoss and overallCompositeLoss values are family-aware and unbounded; values greater than 1.0 "
    "are expected for severe misses and must not be clipped or treated as probabilities. ES-MDA can also run the "
    "old-compatible target-normalized additive objective for reproducibility."
)
STRATEGIC_METRIC_IDS = (
    "core_advancesToBTL",
    "core_hpiMean",
    "core_hpiStd",
    "core_hpiCyclePeriod",
    "income_distribution_jsd",
    "housing_wealth_distribution_jsd",
    "financial_wealth_distribution_jsd",
)


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        description="ES-MDA calibration for four output-calibrated housing-model parameters.",
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
    """Run or dry-run the four-parameter ES-MDA workflow."""

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

    output_root = resolve_repo_path(resolved_repo_root, args.output_root) / output_version / "four-parameter-esmda"
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
    write_json(output_root / "FourParameterEsmdaMetadata.json", metadata)
    _write_parameter_sets_csv(output_root / "InitialEnsemble.csv", initial_parameters)

    if args.dry_run:
        summary = {
            **metadata,
            "dryRun": True,
            "createdOutputVersion": False,
            "initialEnsembleCsv": str(output_root / "InitialEnsemble.csv"),
        }
        write_json(output_root / "FourParameterEsmdaCalibrationSummary.json", summary)
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

        best_iteration_member = min(iteration_member_results, key=member_rank_key)
        elapsed = time.monotonic() - started_at
        print(
            "[four-parameter-esmda] "
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

    baseline_member = _find_baseline_member(all_member_results)
    if baseline_member is None:
        raise RuntimeError("Missing source baseline member from ES-MDA iteration 0 member 0")

    global_best_member = min(all_member_results, key=member_rank_key)
    local_seed_members = sorted(all_member_results, key=member_rank_key)[: args.local_refinement_top_n]
    local_candidates = build_local_refinement_candidates(
        [member.parameters for member in local_seed_members],
        radius=0 if args.no_local_refinement else args.local_refinement_radius,
        max_candidates=args.local_refinement_max_candidates,
    )
    local_iteration = args.assimilation_steps + 1
    print(
        "[four-parameter-esmda] "
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
        warnings.append("No snapped local-refinement candidate passed the configured guardrails; output version was not created.")
        summary = {
            **metadata,
            "dryRun": False,
            "createdOutputVersion": False,
            "globalBest": _member_summary_payload(
                global_best_member,
                snap_parameter_set(global_best_member.parameters, specs=DEFAULT_PARAMETER_SPECS),
            ),
            "baseline": _member_summary_payload(baseline_member, baseline_member.parameters),
            "localRefinement": _local_refinement_summary_payload(
                args=args,
                local_candidates=local_candidates,
                local_member_results=local_member_results,
                promotion=promotion,
            ),
            "warnings": warnings,
            "finalValidationNote": "No output version was promoted because every snapped candidate breached guardrails.",
        }
        write_json(output_root / "FourParameterEsmdaCalibrationSummary.json", summary)
        write_json(evidence_dir / "FourParameterEsmdaCalibrationSummary.json", summary)
        _write_member_results_csv(output_root / "AllEvaluatedMembers.csv", all_member_results)
        _write_member_results_csv(output_root / "LocalRefinementMembers.csv", local_member_results)
        _write_member_results_csv(evidence_dir / "AllEvaluatedMembers.csv", all_member_results)
        _write_member_results_csv(evidence_dir / "LocalRefinementMembers.csv", local_member_results)
        raise RuntimeError("No snapped local-refinement candidate passed guardrails; see FourParameterEsmdaCalibrationSummary.json")

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
        ),
        "selected": _member_summary_payload(selected_member, selected_parameters),
        "baseline": _member_summary_payload(baseline_member, baseline_member.parameters),
        "localRefinement": _local_refinement_summary_payload(
            args=args,
            local_candidates=local_candidates,
            local_member_results=local_member_results,
            promotion=promotion,
        ),
        "warnings": warnings,
        "finalValidationNote": (
            "Selected guardrail-accepted snapped parameters were written to the output version. "
            "Run input-data-versions/validate.sh before claiming release calibration validity."
        ),
    }
    write_json(output_root / "FourParameterEsmdaCalibrationSummary.json", summary)
    write_json(evidence_dir / "FourParameterEsmdaCalibrationSummary.json", summary)
    _write_member_results_csv(output_root / "AllEvaluatedMembers.csv", all_member_results)
    _write_member_results_csv(evidence_dir / "AllEvaluatedMembers.csv", all_member_results)
    _write_member_results_csv(evidence_dir / "LocalRefinementMembers.csv", local_member_results)
    return summary


def build_reproduce_command(args: argparse.Namespace) -> str:
    """Build a shell command that reproduces the requested workflow."""

    command = [
        "python3 -m scripts.python.calibration.output.four_parameter_esmda",
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
        f"--output-root {args.output_root}",
    ]
    if args.evidence_dir:
        command.append(f"--evidence-dir {args.evidence_dir}")
    if args.maven_bin:
        command.append(f"--maven-bin {args.maven_bin}")
    if args.force_rerun:
        command.append("--force-rerun")
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
        "workflow": "four-parameter-esmda",
        "sourceVersion": version,
        "outputVersion": output_version,
        "parameters": list(FOUR_PARAMETER_NAMES),
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
        "alphaSchedule": [float(alpha) for alpha in alphas],
        "alphaScheduleCheckSumInverse": float(np.sum(1.0 / alphas)),
        "parameterSpecs": [asdict(spec) for spec in DEFAULT_PARAMETER_SPECS],
        "observations": [asdict(observation) for observation in observations],
        "outputRoot": str(output_root),
        "evidenceDir": str(evidence_dir),
    }


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


def _write_parameter_sets_csv(path: Path, parameter_sets: Sequence[Mapping[str, float]]) -> None:
    rows = []
    for index, parameters in enumerate(parameter_sets):
        row: dict[str, object] = {"memberId": index}
        row.update({key: float(parameters[key]) for key in FOUR_PARAMETER_NAMES})
        rows.append(row)
    _write_csv(path, rows)


def _write_member_results_csv(path: Path, member_results: Sequence[MemberValidationResult]) -> None:
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
        row.update({key: member.parameters[key] for key in FOUR_PARAMETER_NAMES})
        rows.append(row)
    _write_csv(path, rows)


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _find_baseline_member(member_results: Sequence[MemberValidationResult]) -> MemberValidationResult | None:
    for member in member_results:
        if member.iteration == 0 and member.member_id == 0:
            return member
    return None


def _build_model_quality_warnings(
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

    selected_metrics = _metrics_by_id(selected_member.summary)
    baseline_metrics = _metrics_by_id(baseline_member.summary)
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
        if float(selected_metric_loss) > float(baseline_metric_loss) + 0.1:
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
    """Select the best snapped candidate that passes model-quality guardrails."""

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
    lowest_loss_candidate = min(candidates, key=member_rank_key)
    if accepted_candidates:
        promoted = min(accepted_candidates, key=member_rank_key)
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
    loss_improvement = baseline_member.ranking_loss - candidate.ranking_loss
    fail_count_increase = int(candidate_counts.get("fail", 0)) - int(baseline_counts.get("fail", 0))
    strategic_degradations = _strategic_metric_degradations(candidate=candidate, baseline_member=baseline_member)
    boundary_parameters = _hard_boundary_parameters(candidate.parameters)
    rejection_reasons: list[str] = []

    if loss_improvement < DEFAULT_REQUIRED_LOSS_IMPROVEMENT:
        rejection_reasons.append(
            f"loss improvement {loss_improvement:.6f} is below minimum {DEFAULT_REQUIRED_LOSS_IMPROVEMENT:.6f}"
        )
    if fail_count_increase > 0 and loss_improvement < DEFAULT_MATERIAL_LOSS_IMPROVEMENT:
        rejection_reasons.append(
            "required fail count increased without material loss improvement "
            f"({fail_count_increase:+d} fails, improvement {loss_improvement:.6f})"
        )
    if strategic_degradations:
        rejection_reasons.append(
            "strategic metric loss degraded beyond tolerance: "
            + ", ".join(item["metricId"] for item in strategic_degradations)
        )
    if boundary_parameters and loss_improvement < DEFAULT_BOUNDARY_LOSS_IMPROVEMENT:
        rejection_reasons.append(
            "candidate sits on hard parameter boundary without strong loss improvement: "
            + ", ".join(boundary_parameters)
        )
    if (
        candidate.normalized_source_movement > DEFAULT_EXCESSIVE_MOVEMENT_THRESHOLD
        and loss_improvement < DEFAULT_MATERIAL_LOSS_IMPROVEMENT
    ):
        rejection_reasons.append(
            "normalized source movement is excessive for marginal loss improvement "
            f"({candidate.normalized_source_movement:.6f})"
        )

    return {
        "iteration": candidate.iteration,
        "memberId": candidate.member_id,
        "accepted": not rejection_reasons,
        "rejectionReasons": rejection_reasons,
        "lossImprovementVersusBaseline": loss_improvement,
        "baselineRankingLoss": baseline_member.ranking_loss,
        "candidateRankingLoss": candidate.ranking_loss,
        "rankingObjective": candidate.ranking_objective,
        "failCountIncrease": fail_count_increase,
        "baselineStatusCounts": baseline_counts,
        "candidateStatusCounts": candidate_counts,
        "strategicMetricDegradations": strategic_degradations,
        "hardBoundaryParameters": boundary_parameters,
        "normalizedSourceMovement": candidate.normalized_source_movement,
        "rankKey": list(member_rank_key(candidate)),
    }


def _strategic_metric_degradations(
    *,
    candidate: MemberValidationResult,
    baseline_member: MemberValidationResult,
) -> list[dict[str, object]]:
    selected_metrics = _metrics_by_id(candidate.summary)
    baseline_metrics = _metrics_by_id(baseline_member.summary)
    degraded: list[dict[str, object]] = []
    for metric_id in STRATEGIC_METRIC_IDS:
        selected_metric = selected_metrics.get(metric_id)
        baseline_metric = baseline_metrics.get(metric_id)
        if selected_metric is None or baseline_metric is None:
            continue
        selected_metric_loss = selected_metric.get("metricLoss")
        baseline_metric_loss = baseline_metric.get("metricLoss")
        if selected_metric_loss is None or baseline_metric_loss is None:
            continue
        delta = float(selected_metric_loss) - float(baseline_metric_loss)
        if delta > DEFAULT_STRATEGIC_METRIC_DEGRADATION_TOLERANCE:
            degraded.append(
                {
                    "metricId": metric_id,
                    "baselineMetricLoss": float(baseline_metric_loss),
                    "candidateMetricLoss": float(selected_metric_loss),
                    "delta": delta,
                }
            )
    return degraded


def _hard_boundary_parameters(parameters: Mapping[str, float]) -> list[str]:
    boundary_parameters: list[str] = []
    for spec in DEFAULT_PARAMETER_SPECS:
        value = float(parameters[spec.name])
        if math.isclose(value, spec.lower, rel_tol=0.0, abs_tol=1.0e-12) or math.isclose(
            value,
            spec.upper,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        ):
            boundary_parameters.append(spec.name)
    return boundary_parameters


def _guardrail_thresholds_payload() -> dict[str, object]:
    return {
        "requiredLossImprovement": DEFAULT_REQUIRED_LOSS_IMPROVEMENT,
        "materialLossImprovementForFailCountIncrease": DEFAULT_MATERIAL_LOSS_IMPROVEMENT,
        "strategicMetricDegradationTolerance": DEFAULT_STRATEGIC_METRIC_DEGRADATION_TOLERANCE,
        "excessiveNormalizedSourceMovement": DEFAULT_EXCESSIVE_MOVEMENT_THRESHOLD,
        "boundaryParameterMinimumLossImprovement": DEFAULT_BOUNDARY_LOSS_IMPROVEMENT,
        "strategicMetricIds": list(STRATEGIC_METRIC_IDS),
        "rankingPrimaryObjective": "lowest 2011/W3 overallCompositeLoss when validation-year=2011 and validation-objective=family_aware_metric_loss",
    }


def _metrics_by_id(summary: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    metrics = summary.get("metrics")
    if not isinstance(metrics, Sequence):
        return {}
    return {
        str(metric["metricId"]): metric
        for metric in metrics
        if isinstance(metric, Mapping) and "metricId" in metric
    }


def _member_summary_payload(
    member: MemberValidationResult,
    selected_parameters: Mapping[str, float],
) -> dict[str, object]:
    counts = required_metric_status_counts(member.summary)
    return {
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


def _local_refinement_summary_payload(
    *,
    args: argparse.Namespace,
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
        "oneParameterNeighbourRadius": 0 if args.no_local_refinement else args.local_refinement_radius,
        "maxCandidates": args.local_refinement_max_candidates,
        "deduplicatedSnappedCandidateCount": len(local_candidates),
        "evaluatedCandidateCount": len(local_member_results),
        "seedRuns": len(local_candidates) * len(parse_seed_list(args.seeds)),
        "guardrailThresholds": _guardrail_thresholds_payload(),
        "promotionAccepted": bool(promotion["accepted"]),
        "lowestLossRejected": bool(promotion["lowestLossRejected"]),
        "promoted": _member_summary_payload(promoted_member, promoted_member.parameters),
        "lowestLoss": _member_summary_payload(lowest_loss_member, lowest_loss_member.parameters),
        "promotedDecision": promotion["promotedDecision"],
        "lowestLossDecision": promotion["lowestLossDecision"],
        "candidateDecisions": promotion["decisions"],
    }


def _format_duration(seconds: float) -> str:
    rounded = max(0, int(round(seconds)))
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def main() -> None:
    args = build_arg_parser().parse_args()
    run_calibration(args)


if __name__ == "__main__":
    main()
