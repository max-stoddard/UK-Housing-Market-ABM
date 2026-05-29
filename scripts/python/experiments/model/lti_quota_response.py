#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run and plot the v0o7 versus v5o3 high-LTI quota response experiment.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shlex
import statistics
import subprocess
import tempfile
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "lti_quota_response_matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from scripts.python.helpers.common.abm_policy_sweep import (
    build_snapshot_local_config_text,
    ensure_project_compiled,
    load_core_indicator_values,
    resolve_maven_bin,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir

DEFAULT_OUTPUT_DIR = "tmp/lti-quota-response"
DEFAULT_VERSIONS = ("v0o7", "v5o3")
VERSION_LABELS = {
    "v0o7": "2011 calibration (v0o7)",
    "v5o3": "2024 calibration (v5o3)",
}
VERSION_COLORS = {
    "v0o7": "#4B5563",
    "v5o3": "#0F766E",
}
DEFAULT_SEEDS = tuple(range(1, 11))
DEFAULT_WORKERS = 20
N_STEPS = 3500
METRIC_WINDOW = {"mode": "index_slice", "start_index": 500, "end_index": 3500}
BASELINE_QUOTA = 0.150
DEFAULT_QUOTA_VALUES = (
    0.000,
    0.025,
    0.050,
    0.075,
    0.100,
    0.125,
    0.150,
    0.175,
    0.200,
    0.225,
    0.250,
    0.275,
    0.300,
)
LTI_QUOTA_KEYS = (
    "CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB",
    "CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM",
)
SNAPSHOT_LOCAL_EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        "build",
        "configs",
        "dist",
        "figures",
        "generated",
        "output",
        "outputs",
        "plots",
        "results",
        "run",
        "runs",
        "tmp",
    }
)
POLICY_2024_OVERRIDES = {
    "CENTRAL_BANK_INITIAL_BASE_RATE": "0.0510833333",
    "CENTRAL_BANK_LTV_HARD_MAX_FTB": "0.95",
    "CENTRAL_BANK_LTV_HARD_MAX_HM": "0.95",
    "CENTRAL_BANK_LTV_HARD_MAX_BTL": "0.85",
    "CENTRAL_BANK_LTI_SOFT_MAX_FTB": "4.5",
    "CENTRAL_BANK_LTI_SOFT_MAX_HM": "4.5",
    "CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_FTB": "0.15",
    "CENTRAL_BANK_LTI_MAX_FRAC_OVER_SOFT_MAX_HM": "0.15",
    "CENTRAL_BANK_LTI_MONTHS_TO_CHECK": "12",
    "CENTRAL_BANK_AFFORDABILITY_HARD_MAX": "0.9999",
    "CENTRAL_BANK_ICR_HARD_MIN": "0",
}


@dataclass(frozen=True)
class MetricDefinition:
    id: str
    label: str
    file_name: str


@dataclass(frozen=True)
class RunMetric:
    version: str
    seed: int
    quota_label: str
    quota: float
    is_baseline: bool
    metric_id: str
    value: float


@dataclass(frozen=True)
class AggregatedMetricRow:
    version: str
    quota_label: str
    quota: float
    is_baseline: bool
    metric_id: str
    raw_mean: float
    raw_stdev: float
    raw_ci_low: float
    raw_ci_high: float
    raw_n: int
    delta_percent_mean: float
    delta_percent_stdev: float
    delta_percent_ci_low: float
    delta_percent_ci_high: float
    delta_percent_n: int


