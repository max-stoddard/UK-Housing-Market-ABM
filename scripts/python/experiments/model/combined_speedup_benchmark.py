#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Orchestrate and analyze the combined cache plus parallel worker speedup benchmark.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.python.experiments.model import speed_experiment_common as common

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "uk-housing-matplotlib"))

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MATPLOTLIB = True
except ImportError:
    plt = None
    HAS_MATPLOTLIB = False


DEFAULT_SNAPSHOT = common.DEFAULT_SNAPSHOT
DEFAULT_BASE_MODE = common.DEFAULT_BASE_MODE
DEFAULT_TARGET_POPULATION = 5000
DEFAULT_N_STEPS = common.DEFAULT_N_STEPS
DEFAULT_SEED_COUNT = common.DEFAULT_SEED_COUNT
DEFAULT_PARALLEL_WORKERS = common.DEFAULT_PARALLEL_WORKERS
DEFAULT_ORDERING_SEED = 20260529
DEFAULT_JAVA_OPTIONS = ("-XX:ActiveProcessorCount=1",)
HEAVY_OUTPUT_PATTERN = re.compile(r"^Output-run\d+\.csv$")
WORKTREE_SPECIFIC_OUTPUT_FILES = {"config.properties"}
CELL_ORDER = ("A", "B", "C", "D")

CELL_DEFINITIONS = {
    "A": {
        "cache_enabled": False,
        "parallel_enabled": False,
        "source_variant": "cache-off",
        "workers": 1,
    },
    "B": {
        "cache_enabled": True,
        "parallel_enabled": False,
        "source_variant": "cache-on",
        "workers": 1,
    },
    "C": {
        "cache_enabled": False,
        "parallel_enabled": True,
        "source_variant": "cache-off",
        "workers": DEFAULT_PARALLEL_WORKERS,
    },
    "D": {
        "cache_enabled": True,
        "parallel_enabled": True,
        "source_variant": "cache-on",
        "workers": DEFAULT_PARALLEL_WORKERS,
    },
}

@dataclass(frozen=True)
class BenchmarkPlanEntry:
    block_index: int
    run_order_index: int
    cell: str
    cache_enabled: bool
    parallel_enabled: bool
    source_variant: str
    workers: int


def build_block_plan(
    *,
    blocks: int,
    ordering_seed: int,
    parallel_workers: int = DEFAULT_PARALLEL_WORKERS,
) -> list[BenchmarkPlanEntry]:
    _require_positive_int(blocks, "blocks")
    _require_int(ordering_seed, "ordering_seed")
    _require_positive_int(parallel_workers, "parallel_workers")

    rng = random.Random(ordering_seed)
    entries: list[BenchmarkPlanEntry] = []
    for block_index in range(1, blocks + 1):
        block_entries = [_entry_for_cell(block_index, cell, parallel_workers) for cell in CELL_ORDER]
        rng.shuffle(block_entries)
        for entry in block_entries:
            entries.append(
                BenchmarkPlanEntry(
                    block_index=entry.block_index,
                    run_order_index=len(entries) + 1,
                    cell=entry.cell,
                    cache_enabled=entry.cache_enabled,
                    parallel_enabled=entry.parallel_enabled,
                    source_variant=entry.source_variant,
                    workers=entry.workers,
                )
            )
    return entries


def build_dashboard_command(
    entry: BenchmarkPlanEntry,
    *,
    repo_root: Path,
    output_root: Path,
    phase: str = "full",
    snapshot: str = DEFAULT_SNAPSHOT,
    base_mode: str = DEFAULT_BASE_MODE,
    target_population: int = DEFAULT_TARGET_POPULATION,
    n_steps: int = DEFAULT_N_STEPS,
    seed_count: int = DEFAULT_SEED_COUNT,
    ordering_seed: int = DEFAULT_ORDERING_SEED,
    java_options: Sequence[str] = DEFAULT_JAVA_OPTIONS,
    confirm_expensive: bool = True,
) -> list[str]:
    return common.build_parallel_scaling_command(
        repo_root=repo_root,
        output_root=output_root,
        target_population=target_population,
        workers=entry.workers,
        seed_count=seed_count,
        n_steps=n_steps,
        snapshot=snapshot,
        base_mode=base_mode,
        phase=phase,
        ordering_seed=ordering_seed,
        policy_label=policy_label_for(entry),
        java_options=java_options,
        confirm_expensive=confirm_expensive,
    )


