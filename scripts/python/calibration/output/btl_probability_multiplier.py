#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibrate BTL_PROBABILITY_MULTIPLIER against model output prevalence.

The workflow runs snapshot-local model configurations, so it does not mutate
``src/main/resources``. It copies the requested input-data version only after a
selected multiplier has been found, then updates ``BTL_PROBABILITY_MULTIPLIER``
and its adjacent provenance note in the copied ``config.properties``.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from scripts.python.helpers.common.abm_policy_sweep import (
    build_snapshot_local_config_text,
    ensure_project_compiled,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import repo_root as default_repo_root

BTL_PROBABILITY_MULTIPLIER = "BTL_PROBABILITY_MULTIPLIER"
DEFAULT_TARGET = 0.0515255103048705
DEFAULT_SEEDS = (1, 2, 3, 4)
DEFAULT_WORKERS = 20
DEFAULT_PRECISION = 0.005
DEFAULT_COARSE_MIN = 0.05
DEFAULT_COARSE_MAX = 2.0
DEFAULT_COARSE_STEP = 0.05
DEFAULT_FINE_RADIUS = 0.15
DEFAULT_N_STEPS = 2000
DEFAULT_WINDOW_START = 200
DEFAULT_TARGET_TOLERANCE = 1.0e-12
DEFAULT_OUTPUT_ROOT = "tmp/output-calibration"
EVIDENCE_DIR_TEMPLATE = "input-data-versions/calibration-evidence/output-btl-probability-multiplier-{output_version}"
VERSION_NAME_PATTERN = re.compile(r"^v\d+(?:\.\d+)*o?$", re.IGNORECASE)

REQUIRED_RUN_OVERRIDES = {
    "N_STEPS": str(DEFAULT_N_STEPS),
    "recordRentalIncome": "true",
    "recordCoreIndicators": "true",
}


@dataclass(frozen=True)
class SeedRunResult:
    """Extracted metrics for one multiplier/seed model run."""

    stage: str
    multiplier: float
    seed: int
    output_dir: str
    config_path: str
    config_hash: str
    cached: bool
    rental_income_positive_share: float
    active_btl_share: float
    latent_btl_share: float
    btl_stock_fraction: float


@dataclass(frozen=True)
class CandidateSummary:
    """Aggregated metrics for one multiplier candidate."""

    stage: str
    multiplier: float
    target: float
    target_gap: float
    rental_income_positive_share_mean: float
    rental_income_positive_share_stdev: float
    active_btl_share_mean: float
    latent_btl_share_mean: float
    btl_stock_fraction_mean: float
    seed_count: int
    seeds: tuple[int, ...]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calibrate BTL_PROBABILITY_MULTIPLIER from model output prevalence.",
    )
    parser.add_argument(
        "--version",
        required=True,
        help="Input-data version folder to use as the source snapshot, for example v4.14.",
    )
    parser.add_argument(
        "--output-version",
        required=True,
        help="Input-data version folder to create with the selected multiplier, for example v4.14o.",
    )
    parser.add_argument(
        "--seeds",
        default=",".join(str(seed) for seed in DEFAULT_SEEDS),
        help="Comma-separated seed block used for every candidate (default: 1,2,3,4).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Maximum parallel model runs (default: {DEFAULT_WORKERS}).",
    )
    parser.add_argument(
        "--precision",
        type=float,
        default=DEFAULT_PRECISION,
        help=f"Fine-grid spacing and final snapping precision (default: {DEFAULT_PRECISION}).",
    )
    parser.add_argument("--coarse-min", type=float, default=DEFAULT_COARSE_MIN)
    parser.add_argument("--coarse-max", type=float, default=DEFAULT_COARSE_MAX)
    parser.add_argument("--coarse-step", type=float, default=DEFAULT_COARSE_STEP)
    parser.add_argument("--fine-radius", type=float, default=DEFAULT_FINE_RADIUS)
    parser.add_argument(
        "--target",
        type=float,
        default=DEFAULT_TARGET,
        help=f"Survey-side weighted R8 prevalence target (default: {DEFAULT_TARGET}).",
    )
    parser.add_argument(
        "--output-root",
        default=DEFAULT_OUTPUT_ROOT,
        help=f"Transient run output root (default: {DEFAULT_OUTPUT_ROOT}).",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="Retained evidence directory. Defaults to input-data-versions/calibration-evidence/...<output-version>.",
    )
    parser.add_argument("--maven-bin", default="mvn", help="Maven executable (default: mvn).")
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Ignore cached per-run metric files and rerun model outputs.",
    )
    parser.add_argument(
        "--overwrite-version",
        action="store_true",
        help="Replace an existing output-version folder.",
    )
    return parser


