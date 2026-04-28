#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibrate household consumption fractions from LCFS household records.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

import numpy as np
import pandas as pd

from scripts.python.helpers.common.paths import ensure_output_dir, repo_root


ESSENTIAL_CONSUMPTION_FRACTION_KEY = "ESSENTIAL_CONSUMPTION_FRACTION"
MAXIMUM_CONSUMPTION_FRACTION_KEY = "MAXIMUM_CONSUMPTION_FRACTION"

DEFAULT_DATASET_YEAR = 2024
DEFAULT_METHOD = "weighted-modern"
DEFAULT_DATASET_PATHS = {
    2011: Path("private-datasets/lcfs/2011/2011_dvhh_ukanon.tab"),
    2024: Path("private-datasets/lcfs/2024/dvhh_ukanon_v2_2023.tab"),
}

METHOD_CHOICES = ("weighted-modern", "transparent-literal", "legacy-match")
SUMMARY_FILE_NAME = "LcfsConsumptionFractionsSummary.json"
SOURCE_VALUES_FILE_NAME = "LcfsConsumptionFractionsSourceValues.csv"

HISTORICAL_WEEKLY_INCOME_LOWER = 400.0
HISTORICAL_WEEKLY_INCOME_UPPER = 480.0
MODERN_2024_WEEKLY_INCOME_LOWER = 520.0
MODERN_2024_WEEKLY_INCOME_UPPER = 640.0
LEGACY_MONTHLY_INCOME_LOWER = 400.0
LEGACY_MONTHLY_INCOME_UPPER = 480.0
HISTORICAL_ANNUAL_INCOME_SUPPORT_FLOOR = 5900.0
MODERN_2024_ANNUAL_INCOME_SUPPORT_FLOOR = 7400.0
MODERN_MAXIMUM_QUANTILE = 0.99
LEGACY_MATCH_MAXIMUM_QUANTILE = 0.987
CONFIG_VALUE_DECIMALS = 10


@dataclass(frozen=True)
class DatasetColumns:
    modern_income: str
    legacy_income: str
    total_consumption: str
    legacy_total_consumption: str
    weight: str


@dataclass(frozen=True)
class MethodSpec:
    method: str
    income_column: str
    consumption_column: str
    weight_column: str | None
    essential_income_basis: Literal["weekly", "monthly"]
    essential_income_lower: float
    essential_income_upper: float
    annual_income_support_floor: float
    essential_statistic: Literal["weighted_median", "median"]
    maximum_quantile: float
    maximum_statistic: Literal["weighted_quantile", "quantile"]
    config_decimals: int
    rationale: str


@dataclass(frozen=True)
class ParameterEstimate:
    key: str
    value: float
    rounded_config_value: float
    sample_rows: int
    weight_sum: float | None
    statistic: str
    ratio_numerator: str
    ratio_denominator: str
    filter_description: str


@dataclass(frozen=True)
class CalibrationResult:
    dataset_year: int
    dataset_path: str
    method: str
    method_rationale: str
    selected_config_values: dict[str, float]
    estimates: list[ParameterEstimate]
    diagnostics: dict[str, Any]
    method_comparison: list[dict[str, Any]]


DATASET_COLUMNS = {
    2011: DatasetColumns(
        modern_income="p344p",
        legacy_income="incanon",
        total_consumption="P600t",
        legacy_total_consumption="P600",
        weight="weighta",
    ),
    2024: DatasetColumns(
        modern_income="p344p",
        legacy_income="anon_income",
        total_consumption="p600t",
        legacy_total_consumption="p600",
        weight="weighta",
    ),
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calibrate ESSENTIAL_CONSUMPTION_FRACTION and MAXIMUM_CONSUMPTION_FRACTION from LCFS."
    )
    parser.add_argument(
        "--dataset-year",
        type=int,
        choices=sorted(DEFAULT_DATASET_PATHS),
        default=DEFAULT_DATASET_YEAR,
        help="LCFS dataset year/schema to use. Defaults to 2024.",
    )
    parser.add_argument(
        "--input-tab",
        default=None,
        help="Optional LCFS derived household TSV path. Defaults from --dataset-year.",
    )
    parser.add_argument(
        "--method",
        choices=METHOD_CHOICES,
        default=DEFAULT_METHOD,
        help="Calibration method. Defaults to weighted-modern.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path for the selected calibration JSON summary.",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="Optional directory for aggregate evidence CSV/JSON outputs. Raw LCFS rows are not written.",
    )
    return parser


