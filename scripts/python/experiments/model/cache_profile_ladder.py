#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze rental-income cache profile counters emitted by the instrumentation worktree.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.python.experiments.model import speed_experiment_common as common


PROFILE_FILE_TEMPLATE = "RentalIncomeCacheProfile-run{run_index}.json"

PROFILE_COUNTER_FIELDS = (
    "total_queries",
    "clean_hits",
    "dirty_queries",
    "positive_contract_queries",
    "positive_contract_clean_hits",
    "positive_contract_dirty_queries",
    "dirty_recomputes",
    "no_cache_equivalent_contract_scans",
    "cached_contract_scans",
    "max_contracts_scanned_per_recompute",
    "invalidation_events",
    "dirty_transitions",
    "redundant_invalidations",
    "contract_put_events",
    "contract_replace_events",
    "contract_remove_events",
    "payment_state_events",
)

PROFILE_RATE_FIELDS = (
    "hit_rate",
    "recompute_rate",
    "positive_contract_hit_rate",
    "positive_contract_recompute_rate",
    "avoided_scan_share",
    "mean_contracts_per_query",
    "mean_contracts_per_recompute",
)

INVALIDATION_REASON_FIELDS = (
    "contract_put_events",
    "contract_replace_events",
    "contract_remove_events",
    "payment_state_events",
)