def parse_seed_list(raw: str) -> list[int]:
    seeds = [int(token.strip()) for token in raw.split(",") if token.strip()]
    if not seeds:
        raise ValueError("At least one seed is required.")
    if any(seed <= 0 for seed in seeds):
        raise ValueError("Seeds must be positive integers.")
    return seeds


def validate_version_name(version: str) -> str:
    candidate = Path(version)
    if (
        not version
        or candidate.name != version
        or version in {".", ".."}
        or "/" in version
        or "\\" in version
        or VERSION_NAME_PATTERN.fullmatch(version) is None
    ):
        raise ValueError(f"Invalid version folder name: {version!r}")
    return version


def _decimal(value: float | str | Decimal) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def build_candidate_grid(start: float, stop: float, step: float) -> list[float]:
    start_d = _decimal(start)
    stop_d = _decimal(stop)
    step_d = _decimal(step)
    if step_d <= 0:
        raise ValueError("Grid step must be positive.")
    if start_d > stop_d:
        raise ValueError("Grid start must be <= stop.")

    values: list[float] = []
    current = start_d
    while current <= stop_d:
        values.append(float(current))
        current += step_d
    return values


def build_fine_candidate_grid(
    *,
    best_coarse: float,
    lower_bound: float,
    upper_bound: float,
    radius: float,
    precision: float,
) -> list[float]:
    if precision <= 0:
        raise ValueError("precision must be positive.")
    if radius < 0:
        raise ValueError("fine radius must be non-negative.")

    precision_d = _decimal(precision)
    lower_d = max(_decimal(lower_bound), _decimal(best_coarse) - _decimal(radius))
    upper_d = min(_decimal(upper_bound), _decimal(best_coarse) + _decimal(radius))
    start_step = int((lower_d / precision_d).to_integral_value(rounding=ROUND_CEILING))
    end_step = int((upper_d / precision_d).to_integral_value(rounding=ROUND_FLOOR))
    if start_step > end_step:
        raise ValueError("Fine grid is empty.")
    return [float(Decimal(step) * precision_d) for step in range(start_step, end_step + 1)]


def snap_to_precision(value: float, precision: float) -> float:
    if precision <= 0:
        raise ValueError("precision must be positive.")
    value_d = _decimal(value)
    precision_d = _decimal(precision)
    steps = (value_d / precision_d).to_integral_value(rounding=ROUND_HALF_UP)
    return float(steps * precision_d)


def multiplier_label(multiplier: float) -> str:
    return format_float(multiplier, decimals=10).replace("-", "m").replace(".", "p")


