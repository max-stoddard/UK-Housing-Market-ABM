#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the locked national HPA expectation calibration method for production use.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from scripts.python.experiments.nmg.nmg_hpa_expectation_method_search import (
    DEFAULT_PAIRING_RULE_NAME,
    DEFAULT_SIGNAL_METHOD_NAME,
    DEFAULT_SURVEY_METHOD_NAME,
    resolve_anchor_pairings,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.nmg.hpa_expectation import aggregate_expectation, fit_linear_rule
from scripts.python.helpers.ppd.hpa_signal_methods import build_hpa_signal, load_ppd_rows, resolve_base_year


@dataclass(frozen=True)
class CalibrationOutput:
    factor: float
    const: float
    pairing_rule_name: str
    survey_method_name: str
    signal_method_name: str
    survey_means: dict[int, float]
    signal_values: dict[int, float]
    signal_anchor_years: dict[int, int]
    signal_base_years: dict[int, int]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the locked national HPA expectation calibration method.",
    )
    parser.add_argument("nmg_2014_csv", help="Path to NMG 2014 CSV.")
    parser.add_argument("nmg_2024_csv", help="Path to NMG 2024 CSV.")
    parser.add_argument("ppd_csvs", nargs="+", help="One or more PPD CSV files.")
    parser.add_argument(
        "--target-year",
        type=int,
        default=2024,
        help="Production target survey year (default: 2024).",
    )
    return parser


def _load_nmg_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"NMG CSV has no header row: {path}")
        return list(reader)


def run_calibration(
    *,
    nmg_paths: dict[int, Path],
    ppd_paths: list[Path],
    pairing_rule_name: str = DEFAULT_PAIRING_RULE_NAME,
    survey_method_name: str = DEFAULT_SURVEY_METHOD_NAME,
    signal_method_name: str = DEFAULT_SIGNAL_METHOD_NAME,
) -> CalibrationOutput:
    survey_means: dict[int, float] = {}
    for year, path in nmg_paths.items():
        survey_means[year] = aggregate_expectation(
            _load_nmg_rows(path),
            method_name=survey_method_name,
        ).expectation_mean

    ppd_rows, _stats = load_ppd_rows(ppd_paths)
    available_years = {row.transfer_year for row in ppd_rows}
    anchor_pairings = resolve_anchor_pairings(pairing_rule_name, available_years=available_years)

    signal_values: dict[int, float] = {}
    signal_anchor_years: dict[int, int] = {}
    signal_base_years: dict[int, int] = {}
    for survey_year in sorted(nmg_paths):
        anchor_year = anchor_pairings[survey_year]
        base_year = resolve_base_year(available_years, anchor_year=anchor_year)
        signal = build_hpa_signal(
            ppd_rows,
            anchor_year=anchor_year,
            base_year=base_year,
            method_name=signal_method_name,
        )
        signal_values[survey_year] = signal.value
        signal_anchor_years[survey_year] = anchor_year
        signal_base_years[survey_year] = base_year

    factor, const = fit_linear_rule(
        x_values=[signal_values[year] for year in sorted(nmg_paths)],
        y_values=[survey_means[year] for year in sorted(nmg_paths)],
    )

    return CalibrationOutput(
        factor=factor,
        const=const,
        pairing_rule_name=pairing_rule_name,
        survey_method_name=survey_method_name,
        signal_method_name=signal_method_name,
        survey_means=survey_means,
        signal_values=signal_values,
        signal_anchor_years=signal_anchor_years,
        signal_base_years=signal_base_years,
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.target_year != 2024:
        raise SystemExit("This calibration entrypoint is currently locked to target-year 2024.")

    nmg_paths = {
        2014: Path(args.nmg_2014_csv),
        2024: Path(args.nmg_2024_csv),
    }
    for year, path in nmg_paths.items():
        if not path.exists():
            raise SystemExit(f"Missing NMG CSV for {year}: {path}")
    ppd_paths = [Path(path) for path in args.ppd_csvs]
    for path in ppd_paths:
        if not path.exists():
            raise SystemExit(f"Missing PPD CSV: {path}")

    result = run_calibration(nmg_paths=nmg_paths, ppd_paths=ppd_paths)

    print("NMG HPA expectation production calibration")
    print(f"pairing-rule: {result.pairing_rule_name}")
    print(f"survey-method: {result.survey_method_name}")
    print(f"signal-method: {result.signal_method_name}")
    for year in sorted(result.survey_means):
        print(
            f"survey-year {year}: expectation={format_float(result.survey_means[year])} "
            f"ppd-anchor={result.signal_anchor_years[year]} ppd-base={result.signal_base_years[year]} "
            f"signal={format_float(result.signal_values[year])}"
        )
    print(f"HPA_EXPECTATION_FACTOR = {format_float(result.factor)}")
    print(f"HPA_EXPECTATION_CONST = {format_float(result.const)}")


if __name__ == "__main__":
    main()
