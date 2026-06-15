#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run and analyze the rental-income cache speedup population ladder.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
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
    from matplotlib.ticker import MultipleLocator

    HAS_MATPLOTLIB = True
except ImportError:
    MultipleLocator = None
    plt = None
    HAS_MATPLOTLIB = False


DEFAULT_POPULATIONS = (5_000, 10_000, 20_000, 35_000, 50_000)
DEFAULT_BLOCKS = 5
DEFAULT_SEEDS = tuple(range(1, 41))
DEFAULT_PILOT_SEEDS = (1,)
DEFAULT_SEQUENTIAL_WORKERS = 1
DEFAULT_EXPERIMENT_1_MAX_HOURS = 10.0
DEFAULT_EXPERIMENT_1_BUFFER_FRACTION = 0.15
DEFAULT_EXPERIMENT_1_MIN_SEEDS = 25
VARIANTS = ("cache-off", "cache-on")


@dataclass(frozen=True)
class PopulationLadderPlanEntry:
    block_index: int
    run_order_index: int
    target_population: int
    cache_enabled: bool
    source_variant: str
    workers: int
    seed_count: int


@dataclass(frozen=True)
class SequentialPairPlanEntry:
    pair_order_index: int
    run_order_index: int
    target_population: int
    seed: int
    cache_enabled: bool
    source_variant: str


def build_population_ladder_plan(
    *,
    populations: Sequence[int] = DEFAULT_POPULATIONS,
    blocks: int = DEFAULT_BLOCKS,
    ordering_seed: int = common.DEFAULT_ORDERING_SEED,
    workers: int = common.DEFAULT_PARALLEL_WORKERS,
    seed_count: int = common.DEFAULT_SEED_COUNT,
) -> list[PopulationLadderPlanEntry]:
    _require_positive_sequence(populations, "populations")
    _require_positive_int(blocks, "blocks")
    _require_positive_int(workers, "workers")
    _require_positive_int(seed_count, "seed_count")

    rng = random.Random(ordering_seed)
    entries: list[PopulationLadderPlanEntry] = []
    for block_index in range(1, blocks + 1):
        block_entries = [
            PopulationLadderPlanEntry(
                block_index=block_index,
                run_order_index=0,
                target_population=population,
                cache_enabled=variant == "cache-on",
                source_variant=variant,
                workers=workers,
                seed_count=seed_count,
            )
            for population in populations
            for variant in VARIANTS
        ]
        rng.shuffle(block_entries)
        for entry in block_entries:
            entries.append(
                PopulationLadderPlanEntry(
                    block_index=entry.block_index,
                    run_order_index=len(entries) + 1,
                    target_population=entry.target_population,
                    cache_enabled=entry.cache_enabled,
                    source_variant=entry.source_variant,
                    workers=entry.workers,
                    seed_count=entry.seed_count,
                )
            )
    return entries


def build_sequential_paired_plan(
    *,
    populations: Sequence[int] = DEFAULT_POPULATIONS,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    ordering_seed: int = common.DEFAULT_ORDERING_SEED,
) -> list[SequentialPairPlanEntry]:
    populations = tuple(int(population) for population in populations)
    seeds = tuple(int(seed) for seed in seeds)
    _require_positive_sequence(populations, "populations")
    _require_positive_sequence(seeds, "seeds")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must not contain duplicates.")

    rng = random.Random(ordering_seed)
    pairs = [(population, seed) for population in populations for seed in seeds]
    rng.shuffle(pairs)

    entries: list[SequentialPairPlanEntry] = []
    for pair_order_index, (population, seed) in enumerate(pairs, start=1):
        pair_variants = list(VARIANTS)
        rng.shuffle(pair_variants)
        for variant in pair_variants:
            entries.append(
                SequentialPairPlanEntry(
                    pair_order_index=pair_order_index,
                    run_order_index=len(entries) + 1,
                    target_population=population,
                    seed=seed,
                    cache_enabled=variant == "cache-on",
                    source_variant=variant,
                )
            )
    return entries


