#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search modern-window national HPA-expectation method variants for the v4.2 calibration.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.nmg.hpa_expectation import (
    ExpectationAggregate,
    aggregate_expectation,
    classify_hpa_expectation_fit,
    compute_fit_rmse,
    fit_linear_rule,
)
from scripts.python.helpers.ppd.hpa_signal_methods import (
    HpaSignal,
    build_yearly_hpa_signals,
    load_ppd_rows,
)

PRODUCTION_FIT_YEARS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
DIAGNOSTIC_YEARS = (2014, 2016)
STRICT_SENSITIVITY_YEARS = (2020, 2021, 2022, 2023, 2024)
DEFAULT_FIT_YEARS = ",".join(str(year) for year in PRODUCTION_FIT_YEARS)
PRODUCTION_SIGNAL_METHOD = "annual_mean_annualised"
PRODUCTION_CATEGORY_TYPES = {"A"}
ALL_TRANSACTIONS_COMPARISON_KEY = "all_transactions"
RMSE_TIE_TOLERANCE = 1e-6
SURVEY_METHODS = ("midpoint_rounded", "midpoint_exact")
SURVEY_SIMPLICITY_RANK = {
    "midpoint_rounded": 0,
    "midpoint_exact": 1,
}
SIGNAL_SIMPLICITY_RANK = {
    PRODUCTION_SIGNAL_METHOD: 0,
}


@dataclass(frozen=True)
class CandidateEvaluation:
    survey_method_name: str
    signal_method_name: str
    factor: float
    const: float
    is_admissible: bool
    is_preferred: bool
    rmse: float
    survey_simplicity_rank: int
    signal_simplicity_rank: int

    @property
    def simplicity_rank(self) -> tuple[int, int]:
        return self.survey_simplicity_rank, self.signal_simplicity_rank


@dataclass(frozen=True)
class MethodSearchOutput:
    fit_years: tuple[int, ...]
    diagnostic_years: tuple[int, ...]
    nmg_input_paths: dict[int, Path]
    ppd_input_paths: tuple[Path, ...]
    production_signal_method_name: str
    production_category_types: set[str]
    survey_results: dict[int, dict[str, ExpectationAggregate]]
    signal_results: dict[str, dict[int, HpaSignal]]
    diagnostic_signal_results: dict[str, dict[int, HpaSignal]]
    unavailable_diagnostic_years: set[int]
    ranked_results: list[CandidateEvaluation]
    comparison_results: dict[str, CandidateEvaluation]
    strict_window_years: tuple[int, ...]
    strict_window_results: list[CandidateEvaluation]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Search modern-window HPA expectation methods for the v4.2 production calibration.",
    )
    parser.add_argument("nmg_2014_csv", help="Path to NMG 2014 CSV.")
    parser.add_argument("nmg_2016_csv", help="Path to NMG 2016 CSV.")
    parser.add_argument("nmg_2018_csv", help="Path to NMG 2018 CSV.")
    parser.add_argument("nmg_2019_csv", help="Path to NMG 2019 CSV.")
    parser.add_argument("nmg_2020_csv", help="Path to NMG 2020 CSV.")
    parser.add_argument("nmg_2021_csv", help="Path to NMG 2021 CSV.")
    parser.add_argument("nmg_2022_csv", help="Path to NMG 2022 CSV.")
    parser.add_argument("nmg_2023_csv", help="Path to NMG 2023 CSV.")
    parser.add_argument("nmg_2024_csv", help="Path to NMG 2024 CSV.")
    parser.add_argument("ppd_csvs", nargs="+", help="One or more PPD CSV files.")
    parser.add_argument(
        "--fit-years",
        default=DEFAULT_FIT_YEARS,
        help=f"Comma-separated fit years (default: {DEFAULT_FIT_YEARS}).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=20,
        help="Top ranked methods to print (default: 20).",
    )
    return parser


def _load_nmg_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"NMG CSV has no header row: {path}")
        return list(reader)


