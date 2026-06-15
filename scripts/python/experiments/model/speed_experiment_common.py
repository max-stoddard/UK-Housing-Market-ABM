#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared helpers for model-speed experiment orchestration and analysis.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import json
import math
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


DEFAULT_SNAPSHOT = "v0"
DEFAULT_BASE_MODE = "core-minimal-20k-s1"
DEFAULT_N_STEPS = 2000
DEFAULT_SEED_COUNT = 40
DEFAULT_PARALLEL_WORKERS = 20
DEFAULT_ORDERING_SEED = 20260603

T_CRITICAL_975 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


@dataclass(frozen=True)
class ParallelScalingBatch:
    status: str
    wall_clock_seconds: float
    completed_child_count: int
    failed_child_count: int
    canceled_child_count: int
    throughput_runs_per_hour: float
    child_wall_clock_seconds: list[float]
    child_mean_wall_clock_seconds: float | None
    child_median_wall_clock_seconds: float | None
    child_p95_wall_clock_seconds: float | None
    children: list[Mapping[str, Any]]


def build_parallel_scaling_command(
    *,
    repo_root: Path,
    output_root: Path,
    target_population: int,
    workers: int,
    seed_count: int = DEFAULT_SEED_COUNT,
    seeds: Sequence[int] | None = None,
    n_steps: int = DEFAULT_N_STEPS,
    snapshot: str = DEFAULT_SNAPSHOT,
    base_mode: str = DEFAULT_BASE_MODE,
    phase: str = "full",
    ordering_seed: int = DEFAULT_ORDERING_SEED,
    policy_label: str,
    java_options: Sequence[str] = (),
    confirm_expensive: bool = True,
) -> list[str]:
    _require_positive_int(target_population, "target_population")
    _require_positive_int(workers, "workers")
    _require_positive_int(seed_count, "seed_count")
    explicit_seeds = tuple(int(seed) for seed in seeds) if seeds is not None else None
    if explicit_seeds is not None:
        _require_positive_sequence(explicit_seeds, "seeds")
        if len(set(explicit_seeds)) != len(explicit_seeds):
            raise ValueError("seeds must not contain duplicates.")
        if len(explicit_seeds) != seed_count:
            raise ValueError("seed_count must match the explicit seeds length.")
    _require_positive_int(n_steps, "n_steps")
    if phase not in {"pilot", "full"}:
        raise ValueError("phase must be pilot or full.")

    command = [
        "node",
        "--import",
        "tsx/esm",
        "server/parallelScalingReportCli.ts",
        "--phase",
        phase,
        "--repo-root",
        str(repo_root),
        "--snapshot",
        snapshot,
        "--base-mode",
        base_mode,
        "--target-population",
        str(target_population),
        "--n-steps",
        str(n_steps),
        "--seed-count",
        str(seed_count),
        "--workers",
        str(workers),
        "--repeats",
        "1",
        "--ordering-seed",
        str(ordering_seed),
        "--policy-label",
        policy_label,
        "--output-root",
        str(output_root),
    ]
    if explicit_seeds is not None:
        command.extend(["--seeds", ",".join(str(seed) for seed in explicit_seeds)])
    for java_option in java_options:
        command.extend(["--java-option", java_option])
    if phase == "full" and confirm_expensive:
        command.append("--confirm-expensive")
    return command


def load_single_parallel_scaling_batch(raw_json_path: Path) -> ParallelScalingBatch:
    payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
    batches = payload.get("batches", [])
    if len(batches) != 1:
        raise ValueError(f"Expected exactly one batch in {raw_json_path}, found {len(batches)}.")

    batch = batches[0]
    children = list(batch.get("children", []))
    child_wall_clock_seconds = [
        float(child["wallClockSeconds"])
        for child in children
        if is_success_status(str(child.get("status", ""))) and child.get("wallClockSeconds") is not None
    ]
    return ParallelScalingBatch(
        status=str(batch.get("status", "")),
        wall_clock_seconds=float(batch.get("wallClockSeconds", 0.0) or 0.0),
        completed_child_count=int(batch.get("completedChildCount", 0) or 0),
        failed_child_count=int(batch.get("failedChildCount", 0) or 0),
        canceled_child_count=int(batch.get("canceledChildCount", 0) or 0),
        throughput_runs_per_hour=float(batch.get("throughputRunsPerHour", 0.0) or 0.0),
        child_wall_clock_seconds=child_wall_clock_seconds,
        child_mean_wall_clock_seconds=statistics.mean(child_wall_clock_seconds) if child_wall_clock_seconds else None,
        child_median_wall_clock_seconds=statistics.median(child_wall_clock_seconds) if child_wall_clock_seconds else None,
        child_p95_wall_clock_seconds=percentile_nearest_rank(child_wall_clock_seconds, 0.95),
        children=children,
    )


def latest_parallel_scaling_raw_json(output_root: Path) -> Path:
    candidates = sorted(output_root.glob("parallel-scaling/*/parallel_scaling_raw.json"), key=lambda path: path.stat().st_mtime)
    if not candidates:
        raise FileNotFoundError(f"No parallel_scaling_raw.json found under {output_root}")
    return candidates[-1]


def effect_summary(ratios: Sequence[float]) -> dict[str, Any]:
    positive = [float(value) for value in ratios if float(value) > 0.0]
    if not positive:
        return {"estimate": None, "lower_95_ci": None, "upper_95_ci": None, "n": 0}
    return effect_summary_from_logs([math.log(value) for value in positive])


def effect_summary_from_logs(log_values: Sequence[float]) -> dict[str, Any]:
    if not log_values:
        return {"estimate": None, "lower_95_ci": None, "upper_95_ci": None, "n": 0}

    mean_log = statistics.mean(log_values)
    estimate = math.exp(mean_log)
    if len(log_values) == 1:
        return {"estimate": estimate, "lower_95_ci": None, "upper_95_ci": None, "n": 1}

    sd = statistics.stdev(log_values)
    if sd == 0.0:
        return {"estimate": estimate, "lower_95_ci": estimate, "upper_95_ci": estimate, "n": len(log_values)}

    t_critical = T_CRITICAL_975.get(len(log_values) - 1, 1.96)
    half_width = t_critical * sd / math.sqrt(len(log_values))
    return {
        "estimate": estimate,
        "lower_95_ci": math.exp(mean_log - half_width),
        "upper_95_ci": math.exp(mean_log + half_width),
        "n": len(log_values),
    }


def percentile_nearest_rank(values: Sequence[float], quantile: float) -> float | None:
    if not values:
        return None
    if not 0.0 < quantile <= 1.0:
        raise ValueError("quantile must be in (0, 1].")
    ordered = sorted(float(value) for value in values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def read_csv_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [{key: coerce_csv_value(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], headers: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_checked(command: Sequence[str], *, cwd: Path) -> None:
    subprocess.run(list(command), cwd=cwd, check=True)


def is_success_status(status: str) -> bool:
    return status.strip().lower() in {"success", "successful", "succeeded", "complete", "completed", "ok", "passed"}


def coerce_csv_value(value: str | None) -> Any:
    if value is None:
        return None
    text = value.strip()
    if text == "":
        return None
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _require_positive_int(value: int, label: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer.")


def _require_positive_sequence(values: Sequence[int], label: str) -> None:
    if not values:
        raise ValueError(f"{label} must not be empty.")
    for value in values:
        _require_positive_int(value, label)