def write_run_order(plan: Sequence[PopulationLadderPlanEntry | SequentialPairPlanEntry], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    paths = {
        "csv": output_root / "cache_population_ladder_run_order.csv",
        "json": output_root / "cache_population_ladder_run_order.json",
    }
    headers = list(asdict(plan[0]).keys()) if plan else ["block_index"]
    with paths["csv"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for entry in plan:
            writer.writerow(asdict(entry))
    paths["json"].write_text(json.dumps([asdict(entry) for entry in plan], indent=2) + "\n", encoding="utf-8")
    return paths


def build_population_ladder_command(
    entry: PopulationLadderPlanEntry,
    *,
    repo_root: Path,
    output_root: Path,
    phase: str = "full",
    snapshot: str = common.DEFAULT_SNAPSHOT,
    base_mode: str = common.DEFAULT_BASE_MODE,
    n_steps: int = common.DEFAULT_N_STEPS,
    ordering_seed: int = common.DEFAULT_ORDERING_SEED,
    java_options: Sequence[str] = (),
    confirm_expensive: bool = True,
) -> list[str]:
    return common.build_parallel_scaling_command(
        repo_root=repo_root,
        output_root=output_root,
        target_population=entry.target_population,
        workers=entry.workers,
        seed_count=entry.seed_count,
        n_steps=n_steps,
        snapshot=snapshot,
        base_mode=base_mode,
        phase=phase,
        ordering_seed=ordering_seed,
        policy_label=policy_label_for(entry),
        java_options=java_options,
        confirm_expensive=confirm_expensive,
    )


def build_sequential_ladder_command(
    entry: SequentialPairPlanEntry,
    *,
    repo_root: Path,
    output_root: Path,
    phase: str = "full",
    snapshot: str = common.DEFAULT_SNAPSHOT,
    base_mode: str = common.DEFAULT_BASE_MODE,
    n_steps: int = common.DEFAULT_N_STEPS,
    ordering_seed: int = common.DEFAULT_ORDERING_SEED,
    java_options: Sequence[str] = (),
    confirm_expensive: bool = True,
) -> list[str]:
    return common.build_parallel_scaling_command(
        repo_root=repo_root,
        output_root=output_root,
        target_population=entry.target_population,
        workers=DEFAULT_SEQUENTIAL_WORKERS,
        seed_count=1,
        seeds=(entry.seed,),
        n_steps=n_steps,
        snapshot=snapshot,
        base_mode=base_mode,
        phase=phase,
        ordering_seed=ordering_seed,
        policy_label=sequential_policy_label_for(entry),
        java_options=java_options,
        confirm_expensive=confirm_expensive,
    )


def policy_label_for(entry: PopulationLadderPlanEntry) -> str:
    return f"{entry.source_variant}-pop{entry.target_population}-w{entry.workers}-block{entry.block_index:03d}"


def sequential_policy_label_for(entry: SequentialPairPlanEntry) -> str:
    return f"{entry.source_variant}-pop{entry.target_population}-seed{entry.seed}-pair{entry.pair_order_index:03d}"


def load_population_ladder_record(entry: PopulationLadderPlanEntry, raw_json_path: Path) -> dict[str, Any]:
    batch = common.load_single_parallel_scaling_batch(raw_json_path)
    return {
        "block_index": entry.block_index,
        "run_order_index": entry.run_order_index,
        "target_population": entry.target_population,
        "cache_enabled": entry.cache_enabled,
        "source_variant": entry.source_variant,
        "workers": entry.workers,
        "seed_count": entry.seed_count,
        "status": batch.status,
        "completed_child_count": batch.completed_child_count,
        "failed_child_count": batch.failed_child_count,
        "canceled_child_count": batch.canceled_child_count,
        "wall_clock_seconds": batch.wall_clock_seconds,
        "throughput_runs_per_hour": batch.throughput_runs_per_hour,
        "child_mean_wall_clock_seconds": batch.child_mean_wall_clock_seconds,
        "child_median_wall_clock_seconds": batch.child_median_wall_clock_seconds,
        "child_p95_wall_clock_seconds": batch.child_p95_wall_clock_seconds,
        "raw_json_path": str(raw_json_path),
    }


def load_sequential_ladder_record(entry: SequentialPairPlanEntry, raw_json_path: Path) -> dict[str, Any]:
    batch = common.load_single_parallel_scaling_batch(raw_json_path)
    if batch.child_mean_wall_clock_seconds is None:
        run_wall_clock_seconds = None
    else:
        run_wall_clock_seconds = float(batch.child_mean_wall_clock_seconds)
    return {
        "pair_order_index": entry.pair_order_index,
        "run_order_index": entry.run_order_index,
        "target_population": entry.target_population,
        "seed": entry.seed,
        "cache_enabled": entry.cache_enabled,
        "source_variant": entry.source_variant,
        "status": batch.status,
        "run_wall_clock_seconds": run_wall_clock_seconds,
        "batch_wall_clock_seconds": batch.wall_clock_seconds,
        "raw_json_path": str(raw_json_path),
    }


def analyze_population_ladder(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid_rows = [_normalize_batch_row(row) for row in rows if _is_successful_batch(row)]
    complete_pairs = _complete_population_block_pairs(valid_rows)
    block_rows = [_population_block_summary(block_index, population, cells) for block_index, population, cells in complete_pairs]
    population_summaries = [
        _population_summary(population, [row for row in block_rows if row["target_population"] == population])
        for population in sorted({row["target_population"] for row in block_rows})
    ]
    return {
        "schema_version": 1,
        "valid_batch_count": len(valid_rows),
        "complete_population_block_count": len(block_rows),
        "population_summaries": population_summaries,
        "blocks": block_rows,
    }


def analyze_sequential_paired_runs(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid_rows = [_normalize_sequential_row(row) for row in rows if _is_successful_sequential_row(row)]
    grouped: dict[tuple[int, int], dict[str, Mapping[str, Any]]] = {}
    for row in valid_rows:
        key = (int(row["target_population"]), int(row["seed"]))
        grouped.setdefault(key, {})[str(row["source_variant"])] = row

    pair_rows: list[dict[str, Any]] = []
    incomplete_pairs: list[dict[str, Any]] = []
    for (population, seed), cells in sorted(grouped.items()):
        missing = [variant for variant in VARIANTS if variant not in cells]
        if missing:
            incomplete_pairs.append(
                {
                    "target_population": population,
                    "seed": seed,
                    "missing_variants": ",".join(missing),
                    "present_variants": ",".join(sorted(cells)),
                }
            )
            continue
        cache_off = cells["cache-off"]
        cache_on = cells["cache-on"]
        off_seconds = float(cache_off["run_wall_clock_seconds"])
        on_seconds = float(cache_on["run_wall_clock_seconds"])
        log_speedup = math.log(off_seconds / on_seconds)
        pair_rows.append(
            {
                "target_population": population,
                "seed": seed,
                "cache_off_seconds": off_seconds,
                "cache_on_seconds": on_seconds,
                "raw_speedup": off_seconds / on_seconds,
                "log_speedup": log_speedup,
            }
        )

    population_summaries = [
        _sequential_population_summary(population, [row for row in pair_rows if row["target_population"] == population])
        for population in sorted({row["target_population"] for row in pair_rows})
    ]
    return {
        "schema_version": 1,
        "valid_run_count": len(valid_rows),
        "complete_pair_count": len(pair_rows),
        "incomplete_pair_count": len(incomplete_pairs),
        "population_summaries": population_summaries,
        "pairs": pair_rows,
        "incomplete_pairs": incomplete_pairs,
    }


def recommend_sequential_seed_count(
    rows: Sequence[Mapping[str, Any]],
    *,
    target_seed_count: int = 40,
    max_hours: float = DEFAULT_EXPERIMENT_1_MAX_HOURS,
    buffer_fraction: float = DEFAULT_EXPERIMENT_1_BUFFER_FRACTION,
    min_seed_count: int = DEFAULT_EXPERIMENT_1_MIN_SEEDS,
) -> dict[str, Any]:
    _require_positive_int(target_seed_count, "target_seed_count")
    _require_positive_int(min_seed_count, "min_seed_count")
    if max_hours <= 0.0:
        raise ValueError("max_hours must be positive.")
    if buffer_fraction < 0.0:
        raise ValueError("buffer_fraction must be non-negative.")

    analysis = analyze_sequential_paired_runs(rows)
    pilot_pair_seconds = sum(
        float(row["cache_off_seconds"]) + float(row["cache_on_seconds"])
        for row in analysis["pairs"]
    )
    if pilot_pair_seconds <= 0.0:
        safe_seed_count = 0
    else:
        safe_seed_count = math.floor(max_hours * 3600.0 / (pilot_pair_seconds * (1.0 + buffer_fraction)))
    recommended_seed_count = min(target_seed_count, safe_seed_count)
    estimated_full_run_hours = pilot_pair_seconds * recommended_seed_count / 3600.0
    estimated_full_run_hours_with_buffer = estimated_full_run_hours * (1.0 + buffer_fraction)
    return {
        "target_seed_count": target_seed_count,
        "recommended_seed_count": recommended_seed_count,
        "max_hours": max_hours,
        "buffer_fraction": buffer_fraction,
        "min_seed_count": min_seed_count,
        "pilot_pair_seconds": pilot_pair_seconds,
        "estimated_full_run_hours": estimated_full_run_hours,
        "estimated_full_run_hours_with_buffer": estimated_full_run_hours_with_buffer,
        "launch_recommended": recommended_seed_count >= min_seed_count,
        "analysis": analysis,
    }


def write_analysis_outputs(rows: Sequence[Mapping[str, Any]], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary = analyze_population_ladder(rows)
    paths = {
        "by_population_csv": output_root / "cache_population_ladder_by_population.csv",
        "blocks_csv": output_root / "cache_population_ladder_blocks.csv",
        "summary_json": output_root / "cache_population_ladder_summary.json",
        "runtime_plot": output_root / "cache_population_ladder_runtime.png",
        "speedup_plot": output_root / "cache_population_ladder_speedup.png",
    }
    common.write_csv(paths["by_population_csv"], summary["population_summaries"], _population_summary_headers())
    common.write_csv(paths["blocks_csv"], summary["blocks"], _block_summary_headers())
    paths["summary_json"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    _write_plots(paths["runtime_plot"], paths["speedup_plot"], summary["population_summaries"])
    return paths


def write_sequential_analysis_outputs(rows: Sequence[Mapping[str, Any]], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary = analyze_sequential_paired_runs(rows)
    paths = {
        "timing_csv": output_root / "cache_population_ladder_timing.csv",
        "pairs_csv": output_root / "cache_population_ladder_pairs.csv",
        "by_population_csv": output_root / "cache_population_ladder_by_population.csv",
        "incomplete_pairs_csv": output_root / "cache_population_ladder_incomplete_pairs.csv",
        "summary_json": output_root / "cache_population_ladder_summary.json",
        "runtime_plot": output_root / "cache_population_ladder_runtime.png",
        "speedup_plot": output_root / "cache_population_ladder_speedup.png",
    }
    common.write_csv(paths["timing_csv"], [_normalize_sequential_row(row) for row in rows], _sequential_timing_headers())
    common.write_csv(paths["pairs_csv"], summary["pairs"], _sequential_pair_headers())
    common.write_csv(paths["by_population_csv"], summary["population_summaries"], _sequential_population_headers())
    common.write_csv(paths["incomplete_pairs_csv"], summary["incomplete_pairs"], _incomplete_pair_headers())
    paths["summary_json"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    _write_sequential_plots(paths["runtime_plot"], paths["speedup_plot"], summary["population_summaries"])
    return paths


def write_sequential_pilot_outputs(rows: Sequence[Mapping[str, Any]], output_root: Path) -> dict[str, Path]:
    paths = write_sequential_analysis_outputs(rows, output_root)
    recommendation = recommend_sequential_seed_count(rows)
    recommendation_path = output_root / "cache_population_ladder_pilot_recommendation.json"
    recommendation_path.write_text(json.dumps(recommendation, indent=2) + "\n", encoding="utf-8")
    return {**paths, "pilot_recommendation_json": recommendation_path}


def write_batches_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    common.write_csv(path, rows, _batch_headers())


def run_ladder(args: argparse.Namespace) -> int:
    if args.phase == "full" and not args.confirm_expensive:
        raise ValueError("Full cache population ladder is expensive; pass --confirm-expensive.")

    cache_on_root = args.cache_on_root.resolve()
    cache_off_root = args.cache_off_root.resolve()
    output_root = args.output_root.resolve()
    populations = parse_populations(args.populations)
    plan = build_population_ladder_plan(
        populations=populations,
        blocks=args.blocks,
        ordering_seed=args.ordering_seed,
        workers=args.workers,
        seed_count=args.seed_count,
    )
    write_run_order(plan, output_root)

    if not args.skip_gates:
        for variant_root in (cache_off_root, cache_on_root):
            common.run_checked(["./mvnw", "-q", "test"], cwd=variant_root)
            common.run_checked(
                [
                    "bash",
                    "scripts/model/run-speed-regression.sh",
                    "--snapshot",
                    common.DEFAULT_SNAPSHOT,
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
        cell_output_root = (
            output_root
            / "cache-population-ladder"
            / entry.source_variant
            / f"pop{entry.target_population}"
            / f"block{entry.block_index:03d}"
        )
        command = build_population_ladder_command(
            entry,
            repo_root=repo_root,
            output_root=cell_output_root,
            phase=args.phase,
            ordering_seed=args.ordering_seed,
            java_options=args.java_options,
            confirm_expensive=args.confirm_expensive,
        )
        common.run_checked(command, cwd=repo_root / "dashboard")
        records.append(load_population_ladder_record(entry, common.latest_parallel_scaling_raw_json(cell_output_root)))

    write_batches_csv(output_root / "cache_population_ladder_batches.csv", records)
    write_analysis_outputs(records, output_root)
    return 0


def run_sequential_ladder(args: argparse.Namespace, *, pilot: bool) -> int:
    if not pilot and not args.confirm_expensive:
        raise ValueError("Full sequential cache population ladder is expensive; pass --confirm-expensive.")

    cache_on_root = args.cache_on_root.resolve()
    cache_off_root = args.cache_off_root.resolve()
    output_root = args.output_root.resolve()
    populations = parse_populations(args.populations)
    seeds = parse_seeds(args.seeds)
    plan = build_sequential_paired_plan(
        populations=populations,
        seeds=seeds,
        ordering_seed=args.ordering_seed,
    )
    write_run_order(plan, output_root)

    if not args.skip_gates:
        for variant_root in (cache_off_root, cache_on_root):
            common.run_checked(["./mvnw", "-q", "test"], cwd=variant_root)
            common.run_checked(
                [
                    "bash",
                    "scripts/model/run-speed-regression.sh",
                    "--snapshot",
                    common.DEFAULT_SNAPSHOT,
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
        cell_output_root = (
            output_root
            / "cache-population-ladder-sequential"
            / entry.source_variant
            / f"pop{entry.target_population}"
            / f"seed{entry.seed:03d}"
            / f"pair{entry.pair_order_index:03d}"
        )
        command = build_sequential_ladder_command(
            entry,
            repo_root=repo_root,
            output_root=cell_output_root,
            phase=args.phase,
            ordering_seed=args.ordering_seed,
            java_options=args.java_options,
            confirm_expensive=args.confirm_expensive or pilot,
        )
        common.run_checked(command, cwd=repo_root / "dashboard")
        records.append(load_sequential_ladder_record(entry, common.latest_parallel_scaling_raw_json(cell_output_root)))

    if pilot:
        write_sequential_pilot_outputs(records, output_root)
    else:
        write_sequential_analysis_outputs(records, output_root)
    return 0


def parse_populations(raw: str | Sequence[int]) -> tuple[int, ...]:
    if isinstance(raw, str):
        values = tuple(int(value.strip()) for value in raw.split(",") if value.strip())
    else:
        values = tuple(int(value) for value in raw)
    _require_positive_sequence(values, "populations")
    return values


def parse_seeds(raw: str | Sequence[int]) -> tuple[int, ...]:
    if isinstance(raw, str):
        values = tuple(int(value.strip()) for value in raw.split(",") if value.strip())
    else:
        values = tuple(int(value) for value in raw)
    _require_positive_sequence(values, "seeds")
    if len(set(values)) != len(values):
        raise ValueError("seeds must not contain duplicates.")
    return values


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run or analyze the cache speedup population ladder.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Write the randomized population/cache run order.")
    plan_parser.add_argument("--populations", default=",".join(str(value) for value in DEFAULT_POPULATIONS))
    plan_parser.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    plan_parser.add_argument("--workers", type=int, default=common.DEFAULT_PARALLEL_WORKERS)
    plan_parser.add_argument("--seed-count", type=int, default=common.DEFAULT_SEED_COUNT)
    plan_parser.add_argument("--ordering-seed", type=int, default=common.DEFAULT_ORDERING_SEED)
    plan_parser.add_argument("--output-root", required=True, type=Path)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze cache_population_ladder_batches.csv.")
    analyze_parser.add_argument("--batches-csv", required=True, type=Path)
    analyze_parser.add_argument("--output-root", required=True, type=Path)

    sequential_pilot_parser = subparsers.add_parser("pilot-sequential", help="Run one sequential adjacent cache pair per population.")
    sequential_pilot_parser.add_argument("--cache-on-root", required=True, type=Path)
    sequential_pilot_parser.add_argument("--cache-off-root", required=True, type=Path)
    sequential_pilot_parser.add_argument("--output-root", required=True, type=Path)
    sequential_pilot_parser.add_argument("--populations", default=",".join(str(value) for value in DEFAULT_POPULATIONS))
    sequential_pilot_parser.add_argument("--seeds", default=",".join(str(value) for value in DEFAULT_PILOT_SEEDS))
    sequential_pilot_parser.add_argument("--ordering-seed", type=int, default=common.DEFAULT_ORDERING_SEED)
    sequential_pilot_parser.add_argument("--phase", choices=("pilot", "full"), default="full")
    sequential_pilot_parser.add_argument("--confirm-expensive", action="store_true")
    sequential_pilot_parser.add_argument("--skip-gates", action="store_true")
    sequential_pilot_parser.add_argument("--java-option", dest="java_options", action="append", default=[])

    sequential_run_parser = subparsers.add_parser("run-sequential", help="Run the full sequential adjacent cache-pair experiment.")
    sequential_run_parser.add_argument("--cache-on-root", required=True, type=Path)
    sequential_run_parser.add_argument("--cache-off-root", required=True, type=Path)
    sequential_run_parser.add_argument("--output-root", required=True, type=Path)
    sequential_run_parser.add_argument("--populations", default=",".join(str(value) for value in DEFAULT_POPULATIONS))
    sequential_run_parser.add_argument("--seeds", default=",".join(str(value) for value in DEFAULT_SEEDS))
    sequential_run_parser.add_argument("--ordering-seed", type=int, default=common.DEFAULT_ORDERING_SEED)
    sequential_run_parser.add_argument("--phase", choices=("pilot", "full"), default="full")
    sequential_run_parser.add_argument("--confirm-expensive", action="store_true")
    sequential_run_parser.add_argument("--skip-gates", action="store_true")
    sequential_run_parser.add_argument("--java-option", dest="java_options", action="append", default=[])

    sequential_analyze_parser = subparsers.add_parser("analyze-sequential", help="Analyze cache_population_ladder_timing.csv.")
    sequential_analyze_parser.add_argument("--timing-csv", required=True, type=Path)
    sequential_analyze_parser.add_argument("--output-root", required=True, type=Path)
    sequential_analyze_parser.add_argument("--pilot", action="store_true")

    run_parser = subparsers.add_parser("run", help="Run prepared cache-on/cache-off worktrees.")
    run_parser.add_argument("--cache-on-root", required=True, type=Path)
    run_parser.add_argument("--cache-off-root", required=True, type=Path)
    run_parser.add_argument("--output-root", required=True, type=Path)
    run_parser.add_argument("--populations", default=",".join(str(value) for value in DEFAULT_POPULATIONS))
    run_parser.add_argument("--blocks", type=int, default=DEFAULT_BLOCKS)
    run_parser.add_argument("--workers", type=int, default=common.DEFAULT_PARALLEL_WORKERS)
    run_parser.add_argument("--seed-count", type=int, default=common.DEFAULT_SEED_COUNT)
    run_parser.add_argument("--ordering-seed", type=int, default=common.DEFAULT_ORDERING_SEED)
    run_parser.add_argument("--phase", choices=("pilot", "full"), default="full")
    run_parser.add_argument("--confirm-expensive", action="store_true")
    run_parser.add_argument("--skip-gates", action="store_true")
    run_parser.add_argument("--java-option", dest="java_options", action="append", default=[])

    args = parser.parse_args(argv)
    if args.command == "plan":
        write_run_order(
            build_population_ladder_plan(
                populations=parse_populations(args.populations),
                blocks=args.blocks,
                ordering_seed=args.ordering_seed,
                workers=args.workers,
                seed_count=args.seed_count,
            ),
            args.output_root,
        )
        return 0
    if args.command == "analyze":
        write_analysis_outputs(common.read_csv_rows(args.batches_csv), args.output_root)
        return 0
    if args.command == "pilot-sequential":
        return run_sequential_ladder(args, pilot=True)
    if args.command == "run-sequential":
        return run_sequential_ladder(args, pilot=False)
    if args.command == "analyze-sequential":
        rows = common.read_csv_rows(args.timing_csv)
        if args.pilot:
            write_sequential_pilot_outputs(rows, args.output_root)
        else:
            write_sequential_analysis_outputs(rows, args.output_root)
        return 0
    if args.command == "run":
        return run_ladder(args)
    raise AssertionError(f"Unhandled command: {args.command}")


def _complete_population_block_pairs(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[int, int, dict[str, Mapping[str, Any]]]]:
    grouped: dict[tuple[int, int], dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        key = (int(row["block_index"]), int(row["target_population"]))
        grouped.setdefault(key, {})[str(row["source_variant"])] = row
    return [
        (block_index, population, cells)
        for (block_index, population), cells in sorted(grouped.items())
        if all(variant in cells for variant in VARIANTS)
    ]


def _population_block_summary(
    block_index: int,
    target_population: int,
    cells: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    cache_off = cells["cache-off"]
    cache_on = cells["cache-on"]
    off_child_mean = float(cache_off["child_mean_wall_clock_seconds"])
    on_child_mean = float(cache_on["child_mean_wall_clock_seconds"])
    off_throughput = float(cache_off["throughput_runs_per_hour"])
    on_throughput = float(cache_on["throughput_runs_per_hour"])
    return {
        "block_index": block_index,
        "target_population": target_population,
        "cache_off_child_mean_wall_clock_seconds": off_child_mean,
        "cache_on_child_mean_wall_clock_seconds": on_child_mean,
        "cache_off_throughput_runs_per_hour": off_throughput,
        "cache_on_throughput_runs_per_hour": on_throughput,
        "runtime_speedup": off_child_mean / on_child_mean,
        "throughput_speedup": on_throughput / off_throughput,
    }


def _population_summary(target_population: int, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    runtime_speedup = common.effect_summary([float(row["runtime_speedup"]) for row in rows])
    throughput_speedup = common.effect_summary([float(row["throughput_speedup"]) for row in rows])
    off_child = [float(row["cache_off_child_mean_wall_clock_seconds"]) for row in rows]
    on_child = [float(row["cache_on_child_mean_wall_clock_seconds"]) for row in rows]
    off_throughput = [float(row["cache_off_throughput_runs_per_hour"]) for row in rows]
    on_throughput = [float(row["cache_on_throughput_runs_per_hour"]) for row in rows]
    return {
        "target_population": target_population,
        "complete_blocks": len(rows),
        "runtime_speedup": runtime_speedup,
        "runtime_speedup_estimate": runtime_speedup["estimate"],
        "runtime_speedup_lower_95_ci": runtime_speedup["lower_95_ci"],
        "runtime_speedup_upper_95_ci": runtime_speedup["upper_95_ci"],
        "throughput_speedup": throughput_speedup,
        "throughput_speedup_estimate": throughput_speedup["estimate"],
        "throughput_speedup_lower_95_ci": throughput_speedup["lower_95_ci"],
        "throughput_speedup_upper_95_ci": throughput_speedup["upper_95_ci"],
        "cache_off_child_mean_wall_clock_seconds": statistics.mean(off_child) if off_child else None,
        "cache_on_child_mean_wall_clock_seconds": statistics.mean(on_child) if on_child else None,
        "cache_off_geometric_mean_throughput_runs_per_hour": _geometric_mean(off_throughput),
        "cache_on_geometric_mean_throughput_runs_per_hour": _geometric_mean(on_throughput),
    }


def _sequential_population_summary(target_population: int, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    log_values = [float(row["log_speedup"]) for row in rows]
    speedup = common.effect_summary_from_logs(log_values)
    off_seconds = [float(row["cache_off_seconds"]) for row in rows]
    on_seconds = [float(row["cache_on_seconds"]) for row in rows]
    return {
        "target_population": target_population,
        "complete_seed_pairs": len(rows),
        "geometric_mean_speedup": speedup["estimate"],
        "speedup_lower_95_ci": speedup["lower_95_ci"],
        "speedup_upper_95_ci": speedup["upper_95_ci"],
        "cache_off_mean_seconds": statistics.mean(off_seconds) if off_seconds else None,
        "cache_on_mean_seconds": statistics.mean(on_seconds) if on_seconds else None,
        "cache_off_median_seconds": statistics.median(off_seconds) if off_seconds else None,
        "cache_on_median_seconds": statistics.median(on_seconds) if on_seconds else None,
    }


def _write_plots(runtime_path: Path, speedup_path: Path, population_summaries: Sequence[Mapping[str, Any]]) -> None:
    if not HAS_MATPLOTLIB:
        return
    populations = [int(row["target_population"]) for row in population_summaries]
    if not populations:
        return

    off_runtimes = [float(row["cache_off_child_mean_wall_clock_seconds"]) for row in population_summaries]
    on_runtimes = [float(row["cache_on_child_mean_wall_clock_seconds"]) for row in population_summaries]
    speedups = [float(row["runtime_speedup_estimate"]) for row in population_summaries]
    lower = [
        speedup - float(row["runtime_speedup_lower_95_ci"])
        if row["runtime_speedup_lower_95_ci"] is not None
        else 0.0
        for speedup, row in zip(speedups, population_summaries, strict=True)
    ]
    upper = [
        float(row["runtime_speedup_upper_95_ci"]) - speedup
        if row["runtime_speedup_upper_95_ci"] is not None
        else 0.0
        for speedup, row in zip(speedups, population_summaries, strict=True)
    ]

    fig, axis = plt.subplots(figsize=(7.2, 4.3))
    axis.plot(populations, off_runtimes, marker="o", color="#4E79A7", label="Cache off")
    axis.plot(populations, on_runtimes, marker="o", color="#E15759", label="Cache on")
    axis.set_xlabel("Target population")
    axis.set_ylabel("Mean child wall-clock seconds")
    axis.grid(True, axis="both", color="#B8B8B8", linewidth=0.7, alpha=0.45)
    axis.legend()
    fig.tight_layout()
    fig.savefig(runtime_path, dpi=300)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(7.2, 4.3))
    axis.errorbar(populations, speedups, yerr=[lower, upper], marker="o", color="#2F7F6F", capsize=4)
    axis.axhline(1.0, color="#595959", linestyle="--", linewidth=1)
    axis.set_xlabel("Target population")
    axis.set_ylabel("Cache speedup: cache-off runtime / cache-on runtime")
    axis.grid(True, axis="both", color="#B8B8B8", linewidth=0.7, alpha=0.45)
    fig.tight_layout()
    fig.savefig(speedup_path, dpi=300)
    plt.close(fig)


def _write_sequential_plots(runtime_path: Path, speedup_path: Path, population_summaries: Sequence[Mapping[str, Any]]) -> None:
    if not HAS_MATPLOTLIB:
        return
    populations = [int(row["target_population"]) for row in population_summaries]
    if not populations:
        return

    off_runtimes = [float(row["cache_off_mean_seconds"]) for row in population_summaries]
    on_runtimes = [float(row["cache_on_mean_seconds"]) for row in population_summaries]
    speedups = [float(row["geometric_mean_speedup"]) for row in population_summaries]
    lower = [
        speedup - float(row["speedup_lower_95_ci"])
        if row["speedup_lower_95_ci"] is not None
        else 0.0
        for speedup, row in zip(speedups, population_summaries, strict=True)
    ]
    upper = [
        float(row["speedup_upper_95_ci"]) - speedup
        if row["speedup_upper_95_ci"] is not None
        else 0.0
        for speedup, row in zip(speedups, population_summaries, strict=True)
    ]

    fig, axis = plt.subplots(figsize=(7.2, 4.3))
    axis.plot(populations, off_runtimes, marker="o", color="#4E79A7", label="Cache off")
    axis.plot(populations, on_runtimes, marker="o", color="#E15759", label="Cache on")
    axis.set_xlabel("Target population")
    axis.set_ylabel("Mean seed-run wall-clock seconds")
    axis.grid(True, axis="both", color="#B8B8B8", linewidth=0.7, alpha=0.45)
    axis.legend()
    fig.tight_layout()
    fig.savefig(runtime_path, dpi=300)
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(7.2, 4.3))
    speedup_handle = axis.errorbar(
        populations,
        speedups,
        yerr=[lower, upper],
        marker="o",
        color="#2F7F6F",
        capsize=4,
        label="Geometric mean speedup (95% CI)",
    )
    baseline_handle = axis.axhline(1.0, color="#595959", linestyle="--", linewidth=1, label="No speedup (1.0)")
    axis.set_xlabel("Target population")
    axis.set_ylabel("Geometric mean cache optimisation speedup")
    axis.set_xlim(left=0)
    axis.xaxis.set_minor_locator(MultipleLocator(5_000))
    axis.yaxis.set_minor_locator(MultipleLocator(0.004))
    axis.grid(True, axis="both", color="#B8B8B8", linewidth=0.7, alpha=0.45)
    axis.grid(True, which="minor", axis="both", color="#D0D0D0", linewidth=0.45, alpha=0.28)
    axis.legend(
        handles=[speedup_handle, baseline_handle],
        loc="upper left",
        fontsize="x-small",
        frameon=True,
        handlelength=1.6,
        borderpad=0.3,
        labelspacing=0.25,
        borderaxespad=0.35,
    )
    fig.tight_layout()
    fig.savefig(speedup_path, dpi=300)
    plt.close(fig)


def _normalize_batch_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "block_index": int(row["block_index"]),
        "run_order_index": int(row.get("run_order_index", 0) or 0),
        "target_population": int(row["target_population"]),
        "cache_enabled": common.coerce_bool(row.get("cache_enabled")),
        "source_variant": str(row["source_variant"]),
        "workers": int(row["workers"]),
        "seed_count": int(row["seed_count"]),
        "status": str(row["status"]),
        "completed_child_count": int(row.get("completed_child_count", 0) or 0),
        "failed_child_count": int(row.get("failed_child_count", 0) or 0),
        "canceled_child_count": int(row.get("canceled_child_count", 0) or 0),
        "wall_clock_seconds": float(row.get("wall_clock_seconds", 0.0) or 0.0),
        "throughput_runs_per_hour": float(row["throughput_runs_per_hour"]),
        "child_mean_wall_clock_seconds": float(row["child_mean_wall_clock_seconds"]),
        "child_median_wall_clock_seconds": float(row["child_median_wall_clock_seconds"]),
        "child_p95_wall_clock_seconds": float(row["child_p95_wall_clock_seconds"]),
        "raw_json_path": str(row.get("raw_json_path", "")),
    }


def _normalize_sequential_row(row: Mapping[str, Any]) -> dict[str, Any]:
    raw_run_seconds = row.get("run_wall_clock_seconds")
    run_seconds = None if raw_run_seconds is None or raw_run_seconds == "" else float(raw_run_seconds)
    return {
        "pair_order_index": int(row.get("pair_order_index", 0) or 0),
        "run_order_index": int(row.get("run_order_index", 0) or 0),
        "target_population": int(row["target_population"]),
        "seed": int(row["seed"]),
        "cache_enabled": common.coerce_bool(row.get("cache_enabled")),
        "source_variant": str(row["source_variant"]),
        "status": str(row["status"]),
        "run_wall_clock_seconds": run_seconds,
        "batch_wall_clock_seconds": float(row.get("batch_wall_clock_seconds", 0.0) or 0.0),
        "raw_json_path": str(row.get("raw_json_path", "")),
    }


def _is_successful_batch(row: Mapping[str, Any]) -> bool:
    return (
        common.is_success_status(str(row.get("status", "")))
        and float(row.get("throughput_runs_per_hour", 0.0) or 0.0) > 0.0
        and float(row.get("child_mean_wall_clock_seconds", 0.0) or 0.0) > 0.0
    )


def _is_successful_sequential_row(row: Mapping[str, Any]) -> bool:
    return (
        common.is_success_status(str(row.get("status", "")))
        and str(row.get("source_variant", "")) in VARIANTS
        and float(row.get("run_wall_clock_seconds", 0.0) or 0.0) > 0.0
    )


def _geometric_mean(values: Sequence[float]) -> float | None:
    positive = [value for value in values if value > 0.0]
    if not positive:
        return None
    return math.exp(statistics.mean(math.log(value) for value in positive))


def _batch_headers() -> list[str]:
    return [
        "block_index",
        "run_order_index",
        "target_population",
        "cache_enabled",
        "source_variant",
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


def _sequential_timing_headers() -> list[str]:
    return [
        "pair_order_index",
        "run_order_index",
        "target_population",
        "seed",
        "cache_enabled",
        "source_variant",
        "status",
        "run_wall_clock_seconds",
        "batch_wall_clock_seconds",
        "raw_json_path",
    ]


def _sequential_pair_headers() -> list[str]:
    return [
        "target_population",
        "seed",
        "cache_off_seconds",
        "cache_on_seconds",
        "raw_speedup",
        "log_speedup",
    ]


def _sequential_population_headers() -> list[str]:
    return [
        "target_population",
        "complete_seed_pairs",
        "geometric_mean_speedup",
        "speedup_lower_95_ci",
        "speedup_upper_95_ci",
        "cache_off_mean_seconds",
        "cache_on_mean_seconds",
        "cache_off_median_seconds",
        "cache_on_median_seconds",
    ]


def _incomplete_pair_headers() -> list[str]:
    return ["target_population", "seed", "missing_variants", "present_variants"]


def _block_summary_headers() -> list[str]:
    return [
        "block_index",
        "target_population",
        "cache_off_child_mean_wall_clock_seconds",
        "cache_on_child_mean_wall_clock_seconds",
        "cache_off_throughput_runs_per_hour",
        "cache_on_throughput_runs_per_hour",
        "runtime_speedup",
        "throughput_speedup",
    ]


def _population_summary_headers() -> list[str]:
    return [
        "target_population",
        "complete_blocks",
        "runtime_speedup_estimate",
        "runtime_speedup_lower_95_ci",
        "runtime_speedup_upper_95_ci",
        "throughput_speedup_estimate",
        "throughput_speedup_lower_95_ci",
        "throughput_speedup_upper_95_ci",
        "cache_off_child_mean_wall_clock_seconds",
        "cache_on_child_mean_wall_clock_seconds",
        "cache_off_geometric_mean_throughput_runs_per_hour",
        "cache_on_geometric_mean_throughput_runs_per_hour",
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
