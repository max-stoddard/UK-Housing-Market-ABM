#!/usr/bin/env python3
"""Run a live from-scratch SMM versus TuRBO output-calibration comparison.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from scripts.python.calibration.output.candidate_runs import (
    DEFAULT_OUTPUT_ROOT,
    execute_seed_requests_for_members,
    parse_config_parameters,
    parse_seed_list,
    resolve_repo_path,
    validate_version_name,
    write_json,
)
from scripts.python.calibration.output.convergence import (
    write_live_convergence_artifacts,
)
from scripts.python.calibration.output.esmda import OUTPUT_ESMDA_PARAMETER_NAMES
from scripts.python.calibration.output.grid_smm import (
    DEFAULT_GRID_RNG_SEED,
    GRID_ORDER_RANDOM,
    GRID_PROFILE_CARRO_FULL,
    GridCandidate,
    build_grid_candidates,
    order_grid_candidates,
    validate_run_id,
)
from scripts.python.calibration.output.parameter_space import (
    ORIGINAL_SMM_PARAMETER_SPECS,
)
from scripts.python.calibration.output.turbo_core import (
    DEFAULT_RNG_SEED,
    DEFAULT_TRUST_REGION_LENGTH,
    DEFAULT_TRUST_REGION_LENGTH_MAX,
    DEFAULT_TRUST_REGION_LENGTH_MIN,
    DEFAULT_SUCCESS_TOLERANCE,
    TurboDependencyBundle,
    TurboState,
    default_failure_tolerance,
    generate_initial_normalized_design,
    load_turbo_dependencies,
    normalized_points_to_parameter_dicts,
    propose_turbo_candidates,
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
    required_metric_status_counts,
    resolve_calibration_validation_profile,
    summarize_validation_profile,
)
from scripts.python.calibration.output.workflow_helpers import (
    format_duration,
    write_csv,
)
from scripts.python.helpers.common.abm_policy_sweep import (
    ensure_project_compiled,
    resolve_maven_bin,
)
from scripts.python.helpers.common.paths import repo_root as default_repo_root
from scripts.python.validation.model.runner import resolve_was_data_root

WORKFLOW_NAME = "method-comparison"
WORKFLOW_SLUG = "method-comparison"
METHOD_TURBO = "TuRBO method"
METHOD_SMM = "Random-grid method"
METHOD_TURBO_SLUG = "turbo"
METHOD_SMM_SLUG = "smm-random-grid"
METHOD_DISPLAY_LABELS = {
    METHOD_TURBO: "TuRBO",
    METHOD_SMM: "SMM random grid",
}
DEFAULT_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
DEFAULT_WORKERS = 20
DEFAULT_REPLICATES = 5
DEFAULT_EVALUATIONS = 480
DEFAULT_CHECKPOINT_EVALUATIONS = 240
DEFAULT_TURBO_INITIAL_POINTS = 40
DEFAULT_N_STEPS = 3500
DEFAULT_VALIDATION_WINDOW_START = 500
DEFAULT_VALIDATION_WINDOW_END = 3500
METADATA_FILENAME = "MethodComparisonMetadata.json"
SUMMARY_FILENAME = "MethodComparisonSummary.json"
EVALUATED_MEMBERS_FILENAME = "MethodComparisonEvaluatedMembers.csv"


@dataclass
class TurboReplicateState:
    """Mutable optimizer state for one TuRBO replicate."""

    replicate: int
    initial_normalized: np.ndarray
    turbo_state: TurboState
    train_x_rows: list[np.ndarray] = field(default_factory=list)
    train_y_rows: list[list[float]] = field(default_factory=list)
    train_yvar_rows: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateRequest:
    """One method/replicate candidate evaluation request."""

    method: str
    method_slug: str
    replicate: int
    evaluation: int
    member_id: int
    parameters: dict[str, float]
    output_root: Path
    normalized_point: np.ndarray | None = None
    original_grid_member_id: int | None = None


@dataclass(frozen=True)
class CandidateResult:
    """Completed candidate evaluation with cache accounting."""

    request: CandidateRequest
    member: MemberValidationResult
    seed_run_count: int
    cached_seed_run_count: int


def build_arg_parser() -> argparse.ArgumentParser:
    """Build CLI parser for the live comparison workflow."""

    parser = argparse.ArgumentParser(
        description="Live restartable comparison of from-scratch TuRBO and random-prefix SMM.",
    )
    parser.add_argument(
        "--version", required=True, help="Source input-data version, for example v0"
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Stable run id used for cache and live evidence paths",
    )
    parser.add_argument(
        "--validation-year",
        type=int,
        choices=(2011, 2024),
        default=2011,
        help="Validation target year/profile to use (default: 2011).",
    )
    parser.add_argument(
        "--validation-objective",
        choices=(
            FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
            TARGET_NORMALIZED_ADDITIVE_OBJECTIVE,
        ),
        default=FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
        help="Validation objective used for candidate ranking.",
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
    parser.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS, help="Total parallel workers."
    )
    parser.add_argument(
        "--replicates",
        type=int,
        default=DEFAULT_REPLICATES,
        help="Independent method replicates.",
    )
    parser.add_argument(
        "--evaluations",
        type=int,
        default=DEFAULT_EVALUATIONS,
        help="Candidate evaluations per method replicate.",
    )
    parser.add_argument(
        "--checkpoint-evaluations",
        type=int,
        default=DEFAULT_CHECKPOINT_EVALUATIONS,
        help="Evaluation budget checkpoint highlighted in live summaries.",
    )
    parser.add_argument(
        "--smm-grid-profile",
        choices=(GRID_PROFILE_CARRO_FULL,),
        default=GRID_PROFILE_CARRO_FULL,
        help="SMM grid profile for the random-prefix baseline.",
    )
    parser.add_argument(
        "--smm-grid-order",
        choices=(GRID_ORDER_RANDOM,),
        default=GRID_ORDER_RANDOM,
        help="SMM candidate ordering for each replicate.",
    )
    parser.add_argument(
        "--smm-grid-rng-seed",
        type=int,
        default=DEFAULT_GRID_RNG_SEED,
        help=f"Base SMM random-order seed (default: {DEFAULT_GRID_RNG_SEED}).",
    )
    parser.add_argument("--turbo-rng-seed", type=int, default=DEFAULT_RNG_SEED)
    parser.add_argument(
        "--turbo-initial-points", type=int, default=DEFAULT_TURBO_INITIAL_POINTS
    )
    parser.add_argument(
        "--turbo-length", type=float, default=DEFAULT_TRUST_REGION_LENGTH
    )
    parser.add_argument(
        "--turbo-length-min", type=float, default=DEFAULT_TRUST_REGION_LENGTH_MIN
    )
    parser.add_argument(
        "--turbo-length-max", type=float, default=DEFAULT_TRUST_REGION_LENGTH_MAX
    )
    parser.add_argument(
        "--turbo-success-tolerance", type=int, default=DEFAULT_SUCCESS_TOLERANCE
    )
    parser.add_argument("--turbo-failure-tolerance", type=int, default=None)
    parser.add_argument("--turbo-noise-variance-floor", type=float, default=1.0e-6)
    parser.add_argument("--n-steps", type=int, default=DEFAULT_N_STEPS)
    parser.add_argument(
        "--validation-window-start", type=int, default=DEFAULT_VALIDATION_WINDOW_START
    )
    parser.add_argument(
        "--validation-window-end", type=int, default=DEFAULT_VALIDATION_WINDOW_END
    )
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Transient output root (default: {DEFAULT_OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--maven-bin",
        default=None,
        help="Maven executable override (default: repo-local ./mvnw).",
    )
    parser.add_argument(
        "--force-rerun", action="store_true", help="Ignore cached per-seed metric JSON."
    )
    parser.add_argument(
        "--delete-csv-after-metrics",
        action="store_true",
        help="After each seed's metrics are cached, delete generated run CSV outputs from that seed directory.",
    )
    parser.add_argument(
        "--live-plot-x-minor-step",
        type=float,
        default=None,
        help="Optional minor x-grid interval for the live convergence plot.",
    )
    parser.add_argument(
        "--live-plot-y-minor-step",
        type=float,
        default=None,
        help="Optional minor y-grid interval for the live convergence plot.",
    )
    parser.add_argument(
        "--live-plot-reference-x",
        type=float,
        default=None,
        help="Optional vertical reference line x-value for the live convergence plot.",
    )
    parser.add_argument(
        "--live-plot-reference-x-label",
        default=None,
        help="Legend label for --live-plot-reference-x.",
    )
    parser.add_argument(
        "--live-plot-reference-y-loss",
        type=float,
        default=None,
        help="Optional horizontal validation-loss reference line for the live convergence plot.",
    )
    parser.add_argument(
        "--live-plot-reference-y-label",
        default=None,
        help="Legend label for --live-plot-reference-y-loss.",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Write live CSV/HTML only; skip PNG rendering.",
    )
    return parser


def run_method_comparison(
    args: argparse.Namespace, *, repo_root: Path | None = None
) -> dict[str, object]:
    """Run or resume a live method-comparison campaign."""

    started_at = time.monotonic()
    resolved_repo_root = repo_root or default_repo_root()
    version = validate_version_name(args.version)
    run_id = validate_run_id(args.run_id)
    seeds = parse_seed_list(args.seeds)
    _validate_args(args=args, seeds=seeds)

    maven_bin = resolve_maven_bin(resolved_repo_root, args.maven_bin)
    validation_profile = resolve_calibration_validation_profile(
        version=version,
        validation_year=args.validation_year,
    )
    observations = build_validation_observations(
        validation_profile,
        validation_objective=args.validation_objective,
        validation_loss_error_std=args.validation_loss_error_std,
    )
    source_config_path = (
        resolved_repo_root / "input-data-versions" / version / "config.properties"
    )
    if not source_config_path.exists():
        raise RuntimeError(f"Missing source version config: {source_config_path}")
    source_parameters = parse_config_parameters(
        source_config_path.read_text(encoding="utf-8")
    )

    output_root = (
        resolve_repo_path(resolved_repo_root, args.output_root) / run_id / WORKFLOW_SLUG
    )
    output_root.mkdir(parents=True, exist_ok=True)
    metadata = _build_metadata(
        args=args,
        version=version,
        run_id=run_id,
        seeds=seeds,
        validation_profile=validation_profile,
        observations=observations,
        source_parameters=source_parameters,
        output_root=output_root,
    )
    write_json(output_root / METADATA_FILENAME, metadata)

    ensure_project_compiled(resolved_repo_root, maven_bin=maven_bin)
    was_data_root = resolve_was_data_root(
        repo_root=resolved_repo_root, explicit_root=None
    )

    method_workers = args.workers // 2
    smm_replicates = _build_smm_replicates(args)
    turbo_replicates = _build_turbo_replicates(args)
    turbo_dependencies: TurboDependencyBundle | None = None
    turbo_device: str | None = None
    failure_tolerance = (
        args.turbo_failure_tolerance
        if args.turbo_failure_tolerance is not None
        else default_failure_tolerance(
            dimensions=len(ORIGINAL_SMM_PARAMETER_SPECS), batch_size=1
        )
    )

    records: list[dict[str, object]] = []
    total_candidates = args.evaluations * args.replicates * 2
    wave = 0
    for evaluation in range(1, args.evaluations + 1):
        for replicate in range(args.replicates):
            wave += 1
            turbo_request, turbo_dependencies, turbo_device = _next_turbo_request(
                args=args,
                output_root=output_root,
                replicate_state=turbo_replicates[replicate],
                evaluation=evaluation,
                dependencies=turbo_dependencies,
                device=turbo_device,
            )
            smm_request = _next_smm_request(
                output_root=output_root,
                candidates=smm_replicates[replicate],
                replicate=replicate,
                evaluation=evaluation,
            )
            results = _evaluate_candidate_pair(
                repo_root=resolved_repo_root,
                version=version,
                requests=(turbo_request, smm_request),
                seeds=seeds,
                maven_bin=maven_bin,
                force_rerun=args.force_rerun,
                validation_profile=validation_profile,
                was_data_root=was_data_root,
                workers=method_workers,
                delete_csv_after_metrics=args.delete_csv_after_metrics,
                n_steps=args.n_steps,
                validation_window_start=args.validation_window_start,
                validation_window_end=args.validation_window_end,
                observations=observations,
                source_parameters=source_parameters,
            )
            for result in sorted(results, key=lambda item: item.request.method):
                records.append(_member_record(result))
                if result.request.method == METHOD_TURBO:
                    _update_turbo_state(
                        replicate_state=turbo_replicates[result.request.replicate],
                        result=result,
                        failure_tolerance=failure_tolerance,
                        args=args,
                    )
            live = _write_live_outputs(
                args=args,
                output_root=output_root,
                records=records,
                checkpoint_evaluations=(args.checkpoint_evaluations,),
                write_plot=not args.no_plot,
            )
            summary = _summary_payload(
                metadata=metadata,
                records=records,
                live=live,
                started_at=started_at,
                total_candidates=total_candidates,
            )
            write_json(output_root / SUMMARY_FILENAME, summary)
            _print_progress(
                output_root=output_root,
                wave=wave,
                evaluation=evaluation,
                replicate=replicate,
                records=records,
                total_candidates=total_candidates,
                started_at=started_at,
            )

    return _summary_payload(
        metadata=metadata,
        records=records,
        live=_write_live_outputs(
            args=args,
            output_root=output_root,
            records=records,
            checkpoint_evaluations=(args.checkpoint_evaluations,),
            write_plot=not args.no_plot,
        ),
        started_at=started_at,
        total_candidates=total_candidates,
    )


def _validate_args(*, args: argparse.Namespace, seeds: Sequence[int]) -> None:
    if args.workers <= 0:
        raise ValueError("workers must be positive")
    if args.workers < 2 * len(seeds):
        raise ValueError(
            "workers must be at least twice the seed count for paired SMM/TuRBO waves"
        )
    if args.replicates <= 0:
        raise ValueError("replicates must be positive")
    if args.evaluations <= 0:
        raise ValueError("evaluations must be positive")
    if args.checkpoint_evaluations <= 0:
        raise ValueError("checkpoint-evaluations must be positive")
    if args.turbo_initial_points <= 0:
        raise ValueError("turbo-initial-points must be positive")
    if args.turbo_length <= 0.0 or args.turbo_length_min <= 0.0:
        raise ValueError("TuRBO trust-region lengths must be positive")
    if args.turbo_length_max < args.turbo_length:
        raise ValueError(
            "turbo-length-max must be greater than or equal to turbo-length"
        )
    if args.turbo_success_tolerance <= 0:
        raise ValueError("turbo-success-tolerance must be positive")
    if args.turbo_failure_tolerance is not None and args.turbo_failure_tolerance <= 0:
        raise ValueError("turbo-failure-tolerance must be positive")
    if args.turbo_noise_variance_floor <= 0.0:
        raise ValueError("turbo-noise-variance-floor must be positive")
    if args.n_steps <= 0:
        raise ValueError("n-steps must be positive")
    if args.validation_window_start < 0:
        raise ValueError("validation-window-start must be non-negative")
    if args.validation_window_end <= args.validation_window_start:
        raise ValueError(
            "validation-window-end must be greater than validation-window-start"
        )
    if args.validation_window_end > args.n_steps:
        raise ValueError("validation-window-end must be less than or equal to n-steps")
    if args.live_plot_x_minor_step is not None and args.live_plot_x_minor_step <= 0.0:
        raise ValueError("live-plot-x-minor-step must be positive")
    if args.live_plot_y_minor_step is not None and args.live_plot_y_minor_step <= 0.0:
        raise ValueError("live-plot-y-minor-step must be positive")
    if args.live_plot_reference_x is not None and args.live_plot_reference_x < 0.0:
        raise ValueError("live-plot-reference-x must be non-negative")
    if (
        args.live_plot_reference_y_loss is not None
        and args.live_plot_reference_y_loss < 0.0
    ):
        raise ValueError("live-plot-reference-y-loss must be non-negative")


def _build_smm_replicates(args: argparse.Namespace) -> list[list[GridCandidate]]:
    replicates: list[list[GridCandidate]] = []
    base_candidates = build_grid_candidates(args.smm_grid_profile)
    if args.evaluations > len(base_candidates):
        raise ValueError("evaluations must not exceed the selected SMM grid size")
    for replicate in range(args.replicates):
        replicates.append(
            order_grid_candidates(
                base_candidates,
                grid_order=args.smm_grid_order,
                grid_rng_seed=args.smm_grid_rng_seed + replicate,
            )
        )
    return replicates


def _build_turbo_replicates(args: argparse.Namespace) -> list[TurboReplicateState]:
    replicates: list[TurboReplicateState] = []
    for replicate in range(args.replicates):
        initial = generate_initial_normalized_design(
            initial_points=args.turbo_initial_points,
            dimensions=len(ORIGINAL_SMM_PARAMETER_SPECS),
            rng_seed=args.turbo_rng_seed + replicate,
        )
        replicates.append(
            TurboReplicateState(
                replicate=replicate,
                initial_normalized=initial,
                turbo_state=TurboState(length=args.turbo_length),
            )
        )
    return replicates


def _next_turbo_request(
    *,
    args: argparse.Namespace,
    output_root: Path,
    replicate_state: TurboReplicateState,
    evaluation: int,
    dependencies: TurboDependencyBundle | None,
    device: str | None,
) -> tuple[CandidateRequest, TurboDependencyBundle | None, str | None]:
    cached_request = _load_candidate_request(
        output_root=output_root,
        method=METHOD_TURBO,
        method_slug=METHOD_TURBO_SLUG,
        replicate=replicate_state.replicate,
        evaluation=evaluation,
    )
    if cached_request is not None:
        return cached_request, dependencies, device

    if evaluation <= len(replicate_state.initial_normalized):
        normalized = np.asarray(
            replicate_state.initial_normalized[evaluation - 1], dtype=float
        )
    else:
        if dependencies is None:
            dependencies = load_turbo_dependencies()
            device = select_torch_device(dependencies.torch)
        assert device is not None
        normalized = np.asarray(
            propose_turbo_candidates(
                train_x=np.asarray(replicate_state.train_x_rows, dtype=float),
                train_y=np.asarray(replicate_state.train_y_rows, dtype=float),
                train_yvar=np.asarray(replicate_state.train_yvar_rows, dtype=float),
                state=replicate_state.turbo_state,
                batch_size=1,
                rng_seed=args.turbo_rng_seed
                + 10_000 * (replicate_state.replicate + 1)
                + evaluation,
                dependencies=dependencies,
                device=device,
            )[0],
            dtype=float,
        )
    parameters = normalized_points_to_parameter_dicts(
        np.asarray([normalized], dtype=float),
        specs=ORIGINAL_SMM_PARAMETER_SPECS,
    )[0]
    request = CandidateRequest(
        method=METHOD_TURBO,
        method_slug=METHOD_TURBO_SLUG,
        replicate=replicate_state.replicate,
        evaluation=evaluation,
        member_id=replicate_state.replicate * 1000 + evaluation,
        parameters=parameters,
        output_root=output_root
        / "candidate-runs"
        / METHOD_TURBO_SLUG
        / f"replicate-{replicate_state.replicate + 1:02d}",
        normalized_point=normalized,
    )
    _write_candidate_request(output_root=output_root, request=request)
    return request, dependencies, device


def _next_smm_request(
    *,
    output_root: Path,
    candidates: Sequence[GridCandidate],
    replicate: int,
    evaluation: int,
) -> CandidateRequest:
    cached_request = _load_candidate_request(
        output_root=output_root,
        method=METHOD_SMM,
        method_slug=METHOD_SMM_SLUG,
        replicate=replicate,
        evaluation=evaluation,
    )
    if cached_request is not None:
        return cached_request

    candidate = candidates[evaluation - 1]
    request = CandidateRequest(
        method=METHOD_SMM,
        method_slug=METHOD_SMM_SLUG,
        replicate=replicate,
        evaluation=evaluation,
        member_id=replicate * 1000 + evaluation,
        parameters=dict(candidate.parameters),
        output_root=output_root
        / "candidate-runs"
        / METHOD_SMM_SLUG
        / f"replicate-{replicate + 1:02d}",
        original_grid_member_id=candidate.member_id,
    )
    _write_candidate_request(output_root=output_root, request=request)
    return request


def _candidate_request_path(
    *, output_root: Path, method_slug: str, replicate: int, evaluation: int
) -> Path:
    return (
        output_root
        / "candidate-requests"
        / method_slug
        / f"replicate-{replicate + 1:02d}"
        / f"eval-{evaluation:04d}.json"
    )


def _load_candidate_request(
    *,
    output_root: Path,
    method: str,
    method_slug: str,
    replicate: int,
    evaluation: int,
) -> CandidateRequest | None:
    path = _candidate_request_path(
        output_root=output_root,
        method_slug=method_slug,
        replicate=replicate,
        evaluation=evaluation,
    )
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    if int(raw["replicate"]) != replicate + 1 or int(raw["evaluation"]) != evaluation:
        raise RuntimeError(f"Candidate request cache metadata mismatch: {path}")
    if str(raw["methodSlug"]) != method_slug:
        raise RuntimeError(f"Candidate request cache method mismatch: {path}")
    normalized_raw = raw.get("normalizedPoint")
    normalized = (
        np.asarray(normalized_raw, dtype=float) if normalized_raw is not None else None
    )
    original_grid_member_id = raw.get("originalGridMemberId")
    return CandidateRequest(
        method=method,
        method_slug=method_slug,
        replicate=replicate,
        evaluation=evaluation,
        member_id=int(raw["memberId"]),
        parameters={str(key): float(value) for key, value in raw["parameters"].items()},
        output_root=output_root
        / "candidate-runs"
        / method_slug
        / f"replicate-{replicate + 1:02d}",
        normalized_point=normalized,
        original_grid_member_id=(
            int(original_grid_member_id)
            if original_grid_member_id not in {None, ""}
            else None
        ),
    )


def _write_candidate_request(*, output_root: Path, request: CandidateRequest) -> None:
    write_json(
        _candidate_request_path(
            output_root=output_root,
            method_slug=request.method_slug,
            replicate=request.replicate,
            evaluation=request.evaluation,
        ),
        {
            "method": request.method,
            "methodSlug": request.method_slug,
            "replicate": request.replicate + 1,
            "evaluation": request.evaluation,
            "memberId": request.member_id,
            "parameters": request.parameters,
            "normalizedPoint": (
                request.normalized_point.tolist()
                if request.normalized_point is not None
                else None
            ),
            "originalGridMemberId": request.original_grid_member_id,
        },
    )


def _evaluate_candidate_pair(
    *,
    repo_root: Path,
    version: str,
    requests: Sequence[CandidateRequest],
    seeds: Sequence[int],
    maven_bin: str,
    force_rerun: bool,
    validation_profile: object,
    was_data_root: Path,
    workers: int,
    delete_csv_after_metrics: bool,
    n_steps: int,
    validation_window_start: int,
    validation_window_end: int,
    observations: Sequence[object],
    source_parameters: Mapping[str, float],
) -> list[CandidateResult]:
    with ThreadPoolExecutor(
        max_workers=len(requests), thread_name_prefix="method-comparison"
    ) as executor:
        futures = [
            executor.submit(
                _evaluate_candidate,
                repo_root=repo_root,
                version=version,
                request=request,
                seeds=seeds,
                maven_bin=maven_bin,
                force_rerun=force_rerun,
                validation_profile=validation_profile,
                was_data_root=was_data_root,
                workers=workers,
                delete_csv_after_metrics=delete_csv_after_metrics,
                n_steps=n_steps,
                validation_window_start=validation_window_start,
                validation_window_end=validation_window_end,
                observations=observations,
                source_parameters=source_parameters,
            )
            for request in requests
        ]
        return [future.result() for future in as_completed(futures)]


def _evaluate_candidate(
    *,
    repo_root: Path,
    version: str,
    request: CandidateRequest,
    seeds: Sequence[int],
    maven_bin: str,
    force_rerun: bool,
    validation_profile: object,
    was_data_root: Path,
    workers: int,
    delete_csv_after_metrics: bool,
    n_steps: int,
    validation_window_start: int,
    validation_window_end: int,
    observations: Sequence[object],
    source_parameters: Mapping[str, float],
) -> CandidateResult:
    seed_run_results = execute_seed_requests_for_members(
        repo_root=repo_root,
        version=version,
        iteration=request.evaluation,
        member_parameters=[request.parameters],
        seeds=seeds,
        output_root=request.output_root,
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
    grouped = group_seed_run_results_by_member(seed_run_results)
    member = build_member_validation_result(
        version=f"{version}-{request.method_slug}-r{request.replicate + 1}",
        iteration=request.evaluation,
        member_id=request.member_id,
        parameters=request.parameters,
        seed_results=grouped[0],
        seeds=seeds,
        validation_profile=validation_profile,
        observations=observations,
        source_parameters=source_parameters,
        specs=ORIGINAL_SMM_PARAMETER_SPECS,
        validation_window_start=validation_window_start,
        validation_window_end=validation_window_end,
    )
    cached = sum(
        1 for result in seed_run_results if bool(getattr(result, "cached", False))
    )
    return CandidateResult(
        request=request,
        member=member,
        seed_run_count=len(seed_run_results),
        cached_seed_run_count=cached,
    )


def _update_turbo_state(
    *,
    replicate_state: TurboReplicateState,
    result: CandidateResult,
    failure_tolerance: int,
    args: argparse.Namespace,
) -> None:
    assert result.request.normalized_point is not None
    score = -overall_composite_loss(result.member)
    replicate_state.train_x_rows.append(
        np.asarray(result.request.normalized_point, dtype=float)
    )
    replicate_state.train_y_rows.append([score])
    replicate_state.train_yvar_rows.append([args.turbo_noise_variance_floor])
    replicate_state.turbo_state = update_turbo_state(
        replicate_state.turbo_state,
        batch_best_score=score,
        batch_evaluation_count=1,
        success_tolerance=args.turbo_success_tolerance,
        failure_tolerance=failure_tolerance,
        length_min=args.turbo_length_min,
        length_max=args.turbo_length_max,
    )


def _member_record(result: CandidateResult) -> dict[str, object]:
    counts = required_metric_status_counts(result.member.summary)
    record: dict[str, object] = {
        "method": METHOD_DISPLAY_LABELS[result.request.method],
        "methodSlug": result.request.method_slug,
        "replicate": result.request.replicate + 1,
        "evaluation": result.request.evaluation,
        "iteration": result.member.iteration,
        "memberId": result.member.member_id,
        "originalGridMemberId": (
            result.request.original_grid_member_id
            if result.request.original_grid_member_id is not None
            else ""
        ),
        "overallCompositeLoss": overall_composite_loss(result.member),
        "rankingLoss": result.member.ranking_loss,
        "rankingObjective": result.member.ranking_objective,
        "passCount": counts.get("pass", 0),
        "warnCount": counts.get("warn", 0),
        "failCount": counts.get("fail", 0),
        "normalizedSourceMovement": result.member.normalized_source_movement,
        "seedRunCount": result.seed_run_count,
        "cachedSeedRunCount": result.cached_seed_run_count,
        "newSeedRunCount": result.seed_run_count - result.cached_seed_run_count,
    }
    record.update(
        {name: result.member.parameters[name] for name in OUTPUT_ESMDA_PARAMETER_NAMES}
    )
    return record


def _write_live_outputs(
    *,
    args: argparse.Namespace,
    output_root: Path,
    records: Sequence[Mapping[str, object]],
    checkpoint_evaluations: Sequence[int],
    write_plot: bool,
) -> dict[str, object]:
    write_csv(output_root / EVALUATED_MEMBERS_FILENAME, records)
    return write_live_convergence_artifacts(
        records=records,
        output_dir=output_root,
        checkpoint_evaluations=checkpoint_evaluations,
        write_plot=write_plot,
        x_minor_step=args.live_plot_x_minor_step,
        y_minor_step=args.live_plot_y_minor_step,
        reference_x=args.live_plot_reference_x,
        reference_x_label=args.live_plot_reference_x_label,
        reference_y_loss=args.live_plot_reference_y_loss,
        reference_y_label=args.live_plot_reference_y_label,
    )


def _summary_payload(
    *,
    metadata: Mapping[str, object],
    records: Sequence[Mapping[str, object]],
    live: Mapping[str, object],
    started_at: float,
    total_candidates: int,
) -> dict[str, object]:
    return {
        **metadata,
        "evaluatedCandidates": len(records),
        "totalPlannedCandidates": total_candidates,
        "completedFraction": (
            len(records) / float(total_candidates) if total_candidates else 0.0
        ),
        "liveOutputDir": live["outputDir"],
        "liveSummaryRows": live["summaryRows"],
        "elapsed": format_duration(time.monotonic() - started_at),
    }


def _build_metadata(
    *,
    args: argparse.Namespace,
    version: str,
    run_id: str,
    seeds: Sequence[int],
    validation_profile: object,
    observations: Sequence[object],
    source_parameters: Mapping[str, float],
    output_root: Path,
) -> dict[str, object]:
    return {
        "workflow": WORKFLOW_NAME,
        "sourceVersion": version,
        "runId": run_id,
        "methods": [METHOD_TURBO, METHOD_SMM],
        "replicates": args.replicates,
        "evaluations": args.evaluations,
        "checkpointEvaluations": args.checkpoint_evaluations,
        "validationProfile": summarize_validation_profile(validation_profile),
        "validationObjective": args.validation_objective,
        "validationLossErrorStd": args.validation_loss_error_std,
        "seeds": list(seeds),
        "workers": args.workers,
        "pairedWaveWorkersPerMethod": args.workers // 2,
        "nSteps": args.n_steps,
        "validationWindow": {
            "startIndex": args.validation_window_start,
            "endIndex": args.validation_window_end,
        },
        "livePlot": {
            "xMinorStep": args.live_plot_x_minor_step,
            "yMinorStep": args.live_plot_y_minor_step,
            "referenceX": args.live_plot_reference_x,
            "referenceXLabel": args.live_plot_reference_x_label,
            "referenceYLoss": args.live_plot_reference_y_loss,
            "referenceYLabel": args.live_plot_reference_y_label,
        },
        "sourceParameters": dict(source_parameters),
        "smm": {
            "gridProfile": args.smm_grid_profile,
            "gridOrder": args.smm_grid_order,
            "baseGridRngSeed": args.smm_grid_rng_seed,
        },
        "turbo": {
            "parameterDomain": "original-smm",
            "baseRngSeed": args.turbo_rng_seed,
            "initialPoints": args.turbo_initial_points,
            "length": args.turbo_length,
            "lengthMin": args.turbo_length_min,
            "lengthMax": args.turbo_length_max,
            "successTolerance": args.turbo_success_tolerance,
            "failureTolerance": args.turbo_failure_tolerance,
            "noiseVarianceFloor": args.turbo_noise_variance_floor,
            "sourcePointSeededIntoTraining": False,
        },
        "parameterSpecs": [asdict(spec) for spec in ORIGINAL_SMM_PARAMETER_SPECS],
        "observations": [asdict(observation) for observation in observations],
        "restartable": True,
        "restartSemantics": (
            "The comparison runner deterministically replays method/replicate/evaluation requests. "
            "Per-seed metric JSON caches in candidate-runs are reused unless --force-rerun is supplied."
        ),
        "outputRoot": str(output_root),
    }


def _print_progress(
    *,
    output_root: Path,
    wave: int,
    evaluation: int,
    replicate: int,
    records: Sequence[Mapping[str, object]],
    total_candidates: int,
    started_at: float,
) -> None:
    latest_by_method: dict[str, Mapping[str, object]] = {}
    for record in records[-2:]:
        latest_by_method[str(record["method"])] = record
    details = []
    for method in (METHOD_TURBO, METHOD_SMM):
        row = latest_by_method.get(method)
        if row is None:
            continue
        details.append(
            f"{method}=eval{row['evaluation']} loss={float(row['overallCompositeLoss']):.6f}"
        )
    print(
        "[comparison] "
        f"wave={wave} replicate={replicate + 1} evaluation={evaluation} "
        f"completedCandidates={len(records)}/{total_candidates} elapsed={format_duration(time.monotonic() - started_at)} "
        + " ".join(details)
        + f" live={output_root / 'live.html'}",
        flush=True,
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    summary = run_method_comparison(args)
    print(
        "[comparison] complete "
        f"evaluatedCandidates={summary['evaluatedCandidates']} "
        f"live={Path(summary['liveOutputDir']) / 'live.html'}"
    )


if __name__ == "__main__":
    main()