METRIC_DEFINITIONS = {
    "core_debtToIncome": MetricDefinition(
        id="core_debtToIncome",
        label="Mortgage Debt to Income",
        file_name="coreIndicator-debtToIncome.csv",
    ),
    "core_ooLTI": MetricDefinition(
        id="core_ooLTI",
        label="Owner-Occupier LTI",
        file_name="coreIndicator-ooLTI.csv",
    ),
    "core_advancesToFTB": MetricDefinition(
        id="core_advancesToFTB",
        label="Advances to FTB",
        file_name="coreIndicator-advancesToFTB.csv",
    ),
    "core_advancesToHM": MetricDefinition(
        id="core_advancesToHM",
        label="Advances to Home Movers",
        file_name="coreIndicator-advancesToHM.csv",
    ),
    "core_advancesToBTL": MetricDefinition(
        id="core_advancesToBTL",
        label="Advances to BTL",
        file_name="coreIndicator-advancesToBTL.csv",
    ),
}
METRIC_IDS = tuple(METRIC_DEFINITIONS.keys())


@dataclass(frozen=True)
class QuotaPoint:
    point_id: str
    point_index: int
    label: str
    quota: float
    is_baseline: bool
    policy_overrides: dict[str, str]


@dataclass(frozen=True)
class RunRequest:
    version: str
    seed: int
    point: QuotaPoint


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the v0o7 versus v5o3 high-LTI quota response experiment.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for run artifacts and plots (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Maximum parallel model runs (default: {DEFAULT_WORKERS}).",
    )
    parser.add_argument(
        "--seeds",
        default=",".join(str(seed) for seed in DEFAULT_SEEDS),
        help="Comma-separated seeds used for all sweeps (default: 1,2,3,4,5,6,7,8,9,10).",
    )
    parser.add_argument(
        "--quota-values",
        default=",".join(format_float(quota) for quota in DEFAULT_QUOTA_VALUES),
        help="Comma-separated LTI quota values to run.",
    )
    parser.add_argument(
        "--maven-bin",
        default=None,
        help="Maven executable override (default: repo-local ./mvnw).",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Ignore cached model outputs and rerun all quota points.",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help="Skip model execution and regenerate plots from existing outputs.",
    )
    return parser


def _parse_csv_tokens(raw: str) -> list[str]:
    values = [token.strip() for token in raw.split(",") if token.strip()]
    if not values:
        raise SystemExit("Expected a non-empty comma-separated list.")
    return values


def parse_csv_floats(raw: str) -> list[float]:
    values: list[float] = []
    for token in _parse_csv_tokens(raw):
        try:
            value = float(token)
        except ValueError as exc:
            raise SystemExit(f"Invalid floating-point value in comma-separated list: {token!r}.") from exc
        if not math.isfinite(value):
            raise SystemExit(f"Quota values must be finite: {token!r}.")
        if value < 0.0 or value > 1.0:
            raise SystemExit(f"Quota values must be between 0.0 and 1.0: {token!r}.")
        values.append(value)
    return values


def parse_seed_list(raw: str) -> list[int]:
    values: list[int] = []
    seen: set[int] = set()
    for token in _parse_csv_tokens(raw):
        try:
            value = int(token)
        except ValueError as exc:
            raise SystemExit(f"Invalid seed in comma-separated list: {token!r}.") from exc
        if value <= 0:
            raise SystemExit("Seeds must be positive integers.")
        if value in seen:
            raise SystemExit(f"Duplicate seed value is not allowed: {value}.")
        seen.add(value)
        values.append(value)
    return values


def select_metric_window(values: Sequence[float]) -> Sequence[float]:
    if METRIC_WINDOW["mode"] != "index_slice":
        raise RuntimeError(f"Unsupported metric window mode {METRIC_WINDOW['mode']!r}.")
    start_index = int(METRIC_WINDOW["start_index"])
    end_index = int(METRIC_WINDOW["end_index"])
    if len(values) < end_index:
        raise RuntimeError(f"Expected at least {end_index} metric values, got {len(values)}.")
    return values[start_index:end_index]


def _require_finite_metric_value(value: float, context: str) -> None:
    if not math.isfinite(value):
        raise RuntimeError(f"Non-finite metric value for {context}: {value!r}.")


def _require_finite_metric_values(values: Sequence[float]) -> None:
    for index, value in enumerate(values):
        _require_finite_metric_value(value, f"window index {index}")


