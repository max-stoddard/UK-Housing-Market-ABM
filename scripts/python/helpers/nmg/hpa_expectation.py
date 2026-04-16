#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helpers for reconstructing the national NMG house-price expectation rule.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from math import sqrt
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

from scripts.python.helpers.nmg.parsing import parse_int, parse_positive_float

EXPECTATION_DONT_KNOW_CODE = 10
LEGACY_TARGET_FACTOR = 0.44
LEGACY_TARGET_CONST = -0.007
LEGACY_FACTOR_PRINT_DECIMALS = 2
LEGACY_CONST_PRINT_DECIMALS = 3
DEFAULT_EXPECTATION_METHOD_NAMES = (
    "midpoint_rounded",
    "midpoint_exact",
    "midpoint_exact_cap25",
    "midpoint_exact_cap35",
)
DEFAULT_PRODUCTION_EXPECTATION_METHOD_NAMES = (
    "midpoint_exact",
    "midpoint_rounded",
)
OWNER_OCCUPIER_HOUSING_CODES = frozenset({"1", "2"})
RMSE_TIE_TOLERANCE = 1e-6
PRODUCTION_COMPLEXITY_IMPROVEMENT_THRESHOLD = 0.05

_INNER_BANDS = {
    2: (-0.20, -0.10),
    3: (-0.10, -0.05),
    4: (-0.05, -0.02),
    5: (-0.02, 0.02),
    6: (0.02, 0.05),
    7: (0.05, 0.10),
    8: (0.10, 0.20),
}
_SURVEY_FAMILY_SIMPLICITY_RANK = {
    "national_cross_section": 0,
    "owner_occupier_cross_section": 1,
    "matched_panel_subset": 2,
}
_EXPECTATION_METHOD_SIMPLICITY_RANK = {
    "midpoint_exact": 0,
    "midpoint_rounded": 1,
    "midpoint_exact_cap25": 2,
    "midpoint_exact_cap35": 3,
}
_SIGNAL_METHOD_SIMPLICITY_RANK = {
    "java_like_annualised": 0,
    "annual_mean_annualised": 1,
    "annual_mean_cumulative": 2,
    "rolling_quarter_annualised": 3,
    "rolling_quarter_cumulative": 4,
}
_CATEGORY_SIMPLICITY_RANK = {
    "A": 0,
    "all_transactions": 1,
}
_REGRESSION_SIMPLICITY_RANK = {
    "ols": 0,
    "huber": 1,
}
_ANCHOR_POLICY_SIMPLICITY_RANK = {
    "same_year_two_year_base": 0,
    "literal_2014_2018_comment": 1,
    "latest_prior_or_same": 2,
    "nearest_future_or_same": 3,
    "nearest_available": 4,
    "explicit_pair": 5,
    "explicit_rolling_quarter_pair": 6,
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


@dataclass(frozen=True)
class NmgWaveData:
    wave_label: str
    survey_year: int
    input_path: Path
    fieldnames: tuple[str, ...]
    rows: tuple[dict[str, str], ...]

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class SurveyTargetSpec:
    name: str
    expectation_method_name: str
    family_name: str
    housing_codes: frozenset[str] | None = None
    use_matched_panel: bool = False

    @property
    def simplicity_rank(self) -> tuple[int, int]:
        return (
            _SURVEY_FAMILY_SIMPLICITY_RANK[self.family_name],
            _EXPECTATION_METHOD_SIMPLICITY_RANK[self.expectation_method_name],
        )


@dataclass(frozen=True)
class SurveyTargetResult:
    spec: SurveyTargetSpec
    wave_label: str
    survey_year: int
    expectation_aggregate: ExpectationAggregate
    filtered_row_count: int

    @property
    def expectation_mean(self) -> float:
        return self.expectation_aggregate.expectation_mean


@dataclass(frozen=True)
class HpaExpectationFitPoint:
    survey_wave_label: str
    survey_year: int
    survey_target: float
    signal_value: float
    signal_method_name: str
    signal_anchor_year: int
    signal_base_year: int
    signal_months: tuple[int, ...] | None = None


@dataclass(frozen=True)
class HpaExpectationCandidateSpec:
    name: str
    survey_target_spec: SurveyTargetSpec
    signal_method_name: str
    category_key: str
    regression_type: str
    anchor_policy_name: str
    hypothesis_name: str | None = None

    @property
    def simplicity_rank(self) -> tuple[int, int, int, int, int, int]:
        return (
            *self.survey_target_spec.simplicity_rank,
            _SIGNAL_METHOD_SIMPLICITY_RANK[self.signal_method_name],
            _CATEGORY_SIMPLICITY_RANK[self.category_key],
            _REGRESSION_SIMPLICITY_RANK[self.regression_type],
            _ANCHOR_POLICY_SIMPLICITY_RANK[self.anchor_policy_name],
        )


@dataclass(frozen=True)
class HpaExpectationCandidateResult:
    candidate_spec: HpaExpectationCandidateSpec
    factor: float
    const: float
    classification: HpaExpectationFitClassification
    core_rmse: float
    leave_one_out_rmse: float
    legacy_distance: float | None
    fit_points: tuple[HpaExpectationFitPoint, ...]

    @property
    def is_admissible(self) -> bool:
        return self.classification.is_admissible

    @property
    def is_preferred(self) -> bool:
        return self.classification.is_preferred

    @property
    def survey_method_name(self) -> str:
        return self.candidate_spec.survey_target_spec.expectation_method_name

    @property
    def signal_method_name(self) -> str:
        return self.candidate_spec.signal_method_name

    @property
    def category_key(self) -> str:
        return self.candidate_spec.category_key

    @property
    def regression_type(self) -> str:
        return self.candidate_spec.regression_type

    @property
    def simplicity_rank(self) -> tuple[int, int, int, int, int, int]:
        return self.candidate_spec.simplicity_rank


@dataclass(frozen=True)
class ProductionSelection:
    ranked_results: tuple[HpaExpectationCandidateResult, ...]
    selected_result: HpaExpectationCandidateResult
    baseline_result: HpaExpectationCandidateResult | None
    complexity_override_applied: bool
    complexity_override_reason: str | None


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


def infer_survey_year_from_wave_label(wave_label: str) -> int:
    digits = "".join(char for char in wave_label if char.isdigit())
    if len(digits) < 4:
        raise ValueError(f"Could not infer survey year from wave label: {wave_label}")
    return int(digits[:4])


def load_nmg_wave_csv(
    path: Path,
    *,
    wave_label: str | None = None,
    require_expectation_data: bool = True,
    code_column: str = "boe39",
    weight_column: str = "we_factor",
) -> NmgWaveData:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"NMG CSV has no header row: {path}")
        rows = tuple(reader)
        resolved_wave_label = wave_label or path.stem.replace("nmg-", "")
        wave = NmgWaveData(
            wave_label=resolved_wave_label,
            survey_year=infer_survey_year_from_wave_label(resolved_wave_label),
            input_path=path,
            fieldnames=tuple(reader.fieldnames),
            rows=rows,
        )
    if require_expectation_data and not wave_has_valid_expectation_data(
        wave.rows,
        code_column=code_column,
        weight_column=weight_column,
    ):
        raise ValueError(
            f"NMG wave {wave.wave_label} does not contain valid weighted {code_column} responses."
        )
    return wave


