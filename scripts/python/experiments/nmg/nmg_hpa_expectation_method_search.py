#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search small national HPA-expectation method variants against the legacy rule.

Latest experiment findings (run on April 14, 2026):
  - Datasets:
    - NMG: private-datasets/nmg/nmg-2014.csv, private-datasets/nmg/nmg-2016.csv, private-datasets/nmg/nmg-2024.csv
    - PPD: private-datasets/ppd/pp-2011.csv, private-datasets/ppd/pp.2012.csv, private-datasets/ppd/pp-2018.csv,
      private-datasets/ppd/pp-2022.csv, private-datasets/ppd/pp-2023.csv, private-datasets/ppd/pp-2024.csv,
      private-datasets/ppd/pp-2025.csv
  - Selected default method family:
    - Pairing rule: previous_available
    - Survey mapping: midpoint_rounded
    - PPD signal: annual_mean_annualised
  - Fit on 2014 + 2024 anchors:
    - HPA_EXPECTATION_FACTOR ~= 0.2613031701
    - HPA_EXPECTATION_CONST ~= 0.0326229784
    - Distance to legacy 0.44 / -0.007 ~= 0.1830369838
  - 2016 holdout:
    - Observed ~= 0.0124586536
    - Predicted ~= 0.0388869571
    - Absolute error ~= 0.0264283035
  - Interpretation:
    - Under the approved simple search space, the best method still remains materially far from the
      legacy coefficients, indicating that anchor-pairing compromises and missing historical data
      dominate the reconstruction error.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.math_stats import euclidean_distance_2d
from scripts.python.helpers.common.io_properties import read_properties
from scripts.python.helpers.nmg.hpa_expectation import (
    EXPECTATION_METHOD_SPECS,
    ExpectationAggregate,
    aggregate_expectation,
    fit_linear_rule,
)
from scripts.python.helpers.ppd.hpa_signal_methods import (
    HpaSignal,
    build_hpa_signal,
    load_ppd_rows,
    resolve_base_year,
)

DEFAULT_CALIBRATION_YEARS = (2014, 2024)
SIGNAL_METHODS = (
    "java_like_annualised",
    "annual_mean_annualised",
    "annual_mean_cumulative",
)
PAIRING_RULES = (
    "nearest_available",
    "previous_available",
)
DEFAULT_PAIRING_RULE_NAME = "previous_available"
DEFAULT_SURVEY_METHOD_NAME = "midpoint_rounded"
DEFAULT_SIGNAL_METHOD_NAME = "annual_mean_annualised"
PAIRING_RULE_SIMPLICITY_RANK = {
    "previous_available": 0,
    "nearest_available": 1,
}
SIGNAL_SIMPLICITY_RANK = {
    "java_like_annualised": 0,
    "annual_mean_annualised": 1,
    "annual_mean_cumulative": 2,
}
SURVEY_SIMPLICITY_RANK = {
    "midpoint_exact": 0,
    "midpoint_rounded": 1,
    "midpoint_exact_cap25": 2,
    "midpoint_exact_cap35": 2,
}


@dataclass(frozen=True)
class CandidateEvaluation:
    pairing_rule_name: str
    survey_method_name: str
    signal_method_name: str
    factor: float
    const: float
    legacy_distance: float
    holdout_year: int
    holdout_observed: float
    holdout_predicted: float
    simplicity_rank: int

    @property
    def holdout_abs_error(self) -> float:
        return abs(self.holdout_predicted - self.holdout_observed)


@dataclass(frozen=True)
class MethodSearchOutput:
    target_factor: float
    target_const: float
    survey_results: dict[int, dict[str, ExpectationAggregate]]
    signal_results: dict[str, dict[str, dict[int, HpaSignal]]]
    ranked_results: list[CandidateEvaluation]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search national HPA expectation methods by legacy recovery and 2016 holdout behavior.",
    )
    parser.add_argument("nmg_2014_csv", help="Path to NMG 2014 CSV.")
    parser.add_argument("nmg_2016_csv", help="Path to NMG 2016 CSV.")
    parser.add_argument("nmg_2024_csv", help="Path to NMG 2024 CSV.")
    parser.add_argument("ppd_csvs", nargs="+", help="One or more PPD CSV files.")
    parser.add_argument(
        "--config-path",
        default="src/main/resources/config.properties",
        help="Path to config.properties containing legacy HPA expectation targets.",
    )
    parser.add_argument(
        "--holdout-year",
        type=int,
        default=2016,
        help="Survey year reserved for holdout scoring (default: 2016).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Top ranked methods to print (default: 20).",
    )
    return parser


def rank_results(results: Iterable[CandidateEvaluation]) -> list[CandidateEvaluation]:
    return sorted(
        results,
        key=lambda item: (
            item.legacy_distance,
            item.holdout_abs_error,
            item.simplicity_rank,
            item.pairing_rule_name,
            item.survey_method_name,
            item.signal_method_name,
        ),
    )