def resolve_dataset_path(
    input_tab: str | Path | None,
    dataset_year: int,
    *,
    root: Path | None = None,
) -> Path:
    if dataset_year not in DEFAULT_DATASET_PATHS:
        raise ValueError(f"Unsupported LCFS dataset year: {dataset_year}")
    candidate = Path(input_tab).expanduser() if input_tab else DEFAULT_DATASET_PATHS[dataset_year]
    base_root = root if root is not None else repo_root()
    resolved = candidate if candidate.is_absolute() else base_root / candidate
    if not resolved.exists():
        raise FileNotFoundError(f"Missing LCFS household TSV: {resolved}")
    return resolved.resolve()


def method_spec(method: str, dataset_year: int) -> MethodSpec:
    if dataset_year not in DATASET_COLUMNS:
        raise ValueError(f"Unsupported LCFS dataset year: {dataset_year}")
    columns = DATASET_COLUMNS[dataset_year]
    if method == "weighted-modern":
        if dataset_year == 2024:
            essential_income_lower = MODERN_2024_WEEKLY_INCOME_LOWER
            essential_income_upper = MODERN_2024_WEEKLY_INCOME_UPPER
            annual_income_support_floor = MODERN_2024_ANNUAL_INCOME_SUPPORT_FLOOR
        else:
            essential_income_lower = HISTORICAL_WEEKLY_INCOME_LOWER
            essential_income_upper = HISTORICAL_WEEKLY_INCOME_UPPER
            annual_income_support_floor = HISTORICAL_ANNUAL_INCOME_SUPPORT_FLOOR
        return MethodSpec(
            method=method,
            income_column=columns.modern_income,
            consumption_column=columns.total_consumption,
            weight_column=columns.weight,
            essential_income_basis="weekly",
            essential_income_lower=essential_income_lower,
            essential_income_upper=essential_income_upper,
            annual_income_support_floor=annual_income_support_floor,
            essential_statistic="weighted_median",
            maximum_quantile=MODERN_MAXIMUM_QUANTILE,
            maximum_statistic="weighted_quantile",
            config_decimals=CONFIG_VALUE_DECIMALS,
            rationale=(
                "Uses annual survey weights, gross normal weekly household income, "
                "and all-person total consumption expenditure."
            ),
        )
    if method == "transparent-literal":
        return MethodSpec(
            method=method,
            income_column=columns.legacy_income,
            consumption_column=columns.legacy_total_consumption,
            weight_column=columns.weight,
            essential_income_basis="monthly",
            essential_income_lower=LEGACY_MONTHLY_INCOME_LOWER,
            essential_income_upper=LEGACY_MONTHLY_INCOME_UPPER,
            annual_income_support_floor=HISTORICAL_ANNUAL_INCOME_SUPPORT_FLOOR,
            essential_statistic="weighted_median",
            maximum_quantile=MODERN_MAXIMUM_QUANTILE,
            maximum_statistic="weighted_quantile",
            config_decimals=CONFIG_VALUE_DECIMALS,
            rationale=(
                "Implements the existing config comments literally: monthly income "
                "400-480 and 99th percentile for annual income above 5900."
            ),
        )
    if method == "legacy-match":
        return MethodSpec(
            method=method,
            income_column=columns.legacy_income,
            consumption_column=columns.total_consumption,
            weight_column=columns.weight,
            essential_income_basis="weekly",
            essential_income_lower=HISTORICAL_WEEKLY_INCOME_LOWER,
            essential_income_upper=HISTORICAL_WEEKLY_INCOME_UPPER,
            annual_income_support_floor=HISTORICAL_ANNUAL_INCOME_SUPPORT_FLOOR,
            essential_statistic="median",
            maximum_quantile=LEGACY_MATCH_MAXIMUM_QUANTILE,
            maximum_statistic="weighted_quantile",
            config_decimals=2,
            rationale=(
                "Legacy-compatible diagnostic method: the old 0.66 is matched by the "
                "unweighted median in the 400-480 weekly-income band, while the old "
                "0.17 aligns with roughly the weighted 98.7th percentile rather than "
                "the literal weighted 99th percentile."
            ),
        )
    raise ValueError(f"Unsupported LCFS method: {method}")