def resolve_repo_path(repo_root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else repo_root / path


def config_text_hash(config_text: str) -> str:
    return hashlib.sha256(config_text.encode("utf-8")).hexdigest()


def btl_probability_multiplier_comment(
    *,
    target: float,
    selected_multiplier: float,
    selected_share: float | None = None,
) -> list[str]:
    selected_note = (
        f"# Selected BTL_PROBABILITY_MULTIPLIER = {format_float(selected_multiplier, decimals=10)}."
        if selected_share is None
        else (
            f"# Selected BTL_PROBABILITY_MULTIPLIER = {format_float(selected_multiplier, decimals=10)}; "
            f"selected model-side share = {format_float(selected_share, decimals=16)}."
        )
    )
    return [
        "# Multiplier for the probability of being a buy-to-let investor, output-calibrated against the weighted",
        f"# WAS Round 8 positive-gross-rental-income household share target ({format_float(target, decimals=16)}).",
        selected_note,
    ]


def update_config_property(
    config_text: str,
    key: str,
    value: str,
    preceding_comment_lines: Sequence[str] | None = None,
) -> str:
    lines = config_text.splitlines()
    output: list[str] = []
    seen = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        line_key = line.split("=", 1)[0].strip()
        if line_key == key:
            if preceding_comment_lines is not None:
                while output and output[-1].strip().startswith("#"):
                    output.pop()
                output.extend(preceding_comment_lines)
            output.append(f"{key} = {value}")
            seen = True
        else:
            output.append(line)
    if not seen:
        raise RuntimeError(f"Missing config property {key!r}.")
    return "\n".join(output) + "\n"


def create_output_version(
    *,
    repo_root: Path,
    source_version: str,
    output_version: str,
    selected_multiplier: float,
    overwrite: bool,
    target: float = DEFAULT_TARGET,
    selected_share: float | None = None,
) -> Path:
    source_version = validate_version_name(source_version)
    output_version = validate_version_name(output_version)
    if source_version.lower() == output_version.lower():
        raise ValueError("Source and output version folders must be different.")
    source_dir = repo_root / "input-data-versions" / source_version
    output_dir = repo_root / "input-data-versions" / output_version
    if not (source_dir / "config.properties").exists():
        raise RuntimeError(f"Missing source version config: {source_dir / 'config.properties'}")
    if output_dir.exists():
        if not overwrite:
            raise RuntimeError(f"Output version already exists: {output_dir}")
        shutil.rmtree(output_dir)

    shutil.copytree(source_dir, output_dir)
    config_path = output_dir / "config.properties"
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        update_config_property(
            config_text,
            BTL_PROBABILITY_MULTIPLIER,
            format_float(selected_multiplier, decimals=10),
            preceding_comment_lines=btl_probability_multiplier_comment(
                target=target,
                selected_multiplier=selected_multiplier,
                selected_share=selected_share,
            ),
        ),
        encoding="utf-8",
    )
    return output_dir


def build_run_overrides(*, multiplier: float, seed: int) -> dict[str, str]:
    overrides = dict(REQUIRED_RUN_OVERRIDES)
    overrides["SEED"] = str(seed)
    overrides[BTL_PROBABILITY_MULTIPLIER] = format_float(multiplier, decimals=10)
    return overrides


def extract_rental_income_positive_share(
    path: Path,
    *,
    start_time: int = DEFAULT_WINDOW_START,
    end_time: int = DEFAULT_N_STEPS,
) -> float:
    shares: list[float] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            delimiter = ";" if ";" in stripped else ","
            columns = [column.strip() for column in stripped.split(delimiter)]
            if len(columns) < 2:
                continue
            try:
                time_value = int(columns[0])
            except ValueError:
                continue
            if time_value < start_time or time_value > end_time:
                continue
            values = [float(column) for column in columns[1:] if column]
            if not values:
                continue
            shares.append(sum(1 for value in values if value > 0.0) / len(values))
    if not shares:
        raise RuntimeError(f"No rental-income observations in requested window: {path}")
    return float(statistics.fmean(shares))