def build_default_survey_target_specs(
    *,
    expectation_method_names: Sequence[str] = DEFAULT_EXPECTATION_METHOD_NAMES,
    include_owner_occupier: bool = True,
    include_matched_panel: bool = True,
) -> list[SurveyTargetSpec]:
    specs: list[SurveyTargetSpec] = []
    for method_name in expectation_method_names:
        specs.append(
            SurveyTargetSpec(
                name=f"national_cross_section__{method_name}",
                expectation_method_name=method_name,
                family_name="national_cross_section",
            )
        )
        if include_owner_occupier:
            specs.append(
                SurveyTargetSpec(
                    name=f"owner_occupier_cross_section__{method_name}",
                    expectation_method_name=method_name,
                    family_name="owner_occupier_cross_section",
                    housing_codes=OWNER_OCCUPIER_HOUSING_CODES,
                )
            )
        if include_matched_panel:
            specs.append(
                SurveyTargetSpec(
                    name=f"matched_panel_subset__{method_name}",
                    expectation_method_name=method_name,
                    family_name="matched_panel_subset",
                    use_matched_panel=True,
                )
            )
    return specs


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


def wave_has_valid_expectation_data(
    rows: Iterable[dict[str, str]],
    *,
    code_column: str = "boe39",
    weight_column: str = "we_factor",
) -> bool:
    for row in rows:
        if parse_positive_float(row.get(weight_column)) is None:
            continue
        code = parse_int(row.get(code_column))
        if code is None or code == EXPECTATION_DONT_KNOW_CODE:
            continue
        if code in {1, 2, 3, 4, 5, 6, 7, 8, 9}:
            return True
    return False


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