def required_columns_for_method(spec: MethodSpec) -> list[str]:
    columns = [spec.income_column, spec.consumption_column]
    if spec.weight_column:
        columns.append(spec.weight_column)
    return columns


def load_lcfs_data(path: Path, required_columns: Iterable[str]) -> pd.DataFrame:
    columns = list(dict.fromkeys(required_columns))
    try:
        data = pd.read_csv(
            path,
            sep="\t",
            usecols=columns,
            na_values=[" ", ""],
            low_memory=False,
        )
    except ValueError as exc:
        raise ValueError(f"LCFS household data missing required columns: {columns}") from exc
    missing_columns = [column for column in columns if column not in data.columns]
    if missing_columns:
        raise ValueError(f"LCFS household data missing required columns: {missing_columns}")
    for column in columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data


def weighted_quantile(values: pd.Series | np.ndarray, weights: pd.Series | np.ndarray, quantile: float) -> float:
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")
    value_array = np.asarray(values, dtype=float)
    weight_array = np.asarray(weights, dtype=float)
    valid_mask = np.isfinite(value_array) & np.isfinite(weight_array) & (weight_array > 0.0)
    if not valid_mask.any():
        raise ValueError("No positive-weight observations for weighted quantile.")
    value_array = value_array[valid_mask]
    weight_array = weight_array[valid_mask]
    order = np.argsort(value_array)
    sorted_values = value_array[order]
    sorted_weights = weight_array[order]
    cumulative_weights = np.cumsum(sorted_weights)
    cumulative_share = cumulative_weights / cumulative_weights[-1]
    return float(np.interp(quantile, cumulative_share, sorted_values))


def _round_config_value(value: float, decimals: int) -> float:
    return round(float(value), decimals)


def _weight_sum(data: pd.DataFrame, weight_column: str | None) -> float | None:
    if weight_column is None:
        return None
    return float(data[weight_column].sum())


def _statistic_value(ratios: pd.Series, weights: pd.Series | None, statistic: str, quantile: float | None = None) -> float:
    if ratios.empty:
        raise ValueError("No LCFS observations available after applying calibration filters.")
    if statistic == "median":
        return float(ratios.median())
    if statistic == "quantile":
        if quantile is None:
            raise ValueError("quantile is required for quantile statistic")
        return float(ratios.quantile(quantile))
    if statistic == "weighted_median":
        if weights is None:
            raise ValueError("weights are required for weighted median")
        return weighted_quantile(ratios, weights, 0.5)
    if statistic == "weighted_quantile":
        if weights is None:
            raise ValueError("weights are required for weighted quantile")
        if quantile is None:
            raise ValueError("quantile is required for weighted quantile")
        return weighted_quantile(ratios, weights, quantile)
    raise ValueError(f"Unsupported statistic: {statistic}")