def _mean(values: Sequence[float]) -> float:
    if len(values) == 0:
        raise RuntimeError("Cannot summarize an empty metric window.")
    _require_finite_metric_values(values)
    return float(statistics.mean(values))


def _summary(values: Sequence[float]) -> tuple[float, float, float, float, int]:
    n = len(values)
    mean = _mean(values)
    if n == 1:
        return mean, 0.0, mean, mean, n

    stdev = float(statistics.pstdev(values))
    ci_radius = 1.96 * stdev / math.sqrt(n)
    return mean, stdev, mean - ci_radius, mean + ci_radius, n


def aggregate_run_metrics(run_metrics: Sequence[RunMetric]) -> list[AggregatedMetricRow]:
    baselines: dict[tuple[str, int, str], float] = {}
    for row in run_metrics:
        _require_finite_metric_value(
            row.value,
            f"version {row.version}, seed {row.seed}, quota {row.quota_label}, metric {row.metric_id}",
        )
        if row.is_baseline:
            baselines[(row.version, row.seed, row.metric_id)] = row.value

    raw_values: dict[tuple[str, str, str], list[float]] = {}
    delta_values: dict[tuple[str, str, str], list[float]] = {}
    group_metadata: dict[tuple[str, str, str], tuple[float, bool]] = {}

    for row in run_metrics:
        baseline_key = (row.version, row.seed, row.metric_id)
        if baseline_key not in baselines:
            raise RuntimeError(
                f"Missing baseline for version {row.version}, seed {row.seed}, metric {row.metric_id}."
            )

        baseline = baselines[baseline_key]
        if math.isclose(baseline, 0.0, rel_tol=0.0, abs_tol=1e-12):
            raise RuntimeError(
                f"Baseline is zero or near zero for version {row.version}, seed {row.seed}, metric {row.metric_id}."
            )

        group_key = (row.version, row.quota_label, row.metric_id)
        metadata = (row.quota, row.is_baseline)
        if group_key in group_metadata and group_metadata[group_key] != metadata:
            raise RuntimeError(f"Inconsistent quota metadata for metric group {group_key}.")
        group_metadata[group_key] = metadata

        raw_values.setdefault(group_key, []).append(row.value)
        delta_values.setdefault(group_key, []).append(100.0 * (row.value - baseline) / baseline)

    rows: list[AggregatedMetricRow] = []
    for group_key in sorted(raw_values):
        version, quota_label, metric_id = group_key
        quota, is_baseline = group_metadata[group_key]
        raw_mean, raw_stdev, raw_ci_low, raw_ci_high, raw_n = _summary(raw_values[group_key])
        delta_mean, delta_stdev, delta_ci_low, delta_ci_high, delta_n = _summary(delta_values[group_key])
        rows.append(
            AggregatedMetricRow(
                version=version,
                quota_label=quota_label,
                quota=quota,
                is_baseline=is_baseline,
                metric_id=metric_id,
                raw_mean=raw_mean,
                raw_stdev=raw_stdev,
                raw_ci_low=raw_ci_low,
                raw_ci_high=raw_ci_high,
                raw_n=raw_n,
                delta_percent_mean=delta_mean,
                delta_percent_stdev=delta_stdev,
                delta_percent_ci_low=delta_ci_low,
                delta_percent_ci_high=delta_ci_high,
                delta_percent_n=delta_n,
            )
        )
    return rows


