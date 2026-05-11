#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aligned LTV-cap sensitivity sweeps by borrower group for debt-to-income plots.

Latest findings:
  - Command: `python3 -m scripts.python.experiments.model.boe_policy_ltv_by_group`
  - Comparison: `v0` versus `v4.1`, seeds `1,2,3,4`, `20` workers, aligned five-point LTV grids centered on the `v4.1` defaults.
  - FTB: tightening from `0.95` to `0.90` moved mortgage debt-to-income by `-13.941` in `v4.1` versus `-10.151` in `v0`; HM: loosening to `1.00` moved debt-to-income by `-0.877` versus `+0.618`; BTL: loosening to `0.90` moved debt-to-income by `+0.499` versus `+2.254`.
  - Interpretation: over this narrow default-centered range the clearest version divergence is the home-mover sweep, where `v4.1` remains below baseline as the cap loosens, while FTB and BTL respond more strongly in `v0` than `v4.1`.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from pathlib import Path
from typing import Mapping, Sequence

from scripts.python.experiments.model.policy_story_catalog import (
    PolicyStoryDefinition,
    get_policy_story_catalog,
)
from scripts.python.experiments.model.policy_story_reporting import plot_story_figure
from scripts.python.helpers.common.abm_policy_sweep import (
    AggregateStat,
    AggregatedStoryResults,
    ensure_project_compiled,
    resolve_maven_bin,
    run_story_sweep,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir

DEFAULT_VERSIONS = "v0,v4.1"
DEFAULT_SEEDS = "1,2,3,4"
DEFAULT_WORKERS = 20
DEFAULT_OUTPUT_DIR = "tmp/boe_policy_story_ltv_by_group"
DEFAULT_STAGE_NAME = "ltv_by_group"
MODEL_RUNS_DIRNAME = "model_runs"
PLOT_INDICATOR_ID = "core_debtToIncome"

FTB_GRID = (0.90, 0.925, 0.95, 0.975, 1.00)
HM_GRID = (0.90, 0.925, 0.95, 0.975, 1.00)
BTL_GRID = (0.80, 0.825, 0.85, 0.875, 0.90)

PLOT_FILE_NAMES = {
    "ftb_ltv_cap": "01_ftb_ltv_cap_dti.png",
    "hm_ltv_cap": "02_hm_ltv_cap_dti.png",
    "btl_ltv_cap": "03_btl_ltv_cap_dti.png",
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run aligned LTV-cap sensitivity sweeps and plot debt-to-income deltas by borrower group.",
    )
    parser.add_argument(
        "--versions",
        default=DEFAULT_VERSIONS,
        help="Comma-separated input-data versions to compare (default: v0,v4.1).",
    )
    parser.add_argument(
        "--seeds",
        default=DEFAULT_SEEDS,
        help="Comma-separated seeds used for all sweeps (default: 1,2,3,4).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help="Maximum parallel model runs (default: 20).",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for plots, summaries, and reusable run caches.",
    )
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Ignore cached run_metrics.json files and rerun model outputs.",
    )
    parser.add_argument(
        "--maven-bin",
        default=None,
        help="Maven executable override (default: repo-local ./mvnw).",
    )
    return parser


def parse_csv_list(raw: str) -> list[str]:
    values = [token.strip() for token in raw.split(",") if token.strip()]
    if not values:
        raise SystemExit("Expected a non-empty comma-separated list.")
    return values


def parse_seed_list(raw: str) -> list[int]:
    values = [int(token) for token in parse_csv_list(raw)]
    if any(value <= 0 for value in values):
        raise SystemExit("Seeds must be positive integers.")
    return values


def validate_versions(raw_versions: list[str]) -> list[str]:
    if len(raw_versions) != 2:
        raise SystemExit("This workflow requires exactly two versions: baseline `v0` and modern `v4.1`.")
    if raw_versions[0] != "v0":
        raise SystemExit("This workflow requires `v0` as the first comparison version.")
    if raw_versions[1] != "v4.1":
        raise SystemExit("This workflow currently supports only `v4.1` as the modern comparison version.")
    return raw_versions


def _always_binding(_: Mapping[str, str]) -> bool:
    return True


def build_ltv_sensitivity_stories() -> list[PolicyStoryDefinition]:
    catalog = {story.story_id: story for story in get_policy_story_catalog()}
    return [
        replace(
            catalog["ftb_ltv_cap"],
            screen_values=FTB_GRID,
            final_values=FTB_GRID,
            baseline_value=0.95,
            primary_outputs=(PLOT_INDICATOR_ID,),
            secondary_outputs=(),
            figure_indicator_ids=(PLOT_INDICATOR_ID,),
            figure_headline_indicator_id=PLOT_INDICATOR_ID,
        ),
        replace(
            catalog["hm_ltv_cap"],
            screen_values=HM_GRID,
            final_values=HM_GRID,
            baseline_value=0.95,
            primary_outputs=(PLOT_INDICATOR_ID,),
            secondary_outputs=(),
            figure_indicator_ids=(PLOT_INDICATOR_ID,),
            figure_headline_indicator_id=PLOT_INDICATOR_ID,
        ),
        PolicyStoryDefinition(
            story_id="btl_ltv_cap",
            title="Buy-to-Let LTV Cap (Aligned Bank + Central-Bank Limit)",
            instrument_label="aligned BTL bank + central-bank hard LTV cap",
            description="Tighten or loosen the aligned buy-to-let hard LTV cap.",
            axis_label="Buy-to-let hard LTV cap",
            axis_units="ratio",
            fixed_updates={},
            swept_keys=("CENTRAL_BANK_LTV_HARD_MAX_BTL",),
            screen_values=BTL_GRID,
            final_values=BTL_GRID,
            baseline_value=0.85,
            primary_outputs=(PLOT_INDICATOR_ID,),
            secondary_outputs=(),
            figure_indicator_ids=(PLOT_INDICATOR_ID,),
            figure_headline_indicator_id=PLOT_INDICATOR_ID,
            expected_primary_direction=1,
            policy_relevance_weight=0.55,
            calibration_link_weight=0.50,
            fallback_rank=0,
            mechanism_summary=(
                "looser BTL leverage limits allow investors to carry more mortgage debt when deposit constraints bind"
            ),
            recalibration_summary=(
                "The v4.1 aligned hard-LTV defaults make investor leverage changes easier to compare cleanly against v0."
            ),
            binding_checker=_always_binding,
            sources=(),
            effective_rule="min_cap",
            linked_bank_keys=("BANK_LTV_HARD_MAX_BTL",),
        ),
    ]


