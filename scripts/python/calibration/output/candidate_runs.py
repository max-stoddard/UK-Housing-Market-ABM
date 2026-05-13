"""Snapshot-local candidate execution helpers for output ES-MDA calibration.

@author: Max Stoddard
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping, Sequence

from scripts.python.calibration.output.esmda import DEFAULT_PARAMETER_SPECS, ParameterSpec
from scripts.python.helpers.common.abm_policy_sweep import build_snapshot_local_config_text
from scripts.python.helpers.common.cli import format_float
from scripts.python.validation.model.runner import VALIDATION_RECORDING_OVERRIDES, _extract_seed_metrics
from scripts.python.validation.model.validation_profiles import ValidationProfile

VERSION_NAME_PATTERN = re.compile(r"^v\d+(?:\.\d+)*(?:o+|o\d+)?$", re.IGNORECASE)
DEFAULT_OUTPUT_ROOT = "tmp/output-calibration"
EVIDENCE_DIR_TEMPLATE = "input-data-versions/calibration-evidence/output-four-parameter-esmda-{output_version}"


@dataclass(frozen=True)
class SeedRunResult:
    """Validation metrics extracted from one candidate/seed model run."""

    iteration: int
    member_id: int
    seed: int
    parameters: dict[str, float]
    output_dir: str
    config_path: str
    config_hash: str
    validation_profile_id: str
    metric_ids: tuple[str, ...]
    cached: bool
    metrics: dict[str, float]


def parse_seed_list(raw: str) -> list[int]:
    """Parse a comma-separated positive seed list."""

    seeds = [int(token.strip()) for token in raw.split(",") if token.strip()]
    if not seeds:
        raise ValueError("At least one seed is required")
    if any(seed <= 0 for seed in seeds):
        raise ValueError("Seeds must be positive integers")
    return seeds


def validate_version_name(version: str) -> str:
    """Validate a safe input-data version folder name."""

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


def resolve_repo_path(repo_root: Path, raw_path: str | Path) -> Path:
    """Resolve a repo-relative path against the repository root."""

    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else repo_root / path


def config_text_hash(config_text: str) -> str:
    """Return a stable hash for generated Java config text."""

    return hashlib.sha256(config_text.encode("utf-8")).hexdigest()


def parse_config_parameters(
    config_text: str,
    *,
    specs: Sequence[ParameterSpec] = DEFAULT_PARAMETER_SPECS,
) -> dict[str, float]:
    """Extract the calibrated parameter values from a Java properties file."""

    found: dict[str, float] = {}
    wanted = {spec.name for spec in specs}
    for line in config_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key in wanted:
            found[normalized_key] = float(raw_value.strip())

    missing = sorted(wanted - found.keys())
    if missing:
        raise RuntimeError(f"Missing calibrated config parameters: {missing}")
    return found


def update_config_properties(config_text: str, updates: Mapping[str, str | float]) -> str:
    """Apply multiple config property updates and fail if any target key is absent."""

    update_text = {key: str(value) for key, value in updates.items()}
    output: list[str] = []
    seen: set[str] = set()
    for line in config_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in update_text:
            output.append(f"{key} = {update_text[key]}")
            seen.add(key)
        else:
            output.append(line)

    missing = sorted(set(update_text) - seen)
    if missing:
        raise RuntimeError(f"Missing config properties for update: {missing}")
    return "\n".join(output) + "\n"


def format_parameter_updates(parameters: Mapping[str, float]) -> dict[str, str]:
    """Format parameter values consistently for Java config overlays."""

    return {key: format_float(float(value), decimals=12) for key, value in parameters.items()}


def build_candidate_run_overrides(*, parameters: Mapping[str, float], seed: int) -> dict[str, str]:
    """Build validation recording and parameter overrides for one seed run."""

    overrides = dict(VALIDATION_RECORDING_OVERRIDES)
    overrides["SEED"] = str(seed)
    overrides.update(format_parameter_updates(parameters))
    return overrides


def build_candidate_batches(
    member_ids: Sequence[int],
    *,
    seed_count: int,
    workers: int,
) -> list[list[int]]:
    """Batch member ids so each batch can run all seeds for a few candidates."""

    if seed_count <= 0:
        raise ValueError("seed_count must be positive")
    if workers <= 0:
        raise ValueError("workers must be positive")
    candidate_parallelism = max(1, math.ceil(workers / seed_count))
    return [
        list(member_ids[start : start + candidate_parallelism])
        for start in range(0, len(member_ids), candidate_parallelism)
    ]


def load_cached_seed_run_result(
    path: Path,
    *,
    expected_iteration: int,
    expected_member_id: int,
    expected_seed: int,
    expected_config_hash: str,
    expected_validation_profile_id: str,
    expected_metric_ids: Sequence[str],
) -> SeedRunResult | None:
    """Load a cached seed result if the cache metadata exactly matches."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    try:
        metric_ids = tuple(str(metric_id) for metric_id in raw["metric_ids"])
        if int(raw["iteration"]) != expected_iteration:
            return None
        if int(raw["member_id"]) != expected_member_id:
            return None
        if int(raw["seed"]) != expected_seed:
            return None
        if str(raw["config_hash"]) != expected_config_hash:
            return None
        if str(raw["validation_profile_id"]) != expected_validation_profile_id:
            return None
        if metric_ids != tuple(expected_metric_ids):
            return None
    except (KeyError, TypeError, ValueError):
        return None

    return SeedRunResult(
        iteration=int(raw["iteration"]),
        member_id=int(raw["member_id"]),
        seed=int(raw["seed"]),
        parameters={str(key): float(value) for key, value in raw["parameters"].items()},
        output_dir=str(raw["output_dir"]),
        config_path=str(raw["config_path"]),
        config_hash=expected_config_hash,
        validation_profile_id=expected_validation_profile_id,
        metric_ids=metric_ids,
        cached=True,
        metrics={str(key): float(value) for key, value in raw["metrics"].items()},
    )