def compute_estimates(data: pd.DataFrame, spec: MethodSpec) -> tuple[list[ParameterEstimate], dict[str, Any]]:
    positive_mask = (
        data[spec.income_column].notna()
        & data[spec.consumption_column].notna()
        & (data[spec.income_column] > 0.0)
        & (data[spec.consumption_column] > 0.0)
    )
    if spec.weight_column:
        positive_mask &= data[spec.weight_column].notna() & (data[spec.weight_column] > 0.0)

    valid_data = data.loc[positive_mask].copy()
    if valid_data.empty:
        raise ValueError("No valid LCFS observations after requiring positive income, consumption, and weights.")

    if spec.essential_income_basis == "weekly":
        essential_mask = (
            (valid_data[spec.income_column] >= spec.essential_income_lower)
            & (valid_data[spec.income_column] <= spec.essential_income_upper)
        )
        essential_filter = (
            f"{spec.income_column} between {spec.essential_income_lower:g} and "
            f"{spec.essential_income_upper:g} weekly"
        )
    else:
        monthly_income = valid_data[spec.income_column] * 52.0 / 12.0
        essential_mask = (
            (monthly_income >= spec.essential_income_lower)
            & (monthly_income <= spec.essential_income_upper)
        )
        essential_filter = (
            f"{spec.income_column} converted to monthly income between "
            f"{spec.essential_income_lower:g} and {spec.essential_income_upper:g}"
        )

    essential_data = valid_data.loc[essential_mask].copy()
    maximum_data = valid_data.loc[valid_data[spec.income_column] * 52.0 > spec.annual_income_support_floor].copy()

    essential_ratios = essential_data[spec.consumption_column] / essential_data[spec.income_column]
    maximum_ratios = maximum_data[spec.consumption_column] / (12.0 * maximum_data[spec.income_column])
    essential_weights = essential_data[spec.weight_column] if spec.weight_column else None
    maximum_weights = maximum_data[spec.weight_column] if spec.weight_column else None

    essential_value = _statistic_value(
        essential_ratios,
        essential_weights,
        spec.essential_statistic,
    )
    maximum_value = _statistic_value(
        maximum_ratios,
        maximum_weights,
        spec.maximum_statistic,
        spec.maximum_quantile,
    )

    estimates = [
        ParameterEstimate(
            key=ESSENTIAL_CONSUMPTION_FRACTION_KEY,
            value=essential_value,
            rounded_config_value=_round_config_value(essential_value, spec.config_decimals),
            sample_rows=int(len(essential_data)),
            weight_sum=_weight_sum(essential_data, spec.weight_column),
            statistic=spec.essential_statistic,
            ratio_numerator=spec.consumption_column,
            ratio_denominator=spec.income_column,
            filter_description=essential_filter,
        ),
        ParameterEstimate(
            key=MAXIMUM_CONSUMPTION_FRACTION_KEY,
            value=maximum_value,
            rounded_config_value=_round_config_value(maximum_value, spec.config_decimals),
            sample_rows=int(len(maximum_data)),
            weight_sum=_weight_sum(maximum_data, spec.weight_column),
            statistic=f"{spec.maximum_statistic}_{spec.maximum_quantile:g}",
            ratio_numerator=spec.consumption_column,
            ratio_denominator=f"12 * {spec.income_column}",
            filter_description=f"{spec.income_column} * 52 > {spec.annual_income_support_floor:g}",
        ),
    ]
    diagnostics = {
        "rawRows": int(len(data)),
        "validRows": int(len(valid_data)),
        "droppedRows": int(len(data) - len(valid_data)),
        "nonPositiveOrMissingIncomeRows": int((data[spec.income_column].isna() | (data[spec.income_column] <= 0.0)).sum()),
        "nonPositiveOrMissingConsumptionRows": int(
            (data[spec.consumption_column].isna() | (data[spec.consumption_column] <= 0.0)).sum()
        ),
        "nonPositiveOrMissingWeightRows": (
            int((data[spec.weight_column].isna() | (data[spec.weight_column] <= 0.0)).sum())
            if spec.weight_column
            else None
        ),
        "incomeColumn": spec.income_column,
        "consumptionColumn": spec.consumption_column,
        "weightColumn": spec.weight_column,
        "essentialIncomeBasis": spec.essential_income_basis,
    }
    return estimates, diagnostics


def build_method_comparison(dataset_year: int, dataset_path: Path) -> list[dict[str, Any]]:
    comparison: list[dict[str, Any]] = []
    for method in METHOD_CHOICES:
        spec = method_spec(method, dataset_year)
        data = load_lcfs_data(dataset_path, required_columns_for_method(spec))
        estimates, diagnostics = compute_estimates(data, spec)
        comparison.append(
            {
                "method": method,
                "methodRationale": spec.rationale,
                "selectedConfigValues": {
                    estimate.key: estimate.rounded_config_value for estimate in estimates
                },
                "rawValues": {estimate.key: estimate.value for estimate in estimates},
                "estimates": [asdict(estimate) for estimate in estimates],
                "diagnostics": diagnostics,
            }
        )
    return comparison


