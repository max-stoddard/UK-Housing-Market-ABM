#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reproduce the v4.8 PSD 2011 LTI hard-max parameters from the historical source bins.

Latest experiment findings (run on April 17, 2026):
  - Config: input-data-versions/v4.8/config.properties
  - PSD 2011 inputs:
    - private-datasets/psd/2005-2013/psd-mortgages-2005-2013-p3-loan-characteristic.csv
    - private-datasets/psd/2005-2013/psd-mortgages-2005-2013-p6-ftbs.csv
  - Reproduced method:
    - ftb=ftb_joint|hm=hm_subtracted|q=0.99|open=6.0|interp=linear
  - Raw estimates:
    - BANK_LTI_HARD_MAX_FTB ~= 5.3862737034
    - BANK_LTI_HARD_MAX_HM ~= 5.5926900167
  - Rounded policy estimates:
    - BANK_LTI_HARD_MAX_FTB = 5.4
    - BANK_LTI_HARD_MAX_HM = 5.6
  - Interpretation:
    - The historical v4.8 LTI ceilings are reproducible at config precision from
      the available PSD 2011 income-multiple bins; affordability remains
      intentionally out of scope because no defensible 2011 affordability
      observable is present in the current repo-local PSD extracts.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from scripts.python.experiments.psd.psd_lti_hard_max_method_search import (
    DEFAULT_LTI_METHOD,
    LtiMethodResult,
    LtiSearchOutput,
    TARGET_FTB_KEY,
    TARGET_HM_KEY,
    run_lti_search,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir, repo_root

RESULTS_FILE_NAME = "PsdV48LtiReproductionResults.csv"
SUMMARY_FILE_NAME = "psd-v48-lti-reproduction-summary.md"
DEFAULT_OUTPUT_DIR = repo_root() / "tmp" / "recalibration-recalculation-summaries"
DEFAULT_OUTPUT_DIR_DISPLAY = "tmp/recalibration-recalculation-summaries"


@dataclass(frozen=True)
class ParameterReproduction:
    key: str
    target: float
    raw_estimate: float
    rounded_estimate: float
    passes_target: bool
    exact_method_used: str
    reproduce_command: str
    advantages: str
    best_method_judgment: str
    improvements: str
    defensibility: str


@dataclass(frozen=True)
class V48LtiReproductionOutput:
    search_output: LtiSearchOutput
    default_result: LtiMethodResult
    ftb: ParameterReproduction
    hm: ParameterReproduction
    reproduce_command: str
    config_path: Path
    p3_csv: Path
    p6_csv: Path
    target_year: int


def _passes_target(raw_estimate: float, target: float) -> bool:
    return round(raw_estimate, 1) == round(target, 1)


def _build_reproduce_command(
    *,
    p3_csv: Path,
    p6_csv: Path,
    config_path: Path,
    target_year: int,
    top_k: int,
    output_dir_display: str,
) -> str:
    return (
        "python3 -m scripts.python.experiments.psd.psd_v48_lti_reproduction "
        f"--config-path {config_path} "
        f"--p3-csv {p3_csv} "
        f"--p6-csv {p6_csv} "
        f"--target-year {target_year} "
        f"--top-k {top_k} "
        f"--output-dir {output_dir_display}"
    )


def _describe_exact_method(key: str) -> str:
    if key == TARGET_FTB_KEY:
        return (
            "Python uses run_lti_search() with the decision-record default method. "
            "It loads PSD 2011 p6 section 6.2 (joint-income first-time-buyer "
            "income-multiple bins), then applies "
            "binned_weighted_quantile(..., quantile=0.99, open_upper=6.0, "
            "interpolation='linear') and rounds the raw estimate to 1dp."
        )
    return (
        "Python uses run_lti_search() with the decision-record default method. "
        "It builds the home-mover proxy distribution as "
        "(p3 section 3.7.1 + p3 section 3.7.2) - (p6 section 6.1 + p6 section 6.2), "
        "then applies binned_weighted_quantile(..., quantile=0.99, open_upper=6.0, "
        "interpolation='linear') and rounds the raw estimate to 1dp."
    )


def _build_parameter_reproduction(
    *,
    key: str,
    target: float,
    raw_estimate: float,
    reproduce_command: str,
) -> ParameterReproduction:
    rounded_estimate = round(raw_estimate, 1)
    passes_target = _passes_target(raw_estimate, target)

    if key == TARGET_FTB_KEY:
        advantages = (
            "Uses the direct PSD 2011 joint-income FTB bins, so the percentile is "
            "estimated from the most policy-relevant segment available in the source."
        )
    else:
        advantages = (
            "Uses all-borrower and FTB PSD 2011 bins to construct an explicit "
            "home-mover proxy, preserving source coverage instead of inventing a "
            "new external assumption."
        )

    return ParameterReproduction(
        key=key,
        target=target,
        raw_estimate=raw_estimate,
        rounded_estimate=rounded_estimate,
        passes_target=passes_target,
        exact_method_used=_describe_exact_method(key),
        reproduce_command=reproduce_command,
        advantages=advantages,
        best_method_judgment=(
            "Yes for the currently available PSD 2011 source bundle in this repo. "
            "This method is the decision-record default and ranks first by rounded "
            "target match, then by raw-distance tie-break."
        ),
        improvements=(
            "If loan-level PSD microdata or a documented home-mover-specific table "
            "becomes available, recompute the percentile without the open-top tail "
            "assumption or all-minus-FTB subtraction proxy. A codebook-backed proof "
            "of the 6.0 open-top choice would also tighten provenance."
        ),
        defensibility=(
            "Yes within the available 2011 PSD extracts. The method is explicit, "
            "search-ranked, source-aligned, and transparent about the final 1dp "
            "rounding rule used to reproduce the config values."
        ),
    )


def run_v48_lti_reproduction(
    *,
    p3_csv: Path,
    p6_csv: Path,
    config_path: Path,
    target_year: int,
    top_k: int,
    output_dir_display: str,
) -> V48LtiReproductionOutput:
    search_output = run_lti_search(
        p3_csv=p3_csv,
        p6_csv=p6_csv,
        config_path=config_path,
        target_year=target_year,
    )
    default_result = next(
        result for result in search_output.results if result.method == DEFAULT_LTI_METHOD
    )
    reproduce_command = _build_reproduce_command(
        p3_csv=p3_csv,
        p6_csv=p6_csv,
        config_path=config_path,
        target_year=target_year,
        top_k=top_k,
        output_dir_display=output_dir_display,
    )

    return V48LtiReproductionOutput(
        search_output=search_output,
        default_result=default_result,
        ftb=_build_parameter_reproduction(
            key=TARGET_FTB_KEY,
            target=search_output.target_ftb,
            raw_estimate=default_result.ftb_estimate_raw,
            reproduce_command=reproduce_command,
        ),
        hm=_build_parameter_reproduction(
            key=TARGET_HM_KEY,
            target=search_output.target_hm,
            raw_estimate=default_result.hm_estimate_raw,
            reproduce_command=reproduce_command,
        ),
        reproduce_command=reproduce_command,
        config_path=config_path,
        p3_csv=p3_csv,
        p6_csv=p6_csv,
        target_year=target_year,
    )


def build_summary_markdown(output: V48LtiReproductionOutput) -> str:
    lines = [
        "# PSD v4.8 LTI Reproduction Summary",
        "",
        "- Scope: `BANK_LTI_HARD_MAX_FTB` and `BANK_LTI_HARD_MAX_HM` only.",
        (
            "- Scope note: `BANK_AFFORDABILITY_HARD_MAX` was excluded by revised "
            "task requirements because no sufficient 2011 affordability source "
            "artifact was provided and the current repo-local PSD extracts do not "
            "contain a defensible affordability observable."
        ),
        f"- Config: `{output.config_path}`",
        f"- PSD p3 source: `{output.p3_csv}`",
        f"- PSD p6 source: `{output.p6_csv}`",
        f"- Target year: `{output.target_year}`",
        f"- Reproduce command: `{output.reproduce_command}`",
        "",
        "## Results",
        "",
        "| Parameter | Target | Raw estimate | Rounded 1dp | Pass | Method |",
        "| --- | --- | --- | --- | --- | --- |",
        (
            f"| {output.ftb.key} | {format_float(output.ftb.target, decimals=1)} | "
            f"{format_float(output.ftb.raw_estimate)} | "
            f"{format_float(output.ftb.rounded_estimate, decimals=1)} | "
            f"{'pass' if output.ftb.passes_target else 'fail'} | "
            f"`{output.default_result.method.method_id}` |"
        ),
        (
            f"| {output.hm.key} | {format_float(output.hm.target, decimals=1)} | "
            f"{format_float(output.hm.raw_estimate)} | "
            f"{format_float(output.hm.rounded_estimate, decimals=1)} | "
            f"{'pass' if output.hm.passes_target else 'fail'} | "
            f"`{output.default_result.method.method_id}` |"
        ),
        "",
    ]

    for item in (output.ftb, output.hm):
        lines.extend(
            [
                f"## {item.key}",
                "",
                f"- Exact method used in Python: {item.exact_method_used}",
                f"- Exact command: `{item.reproduce_command}`",
                f"- Raw estimate: `{format_float(item.raw_estimate)}`",
                f"- Rounded 1dp estimate: `{format_float(item.rounded_estimate, decimals=1)}`",
                (
                    "- Pass against v4.8 target: "
                    f"`{'pass' if item.passes_target else 'fail'}` "
                    f"(target `{format_float(item.target, decimals=1)}`)"
                ),
                f"- Advantages: {item.advantages}",
                (
                    "- Is this the best possible method for this specific data source? "
                    f"{item.best_method_judgment}"
                ),
                f"- Improvements for more robustness/accuracy: {item.improvements}",
                (
                    "- Is this the most coherent, logical and defensible method? "
                    f"{item.defensibility}"
                ),
                "",
            ]
        )

    return "\n".join(lines) + "\n"


def write_results_csv(output: V48LtiReproductionOutput, output_dir: str | Path | None) -> Path:
    output_root = ensure_output_dir(output_dir, default_dir=DEFAULT_OUTPUT_DIR)
    output_path = output_root / RESULTS_FILE_NAME
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "is_default_method",
                "method_id",
                "target_ftb",
                "target_hm",
                "ftb_raw",
                "hm_raw",
                "ftb_rounded_1dp",
                "hm_rounded_1dp",
                "distance_rounded",
                "distance_raw",
            ]
        )
        for rank, item in enumerate(output.search_output.results, start=1):
            writer.writerow(
                [
                    rank,
                    "yes" if item.method == DEFAULT_LTI_METHOD else "no",
                    item.method.method_id,
                    output.search_output.target_ftb,
                    output.search_output.target_hm,
                    item.ftb_estimate_raw,
                    item.hm_estimate_raw,
                    item.ftb_estimate_rounded,
                    item.hm_estimate_rounded,
                    item.distance_rounded,
                    item.distance_raw,
                ]
            )
    return output_path