def extract_output_run_diagnostics(
    path: Path,
    *,
    start_time: int = DEFAULT_WINDOW_START,
    end_time: int = DEFAULT_N_STEPS,
) -> dict[str, float]:
    active_btl_shares: list[float] = []
    latent_btl_shares: list[float] = []
    btl_stock_fractions: list[float] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";", skipinitialspace=True)
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing header row in {path}")
        for row in reader:
            clean = {str(key).strip(): str(value).strip() for key, value in row.items() if key is not None}
            if not clean:
                continue
            try:
                time_value = int(float(clean["Model time"]))
            except (KeyError, ValueError):
                continue
            if time_value < start_time or time_value > end_time:
                continue
            total_population = float(clean["TotalPopulation"])
            if total_population <= 0:
                continue
            active_btl_shares.append(float(clean["nActiveBTL"]) / total_population)
            latent_btl_shares.append(float(clean["nBTL"]) / total_population)
            btl_stock_fractions.append(float(clean["BTLStockFraction"]))

    if not active_btl_shares:
        raise RuntimeError(f"No Output-run1 diagnostics in requested window: {path}")
    return {
        "active_btl_share": float(statistics.fmean(active_btl_shares)),
        "latent_btl_share": float(statistics.fmean(latent_btl_shares)),
        "btl_stock_fraction": float(statistics.fmean(btl_stock_fractions)),
    }


def extract_seed_run_result(
    *,
    stage: str,
    multiplier: float,
    seed: int,
    output_dir: Path,
    config_path: Path,
    config_hash: str,
    cached: bool,
) -> SeedRunResult:
    rental_share = extract_rental_income_positive_share(output_dir / "MonthlyGrossRentalIncome-run1.csv")
    output_diagnostics = extract_output_run_diagnostics(output_dir / "Output-run1.csv")
    return SeedRunResult(
        stage=stage,
        multiplier=multiplier,
        seed=seed,
        output_dir=str(output_dir),
        config_path=str(config_path),
        config_hash=config_hash,
        cached=cached,
        rental_income_positive_share=rental_share,
        active_btl_share=output_diagnostics["active_btl_share"],
        latent_btl_share=output_diagnostics["latent_btl_share"],
        btl_stock_fraction=output_diagnostics["btl_stock_fraction"],
    )


def load_cached_seed_result(
    path: Path,
    *,
    expected_stage: str,
    expected_multiplier: float,
    expected_seed: int,
    expected_config_hash: str,
) -> SeedRunResult | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    try:
        if str(raw["stage"]) != expected_stage:
            return None
        if abs(float(raw["multiplier"]) - expected_multiplier) > DEFAULT_TARGET_TOLERANCE:
            return None
        if int(raw["seed"]) != expected_seed:
            return None

        cached_config_hash = raw.get("config_hash")
        if cached_config_hash is None:
            config_path = Path(str(raw["config_path"]))
            if not config_path.exists():
                return None
            cached_config_hash = config_text_hash(config_path.read_text(encoding="utf-8"))
        if cached_config_hash != expected_config_hash:
            return None

        output_dir = Path(str(raw["output_dir"]))
        if not (output_dir / "MonthlyGrossRentalIncome-run1.csv").exists():
            return None
        if not (output_dir / "Output-run1.csv").exists():
            return None
    except (KeyError, TypeError, ValueError, OSError):
        return None

    return SeedRunResult(
        stage=str(raw["stage"]),
        multiplier=float(raw["multiplier"]),
        seed=int(raw["seed"]),
        output_dir=str(raw["output_dir"]),
        config_path=str(raw["config_path"]),
        config_hash=expected_config_hash,
        cached=True,
        rental_income_positive_share=float(raw["rental_income_positive_share"]),
        active_btl_share=float(raw["active_btl_share"]),
        latent_btl_share=float(raw["latent_btl_share"]),
        btl_stock_fraction=float(raw["btl_stock_fraction"]),
    )


