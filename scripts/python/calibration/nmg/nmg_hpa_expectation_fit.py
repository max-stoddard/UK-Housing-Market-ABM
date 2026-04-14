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
    PRODUCTION_CATEGORY_TYPES,
    PRODUCTION_FIT_YEARS,
    PRODUCTION_SIGNAL_METHOD,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.nmg.hpa_expectation import (
    HpaExpectationFitClassification,
    aggregate_expectation,
    classify_hpa_expectation_fit,
    compute_fit_rmse,
    fit_linear_rule,
)
from scripts.python.helpers.ppd.hpa_signal_methods import build_yearly_hpa_signals, load_ppd_rows

LOCKED_SURVEY_METHOD = "midpoint_exact"
LOCKED_SIGNAL_METHOD = PRODUCTION_SIGNAL_METHOD
LOCKED_CATEGORY_TYPES = set(PRODUCTION_CATEGORY_TYPES)
PRODUCTION_YEARS = PRODUCTION_FIT_YEARS


@dataclass(frozen=True)
class CalibrationOutput:
    factor: float
    const: float
    survey_method_name: str
    signal_method_name: str
    survey_means: dict[int, float]
    signal_values: dict[int, float]
    signal_anchor_years: dict[int, int]
    signal_base_years: dict[int, int]
    category_types: set[str]
    classification: HpaExpectationFitClassification
    rmse: float


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the locked national HPA expectation calibration method.",
    )
    parser.add_argument("nmg_2018_csv", help="Path to NMG 2018 CSV.")
    parser.add_argument("nmg_2019_csv", help="Path to NMG 2019 CSV.")
    parser.add_argument("nmg_2020_csv", help="Path to NMG 2020 CSV.")
    parser.add_argument("nmg_2021_csv", help="Path to NMG 2021 CSV.")
    parser.add_argument("nmg_2022_csv", help="Path to NMG 2022 CSV.")
    parser.add_argument("nmg_2023_csv", help="Path to NMG 2023 CSV.")
    parser.add_argument("nmg_2024_csv", help="Path to NMG 2024 CSV.")
    parser.add_argument("--ppd", nargs="+", required=True, help="One or more PPD CSV files.")
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
    survey_method_name: str = LOCKED_SURVEY_METHOD,
    signal_method_name: str = LOCKED_SIGNAL_METHOD,
    category_types: set[str] | None = LOCKED_CATEGORY_TYPES,
) -> CalibrationOutput:
    survey_means: dict[int, float] = {}
    for year in sorted(nmg_paths):
        survey_means[year] = aggregate_expectation(
            _load_nmg_rows(nmg_paths[year]),
            method_name=survey_method_name,
        ).expectation_mean

    ppd_rows, _stats = load_ppd_rows(
        ppd_paths,
        category_types=category_types,
    )
    signals = build_yearly_hpa_signals(
        ppd_rows,
        anchor_years=PRODUCTION_YEARS,
        method_name=signal_method_name,
    )
    signal_values = {year: signals[year].value for year in PRODUCTION_YEARS}
    factor, const = fit_linear_rule(
        x_values=[signal_values[year] for year in PRODUCTION_YEARS],
        y_values=[survey_means[year] for year in PRODUCTION_YEARS],
    )
    classification = classify_hpa_expectation_fit(factor, const)
    rmse = compute_fit_rmse(
        x_values=[signal_values[year] for year in PRODUCTION_YEARS],
        y_values=[survey_means[year] for year in PRODUCTION_YEARS],
        factor=factor,
        const=const,
    )

    return CalibrationOutput(
        factor=factor,
        const=const,
        survey_method_name=survey_method_name,
        signal_method_name=signal_method_name,
        survey_means=survey_means,
        signal_values=signal_values,
        signal_anchor_years={year: signals[year].anchor_year for year in PRODUCTION_YEARS},
        signal_base_years={year: signals[year].base_year for year in PRODUCTION_YEARS},
        category_types=set(category_types or set()),
        classification=classification,
        rmse=rmse,
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.target_year != 2024:
        raise SystemExit("This calibration entrypoint is currently locked to target-year 2024.")

    nmg_paths = {
        2018: Path(args.nmg_2018_csv),
        2019: Path(args.nmg_2019_csv),
        2020: Path(args.nmg_2020_csv),
        2021: Path(args.nmg_2021_csv),
        2022: Path(args.nmg_2022_csv),
        2023: Path(args.nmg_2023_csv),
        2024: Path(args.nmg_2024_csv),
    }
    for year, path in nmg_paths.items():
        if not path.exists():
            raise SystemExit(f"Missing NMG CSV for {year}: {path}")
    ppd_paths = [Path(path) for path in args.ppd]
    for path in ppd_paths:
        if not path.exists():
            raise SystemExit(f"Missing PPD CSV: {path}")

    result = run_calibration(nmg_paths=nmg_paths, ppd_paths=ppd_paths)
    if not result.classification.is_admissible:
        raise SystemExit("Revised v4.2 HPA calibration produced an inadmissible fit.")

    print("NMG HPA expectation production calibration")
    print(f"survey-method: {result.survey_method_name}")
    print(f"signal-method: {result.signal_method_name}")
    print(f"category-types: {','.join(sorted(result.category_types))}")
    print(f"plausibility: {result.classification.label}")
    print(f"fit-rmse: {format_float(result.rmse)}")
    for year in PRODUCTION_YEARS:
        print(
            f"survey-year {year}: expectation={format_float(result.survey_means[year])} "
            f"ppd-anchor={result.signal_anchor_years[year]} ppd-base={result.signal_base_years[year]} "
            f"signal={format_float(result.signal_values[year])}"
        )
    print(f"HPA_EXPECTATION_FACTOR = {format_float(result.factor)}")
    print(f"HPA_EXPECTATION_CONST = {format_float(result.const)}")


if __name__ == "__main__":
    main()