def run_seed_request(
    *,
    repo_root: Path,
    version: str,
    iteration: int,
    member_id: int,
    parameters: Mapping[str, float],
    seed: int,
    output_root: Path,
    maven_bin: str,
    force_rerun: bool,
    validation_profile: ValidationProfile,
    was_data_root: Path,
) -> SeedRunResult:
    """Run or reuse one snapshot-local candidate/seed evaluation."""

    version_config_path = repo_root / "input-data-versions" / version / "config.properties"
    if not version_config_path.exists():
        raise RuntimeError(f"Missing version config: {version_config_path}")

    iter_dir = f"iter-{iteration:02d}"
    member_dir = f"member-{member_id:03d}"
    seed_dir = f"seed-{seed}"
    output_dir = output_root / "runs" / iter_dir / member_dir / seed_dir
    config_path = output_root / "configs" / iter_dir / member_dir / f"{seed_dir}.properties"
    metrics_path = output_dir / "four_parameter_seed_metrics.json"
    metric_ids = tuple(validation_profile.targets_by_id.keys())

    config_text = build_snapshot_local_config_text(
        version_config_path,
        build_candidate_run_overrides(parameters=parameters, seed=seed),
    )
    expected_config_hash = config_text_hash(config_text)
    if metrics_path.exists() and not force_rerun:
        cached = load_cached_seed_run_result(
            metrics_path,
            expected_iteration=iteration,
            expected_member_id=member_id,
            expected_seed=seed,
            expected_config_hash=expected_config_hash,
            expected_validation_profile_id=validation_profile.profile_id,
            expected_metric_ids=metric_ids,
        )
        if cached is not None:
            return cached

    if output_dir.exists() and config_path.exists() and not force_rerun:
        existing_config_text = config_path.read_text(encoding="utf-8")
        if config_text_hash(existing_config_text) == expected_config_hash:
            recovered = _try_recover_seed_metrics(
                iteration=iteration,
                member_id=member_id,
                seed=seed,
                parameters=parameters,
                output_dir=output_dir,
                config_path=config_path,
                config_hash=expected_config_hash,
                validation_profile=validation_profile,
                was_data_root=was_data_root,
                metric_ids=metric_ids,
                metrics_path=metrics_path,
            )
            if recovered is not None:
                return recovered

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    exec_args = f'-configFile "{config_path}" -outputFolder "{output_dir}" -dev'
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
            "Four-parameter candidate model run failed.\n"
            f"version={version} iteration={iteration} member={member_id} seed={seed}\n"
            f"Output tail:\n{proc.stdout[-3000:]}"
        )

    metrics = _extract_seed_metrics(
        seed_output_dir=output_dir,
        was_data_root=was_data_root,
        validation_profile=validation_profile,
    )
    result = SeedRunResult(
        iteration=iteration,
        member_id=member_id,
        seed=seed,
        parameters={str(key): float(value) for key, value in parameters.items()},
        output_dir=str(output_dir),
        config_path=str(config_path),
        config_hash=expected_config_hash,
        validation_profile_id=validation_profile.profile_id,
        metric_ids=metric_ids,
        cached=False,
        metrics=metrics,
    )
    metrics_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return result


def _try_recover_seed_metrics(
    *,
    iteration: int,
    member_id: int,
    seed: int,
    parameters: Mapping[str, float],
    output_dir: Path,
    config_path: Path,
    config_hash: str,
    validation_profile: ValidationProfile,
    was_data_root: Path,
    metric_ids: Sequence[str],
    metrics_path: Path,
) -> SeedRunResult | None:
    """Recover a cache entry from an already-complete seed output directory."""

    try:
        metrics = _extract_seed_metrics(
            seed_output_dir=output_dir,
            was_data_root=was_data_root,
            validation_profile=validation_profile,
        )
    except (FileNotFoundError, RuntimeError, ValueError, OSError):
        return None

    result = SeedRunResult(
        iteration=iteration,
        member_id=member_id,
        seed=seed,
        parameters={str(key): float(value) for key, value in parameters.items()},
        output_dir=str(output_dir),
        config_path=str(config_path),
        config_hash=config_hash,
        validation_profile_id=validation_profile.profile_id,
        metric_ids=tuple(metric_ids),
        cached=True,
        metrics=metrics,
    )
    metrics_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return result


