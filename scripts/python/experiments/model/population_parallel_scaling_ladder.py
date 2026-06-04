#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run and analyze population-size parallel worker scaling ladders.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.python.experiments.model import parallel_scaling_report
from scripts.python.experiments.model import speed_experiment_common as common

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "uk-housing-matplotlib"))

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MultipleLocator

    HAS_MATPLOTLIB = True
except ImportError:
    Line2D = None
    MultipleLocator = None
    plt = None
    HAS_MATPLOTLIB = False


DEFAULT_POPULATIONS = (5_000, 10_000, 20_000)
DEFAULT_WORKER_COUNTS = (1, 2, 4, 8, 12, 16, 20, 24, 32)
DEFAULT_REPEATS = 3
DEFAULT_POLICY_LABEL_PREFIX = "default-no-apc"
TENK_POPULATION = 10_000


@dataclass(frozen=True)
class PopulationLadderPlanEntry:
    run_order_index: int
    target_population: int
    worker_counts: tuple[int, ...]
    repeats: int
    seed_count: int


def build_population_ladder_plan(
    *,
    populations: Sequence[int] = DEFAULT_POPULATIONS,
    worker_counts: Sequence[int] = DEFAULT_WORKER_COUNTS,
    repeats: int = DEFAULT_REPEATS,
    seed_count: int = common.DEFAULT_SEED_COUNT,
    ordering_seed: int = common.DEFAULT_ORDERING_SEED,
) -> list[PopulationLadderPlanEntry]:
    del ordering_seed
    populations = tuple(int(value) for value in populations)
    worker_counts = tuple(int(value) for value in worker_counts)
    _require_positive_sequence(populations, "populations")
    _require_positive_sequence(worker_counts, "worker_counts")
    _require_positive_int(repeats, "repeats")
    _require_positive_int(seed_count, "seed_count")
    if seed_count < max(worker_counts):
        raise ValueError("seed_count must be at least the largest worker count.")

    return [
        PopulationLadderPlanEntry(
            run_order_index=index,
            target_population=population,
            worker_counts=worker_counts,
            repeats=repeats,
            seed_count=seed_count,
        )
        for index, population in enumerate(populations, start=1)
    ]


def build_dashboard_command(
    entry: PopulationLadderPlanEntry,
    *,
    repo_root: Path,
    output_root: Path,
    phase: str = "full",
    snapshot: str = common.DEFAULT_SNAPSHOT,
    base_mode: str = common.DEFAULT_BASE_MODE,
    n_steps: int = common.DEFAULT_N_STEPS,
    ordering_seed: int = common.DEFAULT_ORDERING_SEED,
    confirm_expensive: bool = True,
) -> list[str]:
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
        str(entry.target_population),
        "--n-steps",
        str(n_steps),
        "--seed-count",
        str(entry.seed_count),
        "--workers",
        ",".join(str(value) for value in entry.worker_counts),
        "--repeats",
        str(entry.repeats),
        "--ordering-seed",
        str(ordering_seed),
        "--policy-label",
        policy_label_for(entry),
        "--output-root",
        str(output_root),
    ]
    if phase == "full" and confirm_expensive:
        command.append("--confirm-expensive")
    return command


def policy_label_for(entry: PopulationLadderPlanEntry) -> str:
    return f"{DEFAULT_POLICY_LABEL_PREFIX}-pop{entry.target_population}"


def write_run_order(plan: Sequence[PopulationLadderPlanEntry], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "csv": output_root / "population_parallel_scaling_run_order.csv",
        "json": output_root / "population_parallel_scaling_run_order.json",
    }
    rows = [
        {
            **asdict(entry),
            "worker_counts": ",".join(str(value) for value in entry.worker_counts),
        }
        for entry in plan
    ]
    common.write_csv(
        paths["csv"],
        rows,
        ["run_order_index", "target_population", "worker_counts", "repeats", "seed_count"],
    )
    paths["json"].write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return paths