def run_calibration(
    *,
    dataset_year: int = DEFAULT_DATASET_YEAR,
    input_tab: str | Path | None = None,
    method: str = DEFAULT_METHOD,
    output_json: str | Path | None = None,
    evidence_dir: str | Path | None = None,
) -> dict[str, Any]:
    dataset_path = resolve_dataset_path(input_tab, dataset_year)
    spec = method_spec(method, dataset_year)
    data = load_lcfs_data(dataset_path, required_columns_for_method(spec))
    estimates, diagnostics = compute_estimates(data, spec)
    comparison = build_method_comparison(dataset_year, dataset_path)
    selected_values = {estimate.key: estimate.rounded_config_value for estimate in estimates}
    result = CalibrationResult(
        dataset_year=dataset_year,
        dataset_path=str(dataset_path),
        method=method,
        method_rationale=spec.rationale,
        selected_config_values=selected_values,
        estimates=estimates,
        diagnostics=diagnostics,
        method_comparison=comparison,
    )
    result_dict = _result_to_dict(result)

    if output_json:
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result_dict, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    if evidence_dir:
        write_evidence(result_dict, evidence_dir)
    return result_dict


def _result_to_dict(result: CalibrationResult) -> dict[str, Any]:
    return {
        "datasetYear": result.dataset_year,
        "datasetPath": result.dataset_path,
        "method": result.method,
        "methodRationale": result.method_rationale,
        "selectedConfigValues": result.selected_config_values,
        "estimates": [asdict(estimate) for estimate in result.estimates],
        "diagnostics": result.diagnostics,
        "methodComparison": result.method_comparison,
    }


def write_evidence(result: dict[str, Any], evidence_dir: str | Path) -> None:
    target_dir = ensure_output_dir(evidence_dir)
    summary_path = target_dir / SUMMARY_FILE_NAME
    source_values_path = target_dir / SOURCE_VALUES_FILE_NAME
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    with source_values_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "datasetYear",
                "method",
                "parameter",
                "value",
                "roundedConfigValue",
                "sampleRows",
                "weightSum",
                "statistic",
                "ratioNumerator",
                "ratioDenominator",
                "filterDescription",
            ],
        )
        writer.writeheader()
        for method_result in result["methodComparison"]:
            for parameter, value in method_result["rawValues"].items():
                estimate = next(
                    (
                        candidate
                        for candidate in method_result["estimates"]
                        if candidate["key"] == parameter
                    ),
                    None,
                )
                if estimate is None:
                    estimate = _estimate_from_method_result(method_result, parameter)
                writer.writerow(
                    {
                        "datasetYear": result["datasetYear"],
                        "method": method_result["method"],
                        "parameter": parameter,
                        "value": value,
                        "roundedConfigValue": method_result["selectedConfigValues"][parameter],
                        "sampleRows": estimate["sample_rows"],
                        "weightSum": estimate["weight_sum"],
                        "statistic": estimate["statistic"],
                        "ratioNumerator": estimate["ratio_numerator"],
                        "ratioDenominator": estimate["ratio_denominator"],
                        "filterDescription": estimate["filter_description"],
                    }
                )


def _estimate_from_method_result(method_result: dict[str, Any], parameter: str) -> dict[str, Any]:
    diagnostics = method_result["diagnostics"]
    if parameter == ESSENTIAL_CONSUMPTION_FRACTION_KEY:
        return {
            "sample_rows": "",
            "weight_sum": "",
            "statistic": "see method summary",
            "ratio_numerator": diagnostics["consumptionColumn"],
            "ratio_denominator": diagnostics["incomeColumn"],
            "filter_description": "see method summary",
        }
    return {
        "sample_rows": "",
        "weight_sum": "",
        "statistic": "see method summary",
        "ratio_numerator": diagnostics["consumptionColumn"],
        "ratio_denominator": f"12 * {diagnostics['incomeColumn']}",
        "filter_description": "see method summary",
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    result = run_calibration(
        dataset_year=args.dataset_year,
        input_tab=args.input_tab,
        method=args.method,
        output_json=args.output_json,
        evidence_dir=args.evidence_dir,
    )
    for key, value in result["selectedConfigValues"].items():
        print(f"{key} = {value}")
    print(f"method = {result['method']}")
    print(f"datasetYear = {result['datasetYear']}")


if __name__ == "__main__":
    main()
