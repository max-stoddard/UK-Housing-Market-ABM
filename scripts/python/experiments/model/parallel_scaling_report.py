#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze raw model parallel-scaling benchmark artifacts.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "uk-housing-matplotlib"))

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ImportError:
    plt = None
    HAS_MATPLOTLIB = False


SUCCESS_STATUSES = {
    "complete",
    "completed",
    "done",
    "finished",
    "ok",
    "pass",
    "passed",
    "success",
    "successful",
    "succeeded",
}
EXCLUDED_STATUSES = {
    "abort",
    "aborted",
    "cancel",
    "canceled",
    "cancelled",
    "error",
    "fail",
    "failed",
    "failure",
    "skipped",
    "timeout",
    "timed_out",
}

WORKER_KEYS = ("workers", "parallelWorkers", "parallel_workers", "workerCount", "worker_count")
BATCH_ID_KEYS = ("batchId", "batch_id", "id", "batch", "batchName", "scenarioId", "scenario_id")
REPEAT_KEYS = ("repeat", "repeatIndex", "repeat_index", "replicate", "trial", "runIndex", "run_index")
STATUS_KEYS = ("status", "state", "result", "outcome")
SECONDS_KEYS = (
    "wallClockSeconds",
    "wall_clock_seconds",
    "batchWallClockSeconds",
    "batch_wall_clock_seconds",
    "durationSeconds",
    "duration_seconds",
    "elapsedSeconds",
    "elapsed_seconds",
    "runtimeSeconds",
    "runtime_seconds",
    "seconds",
)
MILLISECONDS_KEYS = (
    "wallClockMs",
    "wall_clock_ms",
    "durationMs",
    "duration_ms",
    "elapsedMs",
    "elapsed_ms",
    "runtimeMs",
    "runtime_ms",
    "milliseconds",
)
START_KEYS = ("startedAt", "started_at", "startTime", "start_time", "start")
END_KEYS = ("endedAt", "ended_at", "finishedAt", "finished_at", "endTime", "end_time", "end")
RUN_COUNT_KEYS = (
    "successfulRuns",
    "successful_runs",
    "completedSuccessfulRuns",
    "completed_successful_runs",
    "completedChildCount",
    "completed_child_count",
    "completedRuns",
    "completed_runs",
    "successCount",
    "success_count",
    "runsCompleted",
    "runs_completed",
)
THROUGHPUT_KEYS = (
    "throughputRunsPerHour",
    "throughput_runs_per_hour",
    "runsPerHour",
    "runs_per_hour",
)
FALLBACK_RUN_COUNT_KEYS = ("runs", "modelRuns", "model_runs", "childCount", "child_count", "totalRuns", "total_runs")
NESTED_CHILD_KEYS = ("children", "childResults", "child_results", "childRows", "child_rows", "modelRuns", "model_runs", "runs")
SEPARATE_BATCH_KEYS = ("batchResults", "batch_results", "batches", "batchRows", "batch_rows")
SEPARATE_CHILD_KEYS = ("childResults", "child_results", "children", "childRows", "child_rows", "modelRuns", "model_runs", "runs")


def read_raw_results(path: Path) -> Mapping[str, Any] | list[Mapping[str, Any]]:
    """Read a raw JSON or CSV scaling artifact."""

    if path.suffix.lower() == ".csv":
        return _read_raw_csv(path)
    return json.loads(path.read_text(encoding="utf-8"))