def run_seed_request(
    *,
    repo_root: Path,
    version: str,
    stage: str,
    multiplier: float,
    seed: int,
    output_root: Path,
    maven_bin: str,
    force_rerun: bool,
) -> SeedRunResult:
    safe_multiplier = multiplier_label(multiplier)
    run_dir = output_root / "runs" / stage / f"multiplier-{safe_multiplier}" / f"seed-{seed}"
    config_path = output_root / "configs" / stage / f"multiplier-{safe_multiplier}-seed-{seed}.properties"
    metrics_path = run_dir / "btl_multiplier_metrics.json"

    version_config_path = repo_root / "input-data-versions" / version / "config.properties"
    if not version_config_path.exists():
        raise RuntimeError(f"Missing version config: {version_config_path}")

    config_text = build_snapshot_local_config_text(
        version_config_path,
        build_run_overrides(multiplier=multiplier, seed=seed),
    )
    expected_config_hash = config_text_hash(config_text)
    if metrics_path.exists() and not force_rerun:
        cached_result = load_cached_seed_result(
            metrics_path,
            expected_stage=stage,
            expected_multiplier=multiplier,
            expected_seed=seed,
            expected_config_hash=expected_config_hash,
        )
        if cached_result is not None:
            return cached_result

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")

    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    exec_args = f'-configFile "{config_path}" -outputFolder "{run_dir}" -dev'
    proc = subprocess.run(
        [maven_bin, "-q", "exec:java", f"-Dexec.args={exec_args}"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "BTL multiplier model run failed.\n"
            f"version={version} stage={stage} multiplier={multiplier} seed={seed}\n"
            f"Output tail:\n{proc.stdout[-3000:]}"
        )

    result = extract_seed_run_result(
        stage=stage,
        multiplier=multiplier,
        seed=seed,
        output_dir=run_dir,
        config_path=config_path,
        config_hash=expected_config_hash,
        cached=False,
    )
    metrics_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return result


def aggregate_candidate_results(
    *,
    stage: str,
    multiplier: float,
    seed_results: Sequence[SeedRunResult],
    target: float,
) -> CandidateSummary:
    ordered_results = sorted(seed_results, key=lambda item: item.seed)
    rental_shares = [result.rental_income_positive_share for result in ordered_results]
    mean_share = float(statistics.fmean(rental_shares))
    stdev = float(statistics.pstdev(rental_shares)) if len(rental_shares) > 1 else 0.0
    return CandidateSummary(
        stage=stage,
        multiplier=multiplier,
        target=target,
        target_gap=abs(mean_share - target),
        rental_income_positive_share_mean=mean_share,
        rental_income_positive_share_stdev=stdev,
        active_btl_share_mean=float(statistics.fmean(result.active_btl_share for result in ordered_results)),
        latent_btl_share_mean=float(statistics.fmean(result.latent_btl_share for result in ordered_results)),
        btl_stock_fraction_mean=float(statistics.fmean(result.btl_stock_fraction for result in ordered_results)),
        seed_count=len(ordered_results),
        seeds=tuple(result.seed for result in ordered_results),
    )


def select_best_candidate(candidates: Sequence[CandidateSummary]) -> CandidateSummary:
    if not candidates:
        raise ValueError("Cannot select from an empty candidate list.")
    return sorted(candidates, key=lambda item: (item.target_gap, item.multiplier))[0]


def build_stage_search_diagnostics(
    *,
    summaries: Sequence[CandidateSummary],
    selected: CandidateSummary,
    target: float,
    target_tolerance: float = DEFAULT_TARGET_TOLERANCE,
) -> dict[str, object]:
    if not summaries:
        raise ValueError("Cannot diagnose an empty candidate list.")

    multipliers = [summary.multiplier for summary in summaries]
    shares = [summary.rental_income_positive_share_mean for summary in summaries]
    min_multiplier = min(multipliers)
    max_multiplier = max(multipliers)
    min_share = min(shares)
    max_share = max(shares)
    target_bracketed = min_share - target_tolerance <= target <= max_share + target_tolerance
    all_candidates_above_target = min_share > target + target_tolerance
    all_candidates_below_target = max_share < target - target_tolerance
    selected_on_lower_boundary = abs(selected.multiplier - min_multiplier) <= target_tolerance
    selected_on_upper_boundary = abs(selected.multiplier - max_multiplier) <= target_tolerance
    target_hit = selected.target_gap <= target_tolerance

    if all_candidates_above_target:
        target_position = "below_candidate_outputs"
    elif all_candidates_below_target:
        target_position = "above_candidate_outputs"
    else:
        target_position = "within_candidate_output_range"

    return {
        "candidateCount": len(summaries),
        "minMultiplier": min_multiplier,
        "maxMultiplier": max_multiplier,
        "minRentalIncomePositiveShareMean": min_share,
        "maxRentalIncomePositiveShareMean": max_share,
        "selectedMultiplier": selected.multiplier,
        "selectedTargetGap": selected.target_gap,
        "selectedOnLowerBoundary": selected_on_lower_boundary,
        "selectedOnUpperBoundary": selected_on_upper_boundary,
        "targetBracketed": target_bracketed,
        "targetHit": target_hit,
        "targetPosition": target_position,
    }


def build_search_diagnostics(
    *,
    coarse_summaries: Sequence[CandidateSummary],
    fine_summaries: Sequence[CandidateSummary],
    best_coarse: CandidateSummary,
    best_fine: CandidateSummary,
    target: float,
    target_tolerance: float = DEFAULT_TARGET_TOLERANCE,
) -> dict[str, object]:
    coarse = build_stage_search_diagnostics(
        summaries=coarse_summaries,
        selected=best_coarse,
        target=target,
        target_tolerance=target_tolerance,
    )
    fine = build_stage_search_diagnostics(
        summaries=fine_summaries,
        selected=best_fine,
        target=target,
        target_tolerance=target_tolerance,
    )

    warnings: list[str] = []
    for stage_name, diagnostics in (("coarse", coarse), ("fine", fine)):
        if not diagnostics["targetBracketed"]:
            warnings.append(
                f"{stage_name} candidate outputs do not bracket the target; "
                "the promoted value is the closest tested candidate."
            )
        if diagnostics["selectedOnLowerBoundary"]:
            warnings.append(f"{stage_name} selected candidate is on the lower search boundary.")
        if diagnostics["selectedOnUpperBoundary"]:
            warnings.append(f"{stage_name} selected candidate is on the upper search boundary.")
        if not diagnostics["targetHit"]:
            warnings.append(f"{stage_name} selected candidate does not exactly hit the target.")

    return {
        "targetTolerance": target_tolerance,
        "coarse": coarse,
        "fine": fine,
        "warnings": warnings,
        "promotedWithWarnings": bool(warnings),
    }


def execute_stage(
    *,
    repo_root: Path,
    version: str,
    output_root: Path,
    stage: str,
    candidates: Sequence[float],
    seeds: Sequence[int],
    target: float,
    workers: int,
    maven_bin: str,
    force_rerun: bool,
) -> tuple[list[SeedRunResult], list[CandidateSummary]]:
    if workers <= 0:
        raise ValueError("workers must be positive.")
    if not candidates:
        raise ValueError("At least one candidate is required.")

    total_runs = len(candidates) * len(seeds)
    started_at = time.monotonic()
    print(
        f"[btl-calibration] stage={stage} candidates={len(candidates)} seeds={len(seeds)} "
        f"runs={total_runs} workers={workers}",
        flush=True,
    )

    run_results: list[SeedRunResult] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="btl-calibration") as executor:
        futures = []
        for multiplier in candidates:
            for seed in seeds:
                futures.append(
                    executor.submit(
                        run_seed_request,
                        repo_root=repo_root,
                        version=version,
                        stage=stage,
                        multiplier=multiplier,
                        seed=seed,
                        output_root=output_root,
                        maven_bin=maven_bin,
                        force_rerun=force_rerun,
                    )
                )

        for index, future in enumerate(as_completed(futures), start=1):
            result = future.result()
            run_results.append(result)
            elapsed = time.monotonic() - started_at
            print(
                f"[btl-calibration] stage={stage} progress={index}/{total_runs} "
                f"multiplier={format_float(result.multiplier)} seed={result.seed} "
                f"share={result.rental_income_positive_share:.6f}"
                f"{' cached' if result.cached else ''} elapsed={_format_duration(elapsed)}",
                flush=True,
            )

    grouped: dict[float, list[SeedRunResult]] = {candidate: [] for candidate in candidates}
    for result in run_results:
        grouped[result.multiplier].append(result)

    summaries = [
        aggregate_candidate_results(
            stage=stage,
            multiplier=multiplier,
            seed_results=grouped[multiplier],
            target=target,
        )
        for multiplier in candidates
    ]
    summaries.sort(key=lambda item: item.multiplier)
    best = select_best_candidate(summaries)
    print(
        f"[btl-calibration] stage={stage} best={format_float(best.multiplier)} "
        f"share={best.rental_income_positive_share_mean:.6f} gap={best.target_gap:.6f}",
        flush=True,
    )
    return sorted(run_results, key=lambda item: (item.multiplier, item.seed)), summaries