def load_population_records(raw_json_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
    workload = payload.get("workload", {})
    if not isinstance(workload, Mapping):
        raise ValueError(f"Raw JSON lacks workload metadata: {raw_json_path}")
    target_population = int(workload["targetPopulation"])
    seed_count = int(workload["seedCount"])
    rows: list[dict[str, Any]] = []
    for batch in payload.get("batches", []):
        if not isinstance(batch, Mapping):
            continue
        child_seconds = _successful_child_seconds(batch.get("children", []))
        rows.append(
            {
                "repeat_index": int(batch.get("repeatIndex", 0) or 0),
                "run_order_index": int(batch.get("runOrderIndex", 0) or 0),
                "target_population": target_population,
                "workers": int(batch["workerCount"]),
                "seed_count": seed_count,
                "status": str(batch.get("status", "")),
                "completed_child_count": int(batch.get("completedChildCount", 0) or 0),
                "failed_child_count": int(batch.get("failedChildCount", 0) or 0),
                "canceled_child_count": int(batch.get("canceledChildCount", 0) or 0),
                "wall_clock_seconds": float(batch.get("wallClockSeconds", 0.0) or 0.0),
                "throughput_runs_per_hour": float(batch.get("throughputRunsPerHour", 0.0) or 0.0),
                "child_mean_wall_clock_seconds": statistics.mean(child_seconds) if child_seconds else None,
                "child_median_wall_clock_seconds": statistics.median(child_seconds) if child_seconds else None,
                "child_p95_wall_clock_seconds": common.percentile_nearest_rank(child_seconds, 0.95),
                "raw_json_path": str(raw_json_path),
            }
        )
    return rows


def analyze_population_worker_ladder(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized_rows = [_normalize_batch_row(row) for row in rows]
    analyses: list[dict[str, Any]] = []
    for population in sorted({row["target_population"] for row in normalized_rows}):
        population_rows = [row for row in normalized_rows if row["target_population"] == population]
        analysis = parallel_scaling_report.analyze_raw_payload({"batches": [_batch_for_report(row) for row in population_rows]})
        analyses.append(
            {
                "target_population": population,
                "summary": analysis["summary"],
                "worker_summaries": analysis["worker_summaries"],
                "regression": analysis["regression"],
            }
        )

    return {
        "schema_version": 1,
        "target_populations": [row["target_population"] for row in analyses],
        "population_analyses": analyses,
        "summary_rows": _summary_rows(analyses),
        "result_rows": _result_rows(analyses),
        "usl_fit_rows": _usl_fit_rows(analyses),
        "tenk_worker_summary": _tenk_worker_summary(analyses),
    }


def write_analysis_outputs(rows: Sequence[Mapping[str, Any]], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    analysis = analyze_population_worker_ladder(rows)
    paths = {
        "results_csv": output_root / "population_parallel_scaling_results.csv",
        "usl_fit_csv": output_root / "population_parallel_scaling_usl_fit.csv",
        "summary_csv": output_root / "population_parallel_scaling_summary.csv",
        "tenk_worker_summary_csv": output_root / "population_parallel_scaling_10k_worker_summary.csv",
        "summary_json": output_root / "population_parallel_scaling_summary.json",
        "throughput_plot": output_root / "population_parallel_scaling_throughput.png",
    }
    common.write_csv(paths["results_csv"], analysis["result_rows"], _result_headers())
    common.write_csv(paths["usl_fit_csv"], analysis["usl_fit_rows"], _usl_fit_headers())
    common.write_csv(paths["summary_csv"], analysis["summary_rows"], _summary_headers())
    common.write_csv(paths["tenk_worker_summary_csv"], analysis["tenk_worker_summary"], _tenk_worker_headers())
    paths["summary_json"].write_text(
        json.dumps(
            {
                "schema_version": analysis["schema_version"],
                "target_populations": analysis["target_populations"],
                "population_analyses": analysis["population_analyses"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_throughput_plot(paths["throughput_plot"], analysis["population_analyses"])
    return paths


def write_batches_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    common.write_csv(path, rows, _batch_headers())


def run_ladder(args: argparse.Namespace) -> int:
    if args.phase == "full" and not args.confirm_expensive:
        raise ValueError("Full population parallel scaling ladder is expensive; pass --confirm-expensive.")

    repo_root = args.repo_root.resolve()
    output_root = args.output_root.resolve()
    plan = build_population_ladder_plan(
        populations=parse_int_list(args.populations, "populations"),
        worker_counts=parse_int_list(args.workers, "workers"),
        repeats=args.repeats,
        seed_count=args.seed_count,
        ordering_seed=args.ordering_seed,
    )
    write_run_order(plan, output_root)

    records: list[dict[str, Any]] = []
    for entry in plan:
        population_output_root = output_root / "population-parallel-scaling" / f"pop{entry.target_population}"
        command = build_dashboard_command(
            entry,
            repo_root=repo_root,
            output_root=population_output_root,
            phase=args.phase,
            snapshot=args.snapshot,
            base_mode=args.base_mode,
            n_steps=args.n_steps,
            ordering_seed=args.ordering_seed,
            confirm_expensive=args.confirm_expensive,
        )
        common.run_checked(command, cwd=repo_root / "dashboard")
        records.extend(load_population_records(common.latest_parallel_scaling_raw_json(population_output_root)))

    write_batches_csv(output_root / "population_parallel_scaling_batches.csv", records)
    write_analysis_outputs(records, output_root)
    return 0


def parse_int_list(raw: str | Sequence[int], label: str) -> tuple[int, ...]:
    if isinstance(raw, str):
        values = tuple(int(value.strip()) for value in raw.split(",") if value.strip())
    else:
        values = tuple(int(value) for value in raw)
    _require_positive_sequence(values, label)
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or analyze population parallel scaling ladders.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Write the planned population ladder commands.")
    plan_parser.add_argument("--populations", default=",".join(str(value) for value in DEFAULT_POPULATIONS))
    plan_parser.add_argument("--workers", default=",".join(str(value) for value in DEFAULT_WORKER_COUNTS))
    plan_parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    plan_parser.add_argument("--seed-count", type=int, default=common.DEFAULT_SEED_COUNT)
    plan_parser.add_argument("--ordering-seed", type=int, default=common.DEFAULT_ORDERING_SEED)
    plan_parser.add_argument("--output-root", required=True, type=Path)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze raw JSONs or a combined batches CSV.")
    analyze_parser.add_argument("--raw-json", action="append", default=[], type=Path)
    analyze_parser.add_argument("--batches-csv", type=Path)
    analyze_parser.add_argument("--output-root", required=True, type=Path)

    run_parser = subparsers.add_parser("run", help="Run the population worker ladders through the dashboard CLI.")
    run_parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    run_parser.add_argument("--output-root", required=True, type=Path)
    run_parser.add_argument("--snapshot", default=common.DEFAULT_SNAPSHOT)
    run_parser.add_argument("--base-mode", default=common.DEFAULT_BASE_MODE)
    run_parser.add_argument("--populations", default=",".join(str(value) for value in DEFAULT_POPULATIONS))
    run_parser.add_argument("--workers", default=",".join(str(value) for value in DEFAULT_WORKER_COUNTS))
    run_parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    run_parser.add_argument("--seed-count", type=int, default=common.DEFAULT_SEED_COUNT)
    run_parser.add_argument("--n-steps", type=int, default=common.DEFAULT_N_STEPS)
    run_parser.add_argument("--ordering-seed", type=int, default=common.DEFAULT_ORDERING_SEED)
    run_parser.add_argument("--phase", choices=("pilot", "full"), default="full")
    run_parser.add_argument("--confirm-expensive", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "plan":
        write_run_order(
            build_population_ladder_plan(
                populations=parse_int_list(args.populations, "populations"),
                worker_counts=parse_int_list(args.workers, "workers"),
                repeats=args.repeats,
                seed_count=args.seed_count,
                ordering_seed=args.ordering_seed,
            ),
            args.output_root,
        )
        return 0
    if args.command == "analyze":
        if args.batches_csv is not None and args.raw_json:
            raise ValueError("Use either --batches-csv or --raw-json, not both.")
        if args.batches_csv is None and not args.raw_json:
            raise ValueError("Analyze requires --batches-csv or at least one --raw-json.")
        rows = common.read_csv_rows(args.batches_csv) if args.batches_csv else [
            row
            for raw_json in args.raw_json
            for row in load_population_records(raw_json)
        ]
        write_analysis_outputs(rows, args.output_root)
        return 0
    if args.command == "run":
        return run_ladder(args)
    raise AssertionError(f"Unhandled command: {args.command}")


def _successful_child_seconds(children: Any) -> list[float]:
    if not isinstance(children, list):
        return []
    return [
        float(child["wallClockSeconds"])
        for child in children
        if isinstance(child, Mapping)
        and common.is_success_status(str(child.get("status", "")))
        and child.get("wallClockSeconds") is not None
    ]


def _normalize_batch_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "repeat_index": int(row.get("repeat_index", 0) or 0),
        "run_order_index": int(row.get("run_order_index", 0) or 0),
        "target_population": int(row["target_population"]),
        "workers": int(row["workers"]),
        "seed_count": int(row["seed_count"]),
        "status": str(row["status"]),
        "completed_child_count": int(row.get("completed_child_count", 0) or 0),
        "failed_child_count": int(row.get("failed_child_count", 0) or 0),
        "canceled_child_count": int(row.get("canceled_child_count", 0) or 0),
        "wall_clock_seconds": float(row.get("wall_clock_seconds", 0.0) or 0.0),
        "throughput_runs_per_hour": float(row.get("throughput_runs_per_hour", 0.0) or 0.0),
        "child_mean_wall_clock_seconds": _optional_float(row.get("child_mean_wall_clock_seconds")),
        "child_median_wall_clock_seconds": _optional_float(row.get("child_median_wall_clock_seconds")),
        "child_p95_wall_clock_seconds": _optional_float(row.get("child_p95_wall_clock_seconds")),
        "raw_json_path": str(row.get("raw_json_path", "")),
    }


def _batch_for_report(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "batch_id": f"pop{row['target_population']}-r{row['repeat_index']}-w{row['workers']}",
        "workers": row["workers"],
        "status": row["status"],
        "wall_clock_seconds": row["wall_clock_seconds"],
        "completed_child_count": row["completed_child_count"],
        "failed_child_count": row["failed_child_count"],
        "canceled_child_count": row["canceled_child_count"],
    }


def _result_rows(analyses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for population_analysis in analyses:
        population = int(population_analysis["target_population"])
        for worker in population_analysis["worker_summaries"]:
            rows.append(
                {
                    "target_population": population,
                    "workers": worker["workers"],
                    "successful_repeats": worker["successful_repeats"],
                    "mean_throughput_runs_per_hour": worker["mean_throughput_per_hour"],
                    "throughput_ci95_low": worker["throughput_ci95_low"],
                    "throughput_ci95_high": worker["throughput_ci95_high"],
                    "speedup_vs_1_worker": worker["speedup_vs_1_worker"],
                    "scaling_efficiency": worker["scaling_efficiency"],
                    "mean_batch_wall_clock_seconds": worker["mean_batch_wall_clock_seconds"],
                    "child_wall_clock_mean_seconds": worker["child_wall_clock_mean_seconds"],
                }
            )
    return rows


def _summary_rows(analyses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for population_analysis in analyses:
        population = int(population_analysis["target_population"])
        by_worker = {int(row["workers"]): row for row in population_analysis["worker_summaries"]}
        summary = population_analysis["summary"]
        regression = population_analysis["regression"]
        best = summary.get("best_mean_throughput") or {}
        row_20 = by_worker.get(20)
        row_24 = by_worker.get(24)
        row_32 = by_worker.get(32)
        throughput_20 = None if row_20 is None else row_20["mean_throughput_per_hour"]
        rows.append(
            {
                "target_population": population,
                "one_worker_mean_throughput_runs_per_hour": _worker_metric(by_worker, 1, "mean_throughput_per_hour"),
                "best_workers": best.get("workers"),
                "best_mean_throughput_runs_per_hour": best.get("mean_throughput_per_hour"),
                "throughput_20_workers": throughput_20,
                "throughput_ratio_24_vs_20": None
                if row_24 is None
                else _safe_divide(row_24["mean_throughput_per_hour"], throughput_20),
                "throughput_ratio_32_vs_20": None
                if row_32 is None
                else _safe_divide(row_32["mean_throughput_per_hour"], throughput_20),
                "contention_alpha": regression.get("contention_alpha"),
                "coherency_beta": regression.get("coherency_beta"),
                "r_squared": regression.get("r_squared"),
                "usl_included_workers": ",".join(str(worker) for worker in regression.get("included_workers", [])),
                "usl_included_successful_batch_rows": regression.get("included_successful_batch_rows"),
                "successful_batch_count": summary.get("successful_batch_count"),
            }
        )
    return rows


def _usl_fit_rows(analyses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for population_analysis in analyses:
        population = int(population_analysis["target_population"])
        regression = population_analysis["regression"]
        included_workers = {int(worker) for worker in regression.get("included_workers", [])}
        fitted_values = regression.get("fitted_values", {})
        if not isinstance(fitted_values, Mapping):
            continue
        for raw_workers, fitted in sorted(fitted_values.items(), key=lambda item: int(item[0])):
            if not isinstance(fitted, Mapping):
                continue
            workers = int(raw_workers)
            rows.append(
                {
                    "target_population": population,
                    "workers": workers,
                    "included_in_fit": workers in included_workers,
                    "fitted_throughput_per_hour": fitted.get("fitted_throughput_per_hour"),
                    "extrapolation": fitted.get("extrapolation"),
                    "contention_alpha": regression.get("contention_alpha"),
                    "coherency_beta": regression.get("coherency_beta"),
                    "r_squared": regression.get("r_squared"),
                }
            )
    return rows


def _tenk_worker_summary(analyses: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    tenk = next((analysis for analysis in analyses if int(analysis["target_population"]) == TENK_POPULATION), None)
    if tenk is None:
        return []
    rows = []
    previous_workers: int | None = None
    previous_tput: float | None = None
    for worker in sorted(tenk["worker_summaries"], key=lambda row: int(row["workers"])):
        workers = int(worker["workers"])
        tput = worker["mean_throughput_per_hour"]
        marginal_gain = None
        if previous_workers is not None and previous_tput is not None and tput is not None:
            marginal_gain = (float(tput) - previous_tput) / (workers - previous_workers)
        rows.append(
            {
                "workers": workers,
                "tput": tput,
                "tput_ci95_low": worker["throughput_ci95_low"],
                "tput_ci95_high": worker["throughput_ci95_high"],
                "speedup": worker["speedup_vs_1_worker"],
                "efficiency": worker["scaling_efficiency"],
                "marginal_gain": marginal_gain,
            }
        )
        previous_workers = workers
        previous_tput = None if tput is None else float(tput)
    return rows


def _write_throughput_plot(path: Path, analyses: Sequence[Mapping[str, Any]]) -> None:
    if not HAS_MATPLOTLIB or plt is None or Line2D is None:
        return

    colors = {
        5_000: "#2563EB",
        10_000: "#B45309",
        20_000: "#2F7F6F",
    }
    fallback_colors = ["#2563EB", "#B45309", "#2F7F6F", "#7C3AED", "#DC2626"]
    fig, axis = plt.subplots(figsize=(8, 5))
    all_y_values: list[float] = []
    all_x_values: list[int] = []

    for index, population_analysis in enumerate(analyses):
        population = int(population_analysis["target_population"])
        rows = sorted(population_analysis["worker_summaries"], key=lambda row: int(row["workers"]))
        x_values = [int(row["workers"]) for row in rows]
        y_values = [float(row["mean_throughput_per_hour"]) for row in rows if row["mean_throughput_per_hour"] is not None]
        all_x_values.extend(x_values)
        all_y_values.extend(y_values)
        color = colors.get(population, fallback_colors[index % len(fallback_colors)])
        yerr = parallel_scaling_report._error_bars(
            rows,
            "mean_throughput_per_hour",
            "throughput_ci95_low",
            "throughput_ci95_high",
        )
        axis.errorbar(
            x_values,
            [float(row["mean_throughput_per_hour"]) for row in rows],
            yerr=yerr,
            fmt="o-",
            capsize=4,
            color=color,
            label=f"{population:,} households",
        )
        parallel_scaling_report._plot_usl_fit(
            axis,
            regression=population_analysis["regression"],
            color=color,
            label="_nolegend_",
            x_max=max(x_values) if x_values else None,
        )

    axis.axvline(
        20,
        color="#595959",
        linestyle="--",
        linewidth=1.2,
        alpha=0.75,
    )
    _configure_axes(axis, all_x_values, all_y_values)
    axis.set_xlabel("Parallel workers")
    axis.set_ylabel("Completed model runs per hour")

    first_legend = axis.legend(title="Target population", loc="upper left")
    axis.add_artist(first_legend)
    reference_handles = [
        Line2D([0], [0], color="#595959", linestyle="--", linewidth=1.2, label="20 logical processors"),
        Line2D([0], [0], color="#595959", linestyle=":", linewidth=1.4, label="USL fit"),
    ]
    axis.legend(handles=reference_handles, title="Reference", loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def _configure_axes(axis: Any, x_values: Sequence[int], y_values: Sequence[float]) -> None:
    axis.set_xlim(left=0, right=(max(x_values) + 1 if x_values else 33))
    max_y = max(y_values) if y_values else 1.0
    y_major = _nice_y_major(max_y)
    y_minor = y_major / 5.0
    axis.xaxis.set_major_locator(MultipleLocator(5))
    axis.xaxis.set_minor_locator(MultipleLocator(1))
    axis.yaxis.set_major_locator(MultipleLocator(y_major))
    axis.yaxis.set_minor_locator(MultipleLocator(y_minor))
    axis.set_axisbelow(True)
    axis.grid(True, which="major", color="#D1D5DB", linewidth=0.7, alpha=0.7)
    axis.grid(True, which="minor", color="#E5E7EB", linewidth=0.4, alpha=0.45)


def _nice_y_major(max_y: float) -> float:
    if max_y <= 500:
        return 100
    if max_y <= 1_000:
        return 200
    if max_y <= 2_500:
        return 500
    if max_y <= 5_000:
        return 1_000
    return 2_000


def _worker_metric(by_worker: Mapping[int, Mapping[str, Any]], workers: int, metric: str) -> Any:
    row = by_worker.get(workers)
    return None if row is None else row.get(metric)


def _safe_divide(numerator: Any, denominator: Any) -> float | None:
    if numerator is None or denominator is None:
        return None
    denominator = float(denominator)
    if denominator == 0.0:
        return None
    return float(numerator) / denominator


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    value = float(value)
    if math.isnan(value):
        return None
    return value


def _batch_headers() -> list[str]:
    return [
        "repeat_index",
        "run_order_index",
        "target_population",
        "workers",
        "seed_count",
        "status",
        "completed_child_count",
        "failed_child_count",
        "canceled_child_count",
        "wall_clock_seconds",
        "throughput_runs_per_hour",
        "child_mean_wall_clock_seconds",
        "child_median_wall_clock_seconds",
        "child_p95_wall_clock_seconds",
        "raw_json_path",
    ]


def _result_headers() -> list[str]:
    return [
        "target_population",
        "workers",
        "successful_repeats",
        "mean_throughput_runs_per_hour",
        "throughput_ci95_low",
        "throughput_ci95_high",
        "speedup_vs_1_worker",
        "scaling_efficiency",
        "mean_batch_wall_clock_seconds",
        "child_wall_clock_mean_seconds",
    ]


def _summary_headers() -> list[str]:
    return [
        "target_population",
        "one_worker_mean_throughput_runs_per_hour",
        "best_workers",
        "best_mean_throughput_runs_per_hour",
        "throughput_20_workers",
        "throughput_ratio_24_vs_20",
        "throughput_ratio_32_vs_20",
        "contention_alpha",
        "coherency_beta",
        "r_squared",
        "usl_included_workers",
        "usl_included_successful_batch_rows",
        "successful_batch_count",
    ]


def _usl_fit_headers() -> list[str]:
    return [
        "target_population",
        "workers",
        "included_in_fit",
        "fitted_throughput_per_hour",
        "extrapolation",
        "contention_alpha",
        "coherency_beta",
        "r_squared",
    ]


def _tenk_worker_headers() -> list[str]:
    return [
        "workers",
        "tput",
        "tput_ci95_low",
        "tput_ci95_high",
        "speedup",
        "efficiency",
        "marginal_gain",
    ]


def _require_positive_sequence(values: Sequence[int], label: str) -> None:
    if not values:
        raise ValueError(f"{label} must not be empty.")
    for value in values:
        _require_positive_int(value, label)


def _require_positive_int(value: int, label: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer.")


if __name__ == "__main__":
    raise SystemExit(main())