def policy_label_for(entry: BenchmarkPlanEntry) -> str:
    return f"{entry.source_variant}-w{entry.workers}-block{entry.block_index:03d}-{entry.cell}"


def analyze_blocks(rows: Sequence[Mapping[str, Any]], *, minimum_headline_blocks: int = 8) -> dict[str, Any]:
    valid_rows = [_normalize_batch_row(row) for row in rows if _is_successful_batch(row)]
    blocks = _complete_blocks(valid_rows)
    block_rows = [_block_summary(block_index, cells) for block_index, cells in blocks]

    cache_logs = [_log_ratio(cells["B"], cells["A"]) for _block_index, cells in blocks]
    parallel_logs = [_log_ratio(cells["C"], cells["A"]) for _block_index, cells in blocks]
    combined_logs = [_log_ratio(cells["D"], cells["A"]) for _block_index, cells in blocks]
    interaction_logs = [
        combined_logs[index] - cache_logs[index] - parallel_logs[index] for index in range(len(combined_logs))
    ]

    effects = {
        "cache_only": _effect_summary(cache_logs),
        "parallel_only": _effect_summary(parallel_logs),
        "combined": _effect_summary(combined_logs),
        "interaction": _effect_summary(interaction_logs),
    }
    combined_lower = effects["combined"]["lower_95_ci"]
    return {
        "schema_version": 1,
        "complete_block_count": len(blocks),
        "valid_batch_count": len(valid_rows),
        "headline_complete": len(blocks) >= minimum_headline_blocks and combined_lower is not None,
        "confirmatory_criterion_met": combined_lower is not None and combined_lower > 1.0,
        "effects": effects,
        "cell_summaries": _cell_summaries(valid_rows),
        "blocks": block_rows,
    }