def _build_survey_results(nmg_paths: dict[int, Path]) -> dict[int, dict[str, ExpectationAggregate]]:
    survey_results: dict[int, dict[str, ExpectationAggregate]] = {}
    for year, path in nmg_paths.items():
        rows = _load_nmg_rows(path)
        survey_results[year] = {
            method_name: aggregate_expectation(rows, method_name=method_name)
            for method_name in SURVEY_METHODS
        }
    return survey_results


def _parse_years(value: str) -> tuple[int, ...]:
    years = tuple(int(token.strip()) for token in value.split(",") if token.strip())
    if len(years) < 2:
        raise ValueError("At least two fit years are required.")
    return years


def evaluate_candidate(
    *,
    survey_method_name: str,
    signal_method_name: str,
    fit_years: Iterable[int],
    survey_results: dict[int, dict[str, ExpectationAggregate]],
    signal_results: dict[str, dict[int, HpaSignal]],
) -> CandidateEvaluation:
    fit_years_tuple = tuple(int(year) for year in fit_years)
    y_values = [survey_results[year][survey_method_name].expectation_mean for year in fit_years_tuple]
    x_values = [signal_results[signal_method_name][year].value for year in fit_years_tuple]
    factor, const = fit_linear_rule(x_values=x_values, y_values=y_values)
    classification = classify_hpa_expectation_fit(factor, const)
    rmse = compute_fit_rmse(x_values=x_values, y_values=y_values, factor=factor, const=const)
    return CandidateEvaluation(
        survey_method_name=survey_method_name,
        signal_method_name=signal_method_name,
        factor=factor,
        const=const,
        is_admissible=classification.is_admissible,
        is_preferred=classification.is_preferred,
        rmse=rmse,
        survey_simplicity_rank=SURVEY_SIMPLICITY_RANK[survey_method_name],
        signal_simplicity_rank=SIGNAL_SIMPLICITY_RANK[signal_method_name],
    )


def rank_results(results: Iterable[CandidateEvaluation]) -> list[CandidateEvaluation]:
    admissible_results = [item for item in results if item.is_admissible]
    lowest_admissible_rmse = min((item.rmse for item in admissible_results), default=None)
    if lowest_admissible_rmse is None:
        lowest_admissible_rmse = min(item.rmse for item in results)

    return sorted(
        results,
        key=lambda item: (
            not item.is_admissible,
            not item.is_preferred,
            round(item.rmse / RMSE_TIE_TOLERANCE) if RMSE_TIE_TOLERANCE > 0 else item.rmse,
            item.survey_simplicity_rank if abs(item.rmse - lowest_admissible_rmse) <= RMSE_TIE_TOLERANCE else 99,
            item.signal_simplicity_rank if abs(item.rmse - lowest_admissible_rmse) <= RMSE_TIE_TOLERANCE else 99,
            item.rmse,
            item.survey_method_name,
            item.signal_method_name,
        ),
    )