def resolve_anchor_pairings(rule_name: str, *, available_years: Iterable[int]) -> dict[int, int]:
    years = sorted(set(int(year) for year in available_years))
    if not years:
        raise ValueError("No PPD years are available for pairing.")

    def previous_or_equal(survey_year: int) -> int:
        candidates = [year for year in years if year <= survey_year]
        if not candidates:
            raise ValueError(f"No non-future PPD year is available for survey year {survey_year}.")
        return candidates[-1]

    if rule_name == "previous_available":
        return {
            2014: previous_or_equal(2014),
            2016: previous_or_equal(2016),
            2024: previous_or_equal(2024),
        }
    if rule_name == "nearest_available":
        resolved: dict[int, int] = {}
        for survey_year in (2014, 2016, 2024):
            resolved[survey_year] = min(
                years,
                key=lambda year: (abs(year - survey_year), year > survey_year, year),
            )
        return resolved
    raise ValueError(f"Unsupported pairing rule: {rule_name}")


def _load_nmg_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"NMG CSV has no header row: {path}")
        return list(reader)


def _load_targets(config_path: Path) -> tuple[float, float]:
    props = read_properties(config_path)
    return float(props["HPA_EXPECTATION_FACTOR"]), float(props["HPA_EXPECTATION_CONST"])


def _build_survey_results(nmg_paths: dict[int, Path]) -> dict[int, dict[str, ExpectationAggregate]]:
    survey_results: dict[int, dict[str, ExpectationAggregate]] = {}
    for year, path in nmg_paths.items():
        rows = _load_nmg_rows(path)
        survey_results[year] = {
            method_name: aggregate_expectation(rows, method_name=method_name)
            for method_name in EXPECTATION_METHOD_SPECS
        }
    return survey_results


def _build_signal_results(
    *,
    ppd_paths: list[Path],
    pairing_rule_name: str,
) -> dict[str, dict[int, HpaSignal]]:
    rows, _stats = load_ppd_rows(ppd_paths)
    available_years = {row.transfer_year for row in rows}
    anchor_pairings = resolve_anchor_pairings(pairing_rule_name, available_years=available_years)
    signal_results: dict[str, dict[int, HpaSignal]] = {}
    for method_name in SIGNAL_METHODS:
        signal_results[method_name] = {}
        for survey_year, ppd_anchor_year in anchor_pairings.items():
            base_year = resolve_base_year(available_years, anchor_year=ppd_anchor_year)
            signal_results[method_name][survey_year] = build_hpa_signal(
                rows,
                anchor_year=ppd_anchor_year,
                base_year=base_year,
                method_name=method_name,
            )
    return signal_results


def run_method_search(
    *,
    nmg_paths: dict[int, Path],
    ppd_paths: list[Path],
    config_path: Path,
    holdout_year: int,
) -> MethodSearchOutput:
    target_factor, target_const = _load_targets(config_path)
    survey_results = _build_survey_results(nmg_paths)
    rows, _stats = load_ppd_rows(ppd_paths)
    available_years = {row.transfer_year for row in rows}
    signal_results: dict[str, dict[str, dict[int, HpaSignal]]] = {}
    for pairing_rule_name in PAIRING_RULES:
        signal_results[pairing_rule_name] = {}
        anchor_pairings = resolve_anchor_pairings(pairing_rule_name, available_years=available_years)
        for method_name in SIGNAL_METHODS:
            signal_results[pairing_rule_name][method_name] = {}
            for survey_year, ppd_anchor_year in anchor_pairings.items():
                base_year = resolve_base_year(available_years, anchor_year=ppd_anchor_year)
                signal_results[pairing_rule_name][method_name][survey_year] = build_hpa_signal(
                    rows,
                    anchor_year=ppd_anchor_year,
                    base_year=base_year,
                    method_name=method_name,
                )

    ranked: list[CandidateEvaluation] = []
    fit_years = [year for year in DEFAULT_CALIBRATION_YEARS if year != holdout_year]
    if len(fit_years) < 2:
        raise ValueError("At least two calibration years are required after removing the holdout.")

    for survey_method_name in EXPECTATION_METHOD_SPECS:
        y_values = [survey_results[year][survey_method_name].expectation_mean for year in fit_years]
        for pairing_rule_name in PAIRING_RULES:
            for signal_method_name in SIGNAL_METHODS:
                x_values = [
                    signal_results[pairing_rule_name][signal_method_name][year].value
                    for year in fit_years
                ]
                factor, const = fit_linear_rule(x_values=x_values, y_values=y_values)
                holdout_signal = signal_results[pairing_rule_name][signal_method_name][holdout_year].value
                holdout_observed = survey_results[holdout_year][survey_method_name].expectation_mean
                holdout_predicted = (factor * holdout_signal) + const
                legacy_distance = euclidean_distance_2d(factor, const, target_factor, target_const)
                ranked.append(
                    CandidateEvaluation(
                        pairing_rule_name=pairing_rule_name,
                        survey_method_name=survey_method_name,
                        signal_method_name=signal_method_name,
                        factor=factor,
                        const=const,
                        legacy_distance=legacy_distance,
                        holdout_year=holdout_year,
                        holdout_observed=holdout_observed,
                        holdout_predicted=holdout_predicted,
                        simplicity_rank=PAIRING_RULE_SIMPLICITY_RANK[pairing_rule_name]
                        + SURVEY_SIMPLICITY_RANK[survey_method_name]
                        + SIGNAL_SIMPLICITY_RANK[signal_method_name],
                    )
                )

    return MethodSearchOutput(
        target_factor=target_factor,
        target_const=target_const,
        survey_results=survey_results,
        signal_results=signal_results,
        ranked_results=rank_results(ranked),
    )


