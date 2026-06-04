#!/usr/bin/env python3
"""Run restartable grid SMM for jointly output-calibrated parameters.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import itertools
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from scripts.python.calibration.output.candidate_runs import (
    DEFAULT_OUTPUT_ROOT,
    execute_seed_requests_for_members,
    parse_config_parameters,
    parse_seed_list,
    resolve_repo_path,
    validate_version_name,
    write_json,
)
from scripts.python.calibration.output.esmda import (
    BTL_CHOICE_INTENSITY,
    BTL_PROBABILITY_MULTIPLIER,
    MARKET_AVERAGE_PRICE_DECAY,
    OUTPUT_ESMDA_PARAMETER_NAMES,
    PSYCHOLOGICAL_COST_OF_RENTING,
    SENSITIVITY_RENT_OR_PURCHASE,
    TRANSFORM_BOUNDED_LOGIT,
    TRANSFORM_LOG10,
    ParameterSpec,
)
from scripts.python.calibration.output.validation_bridge import (
    DEFAULT_VALIDATION_LOSS_ERROR_STD,
    FAMILY_AWARE_METRIC_LOSS_OBJECTIVE,
    TARGET_NORMALIZED_ADDITIVE_OBJECTIVE,
    build_member_validation_result,
    build_validation_observations,
    group_seed_run_results_by_member,
    overall_composite_loss,
    resolve_calibration_validation_profile,
    summarize_validation_profile,
)
from scripts.python.calibration.output.workflow_helpers import (
    format_duration,
    member_summary_payload,
    write_csv,
    write_member_results_csv,
)
from scripts.python.helpers.common.abm_policy_sweep import ensure_project_compiled, resolve_maven_bin
from scripts.python.helpers.common.paths import repo_root as default_repo_root
from scripts.python.validation.model.runner import resolve_was_data_root
from scripts.python.validation.model.schema import VALIDATION_WINDOW_END, VALIDATION_WINDOW_START

WORKFLOW_NAME = "grid-smm"
WORKFLOW_SLUG = "grid-smm"
GRID_PROFILE_CARRO_THREE_LEVEL = "carro-three-level"
DEFAULT_SEEDS = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
DEFAULT_WORKERS = 20
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
METADATA_FILENAME = "OutputGridSmmMetadata.json"
SUMMARY_FILENAME = "OutputGridSmmCalibrationSummary.json"
CANDIDATE_GRID_FILENAME = "GridCandidates.csv"
EVALUATED_MEMBERS_FILENAME = "SmmEvaluatedMembers.csv"
EVIDENCE_DIR_TEMPLATE = "input-data-versions/calibration-evidence/output-grid-smm-{run_id}"
LOSS_HANDLING_NOTE = (
    "Grid SMM evaluates a deterministic three-level sub-grid of the original Carro et al. "
    "five-parameter grid against the same family-aware validation loss used by the v0o7 TuRBO campaign. "
    "No output version is promoted by this workflow; the evidence is method-comparison only."
)

CARRO_THREE_LEVEL_VALUES: dict[str, tuple[float, float, float]] = {
    PSYCHOLOGICAL_COST_OF_RENTING: (0.3, 0.4, 0.5),
    SENSITIVITY_RENT_OR_PURCHASE: (0.0003162, 0.001, 0.003162),
    BTL_PROBABILITY_MULTIPLIER: (1.72, 1.76, 1.8),
    BTL_CHOICE_INTENSITY: (31.62, 100.0, 316.2),
    MARKET_AVERAGE_PRICE_DECAY: (0.3, 0.5, 0.7),
}

SMM_PARAMETER_SPECS = (
    ParameterSpec(
        name=PSYCHOLOGICAL_COST_OF_RENTING,
        lower=0.0,
        upper=0.5,
        prior_lower=0.3,
        prior_upper=0.5,
        transform=TRANSFORM_BOUNDED_LOGIT,
    ),
    ParameterSpec(
        name=SENSITIVITY_RENT_OR_PURCHASE,
        lower=0.00001,
        upper=0.1,
        prior_lower=0.0003162,
        prior_upper=0.003162,
        transform=TRANSFORM_LOG10,
    ),
    ParameterSpec(
        name=BTL_PROBABILITY_MULTIPLIER,
        lower=1.6,
        upper=1.8,
        prior_lower=1.72,
        prior_upper=1.8,
        transform=TRANSFORM_LOG10,
    ),
    ParameterSpec(
        name=BTL_CHOICE_INTENSITY,
        lower=0.1,
        upper=1000.0,
        prior_lower=31.62,
        prior_upper=316.2,
        transform=TRANSFORM_LOG10,
    ),
    ParameterSpec(
        name=MARKET_AVERAGE_PRICE_DECAY,
        lower=0.1,
        upper=0.9,
        prior_lower=0.3,
        prior_upper=0.7,
        transform=TRANSFORM_BOUNDED_LOGIT,
    ),
)


@dataclass(frozen=True)
class GridCandidate:
    """One deterministic SMM-grid parameter candidate."""

    member_id: int
    level_indices: tuple[int, ...]
    center_distance: int
    parameters: dict[str, float]


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""

    parser = argparse.ArgumentParser(
        description="Restartable grid SMM comparison for output-calibrated housing-model parameters.",
    )
    parser.add_argument("--version", required=True, help="Source input-data version, for example v0")
    parser.add_argument("--run-id", required=True, help="Stable run id used for cache and evidence paths")
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
        help="Validation objective used for member ranking.",
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
    parser.add_argument(
        "--grid-profile",
        choices=(GRID_PROFILE_CARRO_THREE_LEVEL,),
        default=GRID_PROFILE_CARRO_THREE_LEVEL,
        help="Deterministic grid profile to evaluate.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=None,
        help="Optional prefix of the center-out grid to evaluate; useful for pilots and cache warmups.",
    )
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
        help="Retained evidence directory. Defaults to input-data-versions/calibration-evidence/...<run-id>.",
    )
    parser.add_argument("--maven-bin", default=None, help="Maven executable override (default: repo-local ./mvnw).")
    parser.add_argument("--force-rerun", action="store_true", help="Ignore cached per-seed metric JSON.")
    parser.add_argument(
        "--delete-csv-after-metrics",
        action="store_true",
        help="After each seed's metrics are safely cached, delete generated run CSV outputs from that seed directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write metadata and deterministic grid without running Maven.",
    )
    return parser


def build_carro_three_level_candidates() -> list[GridCandidate]:
    """Return the 3^5 Carro-centered grid in deterministic center-out order."""

    parameter_names = tuple(OUTPUT_ESMDA_PARAMETER_NAMES)
    raw_index_tuples = itertools.product(range(3), repeat=len(parameter_names))
    ordered_index_tuples = sorted(
        raw_index_tuples,
        key=lambda indices: (
            sum(abs(index - 1) for index in indices),
            tuple(abs(index - 1) for index in indices),
            indices,
        ),
    )
    candidates: list[GridCandidate] = []
    for member_id, indices in enumerate(ordered_index_tuples):
        parameters = {
            name: CARRO_THREE_LEVEL_VALUES[name][index]
            for name, index in zip(parameter_names, indices, strict=True)
        }
        candidates.append(
            GridCandidate(
                member_id=member_id,
                level_indices=tuple(indices),
                center_distance=sum(abs(index - 1) for index in indices),
                parameters=parameters,
            )
        )
    return candidates


def run_grid_smm(args: argparse.Namespace, *, repo_root: Path | None = None) -> dict[str, object]:
    """Run or dry-run the restartable grid SMM workflow."""

    started_at = time.monotonic()
    resolved_repo_root = repo_root or default_repo_root()
    maven_bin = resolve_maven_bin(resolved_repo_root, args.maven_bin)
    version = validate_version_name(args.version)
    run_id = validate_run_id(args.run_id)
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

    candidates = build_grid_candidates(args.grid_profile)
    if args.max_candidates is not None:
        candidates = candidates[: args.max_candidates]
    parameter_sets = [candidate.parameters for candidate in candidates]

    output_root = resolve_repo_path(resolved_repo_root, args.output_root) / run_id / WORKFLOW_SLUG
    evidence_dir = (
        resolve_repo_path(resolved_repo_root, args.evidence_dir)
        if args.evidence_dir
        else resolved_repo_root / EVIDENCE_DIR_TEMPLATE.format(run_id=run_id)
    )
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "reproduce-command.sh").write_text(build_reproduce_command(args), encoding="utf-8")
    write_grid_candidates_csv(output_root / CANDIDATE_GRID_FILENAME, candidates)

    metadata = _build_metadata(
        args=args,
        version=version,
        run_id=run_id,
        seeds=seeds,
        validation_profile=validation_profile,
        observations=observations,
        source_parameters=source_parameters,
        candidates=candidates,
        output_root=output_root,
        evidence_dir=evidence_dir,
    )
    _write_summary_artifacts(output_root, metadata, is_metadata=True)

    if args.dry_run:
        summary = {
            **metadata,
            "dryRun": True,
            "evaluatedCandidateCount": 0,
            "seedRunCount": 0,
            "cachedSeedRunCount": 0,
            "newSeedRunCount": 0,
            "createdOutputVersion": False,
            "elapsed": format_duration(time.monotonic() - started_at),
        }
        _write_summary_artifacts(output_root, summary)
        return summary

    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "reproduce-command.sh").write_text(build_reproduce_command(args), encoding="utf-8")
    write_grid_candidates_csv(evidence_dir / CANDIDATE_GRID_FILENAME, candidates)
    _write_summary_artifacts(evidence_dir, metadata, is_metadata=True)

    ensure_project_compiled(resolved_repo_root, maven_bin=maven_bin)
    was_data_root = resolve_was_data_root(repo_root=resolved_repo_root, explicit_root=None)

    seed_run_results = execute_seed_requests_for_members(
        repo_root=resolved_repo_root,
        version=version,
        iteration=0,
        member_parameters=parameter_sets,
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
    member_results = [
        build_member_validation_result(
            version=version,
            iteration=0,
            member_id=candidate.member_id,
            parameters=candidate.parameters,
            seed_results=grouped_seed_results[candidate.member_id],
            seeds=seeds,
            validation_profile=validation_profile,
            observations=observations,
            source_parameters=source_parameters,
            specs=SMM_PARAMETER_SPECS,
            validation_window_start=args.validation_window_start,
            validation_window_end=args.validation_window_end,
        )
        for candidate in candidates
    ]
    baseline_member = member_results[0]
    best_member = min(member_results, key=overall_composite_loss)
    cached_seed_run_count = sum(1 for result in seed_run_results if bool(getattr(result, "cached", False)))
    summary = {
        **metadata,
        "dryRun": False,
        "evaluatedCandidateCount": len(member_results),
        "seedRunCount": len(seed_run_results),
        "cachedSeedRunCount": cached_seed_run_count,
        "newSeedRunCount": len(seed_run_results) - cached_seed_run_count,
        "createdOutputVersion": False,
        "baseline": member_summary_payload(
            baseline_member,
            baseline_member.parameters,
            baseline_member=baseline_member,
        ),
        "best": member_summary_payload(
            best_member,
            best_member.parameters,
            baseline_member=baseline_member,
        ),
        "elapsed": format_duration(time.monotonic() - started_at),
        "finalValidationNote": (
            "Grid SMM evidence completed without creating an output version. "
            "Rerunning the same command reuses completed per-seed metric caches unless --force-rerun is supplied."
        ),
    }
    _write_run_outputs(output_root, metadata, summary, member_results)
    _write_run_outputs(evidence_dir, metadata, summary, member_results)
    return summary


def build_grid_candidates(grid_profile: str) -> list[GridCandidate]:
    """Build candidates for a supported grid profile."""

    if grid_profile == GRID_PROFILE_CARRO_THREE_LEVEL:
        return build_carro_three_level_candidates()
    raise ValueError(f"Unsupported grid profile: {grid_profile}")


def validate_run_id(run_id: str) -> str:
    """Validate a safe run id for output/cache paths."""

    if RUN_ID_PATTERN.fullmatch(run_id) is None or run_id in {".", ".."}:
        raise ValueError(f"Invalid run id: {run_id!r}")
    return run_id


def write_grid_candidates_csv(path: Path, candidates: Sequence[GridCandidate]) -> None:
    """Write grid candidates with ordering metadata."""

    rows: list[dict[str, object]] = []
    for candidate in candidates:
        row: dict[str, object] = {
            "memberId": candidate.member_id,
            "centerDistance": candidate.center_distance,
        }
        for name, index in zip(OUTPUT_ESMDA_PARAMETER_NAMES, candidate.level_indices, strict=True):
            row[f"{name}_levelIndex"] = index
        row.update(candidate.parameters)
        rows.append(row)
    write_csv(path, rows)


def build_reproduce_command(args: argparse.Namespace) -> str:
    """Build a shell command that reproduces the requested workflow."""

    command = [
        "python3 -m scripts.python.calibration.output.grid_smm",
        f"--version {args.version}",
        f"--run-id {args.run_id}",
        f"--validation-year {args.validation_year}",
        f"--validation-objective {args.validation_objective}",
        f"--validation-loss-error-std {args.validation_loss_error_std}",
        f"--seeds {args.seeds}",
        f"--workers {args.workers}",
        f"--grid-profile {args.grid_profile}",
        f"--max-candidates {args.max_candidates}" if args.max_candidates is not None else None,
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
    if args.dry_run:
        command.append("--dry-run")
    return (" " + "\\" + "\n  ").join(item for item in command if item is not None) + "\n"


def _validate_execution_args(*, args: argparse.Namespace, seeds: Sequence[int]) -> None:
    if args.workers <= 0:
        raise ValueError("workers must be positive")
    if args.workers < len(seeds):
        raise ValueError("workers must be at least the number of seeds")
    if args.validation_loss_error_std <= 0.0:
        raise ValueError("validation-loss-error-std must be positive")
    if args.max_candidates is not None and args.max_candidates <= 0:
        raise ValueError("max-candidates must be positive")
    if args.max_candidates is not None and args.max_candidates > len(build_grid_candidates(args.grid_profile)):
        raise ValueError("max-candidates must not exceed the grid candidate count")
    if args.validation_window_start < 0:
        raise ValueError("validation-window-start must be non-negative")
    if args.validation_window_end <= args.validation_window_start:
        raise ValueError("validation-window-end must be greater than validation-window-start")
    if args.n_steps is not None:
        if args.n_steps <= 0:
            raise ValueError("n-steps must be positive")
        if args.validation_window_end > args.n_steps:
            raise ValueError("validation-window-end must be less than or equal to n-steps")


def _build_metadata(
    *,
    args: argparse.Namespace,
    version: str,
    run_id: str,
    seeds: Sequence[int],
    validation_profile: object,
    observations: Sequence[object],
    source_parameters: Mapping[str, float],
    candidates: Sequence[GridCandidate],
    output_root: Path,
    evidence_dir: Path,
) -> dict[str, object]:
    return {
        "workflow": WORKFLOW_NAME,
        "sourceVersion": version,
        "runId": run_id,
        "parameters": list(OUTPUT_ESMDA_PARAMETER_NAMES),
        "sourceParameters": dict(source_parameters),
        "validationProfile": summarize_validation_profile(validation_profile),
        "validationLossHandling": LOSS_HANDLING_NOTE,
        "validationObjective": args.validation_objective,
        "rankingObjective": args.validation_objective,
        "validationLossErrorStd": args.validation_loss_error_std,
        "gridProfile": args.grid_profile,
        "gridValues": {key: list(values) for key, values in CARRO_THREE_LEVEL_VALUES.items()},
        "gridOrdering": "center-out by Manhattan distance from the original Carro selected parameter vector",
        "candidateCount": len(candidates),
        "maxCandidates": args.max_candidates,
        "restartable": True,
        "restartSemantics": (
            "Per-seed metric JSON files are keyed by run id, member id, seed, config hash, validation profile, "
            "and metric ids. Rerun the same command without --force-rerun to skip completed seed runs."
        ),
        "seeds": list(seeds),
        "workers": args.workers,
        "nSteps": args.n_steps,
        "validationWindow": {
            "startIndex": args.validation_window_start,
            "endIndex": args.validation_window_end,
        },
        "deleteCsvAfterMetrics": args.delete_csv_after_metrics,
        "forceRerun": args.force_rerun,
        "parameterSpecs": [asdict(spec) for spec in SMM_PARAMETER_SPECS],
        "observations": [asdict(observation) for observation in observations],
        "outputRoot": str(output_root),
        "evidenceDir": str(evidence_dir),
    }


def _write_run_outputs(
    path: Path,
    metadata: Mapping[str, object],
    summary: Mapping[str, object],
    member_results: Sequence[object],
) -> None:
    _write_summary_artifacts(path, metadata, is_metadata=True)
    _write_summary_artifacts(path, summary)
    write_member_results_csv(path / EVALUATED_MEMBERS_FILENAME, member_results)


def _write_summary_artifacts(path: Path, payload: Mapping[str, object], *, is_metadata: bool = False) -> None:
    filename = METADATA_FILENAME if is_metadata else SUMMARY_FILENAME
    write_json(path / filename, payload)


def main() -> None:
    args = build_arg_parser().parse_args()
    summary = run_grid_smm(args)
    print(
        "[grid-smm] "
        f"runId={summary['runId']} dryRun={str(summary['dryRun']).lower()} "
        f"evaluatedCandidates={summary['evaluatedCandidateCount']} "
        f"cachedSeedRuns={summary['cachedSeedRunCount']} "
        f"newSeedRuns={summary['newSeedRunCount']}"
    )


if __name__ == "__main__":
    main()