def run_method_search(
    *,
    nmg_paths: dict[int, Path],
    ppd_paths: list[Path],
    fit_years: Iterable[int],
) -> MethodSearchOutput:
    fit_years_tuple = tuple(int(year) for year in fit_years)
    survey_results = _build_survey_results(nmg_paths)
    category_a_rows, _stats = load_ppd_rows(
        ppd_paths,
        category_types=PRODUCTION_CATEGORY_TYPES,
    )
    signal_results = {
        PRODUCTION_SIGNAL_METHOD: build_yearly_hpa_signals(
            category_a_rows,
            anchor_years=fit_years_tuple,
            method_name=PRODUCTION_SIGNAL_METHOD,
        )
    }
    diagnostic_signal_results: dict[str, dict[int, HpaSignal]] = {PRODUCTION_SIGNAL_METHOD: {}}
    unavailable_diagnostic_years: set[int] = set()
    for year in DIAGNOSTIC_YEARS:
        try:
            diagnostic_signal_results[PRODUCTION_SIGNAL_METHOD][year] = build_yearly_hpa_signals(
                category_a_rows,
                anchor_years=[year],
                method_name=PRODUCTION_SIGNAL_METHOD,
            )[year]
        except ValueError:
            unavailable_diagnostic_years.add(year)

    ranked_results = rank_results(
        [
            evaluate_candidate(
                survey_method_name=survey_method_name,
                signal_method_name=PRODUCTION_SIGNAL_METHOD,
                fit_years=fit_years_tuple,
                survey_results=survey_results,
                signal_results=signal_results,
            )
            for survey_method_name in SURVEY_METHODS
        ]
    )

    all_rows, _all_stats = load_ppd_rows(ppd_paths)
    all_transaction_signal_results = {
        PRODUCTION_SIGNAL_METHOD: build_yearly_hpa_signals(
            all_rows,
            anchor_years=fit_years_tuple,
            method_name=PRODUCTION_SIGNAL_METHOD,
        )
    }
    best_survey_method_name = ranked_results[0].survey_method_name
    comparison_results = {
        ALL_TRANSACTIONS_COMPARISON_KEY: evaluate_candidate(
            survey_method_name=best_survey_method_name,
            signal_method_name=PRODUCTION_SIGNAL_METHOD,
            fit_years=fit_years_tuple,
            survey_results=survey_results,
            signal_results=all_transaction_signal_results,
        )
    }

    strict_signal_results = {
        PRODUCTION_SIGNAL_METHOD: build_yearly_hpa_signals(
            category_a_rows,
            anchor_years=STRICT_SENSITIVITY_YEARS,
            method_name=PRODUCTION_SIGNAL_METHOD,
        )
    }
    strict_window_results = rank_results(
        [
            evaluate_candidate(
                survey_method_name=survey_method_name,
                signal_method_name=PRODUCTION_SIGNAL_METHOD,
                fit_years=STRICT_SENSITIVITY_YEARS,
                survey_results=survey_results,
                signal_results=strict_signal_results,
            )
            for survey_method_name in SURVEY_METHODS
        ]
    )

    return MethodSearchOutput(
        fit_years=fit_years_tuple,
        diagnostic_years=DIAGNOSTIC_YEARS,
        nmg_input_paths=dict(sorted(nmg_paths.items())),
        ppd_input_paths=tuple(ppd_paths),
        production_signal_method_name=PRODUCTION_SIGNAL_METHOD,
        production_category_types=set(PRODUCTION_CATEGORY_TYPES),
        survey_results=survey_results,
        signal_results=signal_results,
        diagnostic_signal_results=diagnostic_signal_results,
        unavailable_diagnostic_years=unavailable_diagnostic_years,
        ranked_results=ranked_results,
        comparison_results=comparison_results,
        strict_window_years=STRICT_SENSITIVITY_YEARS,
        strict_window_results=strict_window_results,
    )


def _format_status(result: CandidateEvaluation) -> str:
    if result.is_preferred:
        return "preferred"
    if result.is_admissible:
        return "admissible"
    return "inadmissible"


def _format_category_types(category_types: set[str]) -> str:
    return ",".join(sorted(category_types))


def _print_ranked_results(results: list[CandidateEvaluation], *, top_k: int) -> None:
    print("Rank\tStatus\tRMSE\tSurveyMethod\tSignalMethod\tFactor\tConst")
    for rank, result in enumerate(results[:top_k], start=1):
        print(
            f"{rank}\t{_format_status(result)}\t{format_float(result.rmse)}\t"
            f"{result.survey_method_name}\t{result.signal_method_name}\t"
            f"{format_float(result.factor)}\t{format_float(result.const)}"
        )


def _print_signal_diagnostics(
    *,
    output: MethodSearchOutput,
    best_result: CandidateEvaluation,
) -> None:
    print("Yearly anchor diagnostics")
    production_signals = output.signal_results[output.production_signal_method_name]
    for year in output.fit_years:
        aggregate = output.survey_results[year][best_result.survey_method_name]
        signal = production_signals[year]
        base_note = "two-year-base" if signal.base_year == year - 2 else "fallback-base"
        print(
            f"{year}: expectation={format_float(aggregate.expectation_mean)} "
            f"signal={format_float(signal.value)} anchor={signal.anchor_year} "
            f"base={signal.base_year} base-note={base_note}"
        )