def build_quota_points(quota_values: Sequence[float], baseline_quota: float) -> list[QuotaPoint]:
    points: list[QuotaPoint] = []
    seen_labels: dict[str, float] = {}
    for index, quota in enumerate(quota_values):
        label = format_float(quota)
        if label in seen_labels:
            raise RuntimeError(
                f"Duplicate quota label {label!r} for values {seen_labels[label]!r} and {quota!r}."
            )
        seen_labels[label] = quota
        safe_label = label.replace(".", "p")
        overrides = dict(POLICY_2024_OVERRIDES)
        for key in LTI_QUOTA_KEYS:
            overrides[key] = label
        points.append(
            QuotaPoint(
                point_id=f"quota_{index:02d}_{safe_label}",
                point_index=index,
                label=label,
                quota=quota,
                is_baseline=math.isclose(quota, baseline_quota, rel_tol=0.0, abs_tol=1e-9),
                policy_overrides=overrides,
            )
        )
    baseline_points = [point for point in points if point.is_baseline]
    if not baseline_points:
        raise RuntimeError(f"Baseline quota {baseline_quota} was not present in the policy grid.")
    if len(baseline_points) > 1:
        baseline_values = ", ".join(format_float(point.quota) for point in baseline_points)
        raise RuntimeError(
            f"Multiple baseline quota values matched {format_float(baseline_quota)}: {baseline_values}."
        )
    return points


def build_run_metrics_payload(
    *,
    request: RunRequest,
    output_dir: str | Path,
    config_path: str | Path,
    metrics: dict[str, float],
    command: Sequence[str],
    cached: bool,
) -> dict[str, object]:
    return {
        "experiment_id": "lti_quota_response",
        "version": request.version,
        "seed": request.seed,
        "quota_label": request.point.label,
        "quota": request.point.quota,
        "point_id": request.point.point_id,
        "is_baseline": request.point.is_baseline,
        "policy_overrides": dict(request.point.policy_overrides),
        "n_steps": N_STEPS,
        "metric_window": dict(METRIC_WINDOW),
        "metric_ids": list(METRIC_IDS),
        "metrics": dict(metrics),
        "output_dir": str(output_dir),
        "config_path": str(config_path),
        "command": list(command),
        "cached": cached,
    }