def _row_matches_housing_codes(row: dict[str, str], housing_codes: frozenset[str]) -> bool:
    for column_name in ("dhousing", "qhousing"):
        value = row.get(column_name)
        if value is None:
            continue
        stripped = value.strip()
        if stripped:
            return stripped in housing_codes
    return False


def build_survey_target_result(
    wave: NmgWaveData,
    spec: SurveyTargetSpec,
    *,
    matched_row_indices: set[int] | None = None,
) -> SurveyTargetResult:
    selected_rows: list[dict[str, str]] = []
    for row_index, row in enumerate(wave.rows):
        if spec.use_matched_panel:
            if matched_row_indices is None:
                raise ValueError(
                    f"Survey target {spec.name} requires matched_row_indices for wave {wave.wave_label}."
                )
            if row_index not in matched_row_indices:
                continue
        if spec.housing_codes is not None and not _row_matches_housing_codes(row, spec.housing_codes):
            continue
        selected_rows.append(row)

    if not selected_rows:
        raise ValueError(f"Survey target {spec.name} selected no rows for wave {wave.wave_label}.")

    return SurveyTargetResult(
        spec=spec,
        wave_label=wave.wave_label,
        survey_year=wave.survey_year,
        expectation_aggregate=aggregate_expectation(
            selected_rows,
            method_name=spec.expectation_method_name,
        ),
        filtered_row_count=len(selected_rows),
    )


def _fit_weighted_linear_rule(
    *,
    x_values: Sequence[float],
    y_values: Sequence[float],
    weights: Sequence[float],
) -> tuple[float, float]:
    if len(x_values) != len(y_values) or len(x_values) != len(weights):
        raise ValueError("x_values, y_values, and weights must have the same length.")
    if len(x_values) < 2:
        raise ValueError("At least two anchor points are required.")
    total_weight = sum(float(weight) for weight in weights)
    if total_weight <= 0:
        raise ValueError("Total weight must be positive.")

    mean_x = sum(weight * value for weight, value in zip(weights, x_values)) / total_weight
    mean_y = sum(weight * value for weight, value in zip(weights, y_values)) / total_weight
    variance_x = sum(weight * ((value - mean_x) ** 2) for weight, value in zip(weights, x_values))
    if variance_x <= 0:
        raise ValueError("Variance of x_values must be positive.")
    covariance_xy = sum(
        weight * (x_value - mean_x) * (y_value - mean_y)
        for weight, x_value, y_value in zip(weights, x_values, y_values)
    )
    factor = covariance_xy / variance_x
    const = mean_y - factor * mean_x
    return factor, const


def _fit_huber_linear_rule(
    *,
    x_values: Sequence[float],
    y_values: Sequence[float],
    max_iterations: int = 50,
    tolerance: float = 1e-12,
) -> tuple[float, float]:
    factor, const = _fit_weighted_linear_rule(
        x_values=x_values,
        y_values=y_values,
        weights=[1.0] * len(x_values),
    )
    for _ in range(max_iterations):
        residuals = [
            y_value - ((factor * x_value) + const)
            for x_value, y_value in zip(x_values, y_values)
        ]
        robust_scale = median(abs(value) for value in residuals)
        if robust_scale <= tolerance:
            return factor, const
        delta = 1.345 * robust_scale
        weights = [
            1.0 if abs(residual) <= delta else delta / abs(residual)
            for residual in residuals
        ]
        new_factor, new_const = _fit_weighted_linear_rule(
            x_values=x_values,
            y_values=y_values,
            weights=weights,
        )
        if abs(new_factor - factor) <= tolerance and abs(new_const - const) <= tolerance:
            return new_factor, new_const
        factor, const = new_factor, new_const
    return factor, const