def _print_comparison_results(output: MethodSearchOutput) -> None:
    comparison = output.comparison_results.get(ALL_TRANSACTIONS_COMPARISON_KEY)
    if comparison is None:
        return

    print("")
    print("All-transactions comparison")
    print(f"survey-method: {comparison.survey_method_name}")
    print(f"signal-method: {comparison.signal_method_name}")
    print(f"plausibility: {_format_status(comparison)}")
    print(f"fit-rmse: {format_float(comparison.rmse)}")
    print(f"factor: {format_float(comparison.factor)}")
    print(f"const: {format_float(comparison.const)}")


def _print_strict_window_results(output: MethodSearchOutput) -> None:
    print("")
    print("Strict 2020 to 2024 sensitivity")
    print(f"Fit years = {', '.join(str(year) for year in output.strict_window_years)}")
    _print_ranked_results(output.strict_window_results, top_k=len(output.strict_window_results))


def _print_diagnostic_behavior(
    *,
    output: MethodSearchOutput,
    best_result: CandidateEvaluation,
) -> None:
    print("")
    print("Diagnostic behavior")
    for year in output.diagnostic_years:
        aggregate = output.survey_results[year][best_result.survey_method_name]
        diagnostic_signal = output.diagnostic_signal_results[output.production_signal_method_name].get(year)
        if diagnostic_signal is None:
            print(
                f"{year}: expectation={format_float(aggregate.expectation_mean)} "
                "signal=unavailable"
            )
            continue
        predicted = (best_result.factor * diagnostic_signal.value) + best_result.const
        print(
            f"{year}: expectation={format_float(aggregate.expectation_mean)} "
            f"signal={format_float(diagnostic_signal.value)} "
            f"predicted={format_float(predicted)}"
        )


def _print_output(output: MethodSearchOutput, top_k: int) -> None:
    print("NMG HPA expectation method search")
    print(
        "NMG inputs = "
        + ", ".join(f"{year}:{path}" for year, path in output.nmg_input_paths.items())
    )
    print("PPD inputs = " + ", ".join(str(path) for path in output.ppd_input_paths))
    print(f"Fit years = {', '.join(str(year) for year in output.fit_years)}")
    print(f"Diagnostic years = {', '.join(str(year) for year in output.diagnostic_years)}")
    print(f"Category types = {_format_category_types(output.production_category_types)}")
    print(f"Signal method = {output.production_signal_method_name}")
    print("")
    _print_ranked_results(output.ranked_results, top_k=top_k)

    best = output.ranked_results[0]
    print("")
    print("Selected production candidate")
    print(f"survey-method: {best.survey_method_name}")
    print(f"signal-method: {best.signal_method_name}")
    print(f"category-types: {_format_category_types(output.production_category_types)}")
    print(f"plausibility: {_format_status(best)}")
    print(f"fit-rmse: {format_float(best.rmse)}")
    print(f"factor: {format_float(best.factor)}")
    print(f"const: {format_float(best.const)}")

    print("")
    _print_signal_diagnostics(output=output, best_result=best)
    _print_comparison_results(output)
    _print_strict_window_results(output)
    _print_diagnostic_behavior(output=output, best_result=best)


def main() -> None:
    args = build_arg_parser().parse_args()
    if args.top_k <= 0:
        raise SystemExit("top-k must be positive.")

    nmg_paths = {
        2014: Path(args.nmg_2014_csv),
        2016: Path(args.nmg_2016_csv),
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

    ppd_paths = [Path(path) for path in args.ppd_csvs]
    for path in ppd_paths:
        if not path.exists():
            raise SystemExit(f"Missing PPD CSV: {path}")

    output = run_method_search(
        nmg_paths=nmg_paths,
        ppd_paths=ppd_paths,
        fit_years=_parse_years(args.fit_years),
    )
    _print_output(output, args.top_k)


if __name__ == "__main__":
    main()