def load_profile_runs(raw_json_path: Path, *, profile_run_index: int = 1) -> list[dict[str, Any]]:
    payload = json.loads(raw_json_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for batch in payload.get("batches", []):
        for child in batch.get("children", []):
            if not common.is_success_status(str(child.get("status", ""))):
                continue
            output_path = _resolve_child_output_path(raw_json_path, child)
            profile_path = output_path / PROFILE_FILE_TEMPLATE.format(run_index=profile_run_index)
            if not profile_path.exists():
                raise FileNotFoundError(
                    f"Successful child seed {child.get('seed')} has no rental-income cache profile at {profile_path}"
                )
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            rows.append(_profile_run_row(raw_json_path, batch, child, output_path, profile_path, profile))
    return rows


def analyze_profile_runs(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    normalized = [_normalize_profile_run(row) for row in rows]
    sums = {
        field: sum(int(row.get(field, 0) or 0) for row in normalized)
        for field in PROFILE_COUNTER_FIELDS
        if field != "max_contracts_scanned_per_recompute"
    }
    max_contracts_scanned = max(
        (int(row.get("max_contracts_scanned_per_recompute", 0) or 0) for row in normalized),
        default=0,
    )
    no_cache_scans = sums["no_cache_equivalent_contract_scans"]
    cached_scans = sums["cached_contract_scans"]
    avoided_scans = no_cache_scans - cached_scans
    invalidation_events = sums["invalidation_events"]
    reason_counts = {field: sums[field] for field in INVALIDATION_REASON_FIELDS}
    wall_clock_seconds = [float(row["wall_clock_seconds"]) for row in normalized if row.get("wall_clock_seconds")]

    return {
        "schema_version": 1,
        "run_count": len(normalized),
        "target_populations": sorted({int(row["target_population"]) for row in normalized}),
        "n_steps": sorted({int(row["n_steps"]) for row in normalized}),
        "seeds": sorted({int(row["seed"]) for row in normalized}),
        "mean_child_wall_clock_seconds": statistics.mean(wall_clock_seconds) if wall_clock_seconds else None,
        "median_child_wall_clock_seconds": statistics.median(wall_clock_seconds) if wall_clock_seconds else None,
        "p95_child_wall_clock_seconds": common.percentile_nearest_rank(wall_clock_seconds, 0.95),
        "total_queries": sums["total_queries"],
        "clean_hits": sums["clean_hits"],
        "dirty_queries": sums["dirty_queries"],
        "positive_contract_queries": sums["positive_contract_queries"],
        "positive_contract_clean_hits": sums["positive_contract_clean_hits"],
        "positive_contract_dirty_queries": sums["positive_contract_dirty_queries"],
        "dirty_recomputes": sums["dirty_recomputes"],
        "no_cache_equivalent_contract_scans": no_cache_scans,
        "cached_contract_scans": cached_scans,
        "avoided_contract_scans": avoided_scans,
        "max_contracts_scanned_per_recompute": max_contracts_scanned,
        "invalidation_events": invalidation_events,
        "dirty_transitions": sums["dirty_transitions"],
        "redundant_invalidations": sums["redundant_invalidations"],
        "invalidation_reason_counts": reason_counts,
        "hit_rate": _ratio(sums["clean_hits"], sums["total_queries"]),
        "recompute_rate": _ratio(sums["dirty_recomputes"], sums["total_queries"]),
        "positive_contract_hit_rate": _ratio(
            sums["positive_contract_clean_hits"], sums["positive_contract_queries"]
        ),
        "positive_contract_recompute_rate": _ratio(
            sums["positive_contract_dirty_queries"], sums["positive_contract_queries"]
        ),
        "avoided_scan_share": _ratio(avoided_scans, no_cache_scans),
        "mean_contracts_per_query": _ratio(no_cache_scans, sums["total_queries"]),
        "mean_contracts_per_recompute": _ratio(cached_scans, sums["dirty_recomputes"]),
        "redundant_invalidation_share": _ratio(sums["redundant_invalidations"], invalidation_events),
    }


def write_analysis_outputs(rows: Sequence[Mapping[str, Any]], output_root: Path) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    summary = analyze_profile_runs(rows)
    paths = {
        "runs_csv": output_root / "rental_income_cache_profile_runs.csv",
        "summary_csv": output_root / "rental_income_cache_profile_summary.csv",
        "summary_json": output_root / "rental_income_cache_profile_summary.json",
    }
    common.write_csv(paths["runs_csv"], [_normalize_profile_run(row) for row in rows], _run_headers())
    common.write_csv(paths["summary_csv"], [_summary_csv_row(summary)], _summary_headers())
    paths["summary_json"].write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze rental-income cache profile counters.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_parser = subparsers.add_parser("analyze", help="Analyze moved profile outputs.")
    source = analyze_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--raw-json", type=Path, help="parallel_scaling_raw.json to analyze.")
    source.add_argument(
        "--profile-root",
        type=Path,
        help="Root containing parallel-scaling/*/parallel_scaling_raw.json; the newest raw JSON is used.",
    )
    analyze_parser.add_argument("--output-root", required=True, type=Path)
    analyze_parser.add_argument("--profile-run-index", type=int, default=1)

    args = parser.parse_args(argv)
    if args.command == "analyze":
        raw_json_path = args.raw_json or common.latest_parallel_scaling_raw_json(args.profile_root)
        rows = load_profile_runs(raw_json_path, profile_run_index=args.profile_run_index)
        paths = write_analysis_outputs(rows, args.output_root)
        print(f"Analyzed {len(rows)} rental-income cache profile runs from {raw_json_path}")
        for label, path in paths.items():
            print(f"{label}: {path}")
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


def _profile_run_row(
    raw_json_path: Path,
    batch: Mapping[str, Any],
    child: Mapping[str, Any],
    output_path: Path,
    profile_path: Path,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "raw_json_path": str(raw_json_path),
        "batch_id": str(batch.get("batchId", "")),
        "task_id": str(child.get("taskId", "")),
        "child_seed": int(child.get("seed", 0) or 0),
        "worker_index": int(child.get("workerIndex", 0) or 0),
        "status": str(child.get("status", "")),
        "wall_clock_seconds": float(child.get("wallClockSeconds", 0.0) or 0.0),
        "output_path": str(output_path),
        "profile_path": str(profile_path),
    }
    row.update(profile)
    return row


def _normalize_profile_run(row: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "raw_json_path": str(row.get("raw_json_path", "")),
        "batch_id": str(row.get("batch_id", "")),
        "task_id": str(row.get("task_id", "")),
        "child_seed": int(row.get("child_seed", row.get("seed", 0)) or 0),
        "worker_index": int(row.get("worker_index", 0) or 0),
        "status": str(row.get("status", "")),
        "wall_clock_seconds": float(row.get("wall_clock_seconds", 0.0) or 0.0),
        "output_path": str(row.get("output_path", "")),
        "profile_path": str(row.get("profile_path", "")),
        "schema_version": int(row.get("schema_version", 0) or 0),
        "n_simulation": int(row.get("n_simulation", 0) or 0),
        "seed": int(row.get("seed", 0) or 0),
        "target_population": int(row.get("target_population", 0) or 0),
        "n_steps": int(row.get("n_steps", 0) or 0),
    }
    for field in PROFILE_COUNTER_FIELDS:
        normalized[field] = int(row.get(field, 0) or 0)
    normalized["avoided_contract_scans"] = int(
        row.get(
            "avoided_contract_scans",
            normalized["no_cache_equivalent_contract_scans"] - normalized["cached_contract_scans"],
        )
        or 0
    )
    for field in PROFILE_RATE_FIELDS:
        normalized[field] = float(row.get(field, 0.0) or 0.0)
    return normalized


def _resolve_child_output_path(raw_json_path: Path, child: Mapping[str, Any]) -> Path:
    raw_output_path = child.get("outputPath") or child.get("output_path")
    if not raw_output_path:
        raise ValueError(f"Child seed {child.get('seed')} is missing outputPath in {raw_json_path}")
    output_path = Path(str(raw_output_path))
    if output_path.is_absolute():
        relocated_output_path = _relocated_output_path(raw_json_path, output_path)
        if relocated_output_path is not None and relocated_output_path.exists():
            return relocated_output_path
        return output_path
    return (raw_json_path.parent / output_path).resolve()


def _relocated_output_path(raw_json_path: Path, output_path: Path) -> Path | None:
    parts = output_path.parts
    if "parallel-scaling" not in parts:
        return None
    marker_index = len(parts) - 1 - parts[::-1].index("parallel-scaling")
    tail = Path(*parts[marker_index:])
    profile_root = raw_json_path.parent.parent.parent
    return profile_root / tail


def _summary_csv_row(summary: Mapping[str, Any]) -> dict[str, Any]:
    reason_counts = dict(summary.get("invalidation_reason_counts", {}))
    row = dict(summary)
    row.pop("seeds", None)
    row.pop("target_populations", None)
    row.pop("n_steps", None)
    row.pop("invalidation_reason_counts", None)
    row["target_populations"] = ";".join(str(value) for value in summary.get("target_populations", []))
    row["n_steps"] = ";".join(str(value) for value in summary.get("n_steps", []))
    row["seed_count"] = len(summary.get("seeds", []))
    row.update(reason_counts)
    return row


def _ratio(numerator: int | float, denominator: int | float) -> float:
    if float(denominator) == 0.0:
        return 0.0
    return float(numerator) / float(denominator)


def _run_headers() -> list[str]:
    return [
        "raw_json_path",
        "batch_id",
        "task_id",
        "child_seed",
        "worker_index",
        "status",
        "wall_clock_seconds",
        "output_path",
        "profile_path",
        "schema_version",
        "n_simulation",
        "seed",
        "target_population",
        "n_steps",
        *PROFILE_COUNTER_FIELDS,
        "avoided_contract_scans",
        *PROFILE_RATE_FIELDS,
    ]


def _summary_headers() -> list[str]:
    return [
        "schema_version",
        "run_count",
        "target_populations",
        "n_steps",
        "seed_count",
        "mean_child_wall_clock_seconds",
        "median_child_wall_clock_seconds",
        "p95_child_wall_clock_seconds",
        "total_queries",
        "clean_hits",
        "dirty_queries",
        "positive_contract_queries",
        "positive_contract_clean_hits",
        "positive_contract_dirty_queries",
        "dirty_recomputes",
        "no_cache_equivalent_contract_scans",
        "cached_contract_scans",
        "avoided_contract_scans",
        "max_contracts_scanned_per_recompute",
        "invalidation_events",
        "dirty_transitions",
        "redundant_invalidations",
        *INVALIDATION_REASON_FIELDS,
        "hit_rate",
        "recompute_rate",
        "positive_contract_hit_rate",
        "positive_contract_recompute_rate",
        "avoided_scan_share",
        "mean_contracts_per_query",
        "mean_contracts_per_recompute",
        "redundant_invalidation_share",
    ]


if __name__ == "__main__":
    raise SystemExit(main())