def write_summary_markdown(
    output: V48LtiReproductionOutput,
    output_dir: str | Path | None,
) -> Path:
    output_root = ensure_output_dir(output_dir, default_dir=DEFAULT_OUTPUT_DIR)
    output_path = output_root / SUMMARY_FILE_NAME
    output_path.write_text(build_summary_markdown(output), encoding="utf-8")
    return output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproduce the v4.8 PSD 2011 LTI hard-max parameters and emit reviewable artifacts."
    )
    parser.add_argument(
        "--config-path",
        default="input-data-versions/v4.8/config.properties",
        help="Path to the v4.8 config.properties file.",
    )
    parser.add_argument(
        "--p3-csv",
        default="private-datasets/psd/2005-2013/psd-mortgages-2005-2013-p3-loan-characteristic.csv",
        help="PSD p3 loan-characteristics CSV.",
    )
    parser.add_argument(
        "--p6-csv",
        default="private-datasets/psd/2005-2013/psd-mortgages-2005-2013-p6-ftbs.csv",
        help="PSD p6 first-time-buyers CSV.",
    )
    parser.add_argument(
        "--target-year",
        type=int,
        default=2011,
        help="Annual PSD column token (default: 2011).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Number of top-ranked methods to print in the CLI summary (default: 20).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory for CSV and markdown artifacts "
            f"(default: {DEFAULT_OUTPUT_DIR_DISPLAY})."
        ),
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    top_k = max(1, args.top_k)
    output_dir_display = args.output_dir or DEFAULT_OUTPUT_DIR_DISPLAY

    output = run_v48_lti_reproduction(
        p3_csv=Path(args.p3_csv),
        p6_csv=Path(args.p6_csv),
        config_path=Path(args.config_path),
        target_year=args.target_year,
        top_k=top_k,
        output_dir_display=output_dir_display,
    )

    print("PSD v4.8 LTI reproduction")
    print(f"Config: {output.config_path}")
    print(f"P3: {output.p3_csv}")
    print(f"P6: {output.p6_csv}")
    print(f"Target year: {output.target_year}")
    print(f"Reproduce command: {output.reproduce_command}")
    print("")
    print(
        "Rank\tDistanceRounded\tDistanceRaw\tFTB(raw)\tHM(raw)\t"
        "FTB(round1dp)\tHM(round1dp)\tMethod"
    )
    for rank, item in enumerate(output.search_output.results[:top_k], start=1):
        print(
            f"{rank}\t{format_float(item.distance_rounded)}\t{format_float(item.distance_raw)}\t"
            f"{format_float(item.ftb_estimate_raw)}\t{format_float(item.hm_estimate_raw)}\t"
            f"{format_float(item.ftb_estimate_rounded, decimals=1)}\t"
            f"{format_float(item.hm_estimate_rounded, decimals=1)}\t"
            f"{item.method.method_id}"
        )

    print("\nDecision-record reproduction")
    print(f"method: {output.default_result.method.method_id}")
    print(
        f"{output.ftb.key}: raw={format_float(output.ftb.raw_estimate)}, "
        f"rounded={format_float(output.ftb.rounded_estimate, decimals=1)}, "
        f"target={format_float(output.ftb.target, decimals=1)}, "
        f"pass={'yes' if output.ftb.passes_target else 'no'}"
    )
    print(
        f"{output.hm.key}: raw={format_float(output.hm.raw_estimate)}, "
        f"rounded={format_float(output.hm.rounded_estimate, decimals=1)}, "
        f"target={format_float(output.hm.target, decimals=1)}, "
        f"pass={'yes' if output.hm.passes_target else 'no'}"
    )

    csv_path = write_results_csv(output, args.output_dir)
    summary_path = write_summary_markdown(output, args.output_dir)
    print(f"\nWrote: {csv_path}")
    print(f"Wrote: {summary_path}")


if __name__ == "__main__":
    main()