def fit_linear_rule(
    *,
    x_values: Iterable[float],
    y_values: Iterable[float],
    regression_type: str = "ols",
) -> tuple[float, float]:
    x_list = [float(value) for value in x_values]
    y_list = [float(value) for value in y_values]
    if len(x_list) != len(y_list):
        raise ValueError("x_values and y_values must have the same length.")
    if len(x_list) < 2:
        raise ValueError("At least two anchor points are required.")

    if regression_type == "ols":
        return _fit_weighted_linear_rule(
            x_values=x_list,
            y_values=y_list,
            weights=[1.0] * len(x_list),
        )
    if regression_type == "huber":
        return _fit_huber_linear_rule(x_values=x_list, y_values=y_list)
    raise ValueError(f"Unsupported regression_type: {regression_type}")


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


def compute_leave_one_out_rmse(
    *,
    x_values: Iterable[float],
    y_values: Iterable[float],
    regression_type: str = "ols",
) -> float:
    x_list = [float(value) for value in x_values]
    y_list = [float(value) for value in y_values]
    if len(x_list) != len(y_list):
        raise ValueError("x_values and y_values must have the same length.")
    if len(x_list) < 3:
        return 0.0
    squared_errors: list[float] = []
    for holdout_index in range(len(x_list)):
        fit_x = [value for index, value in enumerate(x_list) if index != holdout_index]
        fit_y = [value for index, value in enumerate(y_list) if index != holdout_index]
        try:
            factor, const = fit_linear_rule(
                x_values=fit_x,
                y_values=fit_y,
                regression_type=regression_type,
            )
        except ValueError:
            return float("inf")
        predicted = (factor * x_list[holdout_index]) + const
        squared_errors.append((predicted - y_list[holdout_index]) ** 2)
    return sqrt(sum(squared_errors) / len(squared_errors))


def compute_legacy_distance(
    factor: float,
    const: float,
    *,
    target_factor: float = LEGACY_TARGET_FACTOR,
    target_const: float = LEGACY_TARGET_CONST,
) -> float:
    return sqrt(((factor - target_factor) ** 2) + ((const - target_const) ** 2))


def matches_legacy_printed_precision(
    factor: float,
    const: float,
    *,
    target_factor: float = LEGACY_TARGET_FACTOR,
    target_const: float = LEGACY_TARGET_CONST,
    factor_decimals: int = LEGACY_FACTOR_PRINT_DECIMALS,
    const_decimals: int = LEGACY_CONST_PRINT_DECIMALS,
) -> bool:
    return (
        f"{factor:.{factor_decimals}f}" == f"{target_factor:.{factor_decimals}f}"
        and f"{const:.{const_decimals}f}" == f"{target_const:.{const_decimals}f}"
    )


def evaluate_candidate_fit(
    candidate_spec: HpaExpectationCandidateSpec,
    fit_points: Sequence[HpaExpectationFitPoint],
    *,
    legacy_target: tuple[float, float] | None = None,
) -> HpaExpectationCandidateResult:
    x_values = [point.signal_value for point in fit_points]
    y_values = [point.survey_target for point in fit_points]
    factor, const = fit_linear_rule(
        x_values=x_values,
        y_values=y_values,
        regression_type=candidate_spec.regression_type,
    )
    classification = classify_hpa_expectation_fit(factor, const)
    legacy_distance = None
    if legacy_target is not None:
        legacy_distance = compute_legacy_distance(
            factor,
            const,
            target_factor=legacy_target[0],
            target_const=legacy_target[1],
        )
    return HpaExpectationCandidateResult(
        candidate_spec=candidate_spec,
        factor=factor,
        const=const,
        classification=classification,
        core_rmse=compute_fit_rmse(
            x_values=x_values,
            y_values=y_values,
            factor=factor,
            const=const,
        ),
        leave_one_out_rmse=compute_leave_one_out_rmse(
            x_values=x_values,
            y_values=y_values,
            regression_type=candidate_spec.regression_type,
        ),
        legacy_distance=legacy_distance,
        fit_points=tuple(fit_points),
    )