def verify_seed_output_hashes(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_block: dict[int, dict[str, Mapping[int, tuple[tuple[str, str], ...]]]] = {}
    for record in records:
        block_index = int(record["block_index"])
        cell = str(record["cell"])
        cell_hashes: dict[int, tuple[tuple[str, str], ...]] = {}
        for child in record.get("children", []):
            if not _is_success_status(str(child.get("status", "succeeded"))):
                continue
            seed = int(child["seed"])
            output_path = Path(str(child.get("outputPath") or child.get("output_path")))
            cell_hashes[seed] = hash_output_tree(output_path)
        by_block.setdefault(block_index, {})[cell] = cell_hashes

    complete_blocks = 0
    checked_seed_count = 0
    for block_index, cells in sorted(by_block.items()):
        if not all(cell in cells for cell in CELL_ORDER):
            continue
        complete_blocks += 1
        seeds = sorted(set().union(*(set(seed_hashes) for seed_hashes in cells.values())))
        checked_seed_count += len(seeds)
        for seed in seeds:
            reference_cell = CELL_ORDER[0]
            if seed not in cells[reference_cell]:
                raise ValueError(f"Missing output hash for block {block_index} seed {seed} cell {reference_cell}")
            reference = cells[reference_cell][seed]
            for cell in CELL_ORDER[1:]:
                if seed not in cells[cell]:
                    raise ValueError(f"Missing output hash for block {block_index} seed {seed} cell {cell}")
                if cells[cell][seed] != reference:
                    raise ValueError(f"Output hash mismatch for block {block_index} seed {seed}: A vs {cell}")

    return {
        "schema_version": 1,
        "complete_blocks": complete_blocks,
        "checked_seed_count": checked_seed_count,
    }


def hash_output_tree(output_path: Path) -> tuple[tuple[str, str], ...]:
    if not output_path.exists():
        raise FileNotFoundError(f"Missing output path: {output_path}")

    entries: list[tuple[str, str]] = []
    for path in sorted(output_path.rglob("*")):
        if (
            not path.is_file()
            or HEAVY_OUTPUT_PATTERN.match(path.name)
            or path.name in WORKTREE_SPECIFIC_OUTPUT_FILES
        ):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append((path.relative_to(output_path).as_posix(), digest))
    return tuple(entries)


def read_batches_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [{key: _coerce_csv_value(value) for key, value in row.items()} for row in csv.DictReader(handle)]


def write_analysis_outputs(rows: Sequence[Mapping[str, Any]], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary = analyze_blocks(rows)
    paths = {
        "results_csv": output_root / "combined_speedup_results.csv",
        "blocks_csv": output_root / "combined_speedup_blocks.csv",
        "summary_json": output_root / "combined_speedup_summary.json",
        "factorial_model_json": output_root / "combined_speedup_factorial_model.json",
        "throughput_plot": output_root / "combined_speedup_throughput.png",
    }
    _write_results_csv(paths["results_csv"], summary["cell_summaries"])
    _write_blocks_csv(paths["blocks_csv"], summary["blocks"])
    paths["summary_json"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    paths["factorial_model_json"].write_text(
        json.dumps(
            {
                "schema_version": 1,
                "formula": "log(throughput) ~ cache_enabled * parallel_enabled + block",
                "effects": summary["effects"],
                "complete_block_count": summary["complete_block_count"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_throughput_plot(paths["throughput_plot"], summary["cell_summaries"], summary["effects"])
    return paths


def write_run_order(plan: Sequence[BenchmarkPlanEntry], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "csv": output_root / "combined_speedup_run_order.csv",
        "json": output_root / "combined_speedup_run_order.json",
    }
    with paths["csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(plan[0]).keys()) if plan else ["block_index"])
        writer.writeheader()
        for entry in plan:
            writer.writerow(asdict(entry))
    paths["json"].write_text(json.dumps([asdict(entry) for entry in plan], indent=2) + "\n", encoding="utf-8")
    return paths


def load_parallel_scaling_record(entry: BenchmarkPlanEntry, raw_json_path: Path) -> dict[str, Any]:
    batch = common.load_single_parallel_scaling_batch(raw_json_path)
    return {
        "block_index": entry.block_index,
        "run_order_index": entry.run_order_index,
        "cell": entry.cell,
        "cache_enabled": entry.cache_enabled,
        "parallel_enabled": entry.parallel_enabled,
        "source_variant": entry.source_variant,
        "workers": entry.workers,
        "status": batch.status,
        "completed_child_count": batch.completed_child_count,
        "failed_child_count": batch.failed_child_count,
        "canceled_child_count": batch.canceled_child_count,
        "wall_clock_seconds": batch.wall_clock_seconds,
        "throughput_runs_per_hour": batch.throughput_runs_per_hour,
        "children": batch.children,
        "raw_json_path": str(raw_json_path),
    }


def run_benchmark(args: argparse.Namespace) -> int:
    if args.phase == "full" and not args.confirm_expensive:
        raise ValueError("Full combined speedup benchmark is expensive; pass --confirm-expensive.")

    cache_on_root = args.cache_on_root.resolve()
    cache_off_root = args.cache_off_root.resolve()
    output_root = args.output_root.resolve()
    plan = build_block_plan(blocks=args.blocks, ordering_seed=args.ordering_seed)
    write_run_order(plan, output_root)

    if not args.skip_gates:
        for variant_root in (cache_off_root, cache_on_root):
            _run_checked(["./mvnw", "-q", "test"], cwd=variant_root)
            _run_checked(
                [
                    "bash",
                    "scripts/model/run-speed-regression.sh",
                    "--snapshot",
                    DEFAULT_SNAPSHOT,
                    "--mode",
                    "e2e-default-5k-s1",
                    "--contract",
                    "exact",
                    "--baseline-manifest",
                    "docs/model-speed/baselines/v0-e2e-default-5k-s1.exact.sha256",
                    "--repeat",
                    "3",
                    "--pin-cpu",
                    "0",
                    "--active-processor-count",
                    "1",
                    "--output-root",
                    str(output_root / "regressions" / variant_root.name),
                ],
                cwd=variant_root,
            )

    records: list[dict[str, Any]] = []
    for entry in plan:
        repo_root = cache_on_root if entry.source_variant == "cache-on" else cache_off_root
        cell_output_root = output_root / "combined-speedup" / entry.source_variant / f"block{entry.block_index:03d}-{entry.cell}"
        command = build_dashboard_command(
            entry,
            repo_root=repo_root,
            output_root=cell_output_root,
            phase=args.phase,
            ordering_seed=args.ordering_seed,
            confirm_expensive=args.confirm_expensive,
        )
        _run_checked(command, cwd=repo_root / "dashboard")
        records.append(load_parallel_scaling_record(entry, _latest_raw_json(cell_output_root)))

    verify_seed_output_hashes(records)
    _write_combined_batches_csv(output_root / "combined_speedup_batches.csv", records)
    write_analysis_outputs(records, output_root)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or analyze the combined cache/parallel speedup benchmark.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Write the randomized block/cell order.")
    plan_parser.add_argument("--blocks", type=int, default=10)
    plan_parser.add_argument("--ordering-seed", type=int, default=DEFAULT_ORDERING_SEED)
    plan_parser.add_argument("--output-root", required=True, type=Path)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze combined_speedup_batches.csv.")
    analyze_parser.add_argument("--batches-csv", required=True, type=Path)
    analyze_parser.add_argument("--output-root", required=True, type=Path)

    run_parser = subparsers.add_parser("run", help="Run prepared cache-on/cache-off worktrees.")
    run_parser.add_argument("--cache-on-root", required=True, type=Path)
    run_parser.add_argument("--cache-off-root", required=True, type=Path)
    run_parser.add_argument("--output-root", required=True, type=Path)
    run_parser.add_argument("--blocks", type=int, default=10)
    run_parser.add_argument("--ordering-seed", type=int, default=DEFAULT_ORDERING_SEED)
    run_parser.add_argument("--phase", choices=("pilot", "full"), default="full")
    run_parser.add_argument("--confirm-expensive", action="store_true")
    run_parser.add_argument("--skip-gates", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "plan":
        write_run_order(build_block_plan(blocks=args.blocks, ordering_seed=args.ordering_seed), args.output_root)
        return 0
    if args.command == "analyze":
        write_analysis_outputs(read_batches_csv(args.batches_csv), args.output_root)
        return 0
    if args.command == "run":
        return run_benchmark(args)
    raise AssertionError(f"Unhandled command: {args.command}")


def _entry_for_cell(block_index: int, cell: str, parallel_workers: int) -> BenchmarkPlanEntry:
    definition = dict(CELL_DEFINITIONS[cell])
    if definition["parallel_enabled"]:
        definition["workers"] = parallel_workers
    return BenchmarkPlanEntry(block_index=block_index, run_order_index=0, cell=cell, **definition)


def _complete_blocks(rows: Sequence[Mapping[str, Any]]) -> list[tuple[int, dict[str, float]]]:
    grouped: dict[int, dict[str, float]] = {}
    for row in rows:
        block_index = int(row["block_index"])
        cell = str(row["cell"])
        throughput = float(row["throughput_runs_per_hour"])
        if throughput <= 0.0:
            continue
        grouped.setdefault(block_index, {})[cell] = throughput
    return [(block_index, cells) for block_index, cells in sorted(grouped.items()) if all(cell in cells for cell in CELL_ORDER)]


def _block_summary(block_index: int, cells: Mapping[str, float]) -> dict[str, float | int]:
    cache_only = cells["B"] / cells["A"]
    parallel_only = cells["C"] / cells["A"]
    combined = cells["D"] / cells["A"]
    return {
        "block_index": block_index,
        "throughput_A": cells["A"],
        "throughput_B": cells["B"],
        "throughput_C": cells["C"],
        "throughput_D": cells["D"],
        "cache_only_speedup": cache_only,
        "parallel_only_speedup": parallel_only,
        "combined_speedup": combined,
        "interaction": combined / (cache_only * parallel_only),
    }


def _cell_summaries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for cell in CELL_ORDER:
        cell_rows = [row for row in rows if row["cell"] == cell and float(row["throughput_runs_per_hour"]) > 0.0]
        throughputs = [float(row["throughput_runs_per_hour"]) for row in cell_rows]
        definition = CELL_DEFINITIONS[cell]
        summaries.append(
            {
                "cell": cell,
                "cache_enabled": definition["cache_enabled"],
                "parallel_enabled": definition["parallel_enabled"],
                "workers": definition["workers"],
                "valid_batches": len(cell_rows),
                "geometric_mean_throughput_runs_per_hour": _geometric_mean(throughputs),
                "arithmetic_mean_throughput_runs_per_hour": statistics.mean(throughputs) if throughputs else None,
            }
        )
    return summaries


def _effect_summary(log_values: Sequence[float]) -> dict[str, Any]:
    return common.effect_summary_from_logs(log_values)


def _log_ratio(numerator: float, denominator: float) -> float:
    return math.log(numerator) - math.log(denominator)


def _geometric_mean(values: Sequence[float]) -> float | None:
    positive = [value for value in values if value > 0.0]
    if not positive:
        return None
    return math.exp(statistics.mean(math.log(value) for value in positive))


def _is_successful_batch(row: Mapping[str, Any]) -> bool:
    return _is_success_status(str(row.get("status", ""))) and float(row.get("throughput_runs_per_hour", 0.0) or 0.0) > 0.0


def _is_success_status(status: str) -> bool:
    return common.is_success_status(status)


def _normalize_batch_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "block_index": int(row["block_index"]),
        "cell": str(row["cell"]),
        "cache_enabled": _coerce_bool(row.get("cache_enabled")),
        "parallel_enabled": _coerce_bool(row.get("parallel_enabled")),
        "source_variant": str(row.get("source_variant", "")),
        "workers": int(row["workers"]),
        "status": str(row["status"]),
        "completed_child_count": int(row.get("completed_child_count", 0) or 0),
        "failed_child_count": int(row.get("failed_child_count", 0) or 0),
        "canceled_child_count": int(row.get("canceled_child_count", 0) or 0),
        "wall_clock_seconds": float(row.get("wall_clock_seconds", 0.0) or 0.0),
        "throughput_runs_per_hour": float(row["throughput_runs_per_hour"]),
    }


def _write_results_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _write_csv(path, rows, [
        "cell",
        "cache_enabled",
        "parallel_enabled",
        "workers",
        "valid_batches",
        "geometric_mean_throughput_runs_per_hour",
        "arithmetic_mean_throughput_runs_per_hour",
    ])


def _write_blocks_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _write_csv(path, rows, [
        "block_index",
        "throughput_A",
        "throughput_B",
        "throughput_C",
        "throughput_D",
        "cache_only_speedup",
        "parallel_only_speedup",
        "combined_speedup",
        "interaction",
    ])


def _write_combined_batches_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _write_csv(path, rows, [
        "block_index",
        "run_order_index",
        "cell",
        "cache_enabled",
        "parallel_enabled",
        "source_variant",
        "workers",
        "status",
        "completed_child_count",
        "failed_child_count",
        "canceled_child_count",
        "wall_clock_seconds",
        "throughput_runs_per_hour",
        "raw_json_path",
    ])


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]], headers: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_throughput_plot(
    path: Path,
    cell_summaries: Sequence[Mapping[str, Any]],
    effects: Mapping[str, Any],
) -> None:
    if not HAS_MATPLOTLIB:
        return
    labels = [f"{row['cell']} {'cache' if row['cache_enabled'] else 'no-cache'} {row['workers']}w" for row in cell_summaries]
    values = [row["geometric_mean_throughput_runs_per_hour"] or 0.0 for row in cell_summaries]
    fig, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar(labels, values, color=["#595959", "#2f7f6f", "#6b6b9f", "#1f6f9f"])
    axis.set_ylabel("Completed model runs per hour")
    axis.set_xlabel("Benchmark cell")
    axis.tick_params(axis="x", rotation=20)
    combined = effects["combined"]["estimate"]
    if combined is not None:
        axis.set_title(f"Combined D/A speedup: {combined:.3f}x")
    fig.tight_layout()
    fig.savefig(path, dpi=300)
    plt.close(fig)


def _latest_raw_json(output_root: Path) -> Path:
    return common.latest_parallel_scaling_raw_json(output_root)


def _run_checked(command: Sequence[str], *, cwd: Path) -> None:
    common.run_checked(command, cwd=cwd)


def _coerce_csv_value(value: str) -> Any:
    return common.coerce_csv_value(value)


def _coerce_bool(value: Any) -> bool:
    return common.coerce_bool(value)


def _require_positive_int(value: int, label: str) -> None:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer.")


def _require_int(value: int, label: str) -> None:
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")


if __name__ == "__main__":
    raise SystemExit(main())