def build_reproduce_command(args: argparse.Namespace) -> str:
    command_parts = [
        "python3 -m scripts.python.experiments.model.boe_policy_ltv_by_group",
        f"--output-dir {args.output_dir}",
        f"--versions {args.versions}",
        f"--seeds {args.seeds}",
        f"--workers {args.workers}",
    ]
    if args.force_rerun:
        command_parts.append("--force-rerun")
    if args.maven_bin:
        command_parts.append(f"--maven-bin {args.maven_bin}")
    return " \\\n  ".join(command_parts) + "\n"


def write_reproduce_command(path: Path, args: argparse.Namespace) -> None:
    path.write_text(build_reproduce_command(args), encoding="utf-8")


def write_aggregated_results_csv(
    path: Path,
    *,
    stories: Sequence[PolicyStoryDefinition],
    aggregated_by_story_id: Mapping[str, AggregatedStoryResults],
    versions: Sequence[str],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "story_id",
                "title",
                "version",
                "point_id",
                "point_label",
                "x_value",
                "is_baseline",
                "indicator_id",
                "raw_mean",
                "raw_stdev",
                "raw_ci_low",
                "raw_ci_high",
                "raw_n",
                "delta_mean",
                "delta_stdev",
                "delta_ci_low",
                "delta_ci_high",
                "delta_n",
            ]
        )
        for story in stories:
            aggregated = aggregated_by_story_id[story.story_id]
            for version in versions:
                for point in aggregated.versions[version]:
                    raw_stat = point.indicators[PLOT_INDICATOR_ID].mean
                    delta_stat = point.delta_indicators[PLOT_INDICATOR_ID].mean
                    writer.writerow(
                        [
                            story.story_id,
                            story.title,
                            version,
                            point.point_id,
                            point.label,
                            format_float(point.x_value),
                            "true" if point.is_baseline else "false",
                            PLOT_INDICATOR_ID,
                            _fmt_stat(raw_stat, "mean"),
                            _fmt_stat(raw_stat, "stdev"),
                            _fmt_stat(raw_stat, "ci_low"),
                            _fmt_stat(raw_stat, "ci_high"),
                            _fmt_stat(raw_stat, "n"),
                            _fmt_stat(delta_stat, "mean"),
                            _fmt_stat(delta_stat, "stdev"),
                            _fmt_stat(delta_stat, "ci_low"),
                            _fmt_stat(delta_stat, "ci_high"),
                            _fmt_stat(delta_stat, "n"),
                        ]
                    )


def _fmt_stat(stat: AggregateStat | None, field: str) -> str:
    if stat is None:
        return ""
    value = getattr(stat, field)
    if value is None:
        return ""
    if field == "n":
        return str(int(value))
    return format_float(value, decimals=6)


def main() -> None:
    args = build_arg_parser().parse_args()
    repo_root = Path(__file__).resolve().parents[4]
    maven_bin = resolve_maven_bin(repo_root, args.maven_bin)
    versions = validate_versions(parse_csv_list(args.versions))
    seeds = parse_seed_list(args.seeds)
    if args.workers <= 0:
        raise SystemExit("workers must be positive.")

    stories = build_ltv_sensitivity_stories()
    output_dir = ensure_output_dir(args.output_dir)
    model_runs_root = output_dir / MODEL_RUNS_DIRNAME

    ensure_project_compiled(repo_root=repo_root, maven_bin=maven_bin)

    aggregated_by_story_id: dict[str, AggregatedStoryResults] = {}
    for story in stories:
        _, aggregated = run_story_sweep(
            repo_root=repo_root,
            output_root=model_runs_root,
            stage_name=DEFAULT_STAGE_NAME,
            story_id=story.story_id,
            versions=versions,
            seeds=seeds,
            points=story.build_points("final", aligned=True),
            indicator_ids=[PLOT_INDICATOR_ID],
            workers=args.workers,
            force_rerun=args.force_rerun,
            maven_bin=maven_bin,
        )
        aggregated_by_story_id[story.story_id] = aggregated
        plot_path = output_dir / PLOT_FILE_NAMES[story.story_id]
        plot_story_figure(path=plot_path, story=story, aggregated=aggregated)
        print(f"[ltv-by-group] wrote {plot_path}")

    write_aggregated_results_csv(
        output_dir / "aggregated_results.csv",
        stories=stories,
        aggregated_by_story_id=aggregated_by_story_id,
        versions=versions,
    )
    write_reproduce_command(output_dir / "reproduce_command.txt", args)
    print(f"[ltv-by-group] finished output_dir={output_dir}")


if __name__ == "__main__":
    main()
