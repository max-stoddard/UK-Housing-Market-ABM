#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helpers for reconstructing the national NMG house-price expectation rule.

@author: Max Stoddard
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable

from scripts.python.helpers.nmg.parsing import parse_int, parse_positive_float

EXPECTATION_DONT_KNOW_CODE = 10

_INNER_BANDS = {
    2: (-0.20, -0.10),
    3: (-0.10, -0.05),
    4: (-0.05, -0.02),
    5: (-0.02, 0.02),
    6: (0.02, 0.05),
    7: (0.05, 0.10),
    8: (0.10, 0.20),
}


@dataclass(frozen=True)
class ExpectationMethodSpec:
    method_name: str
    lower_open_cap: float
    upper_open_cap: float
    rounded_inner_bands: bool = False


@dataclass(frozen=True)
class ExpectationAggregate:
    method_name: str
    expectation_mean: float
    rows_read: int
    rows_used: int
    rows_dont_know: int
    rows_missing_code: int
    rows_invalid_code: int
    rows_invalid_weight: int
    weight_total_used: float


@dataclass(frozen=True)
class HpaExpectationFitClassification:
    label: str
    is_admissible: bool
    is_preferred: bool


EXPECTATION_METHOD_SPECS = {
    "midpoint_exact": ExpectationMethodSpec(
        method_name="midpoint_exact",
        lower_open_cap=-0.30,
        upper_open_cap=0.30,
        rounded_inner_bands=False,
    ),
    "midpoint_rounded": ExpectationMethodSpec(
        method_name="midpoint_rounded",
        lower_open_cap=-0.30,
        upper_open_cap=0.30,
        rounded_inner_bands=True,
    ),
    "midpoint_exact_cap25": ExpectationMethodSpec(
        method_name="midpoint_exact_cap25",
        lower_open_cap=-0.25,
        upper_open_cap=0.25,
        rounded_inner_bands=False,
    ),
    "midpoint_exact_cap35": ExpectationMethodSpec(
        method_name="midpoint_exact_cap35",
        lower_open_cap=-0.35,
        upper_open_cap=0.35,
        rounded_inner_bands=False,
    ),
}


def get_expectation_method_spec(method_name: str) -> ExpectationMethodSpec:
    try:
        return EXPECTATION_METHOD_SPECS[method_name]
    except KeyError as exc:
        raise ValueError(f"Unsupported expectation method: {method_name}") from exc


def _midpoint(lower: float, upper: float, *, rounded: bool) -> float:
    midpoint = (lower + upper) / 2.0
    if rounded:
        return round(midpoint, 2)
    return midpoint


def map_boe39_code_to_hpa(code: int, *, method_name: str) -> float | None:
    spec = get_expectation_method_spec(method_name)
    if code == EXPECTATION_DONT_KNOW_CODE:
        return None
    if code == 1:
        return _midpoint(spec.lower_open_cap, -0.20, rounded=spec.rounded_inner_bands)
    if code == 9:
        return _midpoint(0.20, spec.upper_open_cap, rounded=spec.rounded_inner_bands)
    bounds = _INNER_BANDS.get(code)
    if bounds is None:
        raise ValueError(f"Unsupported boe39 code: {code}")
    return _midpoint(bounds[0], bounds[1], rounded=spec.rounded_inner_bands)


def aggregate_expectation(
    rows: Iterable[dict[str, str]],
    *,
    method_name: str,
    weight_column: str = "we_factor",
    code_column: str = "boe39",
) -> ExpectationAggregate:
    weighted_total = 0.0
    weight_total = 0.0
    rows_read = 0
    rows_used = 0
    rows_dont_know = 0
    rows_missing_code = 0
    rows_invalid_code = 0
    rows_invalid_weight = 0

    for row in rows:
        rows_read += 1
        weight = parse_positive_float(row.get(weight_column))
        if weight is None:
            rows_invalid_weight += 1
            continue

        raw_code = row.get(code_column)
        if raw_code is None or not raw_code.strip():
            rows_missing_code += 1
            continue
        code = parse_int(raw_code)
        if code is None:
            rows_invalid_code += 1
            continue
        if code == EXPECTATION_DONT_KNOW_CODE:
            rows_dont_know += 1
            continue

        try:
            value = map_boe39_code_to_hpa(code, method_name=method_name)
        except ValueError:
            rows_invalid_code += 1
            continue
        if value is None:
            rows_dont_know += 1
            continue

        weighted_total += weight * value
        weight_total += weight
        rows_used += 1

    if weight_total <= 0:
        raise ValueError("No valid weighted boe39 responses were available.")

    return ExpectationAggregate(
        method_name=method_name,
        expectation_mean=weighted_total / weight_total,
        rows_read=rows_read,
        rows_used=rows_used,
        rows_dont_know=rows_dont_know,
        rows_missing_code=rows_missing_code,
        rows_invalid_code=rows_invalid_code,
        rows_invalid_weight=rows_invalid_weight,
        weight_total_used=weight_total,
    )


def fit_linear_rule(*, x_values: Iterable[float], y_values: Iterable[float]) -> tuple[float, float]:
    x_list = [float(value) for value in x_values]
    y_list = [float(value) for value in y_values]
    if len(x_list) != len(y_list):
        raise ValueError("x_values and y_values must have the same length.")
    if len(x_list) < 2:
        raise ValueError("At least two anchor points are required.")

    mean_x = sum(x_list) / len(x_list)
    mean_y = sum(y_list) / len(y_list)
    variance_x = sum((value - mean_x) ** 2 for value in x_list)
    if variance_x <= 0:
        raise ValueError("Variance of x_values must be positive.")
    covariance_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_list, y_list))
    factor = covariance_xy / variance_x
    const = mean_y - factor * mean_x
    return factor, const


def classify_hpa_expectation_fit(factor: float, const: float) -> HpaExpectationFitClassification:
    is_admissible = 0.0 <= factor <= 1.25 and abs(const) <= 0.03
    is_preferred = 0.2 <= factor <= 0.8 and abs(const) <= 0.01
    if is_preferred:
        label = "preferred"
    elif is_admissible:
        label = "admissible"
    else:
        label = "inadmissible"
    return HpaExpectationFitClassification(
        label=label,
        is_admissible=is_admissible,
        is_preferred=is_preferred,
    )


def compute_fit_rmse(
    *,
    x_values: Iterable[float],
    y_values: Iterable[float],
    factor: float,
    const: float,
) -> float:
    x_list = [float(value) for value in x_values]
    y_list = [float(value) for value in y_values]
    if len(x_list) != len(y_list):
        raise ValueError("x_values and y_values must have the same length.")
    if not x_list:
        raise ValueError("At least one anchor point is required.")
    squared_errors = [((factor * x_value) + const - y_value) ** 2 for x_value, y_value in zip(x_list, y_list)]
    return sqrt(sum(squared_errors) / len(squared_errors))


__all__ = [
    "EXPECTATION_DONT_KNOW_CODE",
    "EXPECTATION_METHOD_SPECS",
    "ExpectationAggregate",
    "ExpectationMethodSpec",
    "HpaExpectationFitClassification",
    "aggregate_expectation",
    "classify_hpa_expectation_fit",
    "compute_fit_rmse",
    "fit_linear_rule",
    "get_expectation_method_spec",
    "map_boe39_code_to_hpa",
]