def analyze_raw_payload(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return batch, per-worker, regression, and oversubscription summaries."""

    batch_rows = _extract_batch_rows(payload)
    separate_child_groups = _extract_separate_child_groups(payload)

    successful_batches: list[dict[str, Any]] = []
    throughputs_by_worker: dict[int, list[float]] = defaultdict(list)
    batch_seconds_by_worker: dict[int, list[float]] = defaultdict(list)
    child_seconds_by_worker: dict[int, list[float]] = defaultdict(list)

    for batch in batch_rows:
        workers = _extract_workers(batch)
        if workers is None or workers <= 0:
            continue
        if not _is_successful_row(batch):
            continue

        child_rows = _children_for_batch(batch, separate_child_groups)
        batch_seconds = _extract_duration_seconds(batch)
        completed_successful_runs = _successful_run_count(batch, child_rows)
        throughput_per_hour = _batch_throughput_per_hour(
            batch,
            completed_successful_runs=completed_successful_runs,
            batch_seconds=batch_seconds,
        )
        if throughput_per_hour is None:
            continue

        repeat = _extract_repeat(batch)
        batch_id = _extract_batch_id(batch)
        normalized_batch = {
            "batch_id": batch_id,
            "repeat": repeat,
            "workers": workers,
            "completed_successful_runs": completed_successful_runs,
            "batch_wall_clock_seconds": batch_seconds,
            "throughput_per_hour": throughput_per_hour,
        }
        successful_batches.append(normalized_batch)
        throughputs_by_worker[workers].append(throughput_per_hour)
        if batch_seconds is not None and batch_seconds > 0.0:
            batch_seconds_by_worker[workers].append(batch_seconds)
        child_seconds_by_worker[workers].extend(_successful_child_seconds(batch, child_rows))

    baseline_mean = _mean(throughputs_by_worker.get(1, []))
    worker_summaries = [
        _summarize_worker(
            workers=workers,
            throughputs=throughputs_by_worker[workers],
            batch_seconds=batch_seconds_by_worker[workers],
            child_seconds=child_seconds_by_worker[workers],
            baseline_mean=baseline_mean,
        )
        for workers in sorted(throughputs_by_worker)
    ]

    regression = _fit_ols(successful_batches)
    summary = _build_summary(
        raw_batch_count=len(batch_rows),
        successful_batches=successful_batches,
        worker_summaries=worker_summaries,
        baseline_mean=baseline_mean,
    )

    return {
        "successful_batches": successful_batches,
        "worker_summaries": worker_summaries,
        "summary": summary,
        "regression": regression,
    }


def write_report_outputs(analysis: Mapping[str, Any], output_root: Path) -> dict[str, Path]:
    """Write CSV, JSON, and plot artifacts at the output root."""

    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "results_csv": output_root / "parallel_scaling_results.csv",
        "summary_json": output_root / "parallel_scaling_summary.json",
        "regression_json": output_root / "parallel_scaling_regression.json",
        "throughput_plot": output_root / "parallel_scaling_throughput.png",
        "batch_time_plot": output_root / "parallel_scaling_batch_time.png",
    }

    _write_results_csv(paths["results_csv"], analysis["worker_summaries"])
    paths["summary_json"].write_text(json.dumps(analysis["summary"], indent=2) + "\n", encoding="utf-8")
    paths["regression_json"].write_text(json.dumps(analysis["regression"], indent=2) + "\n", encoding="utf-8")
    _write_plots(
        throughput_path=paths["throughput_plot"],
        batch_time_path=paths["batch_time_plot"],
        worker_summaries=analysis["worker_summaries"],
        regression=analysis["regression"],
    )
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze UK housing model parallel scaling raw artifacts.")
    parser.add_argument(
        "--raw-json",
        required=True,
        type=Path,
        help="Raw scaling artifact path. JSON is primary, but CSV is also accepted.",
    )
    parser.add_argument(
        "--output-root",
        required=True,
        type=Path,
        help="Directory where final report artifacts should be written.",
    )
    args = parser.parse_args(argv)

    payload = read_raw_results(args.raw_json)
    analysis = analyze_raw_payload(payload)
    write_report_outputs(analysis, args.output_root)
    return 0


def _read_raw_csv(path: Path) -> dict[str, list[dict[str, Any]]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [_coerce_csv_row(row) for row in csv.DictReader(handle)]

    batch_rows: list[dict[str, Any]] = []
    child_rows: list[dict[str, Any]] = []
    for row in rows:
        row_type = str(_get_any(row, ("rowType", "row_type", "type", "kind")) or "").strip().lower()
        if row_type in {"child", "child_result", "child_run", "run"}:
            child_rows.append(row)
        else:
            batch_rows.append(row)
    return {"batches": batch_rows, "children": child_rows}


def _coerce_csv_row(row: Mapping[str, str]) -> dict[str, Any]:
    return {key: _coerce_csv_value(value) for key, value in row.items()}


def _coerce_csv_value(value: str) -> Any:
    text = value.strip()
    if not text:
        return None
    lower = text.lower()
    if lower in {"true", "false"}:
        return lower == "true"
    try:
        if "." not in text and "e" not in lower:
            return int(text)
        return float(text)
    except ValueError:
        return text


def _extract_batch_rows(payload: Mapping[str, Any] | Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if isinstance(payload, Mapping):
        for key in SEPARATE_BATCH_KEYS:
            value = _get_any(payload, (key,))
            if isinstance(value, list):
                return [row for row in value if isinstance(row, Mapping)]
        if _extract_workers(payload) is not None:
            return [payload]
        results = _get_any(payload, ("results", "rows"))
        if isinstance(results, list):
            return [row for row in results if isinstance(row, Mapping) and _row_type(row) != "child"]
        return []

    return [row for row in payload if isinstance(row, Mapping) and _row_type(row) != "child"]


def _extract_separate_child_groups(
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, dict[Any, list[Mapping[str, Any]]]]:
    child_rows: list[Mapping[str, Any]] = []
    if isinstance(payload, Mapping):
        for key in SEPARATE_CHILD_KEYS:
            value = _get_any(payload, (key,))
            if isinstance(value, list):
                child_rows.extend(row for row in value if isinstance(row, Mapping))
        results = _get_any(payload, ("results", "rows"))
        if isinstance(results, list):
            child_rows.extend(row for row in results if isinstance(row, Mapping) and _row_type(row) == "child")
    else:
        child_rows.extend(row for row in payload if isinstance(row, Mapping) and _row_type(row) == "child")

    by_batch_id: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    by_worker_repeat: dict[Any, list[Mapping[str, Any]]] = defaultdict(list)
    for child in child_rows:
        batch_id = _extract_batch_id(child)
        if batch_id is not None:
            by_batch_id[batch_id].append(child)
        workers = _extract_workers(child)
        repeat = _extract_repeat(child)
        if workers is not None and repeat is not None:
            by_worker_repeat[(workers, repeat)].append(child)
    return {"by_batch_id": by_batch_id, "by_worker_repeat": by_worker_repeat}


def _children_for_batch(
    batch: Mapping[str, Any],
    separate_child_groups: Mapping[str, Mapping[Any, list[Mapping[str, Any]]]],
) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for key in NESTED_CHILD_KEYS:
        value = _get_any(batch, (key,))
        if isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, Mapping))

    batch_id = _extract_batch_id(batch)
    if batch_id is not None:
        rows.extend(separate_child_groups["by_batch_id"].get(batch_id, []))

    workers = _extract_workers(batch)
    repeat = _extract_repeat(batch)
    if workers is not None and repeat is not None:
        rows.extend(separate_child_groups["by_worker_repeat"].get((workers, repeat), []))
    return _deduplicate_rows(rows)


def _deduplicate_rows(rows: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    seen: set[int] = set()
    deduped: list[Mapping[str, Any]] = []
    for row in rows:
        marker = id(row)
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped


def _successful_run_count(batch: Mapping[str, Any], child_rows: Sequence[Mapping[str, Any]]) -> int:
    if child_rows:
        return sum(1 for child in child_rows if _is_successful_row(child))

    for key in RUN_COUNT_KEYS:
        value = _as_int(_get_any(batch, (key,)))
        if value is not None:
            return max(0, value)
    for key in FALLBACK_RUN_COUNT_KEYS:
        value = _get_any(batch, (key,))
        if isinstance(value, list):
            continue
        count = _as_int(value)
        if count is not None:
            return max(0, count)
    return 1 if _is_successful_row(batch) else 0


def _batch_throughput_per_hour(
    batch: Mapping[str, Any],
    *,
    completed_successful_runs: int,
    batch_seconds: float | None,
) -> float | None:
    if completed_successful_runs > 0 and batch_seconds is not None and batch_seconds > 0.0:
        return completed_successful_runs * 3600.0 / batch_seconds

    for key in THROUGHPUT_KEYS:
        value = _as_float(_get_any(batch, (key,)))
        if value is not None and value >= 0.0:
            return value
    return None


def _successful_child_seconds(batch: Mapping[str, Any], child_rows: Sequence[Mapping[str, Any]]) -> list[float]:
    seconds = [
        child_seconds
        for child in child_rows
        if _is_successful_row(child)
        for child_seconds in [_extract_duration_seconds(child)]
        if child_seconds is not None and child_seconds >= 0.0
    ]
    if seconds:
        return seconds

    for key in (
        "childWallClockSeconds",
        "child_wall_clock_seconds",
        "childDurationSeconds",
        "child_duration_seconds",
        "childDurationsSeconds",
        "child_durations_seconds",
    ):
        value = _get_any(batch, (key,))
        if isinstance(value, list):
            return [item for item in (_as_float(item) for item in value) if item is not None and item >= 0.0]
    return []


def _summarize_worker(
    *,
    workers: int,
    throughputs: Sequence[float],
    batch_seconds: Sequence[float],
    child_seconds: Sequence[float],
    baseline_mean: float | None,
) -> dict[str, Any]:
    throughput_ci = _ci95(throughputs)
    batch_ci = _ci95(batch_seconds)
    mean_throughput = _mean(throughputs)
    speedup = _safe_divide(mean_throughput, baseline_mean)
    return {
        "workers": workers,
        "successful_repeats": len(throughputs),
        "mean_throughput_per_hour": mean_throughput,
        "median_throughput_per_hour": _median(throughputs),
        "throughput_ci95_low": throughput_ci[0],
        "throughput_ci95_high": throughput_ci[1],
        "mean_batch_wall_clock_seconds": _mean(batch_seconds),
        "median_batch_wall_clock_seconds": _median(batch_seconds),
        "batch_wall_clock_p95_seconds": _percentile(batch_seconds, 95.0),
        "batch_wall_clock_ci95_low": batch_ci[0],
        "batch_wall_clock_ci95_high": batch_ci[1],
        "child_wall_clock_mean_seconds": _mean(child_seconds),
        "child_wall_clock_median_seconds": _median(child_seconds),
        "child_wall_clock_p95_seconds": _percentile(child_seconds, 95.0),
        "speedup_vs_1_worker": speedup,
        "scaling_efficiency": _safe_divide(speedup, float(workers)),
    }


def _build_summary(
    *,
    raw_batch_count: int,
    successful_batches: Sequence[Mapping[str, Any]],
    worker_summaries: Sequence[Mapping[str, Any]],
    baseline_mean: float | None,
) -> dict[str, Any]:
    best = max(
        worker_summaries,
        key=lambda row: float(row["mean_throughput_per_hour"] or float("-inf")),
        default=None,
    )
    return {
        "raw_batch_count": raw_batch_count,
        "successful_batch_count": len(successful_batches),
        "baseline_1_worker_mean_throughput_per_hour": baseline_mean,
        "workers": [row["workers"] for row in worker_summaries],
        "best_mean_throughput": None
        if best is None
        else {
            "workers": best["workers"],
            "mean_throughput_per_hour": best["mean_throughput_per_hour"],
        },
        "oversubscription_comparisons": _oversubscription_comparisons(worker_summaries),
    }


def _oversubscription_comparisons(worker_summaries: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    by_worker = {int(row["workers"]): row for row in worker_summaries}
    baseline = by_worker.get(20)
    comparisons: dict[str, dict[str, Any]] = {}
    for target_workers in (24, 32):
        target = by_worker.get(target_workers)
        key = str(target_workers)
        if baseline is None or target is None:
            comparisons[key] = {
                "available": False,
                "baseline_workers": 20,
                "target_workers": target_workers,
                "throughput_delta_vs_20": None,
                "throughput_ratio_vs_20": None,
                "efficiency_delta_vs_20": None,
            }
            continue

        target_mean = target["mean_throughput_per_hour"]
        baseline_mean = baseline["mean_throughput_per_hour"]
        comparisons[key] = {
            "available": True,
            "baseline_workers": 20,
            "target_workers": target_workers,
            "mean_throughput_per_hour": target_mean,
            "baseline_mean_throughput_per_hour": baseline_mean,
            "throughput_delta_vs_20": None
            if target_mean is None or baseline_mean is None
            else target_mean - baseline_mean,
            "throughput_ratio_vs_20": _safe_divide(target_mean, baseline_mean),
            "efficiency_delta_vs_20": None
            if target["scaling_efficiency"] is None or baseline["scaling_efficiency"] is None
            else target["scaling_efficiency"] - baseline["scaling_efficiency"],
        }
    return comparisons


def _fit_ols(successful_batches: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    points = [
        (float(row["workers"]), float(row["throughput_per_hour"]))
        for row in successful_batches
        if int(row["workers"]) <= 20
    ]
    included_workers = sorted({int(x_value) for x_value, _ in points})
    if len(points) < 2:
        return {
            "valid": False,
            "reason": "Need at least two successful repeat rows with workers <= 20.",
            "max_workers_included": 20,
            "n": len(points),
            "included_workers": included_workers,
            "slope": None,
            "intercept": None,
            "r_squared": None,
        }

    x_values = [point[0] for point in points]
    y_values = [point[1] for point in points]
    x_mean = statistics.fmean(x_values)
    y_mean = statistics.fmean(y_values)
    ss_xx = sum((x_value - x_mean) ** 2 for x_value in x_values)
    if ss_xx <= 0.0:
        return {
            "valid": False,
            "reason": "Need at least two distinct worker counts for OLS regression.",
            "max_workers_included": 20,
            "n": len(points),
            "included_workers": included_workers,
            "slope": None,
            "intercept": None,
            "r_squared": None,
        }

    ss_xy = sum((x_value - x_mean) * (y_value - y_mean) for x_value, y_value in points)
    slope = ss_xy / ss_xx
    intercept = y_mean - slope * x_mean
    predictions = [intercept + slope * x_value for x_value in x_values]
    ss_res = sum((y_value - prediction) ** 2 for y_value, prediction in zip(y_values, predictions))
    ss_tot = sum((y_value - y_mean) ** 2 for y_value in y_values)
    r_squared = 1.0 if ss_tot <= 0.0 else max(0.0, 1.0 - ss_res / ss_tot)

    return {
        "valid": True,
        "max_workers_included": 20,
        "n": len(points),
        "included_workers": included_workers,
        "slope": slope,
        "intercept": intercept,
        "r_squared": r_squared,
    }


def _write_results_csv(path: Path, worker_summaries: Sequence[Mapping[str, Any]]) -> None:
    fieldnames = [
        "workers",
        "successful_repeats",
        "mean_throughput_per_hour",
        "median_throughput_per_hour",
        "throughput_ci95_low",
        "throughput_ci95_high",
        "mean_batch_wall_clock_seconds",
        "median_batch_wall_clock_seconds",
        "batch_wall_clock_p95_seconds",
        "batch_wall_clock_ci95_low",
        "batch_wall_clock_ci95_high",
        "child_wall_clock_mean_seconds",
        "child_wall_clock_median_seconds",
        "child_wall_clock_p95_seconds",
        "speedup_vs_1_worker",
        "scaling_efficiency",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in worker_summaries:
            writer.writerow({field: _csv_cell(row.get(field)) for field in fieldnames})


def _write_plots(
    *,
    throughput_path: Path,
    batch_time_path: Path,
    worker_summaries: Sequence[Mapping[str, Any]],
    regression: Mapping[str, Any],
) -> None:
    if not HAS_MATPLOTLIB or plt is None:
        raise RuntimeError("matplotlib is required to write parallel scaling plots.")

    rows = sorted(worker_summaries, key=lambda row: int(row["workers"]))
    _write_throughput_plot(throughput_path, rows, regression)
    _write_batch_time_plot(batch_time_path, rows)


def _write_throughput_plot(path: Path, rows: Sequence[Mapping[str, Any]], regression: Mapping[str, Any]) -> None:
    x_values = [int(row["workers"]) for row in rows]
    y_values = [float(row["mean_throughput_per_hour"]) for row in rows]
    yerr = _error_bars(rows, "mean_throughput_per_hour", "throughput_ci95_low", "throughput_ci95_high")

    fig, axis = plt.subplots(figsize=(8, 5))
    axis.errorbar(x_values, y_values, yerr=yerr, fmt="o-", capsize=4, label="Mean throughput")
    one_worker = next((row for row in rows if int(row["workers"]) == 1), None)
    if one_worker is not None and one_worker["mean_throughput_per_hour"] is not None and x_values:
        baseline = float(one_worker["mean_throughput_per_hour"])
        ideal_x = [min(x_values), max(x_values)]
        axis.plot(ideal_x, [baseline * value for value in ideal_x], linestyle="--", color="#6B7280", label="Ideal linear")

    if regression.get("valid") and x_values:
        reg_x = [value for value in x_values if value <= 20]
        if reg_x:
            line_x = [min(reg_x), max(reg_x)]
            slope = float(regression["slope"])
            intercept = float(regression["intercept"])
            axis.plot(
                line_x,
                [intercept + slope * value for value in line_x],
                linestyle=":",
                color="#B45309",
                label="OLS <=20 workers",
            )

    _add_core_marker(axis, y_values)
    axis.set_xlabel("Parallel workers")
    axis.set_ylabel("Completed model runs per hour")
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def _write_batch_time_plot(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    x_values = [int(row["workers"]) for row in rows]
    y_values = [float(row["mean_batch_wall_clock_seconds"]) for row in rows]
    yerr = _error_bars(rows, "mean_batch_wall_clock_seconds", "batch_wall_clock_ci95_low", "batch_wall_clock_ci95_high")

    fig, axis = plt.subplots(figsize=(8, 5))
    axis.errorbar(x_values, y_values, yerr=yerr, fmt="o-", capsize=4, label="Mean batch time")
    _add_core_marker(axis, y_values)
    axis.set_xlabel("Parallel workers")
    axis.set_ylabel("Batch wall-clock seconds")
    axis.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def _add_core_marker(axis: Any, y_values: Sequence[float]) -> None:
    axis.axvline(20, linestyle="--", color="#991B1B", linewidth=1.0, label="20 cores")
    if y_values:
        y_min = min(y_values)
        y_max = max(y_values)
        y_text = y_min + 0.95 * (y_max - y_min) if y_max > y_min else y_max
        axis.text(20, y_text, "20 cores", rotation=90, va="top", ha="right", color="#991B1B")


def _error_bars(
    rows: Sequence[Mapping[str, Any]],
    mean_key: str,
    low_key: str,
    high_key: str,
) -> list[list[float]]:
    lower: list[float] = []
    upper: list[float] = []
    for row in rows:
        mean = float(row[mean_key])
        ci_low = row.get(low_key)
        ci_high = row.get(high_key)
        lower.append(0.0 if ci_low is None else max(0.0, mean - float(ci_low)))
        upper.append(0.0 if ci_high is None else max(0.0, float(ci_high) - mean))
    return [lower, upper]


def _row_type(row: Mapping[str, Any]) -> str | None:
    value = _get_any(row, ("rowType", "row_type", "type", "kind"))
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"child", "child_result", "child_run", "run"}:
        return "child"
    if text in {"batch", "batch_result", "batch_run"}:
        return "batch"
    return text


def _is_successful_row(row: Mapping[str, Any]) -> bool:
    status = _normalized_status(row)
    if status is None:
        return True
    if status in EXCLUDED_STATUSES:
        return False
    return status in SUCCESS_STATUSES


def _normalized_status(row: Mapping[str, Any]) -> str | None:
    value = _get_any(row, STATUS_KEYS)
    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "_")
    return text or None


def _extract_workers(row: Mapping[str, Any]) -> int | None:
    value = _as_int(_get_any(row, WORKER_KEYS))
    return value


def _extract_batch_id(row: Mapping[str, Any]) -> Any | None:
    value = _get_any(row, BATCH_ID_KEYS)
    return value if value not in ("", None) else None


def _extract_repeat(row: Mapping[str, Any]) -> Any | None:
    value = _get_any(row, REPEAT_KEYS)
    return value if value not in ("", None) else None


def _extract_duration_seconds(row: Mapping[str, Any]) -> float | None:
    for key in SECONDS_KEYS:
        value = _as_float(_get_any(row, (key,)))
        if value is not None:
            return value
    for key in MILLISECONDS_KEYS:
        value = _as_float(_get_any(row, (key,)))
        if value is not None:
            return value / 1000.0

    start = _parse_datetime(_get_any(row, START_KEYS))
    end = _parse_datetime(_get_any(row, END_KEYS))
    if start is not None and end is not None:
        return max(0.0, (end - start).total_seconds())
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _get_any(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    lower_lookup = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        lowered = key.lower()
        if lowered in lower_lookup:
            return lower_lookup[lowered]
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    number = _as_float(value)
    if number is None:
        return None
    return int(number)


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    if text.endswith("s"):
        text = text[:-1]
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _clean_numbers(values: Sequence[float]) -> list[float]:
    return [float(value) for value in values if math.isfinite(float(value))]


def _mean(values: Sequence[float]) -> float | None:
    clean = _clean_numbers(values)
    return statistics.fmean(clean) if clean else None


def _median(values: Sequence[float]) -> float | None:
    clean = _clean_numbers(values)
    return statistics.median(clean) if clean else None


def _ci95(values: Sequence[float]) -> tuple[float | None, float | None]:
    clean = _clean_numbers(values)
    if len(clean) < 2:
        return None, None
    mean = statistics.fmean(clean)
    half_width = 1.96 * statistics.stdev(clean) / math.sqrt(len(clean))
    return mean - half_width, mean + half_width


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    clean = sorted(_clean_numbers(values))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    rank = (len(clean) - 1) * percentile / 100.0
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return clean[lower_index]
    lower = clean[lower_index]
    upper = clean[upper_index]
    return lower + (upper - lower) * (rank - lower_index)


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    return value


if __name__ == "__main__":
    raise SystemExit(main())