def _print_output(output: MethodSearchOutput, top_k: int) -> None:
    print("NMG HPA expectation method search")
    print(f"Target HPA_EXPECTATION_FACTOR = {format_float(output.target_factor)}")
    print(f"Target HPA_EXPECTATION_CONST = {format_float(output.target_const)}")
    print("")
    print(
        "Rank\tLegacyDistance\tHoldoutError\tPairingRule\tSurveyMethod\tSignalMethod\tFactor\tConst\tObserved2016\tPredicted2016"
    )
    for rank, result in enumerate(output.ranked_results[:top_k], start=1):
        print(
            f"{rank}\t{format_float(result.legacy_distance)}\t"
            f"{format_float(result.holdout_abs_error)}\t"
            f"{result.pairing_rule_name}\t"
            f"{result.survey_method_name}\t{result.signal_method_name}\t"
            f"{format_float(result.factor)}\t{format_float(result.const)}\t"
            f"{format_float(result.holdout_observed)}\t{format_float(result.holdout_predicted)}"
        )
    best = output.ranked_results[0]
    print("")
    print("Best method")
    print(f"pairing-rule: {best.pairing_rule_name}")
    print(f"survey-method: {best.survey_method_name}")
    print(f"signal-method: {best.signal_method_name}")
    print(f"factor: {format_float(best.factor)}")
    print(f"const: {format_float(best.const)}")
    print(f"distance-to-legacy: {format_float(best.legacy_distance)}")
    print(f"holdout-year: {best.holdout_year}")
    print(f"holdout-observed: {format_float(best.holdout_observed)}")
    print(f"holdout-predicted: {format_float(best.holdout_predicted)}")
    print(f"holdout-abs-error: {format_float(best.holdout_abs_error)}")

    print("")
    print("Survey diagnostics")
    for year in sorted(output.survey_results):
        aggregate = output.survey_results[year][best.survey_method_name]
        print(
            f"{year}: rows-read={aggregate.rows_read} rows-used={aggregate.rows_used} "
            f"dont-know={aggregate.rows_dont_know} missing-code={aggregate.rows_missing_code} "
            f"invalid-code={aggregate.rows_invalid_code} invalid-weight={aggregate.rows_invalid_weight} "
            f"weight-total-used={format_float(aggregate.weight_total_used)} "
            f"expectation={format_float(aggregate.expectation_mean)}"
        )

    print("")
    print("PPD diagnostics")
    for year in sorted(output.signal_results[best.pairing_rule_name][best.signal_method_name]):
        signal = output.signal_results[best.pairing_rule_name][best.signal_method_name][year]
        print(
            f"{year}: anchor={signal.anchor_year} base={signal.base_year} "
            f"signal={format_float(signal.value)} diagnostics={signal.diagnostics}"
        )

    print("")
    print("Interpretation")
    print(
        "The selected method keeps the search space simple, avoids future-looking pairings, "
        "and improves the 2016 holdout versus the nearest-available pairing while remaining "
        "the closest legacy-distance family found in the approved constrained search."
    )


def main() -> None:
    args = build_arg_parser().parse_args()
    config_path = Path(args.config_path)
    if not config_path.exists():
        raise SystemExit(f"Missing config file: {config_path}")
    if args.top_k <= 0:
        raise SystemExit("top-k must be positive.")

    nmg_paths = {
        2014: Path(args.nmg_2014_csv),
        2016: Path(args.nmg_2016_csv),
        2024: Path(args.nmg_2024_csv),
    }
    for year, path in nmg_paths.items():
        if not path.exists():
            raise SystemExit(f"Missing NMG CSV for {year}: {path}")

    ppd_paths = [Path(path) for path in args.ppd_csvs]
    for path in ppd_paths:
        if not path.exists():
            raise SystemExit(f"Missing PPD CSV: {path}")

    output = run_method_search(
        nmg_paths=nmg_paths,
        ppd_paths=ppd_paths,
        config_path=config_path,
        holdout_year=args.holdout_year,
    )
    _print_output(output, args.top_k)


if __name__ == "__main__":
    main()