def _is_valid_cached_metric_value(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def load_valid_cached_run_metrics(
    cache_path: str | Path,
    request: RunRequest,
    metric_ids: Sequence[str],
) -> dict[str, object] | None:
    try:
        payload = json.loads(Path(cache_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    expected_identity = {
        "experiment_id": "lti_quota_response",
        "version": request.version,
        "seed": request.seed,
        "quota_label": request.point.label,
        "quota": request.point.quota,
        "point_id": request.point.point_id,
        "is_baseline": request.point.is_baseline,
        "policy_overrides": dict(request.point.policy_overrides),
        "n_steps": N_STEPS,
        "metric_window": dict(METRIC_WINDOW),
        "metric_ids": list(metric_ids),
    }
    for key, expected_value in expected_identity.items():
        if payload.get(key) != expected_value:
            return None

    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        return None
    if set(metrics) != set(metric_ids):
        return None
    if not all(_is_valid_cached_metric_value(metrics[metric_id]) for metric_id in metric_ids):
        return None

    cached_payload = dict(payload)
    cached_payload["cached"] = True
    return cached_payload


def extract_metrics_from_output(output_dir: str | Path) -> dict[str, float]:
    output_path = Path(output_dir)
    metrics: dict[str, float] = {}
    for metric_id in METRIC_IDS:
        definition = METRIC_DEFINITIONS[metric_id]
        raw_values = load_core_indicator_values(output_path / definition.file_name)
        metrics[metric_id] = _mean(select_metric_window(raw_values))
    return metrics


def _generated_config_matches(config_path: Path, config_text: str) -> bool:
    try:
        return config_path.read_text(encoding="utf-8") == config_text
    except OSError:
        return False


def _snapshot_local_dependency_paths(version_dir: Path) -> list[Path]:
    dependencies: list[Path] = []
    stack = [version_dir]
    while stack:
        directory = stack.pop()
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if entry.name.startswith("."):
                        continue
                    if entry.name.lower() in SNAPSHOT_LOCAL_EXCLUDED_DIR_NAMES:
                        continue
                    stack.append(entry)
                elif entry.is_file():
                    dependencies.append(entry)
            except OSError:
                continue
    return dependencies


def _cache_dependency_paths(repo_root: Path, version_config_path: Path) -> list[Path]:
    paths = [repo_root / "pom.xml"]
    paths.extend(_snapshot_local_dependency_paths(version_config_path.parent))
    java_root = repo_root / "src" / "main" / "java"
    if java_root.exists():
        paths.extend(java_root.rglob("*.java"))
    return paths


def _has_newer_cache_dependency(
    *,
    repo_root: Path,
    version_config_path: Path,
    cache_path: Path,
) -> bool:
    try:
        cache_mtime = cache_path.stat().st_mtime
    except OSError:
        return True

    for dependency_path in _cache_dependency_paths(repo_root, version_config_path):
        try:
            if dependency_path.exists() and dependency_path.stat().st_mtime > cache_mtime:
                return True
        except OSError:
            return True
    return False


def execute_java_run(
    *,
    repo_root: Path,
    output_root: Path,
    request: RunRequest,
    force_rerun: bool,
    maven_bin: str,
) -> dict[str, float]:
    run_dir = output_root / "runs" / request.version / f"seed-{request.seed}" / request.point.point_id
    config_path = (
        output_root
        / "configs"
        / request.version
        / f"{request.point.point_id}-seed-{request.seed}.properties"
    )
    cache_path = run_dir / "run_metrics.json"

    version_config_path = repo_root / "input-data-versions" / request.version / "config.properties"
    if not version_config_path.exists():
        raise RuntimeError(f"Missing version config: {version_config_path}")

    overrides = dict(request.point.policy_overrides)
    overrides["SEED"] = str(request.seed)
    overrides["N_STEPS"] = str(N_STEPS)
    config_text = build_snapshot_local_config_text(version_config_path, overrides)

    if cache_path.exists() and not force_rerun:
        cached_payload = load_valid_cached_run_metrics(cache_path, request, METRIC_IDS)
        if (
            cached_payload is not None
            and _generated_config_matches(config_path, config_text)
            and not _has_newer_cache_dependency(
                repo_root=repo_root,
                version_config_path=version_config_path,
                cache_path=cache_path,
            )
        ):
            metrics = cached_payload["metrics"]
            if not isinstance(metrics, dict):
                raise RuntimeError(f"Cached metrics payload was not a mapping: {cache_path}")
            return {metric_id: float(metrics[metric_id]) for metric_id in METRIC_IDS}

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(config_text, encoding="utf-8")

    if run_dir.exists():
        import shutil

        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    exec_args = f'-configFile "{config_path}" -outputFolder "{run_dir}" -dev'
    command = [maven_bin, "-q", "exec:java", f"-Dexec.args={exec_args}"]
    proc = subprocess.run(
        command,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "Model run failed.\n"
            f"version={request.version} seed={request.seed} quota={request.point.label}\n"
            f"Output tail:\n{proc.stdout[-3000:]}"
        )

    metrics = extract_metrics_from_output(run_dir)
    payload = build_run_metrics_payload(
        request=request,
        output_dir=run_dir,
        config_path=config_path,
        metrics=metrics,
        command=command,
        cached=False,
    )
    cache_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return metrics


def write_runs_csv(path: Path, run_metrics: Sequence[RunMetric]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["version", "seed", "quota_label", "quota", "is_baseline", "metric_id", "value"])
        for row in run_metrics:
            writer.writerow(
                [
                    row.version,
                    row.seed,
                    row.quota_label,
                    format_float(row.quota),
                    "true" if row.is_baseline else "false",
                    row.metric_id,
                    format_float(row.value, decimals=10),
                ]
            )


def write_aggregated_csv(path: Path, rows: Sequence[AggregatedMetricRow]) -> None:
    field_names = list(AggregatedMetricRow.__dataclass_fields__)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_aggregated_json(path: Path, rows: Sequence[AggregatedMetricRow]) -> None:
    path.write_text(
        json.dumps([asdict(row) for row in rows], indent=2) + "\n",
        encoding="utf-8",
    )


def load_aggregated_json(path: Path) -> list[AggregatedMetricRow]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"Expected aggregate JSON list: {path}")
    return [AggregatedMetricRow(**row) for row in payload]


def resolve_git_commit(repo_root: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    commit = proc.stdout.strip()
    return commit or None


def build_reproduce_command(args: argparse.Namespace) -> str:
    command_parts = [
        "python3 -m scripts.python.experiments.model.lti_quota_response",
        f"--output-dir {shlex.quote(args.output_dir)}",
        f"--seeds {shlex.quote(args.seeds)}",
        f"--quota-values {shlex.quote(args.quota_values)}",
        f"--workers {args.workers}",
    ]
    if args.force_rerun:
        command_parts.append("--force-rerun")
    if args.maven_bin:
        command_parts.append(f"--maven-bin {shlex.quote(args.maven_bin)}")
    if args.plot_only:
        command_parts.append("--plot-only")
    return " \\\n  ".join(command_parts) + "\n"


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    quota_points: Sequence[QuotaPoint],
    seeds: Sequence[int],
) -> None:
    repo_root = Path(__file__).resolve().parents[4]
    payload = {
        "experiment_id": "lti_quota_response",
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_commit": resolve_git_commit(repo_root),
        "versions": list(DEFAULT_VERSIONS),
        "seeds": list(seeds),
        "quota_points": [asdict(point) for point in quota_points],
        "n_steps": N_STEPS,
        "metric_window": dict(METRIC_WINDOW),
        "metric_ids": list(METRIC_IDS),
        "args": vars(args),
        "reproduce_command": build_reproduce_command(args),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def regenerate_plots(output_dir: Path) -> None:
    rows = load_aggregated_json(output_dir / "lti_quota_response_aggregated.json")
    write_figures(output_dir, rows)


def _rows_for_metric(rows: Sequence[AggregatedMetricRow], metric_id: str) -> list[AggregatedMetricRow]:
    return sorted(
        (row for row in rows if row.metric_id == metric_id),
        key=lambda row: (row.version, row.quota),
    )


def write_figures(output_dir: Path, rows: Sequence[AggregatedMetricRow]) -> None:
    for metric_id in METRIC_IDS:
        metric_rows = _rows_for_metric(rows, metric_id)
        if not metric_rows:
            continue

        fig, ax = plt.subplots(figsize=(8.0, 4.8))
        try:
            plotted_rows: list[AggregatedMetricRow] = []
            for version in DEFAULT_VERSIONS:
                version_rows = [row for row in metric_rows if row.version == version]
                if not version_rows:
                    continue
                plotted_rows.extend(version_rows)

                x_values = [round(row.quota * 100.0, 10) for row in version_rows]
                y_values = [row.delta_percent_mean for row in version_rows]
                ci_low_values = [row.delta_percent_ci_low for row in version_rows]
                ci_high_values = [row.delta_percent_ci_high for row in version_rows]
                color = VERSION_COLORS.get(version)
                label = VERSION_LABELS.get(version, version)
                ax.plot(x_values, y_values, color=color, marker="o", linewidth=2.0, label=label)
                ax.fill_between(
                    x_values,
                    ci_low_values,
                    ci_high_values,
                    color=color,
                    alpha=0.18,
                    linewidth=0,
                )

            ax.axhline(0.0, color="#111827", linewidth=1.0)
            ax.set_xlabel("Share of owner-occupier mortgages allowed above 4.5x income (%)")
            ax.set_ylabel("Change from 15% baseline (%)")
            ax.set_xticks(sorted({round(row.quota * 100.0, 10) for row in plotted_rows}))
            ax.grid(True, color="#D1D5DB", linewidth=0.8, alpha=0.8)
            ax.legend()
            fig.tight_layout()

            fig.savefig(output_dir / f"{metric_id}_lti_quota_response.png", dpi=220)
            pdf_path = output_dir / f"{metric_id}_lti_quota_response.pdf"
            try:
                fig.savefig(pdf_path)
            except Exception as exc:
                warnings.warn(
                    f"Could not save PDF figure {pdf_path}: {exc}",
                    RuntimeWarning,
                    stacklevel=2,
                )
        finally:
            plt.close(fig)


def _run_metric_sort_key(row: RunMetric) -> tuple[str, int, float, int]:
    metric_order = {metric_id: index for index, metric_id in enumerate(METRIC_IDS)}
    return (row.version, row.seed, row.quota, metric_order[row.metric_id])


def _aggregated_metric_sort_key(row: AggregatedMetricRow) -> tuple[str, float, int]:
    metric_order = {metric_id: index for index, metric_id in enumerate(METRIC_IDS)}
    return (row.version, row.quota, metric_order[row.metric_id])


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.workers <= 0:
        raise SystemExit("workers must be positive.")

    output_dir = ensure_output_dir(args.output_dir)
    if args.plot_only:
        regenerate_plots(output_dir)
        return

    repo_root = Path(__file__).resolve().parents[4]
    maven_bin = resolve_maven_bin(repo_root, args.maven_bin)
    seeds = parse_seed_list(args.seeds)
    quota_points = build_quota_points(parse_csv_floats(args.quota_values), BASELINE_QUOTA)

    ensure_project_compiled(repo_root=repo_root, maven_bin=maven_bin)

    requests = [
        RunRequest(version=version, seed=seed, point=point)
        for version in DEFAULT_VERSIONS
        for seed in seeds
        for point in quota_points
    ]

    run_metrics: list[RunMetric] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        future_to_request = {
            executor.submit(
                execute_java_run,
                repo_root=repo_root,
                output_root=output_dir,
                request=request,
                force_rerun=args.force_rerun,
                maven_bin=maven_bin,
            ): request
            for request in requests
        }
        for future in as_completed(future_to_request):
            request = future_to_request[future]
            metrics = future.result()
            for metric_id in METRIC_IDS:
                run_metrics.append(
                    RunMetric(
                        version=request.version,
                        seed=request.seed,
                        quota_label=request.point.label,
                        quota=request.point.quota,
                        is_baseline=request.point.is_baseline,
                        metric_id=metric_id,
                        value=float(metrics[metric_id]),
                    )
                )

    run_metrics.sort(key=_run_metric_sort_key)
    aggregated_rows = aggregate_run_metrics(run_metrics)
    aggregated_rows.sort(key=_aggregated_metric_sort_key)

    write_manifest(output_dir / "manifest.json", args=args, quota_points=quota_points, seeds=seeds)
    write_runs_csv(output_dir / "lti_quota_response_runs.csv", run_metrics)
    write_aggregated_csv(output_dir / "lti_quota_response_aggregated.csv", aggregated_rows)
    write_aggregated_json(output_dir / "lti_quota_response_aggregated.json", aggregated_rows)
    write_figures(output_dir, aggregated_rows)


__all__ = [
    "AggregatedMetricRow",
    "BASELINE_QUOTA",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_QUOTA_VALUES",
    "DEFAULT_SEEDS",
    "DEFAULT_VERSIONS",
    "DEFAULT_WORKERS",
    "LTI_QUOTA_KEYS",
    "METRIC_DEFINITIONS",
    "METRIC_IDS",
    "METRIC_WINDOW",
    "MetricDefinition",
    "N_STEPS",
    "POLICY_2024_OVERRIDES",
    "QuotaPoint",
    "RunMetric",
    "RunRequest",
    "VERSION_COLORS",
    "VERSION_LABELS",
    "aggregate_run_metrics",
    "build_arg_parser",
    "build_quota_points",
    "build_reproduce_command",
    "build_run_metrics_payload",
    "execute_java_run",
    "extract_metrics_from_output",
    "load_valid_cached_run_metrics",
    "load_aggregated_json",
    "main",
    "parse_csv_floats",
    "parse_seed_list",
    "regenerate_plots",
    "resolve_git_commit",
    "select_metric_window",
    "write_aggregated_csv",
    "write_aggregated_json",
    "write_figures",
    "write_manifest",
    "write_runs_csv",
]


if __name__ == "__main__":
    main()