def execute_seed_requests_for_members(
    *,
    repo_root: Path,
    version: str,
    iteration: int,
    member_parameters: Sequence[Mapping[str, float]],
    seeds: Sequence[int],
    output_root: Path,
    maven_bin: str,
    force_rerun: bool,
    validation_profile: ValidationProfile,
    was_data_root: Path,
    workers: int,
) -> list[SeedRunResult]:
    """Run candidate members with grouped candidate concurrency."""

    if workers <= 0:
        raise ValueError("workers must be positive")
    if not member_parameters:
        raise ValueError("At least one member parameter set is required")
    if not seeds:
        raise ValueError("At least one seed is required")

    results: list[SeedRunResult] = []
    member_ids = list(range(len(member_parameters)))
    total_seed_runs = len(member_parameters) * len(seeds)
    completed_by_member: dict[int, int] = {member_id: 0 for member_id in member_ids}
    completed_members: set[int] = set()
    cache_hits = 0
    new_runs = 0
    started_at = time.monotonic()
    for batch in build_candidate_batches(member_ids, seed_count=len(seeds), workers=workers):
        print(
            "[four-parameter-esmda] "
            f"iteration={iteration} evaluatingMembers={batch[0]}..{batch[-1]} "
            f"seedRuns={len(batch) * len(seeds)} totalSeedRuns={total_seed_runs}",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="four-parameter-esmda") as executor:
            futures = []
            for member_id in batch:
                for seed in seeds:
                    futures.append(
                        executor.submit(
                            run_seed_request,
                            repo_root=repo_root,
                            version=version,
                            iteration=iteration,
                            member_id=member_id,
                            parameters=member_parameters[member_id],
                            seed=seed,
                            output_root=output_root,
                            maven_bin=maven_bin,
                            force_rerun=force_rerun,
                            validation_profile=validation_profile,
                            was_data_root=was_data_root,
                        )
                    )
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed_by_member[result.member_id] += 1
                if completed_by_member[result.member_id] == len(seeds):
                    completed_members.add(result.member_id)
                if result.cached:
                    cache_hits += 1
                else:
                    new_runs += 1
                completed_runs = len(results)
                elapsed = time.monotonic() - started_at
                throughput = completed_runs / elapsed if elapsed > 0 else 0.0
                remaining_runs = total_seed_runs - completed_runs
                eta_seconds = remaining_runs / throughput if throughput > 0 else None
                print(
                    "[four-parameter-esmda] "
                    f"iteration={iteration} member={result.member_id} seed={result.seed} "
                    f"cached={str(result.cached).lower()} "
                    f"completedSeedRuns={completed_runs}/{total_seed_runs} "
                    f"completedMembers={len(completed_members)}/{len(member_parameters)} "
                    f"elapsed={_format_duration(elapsed)} throughput={throughput:.3f}runs/s "
                    f"eta={_format_optional_duration(eta_seconds)} finish={_format_finish_time(eta_seconds)} "
                    f"cacheHits={cache_hits} newRuns={new_runs}",
                    flush=True,
                )

    return sorted(results, key=lambda item: (item.iteration, item.member_id, item.seed))


def create_output_version(
    *,
    repo_root: Path,
    source_version: str,
    output_version: str,
    selected_parameters: Mapping[str, float],
    overwrite: bool,
) -> Path:
    """Copy a source input-data snapshot and update only the four calibrated parameters."""

    source_version = validate_version_name(source_version)
    output_version = validate_version_name(output_version)
    if source_version.lower() == output_version.lower():
        raise ValueError("Source and output version folders must be different")

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
        update_config_properties(config_text, format_parameter_updates(selected_parameters)),
        encoding="utf-8",
    )
    return output_dir


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    """Write a JSON artifact with stable indentation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _format_duration(seconds: float) -> str:
    rounded = max(0, int(round(seconds)))
    hours, remainder = divmod(rounded, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_optional_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    return _format_duration(seconds)


def _format_finish_time(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    return (datetime.now().astimezone() + timedelta(seconds=max(0.0, seconds))).isoformat(timespec="seconds")


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "EVIDENCE_DIR_TEMPLATE",
    "SeedRunResult",
    "build_candidate_batches",
    "build_candidate_run_overrides",
    "config_text_hash",
    "create_output_version",
    "execute_seed_requests_for_members",
    "format_parameter_updates",
    "parse_config_parameters",
    "parse_seed_list",
    "resolve_repo_path",
    "run_seed_request",
    "update_config_properties",
    "validate_version_name",
    "write_json",
]