def candidate_summary_rows(summaries: Iterable[CandidateSummary]) -> list[dict[str, object]]:
    return [asdict(summary) | {"seeds": ",".join(str(seed) for seed in summary.seeds)} for summary in summaries]


def write_candidate_csv(path: Path, summaries: Sequence[CandidateSummary]) -> None:
    rows = candidate_summary_rows(summaries)
    if not rows:
        raise ValueError("No candidate summaries to write.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_reproduce_command(args: argparse.Namespace) -> str:
    command = [
        "python3 -m scripts.python.calibration.output.btl_probability_multiplier",
        f"--version {args.version}",
        f"--output-version {args.output_version}",
        f"--seeds {args.seeds}",
        f"--workers {args.workers}",
        f"--precision {format_float(args.precision)}",
        f"--coarse-min {format_float(args.coarse_min)}",
        f"--coarse-max {format_float(args.coarse_max)}",
        f"--coarse-step {format_float(args.coarse_step)}",
        f"--fine-radius {format_float(args.fine_radius)}",
        f"--target {format_float(args.target, decimals=16)}",
        f"--output-root {args.output_root}",
    ]
    if args.evidence_dir:
        command.append(f"--evidence-dir {args.evidence_dir}")
    if args.maven_bin != "mvn":
        command.append(f"--maven-bin {args.maven_bin}")
    if args.force_rerun:
        command.append("--force-rerun")
    if args.overwrite_version:
        command.append("--overwrite-version")
    return (" " + "\\" + "\n  ").join(command) + "\n"


def run_calibration(args: argparse.Namespace) -> dict[str, object]:
    repo_root = default_repo_root()
    version = validate_version_name(args.version)
    output_version = validate_version_name(args.output_version)
    seeds = parse_seed_list(args.seeds)
    if args.workers <= 0:
        raise ValueError("workers must be positive.")
    if args.precision <= 0:
        raise ValueError("precision must be positive.")

    source_config = repo_root / "input-data-versions" / version / "config.properties"
    if not source_config.exists():
        raise RuntimeError(f"Missing input-data version config: {source_config}")
    requested_output_dir = repo_root / "input-data-versions" / output_version
    if requested_output_dir.exists() and not args.overwrite_version:
        raise RuntimeError(f"Output version already exists: {requested_output_dir}")

    output_root = resolve_repo_path(repo_root, args.output_root) / output_version
    evidence_dir = (
        resolve_repo_path(repo_root, args.evidence_dir)
        if args.evidence_dir
        else repo_root / EVIDENCE_DIR_TEMPLATE.format(output_version=output_version)
    )
    output_root.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (output_root / "reproduce-command.sh").write_text(build_reproduce_command(args), encoding="utf-8")
    (evidence_dir / "reproduce-command.sh").write_text(build_reproduce_command(args), encoding="utf-8")

    ensure_project_compiled(repo_root, maven_bin=args.maven_bin)

    coarse_candidates = build_candidate_grid(args.coarse_min, args.coarse_max, args.coarse_step)
    _, coarse_summaries = execute_stage(
        repo_root=repo_root,
        version=version,
        output_root=output_root,
        stage="coarse",
        candidates=coarse_candidates,
        seeds=seeds,
        target=args.target,
        workers=args.workers,
        maven_bin=args.maven_bin,
        force_rerun=args.force_rerun,
    )
    best_coarse = select_best_candidate(coarse_summaries)
    fine_candidates = build_fine_candidate_grid(
        best_coarse=best_coarse.multiplier,
        lower_bound=args.coarse_min,
        upper_bound=args.coarse_max,
        radius=args.fine_radius,
        precision=args.precision,
    )
    _, fine_summaries = execute_stage(
        repo_root=repo_root,
        version=version,
        output_root=output_root,
        stage="fine",
        candidates=fine_candidates,
        seeds=seeds,
        target=args.target,
        workers=args.workers,
        maven_bin=args.maven_bin,
        force_rerun=args.force_rerun,
    )
    best_fine = select_best_candidate(fine_summaries)
    selected_multiplier = snap_to_precision(best_fine.multiplier, args.precision)
    search_diagnostics = build_search_diagnostics(
        coarse_summaries=coarse_summaries,
        fine_summaries=fine_summaries,
        best_coarse=best_coarse,
        best_fine=best_fine,
        target=args.target,
    )
    output_version_dir = create_output_version(
        repo_root=repo_root,
        source_version=version,
        output_version=output_version,
        selected_multiplier=selected_multiplier,
        target=args.target,
        selected_share=best_fine.rental_income_positive_share_mean,
        overwrite=args.overwrite_version,
    )

    all_summaries = [*coarse_summaries, *fine_summaries]
    write_candidate_csv(output_root / "BtlProbabilityMultiplierCandidates.csv", all_summaries)
    write_candidate_csv(evidence_dir / "BtlProbabilityMultiplierCandidates.csv", all_summaries)

    summary: dict[str, object] = {
        "sourceVersion": version,
        "outputVersion": output_version,
        "outputVersionDir": str(output_version_dir),
        "target": args.target,
        "targetDescription": "Weighted WAS R8 positive gross rental income household share.",
        "dataBtlProbabilityChanged": False,
        "seeds": seeds,
        "workers": args.workers,
        "nSteps": DEFAULT_N_STEPS,
        "window": {"startTime": DEFAULT_WINDOW_START, "endTime": DEFAULT_N_STEPS},
        "precision": args.precision,
        "coarseGrid": {
            "min": args.coarse_min,
            "max": args.coarse_max,
            "step": args.coarse_step,
            "candidateCount": len(coarse_candidates),
        },
        "fineGrid": {
            "center": best_coarse.multiplier,
            "radius": args.fine_radius,
            "precision": args.precision,
            "candidateCount": len(fine_candidates),
        },
        "selected": {
            "multiplier": selected_multiplier,
            "stage": best_fine.stage,
            "rentalIncomePositiveShareMean": best_fine.rental_income_positive_share_mean,
            "targetGap": best_fine.target_gap,
            "activeBtlShareMean": best_fine.active_btl_share_mean,
            "latentBtlShareMean": best_fine.latent_btl_share_mean,
            "btlStockFractionMean": best_fine.btl_stock_fraction_mean,
        },
        "bestCoarse": asdict(best_coarse),
        "bestFine": asdict(best_fine),
        "searchDiagnostics": search_diagnostics,
        "selectionRule": "minimize primary target gap; deterministic lower-multiplier ordering only for exact equal gaps",
        "runOutputRoot": str(output_root),
        "evidenceDir": str(evidence_dir),
    }
    write_json(output_root / "BtlProbabilityMultiplierCalibrationSummary.json", summary)
    write_json(evidence_dir / "BtlProbabilityMultiplierCalibrationSummary.json", summary)
    print(
        f"[btl-calibration] selected {BTL_PROBABILITY_MULTIPLIER} = "
        f"{format_float(selected_multiplier, decimals=10)} for {output_version}",
        flush=True,
    )
    return summary


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