def rank_legacy_candidates(
    results: Iterable[HpaExpectationCandidateResult],
    *,
    diagnostic_rmse_by_candidate_name: dict[str, float] | None = None,
) -> list[HpaExpectationCandidateResult]:
    diagnostic_lookup = diagnostic_rmse_by_candidate_name or {}

    def diagnostic_rmse(result: HpaExpectationCandidateResult) -> float:
        return diagnostic_lookup.get(result.candidate_spec.name, float("inf"))

    return sorted(
        results,
        key=lambda item: (
            not matches_legacy_printed_precision(item.factor, item.const),
            item.simplicity_rank
            if matches_legacy_printed_precision(item.factor, item.const)
            else tuple(),
            diagnostic_rmse(item),
            item.legacy_distance if item.legacy_distance is not None else float("inf"),
            item.core_rmse,
            item.leave_one_out_rmse,
            item.simplicity_rank,
            item.candidate_spec.name,
        ),
    )


def rank_production_candidates(
    results: Iterable[HpaExpectationCandidateResult],
) -> list[HpaExpectationCandidateResult]:
    return sorted(
        results,
        key=lambda item: (
            not item.is_admissible,
            not item.is_preferred,
            item.leave_one_out_rmse,
            round(item.core_rmse / RMSE_TIE_TOLERANCE) if RMSE_TIE_TOLERANCE > 0 else item.core_rmse,
            item.simplicity_rank,
            item.candidate_spec.name,
        ),
    )


def select_production_candidate(
    results: Iterable[HpaExpectationCandidateResult],
    *,
    improvement_threshold: float = PRODUCTION_COMPLEXITY_IMPROVEMENT_THRESHOLD,
) -> ProductionSelection:
    ranked_results = tuple(rank_production_candidates(results))
    if not ranked_results:
        raise ValueError("At least one production candidate result is required.")
    return ProductionSelection(
        ranked_results=ranked_results,
        selected_result=ranked_results[0],
        baseline_result=None,
        complexity_override_applied=False,
        complexity_override_reason=None,
    )


__all__ = [
    "DEFAULT_EXPECTATION_METHOD_NAMES",
    "DEFAULT_PRODUCTION_EXPECTATION_METHOD_NAMES",
    "EXPECTATION_DONT_KNOW_CODE",
    "EXPECTATION_METHOD_SPECS",
    "ExpectationAggregate",
    "ExpectationMethodSpec",
    "HpaExpectationCandidateResult",
    "HpaExpectationCandidateSpec",
    "HpaExpectationFitClassification",
    "HpaExpectationFitPoint",
    "LEGACY_TARGET_CONST",
    "LEGACY_TARGET_FACTOR",
    "NmgWaveData",
    "OWNER_OCCUPIER_HOUSING_CODES",
    "ProductionSelection",
    "SurveyTargetResult",
    "SurveyTargetSpec",
    "aggregate_expectation",
    "build_default_survey_target_specs",
    "build_survey_target_result",
    "classify_hpa_expectation_fit",
    "compute_fit_rmse",
    "compute_leave_one_out_rmse",
    "compute_legacy_distance",
    "evaluate_candidate_fit",
    "fit_linear_rule",
    "get_expectation_method_spec",
    "infer_survey_year_from_wave_label",
    "load_nmg_wave_csv",
    "map_boe39_code_to_hpa",
    "matches_legacy_printed_precision",
    "rank_legacy_candidates",
    "rank_production_candidates",
    "select_production_candidate",
    "wave_has_valid_expectation_data",
]
