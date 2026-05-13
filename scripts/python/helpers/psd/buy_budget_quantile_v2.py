#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUY* v2.1 realism-constrained calibration helpers for modern PSD/PPD inputs.

This module intentionally does not perform legacy 2011 reproduction-first
selection. It enforces data-anchored realism constraints for modern BUY*
calibration.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import itertools
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Callable

from scripts.python.helpers.psd.bins import PsdBin, build_bins_from_category_masses, parse_band_label
from scripts.python.helpers.psd.buy_budget_methods import (
    MODERN_2024_BORROWER_GROUP,
    MODERN_2024_INCOME_GROUP,
    MODERN_2024_LOAN_GROUP,
    MODERN_2024_LTV_GROUP,
    MODERN_2024_PROPERTY_GROUP,
)
from scripts.python.helpers.psd.quarterly_long import (
    LongPsdRow,
    aggregate_category_sales,
    load_quarterly_psd_rows,
)

PPD_STATUS_A_ONLY = "a_only"
PPD_STATUS_ALL = "all"
PPD_STATUS_BOTH = "both"
PPD_STATUS_CHOICES = (
    PPD_STATUS_A_ONLY,
    PPD_STATUS_ALL,
    PPD_STATUS_BOTH,
)

YEAR_POLICY_2024_ONLY = "2024_only"
YEAR_POLICY_2025_ONLY = "2025_only"
YEAR_POLICY_POOLED_2024_2025 = "pooled_2024_2025"
YEAR_POLICY_BOTH = "both"
YEAR_POLICY_CHOICES = (
    YEAR_POLICY_2024_ONLY,
    YEAR_POLICY_2025_ONLY,
    YEAR_POLICY_POOLED_2024_2025,
    YEAR_POLICY_BOTH,
)

GUARDRAIL_MODE_WARN = "warn"
GUARDRAIL_MODE_FAIL = "fail"
GUARDRAIL_MODE_CHOICES = (
    GUARDRAIL_MODE_WARN,
    GUARDRAIL_MODE_FAIL,
)

TAIL_FAMILY_PARETO = "pareto"
TAIL_FAMILY_CHOICES = (TAIL_FAMILY_PARETO,)

DEFAULT_INCOME_CHECKPOINTS = (25_000.0, 50_000.0, 100_000.0, 150_000.0, 200_000.0)
DEFAULT_MEDIAN_TARGET_CURVE = {
    25_000: 6.5,
    50_000: 6.0,
    100_000: 5.4,
    150_000: 5.0,
    200_000: 4.8,
}
DEFAULT_PARETO_ALPHA_GRID = (1.2, 1.4, 1.6, 1.8, 2.0, 2.5, 3.0)

SIGMA_WARNING_LOW = 0.2
SIGMA_WARNING_HIGH = 0.6
HARD_P95_MULTIPLE_CAP = 15.0
P95_SOFT_CAP_DEFAULT = 14.0
EXPONENT_MAX_DEFAULT = 1.0
P95_Z = 1.6448536269514722

MEDIAN_LOAN_GROUP = "Median loan amounts (£)"
MEDIAN_LOAN_GROUP_ALT = "Median loan amounts (�)"
MEDIAN_LTV_GROUP = "Median loan-to-value (LTV) ratios (%)"
MEDIAN_LTV_GROUP_ALT = "Median loan-to-value (LTV) ratios (�)"


@dataclass(frozen=True)
class QuantileFitSpec:
    within_bin_points: int = 11
    quantile_grid_size: int = 4000
    quantile_levels: tuple[float, ...] = (
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.75,
        0.80,
        0.85,
        0.90,
        0.95,
    )
    ppd_mean_anchor_weight: float = 4.0
    hard_p95_cap: float = HARD_P95_MULTIPLE_CAP
    exponent_max: float = EXPONENT_MAX_DEFAULT
    p95_soft_cap: float = P95_SOFT_CAP_DEFAULT
    sigma_warning_low: float = SIGMA_WARNING_LOW
    sigma_warning_high: float = SIGMA_WARNING_HIGH
    median_target_curve: "SoftTargetCurve | dict[int, float] | None" = None
    fixed_exponent: float | None = None
    quantile_huber_delta: float = 0.05
    sigma_search_low: float = 0.1
    sigma_search_high: float = 0.8

    def resolved_median_target_curve(self) -> dict[int, float]:
        if self.median_target_curve is None:
            return dict(DEFAULT_MEDIAN_TARGET_CURVE)
        if isinstance(self.median_target_curve, SoftTargetCurve):
            return self.median_target_curve.as_dict()
        return dict(self.median_target_curve)


@dataclass(frozen=True)
class SoftTargetCurve:
    checkpoints: tuple[int, ...]
    max_multiples: tuple[float, ...]

    def as_dict(self) -> dict[int, float]:
        if len(self.checkpoints) != len(self.max_multiples):
            raise ValueError("SoftTargetCurve requires aligned checkpoints and max_multiples.")
        return {income: multiple for income, multiple in zip(self.checkpoints, self.max_multiples)}


@dataclass(frozen=True)
class ObjectiveWeights:
    w_fit: float = 1.0
    w_anchor: float = 8.0
    w_p95: float = 12.0
    w_sigma: float = 3.0
    w_curve: float = 8.0
    profile_id: str = "default"


@dataclass(frozen=True)
class TailSpec:
    family: str = TAIL_FAMILY_PARETO
    pareto_alpha: float = 1.8
    pareto_x_min: float = 100_001.0
    pareto_max_cdf: float = 0.995


@dataclass(frozen=True)
class AnchorDiagnostics:
    median_loan: float
    median_ltv_pct: float
    implied_price: float
    loan_rows: int
    ltv_rows: int


@dataclass(frozen=True)
class ObjectiveComponents:
    objective_total: float
    objective_fit: float
    objective_anchor: float
    objective_p95: float
    objective_sigma: float
    objective_median_curve: float


@dataclass(frozen=True)
class PpdYearMoments:
    year: int
    rows_used: int
    mean_log_price: float
    variance_log_price: float
    std_log_price: float
    sample_log_prices: tuple[float, ...]


@dataclass(frozen=True)
class PpdSummary:
    status_mode: str
    source_paths: tuple[str, ...]
    rows_total: int
    rows_used: int
    year_moments: dict[int, PpdYearMoments]
    loaded_years: tuple[int, ...]


@dataclass(frozen=True)
class RakedPpdTarget:
    status_mode: str
    source_year: int
    source_paths: tuple[str, ...]
    rows_total: int
    rows_source_year: int
    rows_valid_price: int
    rows_used: int
    rows_unmatched_to_psd_bands: int
    rows_non_positive_weight: int
    property_band_count: int
    bands_with_ppd_rows: int
    log_prices: list[float]
    weights: list[float]
    diagnostics: dict[str, float]


@dataclass(frozen=True)
class GuardrailOutcome:
    passed: bool
    hard_failures: tuple[str, ...]
    warnings: tuple[str, ...]
    median_budget_multiples: dict[int, float]
    p95_budget_multiples: dict[int, float]


@dataclass(frozen=True)
class BuyBudgetVariantResult:
    status_mode: str
    year_policy: str
    buy_scale: float
    buy_exponent: float
    buy_mu: float
    buy_sigma: float
    selected_alpha: float
    weight_profile_id: str
    guardrail_mode: str
    guardrails: GuardrailOutcome
    sigma_warning: bool
    fit_years: tuple[int, ...]
    yearly_fit_distance: dict[int, float]
    yearly_fit_mean_error: dict[int, float]
    yearly_fit_std_error: dict[int, float]
    worst_year_fit_distance: float
    objective: ObjectiveComponents
    anchor: AnchorDiagnostics
    fit_degradation_vs_baseline: float | None
    ppd_summary: PpdSummary
    diagnostics: dict[str, float]
    income_quantiles: tuple[float, ...]
    observed_price_quantiles: tuple[float, ...]
    modeled_median_quantiles: tuple[float, ...]
    model_log_price_series: tuple[float, ...]
    tail_income_values: tuple[float, ...]

    @property
    def variant_id(self) -> str:
        return (
            f"status={self.status_mode}|year_policy={self.year_policy}|"
            f"alpha={self.selected_alpha:g}|weights={self.weight_profile_id}"
        )


@dataclass(frozen=True)
class ProductionSelection:
    selected: BuyBudgetVariantResult
    eligible: list[BuyBudgetVariantResult]
    rejected: list[BuyBudgetVariantResult]


@dataclass(frozen=True)
class _PpdAccumulator:
    rows: int
    sum_log: float
    sum_sq_log: float
    sample_log_prices: tuple[float, ...]


@dataclass(frozen=True)
class _MarginalBundle:
    income_values: list[float]
    income_weights: list[float]
    price_values: list[float]
    price_weights: list[float]
    diagnostics: dict[str, float]
    tail_income_values: list[float]


def iter_status_modes(status_mode: str) -> tuple[str, ...]:
    if status_mode == PPD_STATUS_BOTH:
        return (PPD_STATUS_A_ONLY, PPD_STATUS_ALL)
    if status_mode not in (PPD_STATUS_A_ONLY, PPD_STATUS_ALL):
        raise ValueError(f"Unsupported status_mode: {status_mode}")
    return (status_mode,)


def iter_year_policies(year_policy: str) -> tuple[str, ...]:
    if year_policy == YEAR_POLICY_BOTH:
        return (YEAR_POLICY_2024_ONLY, YEAR_POLICY_2025_ONLY, YEAR_POLICY_POOLED_2024_2025)
    if year_policy not in (YEAR_POLICY_2024_ONLY, YEAR_POLICY_2025_ONLY, YEAR_POLICY_POOLED_2024_2025):
        raise ValueError(f"Unsupported year_policy: {year_policy}")
    return (year_policy,)


def fit_years_from_policy(year_policy: str) -> tuple[int, ...]:
    if year_policy == YEAR_POLICY_2024_ONLY:
        return (2024,)
    if year_policy == YEAR_POLICY_2025_ONLY:
        return (2025,)
    if year_policy == YEAR_POLICY_POOLED_2024_2025:
        return (2024, 2025)
    raise ValueError(f"Unsupported year_policy: {year_policy}")


def build_objective_weight_profiles(
    *,
    w_anchor_values: tuple[float, ...],
    w_p95_values: tuple[float, ...],
    w_sigma_values: tuple[float, ...],
    w_curve_values: tuple[float, ...],
) -> tuple[ObjectiveWeights, ...]:
    profiles: list[ObjectiveWeights] = []
    for w_anchor, w_p95, w_sigma, w_curve in itertools.product(
        w_anchor_values,
        w_p95_values,
        w_sigma_values,
        w_curve_values,
    ):
        profile_id = f"a{w_anchor:g}_p{w_p95:g}_s{w_sigma:g}_c{w_curve:g}"
        profiles.append(
            ObjectiveWeights(
                w_fit=1.0,
                w_anchor=float(w_anchor),
                w_p95=float(w_p95),
                w_sigma=float(w_sigma),
                w_curve=float(w_curve),
                profile_id=profile_id,
            )
        )
    return tuple(profiles)


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    total = sum(weights)
    if total <= 0.0:
        raise ValueError("Weighted mean requires positive total weight.")
    return sum(value * weight for value, weight in zip(values, weights)) / total


def _weighted_variance(values: list[float], weights: list[float], mean: float | None = None) -> float:
    total = sum(weights)
    if total <= 0.0:
        raise ValueError("Weighted variance requires positive total weight.")
    center = _weighted_mean(values, weights) if mean is None else mean
    return sum(weight * (value - center) ** 2 for value, weight in zip(values, weights)) / total


def _weighted_quantile(values: list[float], weights: list[float], q: float) -> float:
    if not values or len(values) != len(weights):
        raise ValueError("Weighted quantile requires non-empty aligned arrays.")
    if q < 0.0 or q > 1.0:
        raise ValueError("q must be in [0,1].")

    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    cumulative = 0.0
    total = sum(weight for _, weight in ordered)
    if total <= 0.0:
        raise ValueError("Weighted quantile requires positive total weight.")
    threshold = q * total
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return ordered[-1][0]


def _weighted_quantiles(values: list[float], weights: list[float], levels: tuple[float, ...]) -> tuple[float, ...]:
    if not values or len(values) != len(weights):
        raise ValueError("Weighted quantiles require non-empty aligned arrays.")
    if any(q < 0.0 or q > 1.0 for q in levels):
        raise ValueError("quantile levels must be in [0,1].")
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    total = sum(weight for _, weight in ordered)
    if total <= 0.0:
        raise ValueError("Weighted quantiles require positive total weight.")

    sorted_levels = sorted(enumerate(levels), key=lambda item: item[1])
    output = [ordered[-1][0]] * len(levels)
    cumulative = 0.0
    pointer = 0
    for value, weight in ordered:
        cumulative += weight
        while pointer < len(sorted_levels) and cumulative >= sorted_levels[pointer][1] * total:
            original_index, _level = sorted_levels[pointer]
            output[original_index] = value
            pointer += 1
        if pointer >= len(sorted_levels):
            break
    return tuple(output)


def _weighted_quantile_series(values: list[float], weights: list[float], n_points: int) -> list[float]:
    if n_points <= 0:
        raise ValueError("n_points must be positive.")
    ordered = sorted(zip(values, weights), key=lambda item: item[0])
    levels: list[float] = []
    cumulative: list[float] = []
    running = 0.0
    for value, weight in ordered:
        running += weight
        levels.append(value)
        cumulative.append(running)
    if running <= 0.0:
        raise ValueError("Quantile series requires positive total weight.")

    out: list[float] = []
    pointer = 0
    for idx in range(n_points):
        threshold = ((idx + 0.5) / n_points) * running
        while pointer < len(cumulative) - 1 and threshold > cumulative[pointer]:
            pointer += 1
        out.append(levels[pointer])
    return out


def _expand_property_bins(
    bins: list[PsdBin],
    *,
    open_upper: float,
    within_bin_points: int,
) -> tuple[list[float], list[float], float]:
    values: list[float] = []
    weights: list[float] = []
    total_mass = 0.0

    for item in bins:
        if item.mass <= 0.0:
            continue
        lower = 0.0 if item.lower is None else item.lower
        upper = open_upper if item.upper is None else item.upper
        if upper < lower and item.upper is None:
            upper = lower
        if upper < lower:
            raise ValueError(f"Invalid property bin bounds: {item}")

        if upper == lower:
            points = [lower]
        else:
            width = upper - lower
            points = [
                lower + ((idx + 0.5) * width / within_bin_points)
                for idx in range(within_bin_points)
            ]

        mass_per = item.mass / len(points)
        values.extend(points)
        weights.extend([mass_per] * len(points))
        total_mass += item.mass

    if not values:
        raise ValueError("No usable property values after expansion.")

    return values, weights, total_mass


def _expand_income_bins_with_tail(
    bins: list[PsdBin],
    *,
    within_bin_points: int,
    tail_spec: TailSpec,
    income_open_upper_k: float,
) -> tuple[list[float], list[float], float, list[float], float]:
    if tail_spec.family not in TAIL_FAMILY_CHOICES:
        raise ValueError(f"Unsupported tail family: {tail_spec.family}")
    if tail_spec.pareto_alpha <= 0.0:
        raise ValueError("pareto_alpha must be positive.")
    if tail_spec.pareto_max_cdf <= 0.0 or tail_spec.pareto_max_cdf >= 1.0:
        raise ValueError("pareto_max_cdf must be in (0,1).")

    values: list[float] = []
    weights: list[float] = []
    tail_values: list[float] = []
    total_mass = 0.0
    top_bin_mass = 0.0

    fallback_open_upper = income_open_upper_k * 1_000.0

    for item in bins:
        if item.mass <= 0.0:
            continue
        lower = 0.0 if item.lower is None else item.lower

        if item.upper is None:
            top_bin_mass += item.mass
            total_mass += item.mass
            x_min = max(lower, tail_spec.pareto_x_min)
            points: list[float] = []
            for idx in range(within_bin_points):
                u = ((idx + 0.5) / within_bin_points) * tail_spec.pareto_max_cdf
                raw = x_min / math.pow(max(1.0 - u, 1e-12), 1.0 / tail_spec.pareto_alpha)
                points.append(max(raw, x_min))
            mass_per = item.mass / len(points)
            values.extend(points)
            weights.extend([mass_per] * len(points))
            tail_values.extend(points)
            continue

        upper = item.upper
        if upper < lower:
            raise ValueError(f"Invalid income bin bounds: {item}")

        if upper == lower:
            points = [lower]
        else:
            width = upper - lower
            points = [
                lower + ((idx + 0.5) * width / within_bin_points)
                for idx in range(within_bin_points)
            ]

        mass_per = item.mass / len(points)
        values.extend(points)
        weights.extend([mass_per] * len(points))
        total_mass += item.mass

    if not values:
        # defensive fallback for extreme parsing edge cases
        values = [fallback_open_upper]
        weights = [1.0]

    return values, weights, total_mass, tail_values, top_bin_mass


def _median_anchor_from_rows(rows: list[LongPsdRow], target_year: int) -> AnchorDiagnostics:
    loan_vals: list[float] = []
    ltv_vals: list[float] = []

    for row in rows:
        if row.period.year != target_year:
            continue
        if row.group in (MEDIAN_LOAN_GROUP, MEDIAN_LOAN_GROUP_ALT):
            loan_vals.append(row.sales)
        if row.group in (MEDIAN_LTV_GROUP, MEDIAN_LTV_GROUP_ALT):
            ltv_vals.append(row.sales)

    if not loan_vals:
        raise ValueError(f"Missing '{MEDIAN_LOAN_GROUP}' rows for year {target_year}.")
    if not ltv_vals:
        raise ValueError(f"Missing '{MEDIAN_LTV_GROUP}' rows for year {target_year}.")

    median_loan = sum(loan_vals) / len(loan_vals)
    median_ltv = sum(ltv_vals) / len(ltv_vals)
    if median_ltv <= 0.0:
        raise ValueError("Median LTV must be positive for anchor computation.")

    implied = median_loan / (median_ltv / 100.0)
    return AnchorDiagnostics(
        median_loan=median_loan,
        median_ltv_pct=median_ltv,
        implied_price=implied,
        loan_rows=len(loan_vals),
        ltv_rows=len(ltv_vals),
    )


def _modern_income_price_marginals(
    *,
    rows: list[LongPsdRow],
    target_year_psd: int,
    within_bin_points: int,
    income_open_upper_k: float,
    property_open_upper_k: float,
    tail_spec: TailSpec,
) -> _MarginalBundle:
    income_sales = aggregate_category_sales(rows, group=MODERN_2024_INCOME_GROUP, year=target_year_psd)
    property_sales = aggregate_category_sales(rows, group=MODERN_2024_PROPERTY_GROUP, year=target_year_psd)
    loan_sales = aggregate_category_sales(rows, group=MODERN_2024_LOAN_GROUP, year=target_year_psd)
    ltv_sales = aggregate_category_sales(rows, group=MODERN_2024_LTV_GROUP, year=target_year_psd)
    borrower_sales = aggregate_category_sales(rows, group=MODERN_2024_BORROWER_GROUP, year=target_year_psd)

    if not income_sales:
        raise ValueError(f"Missing modern income group '{MODERN_2024_INCOME_GROUP}' for year {target_year_psd}.")
    if not property_sales:
        raise ValueError(f"Missing modern property group '{MODERN_2024_PROPERTY_GROUP}' for year {target_year_psd}.")

    unknown_income_mass = 0.0
    for label, mass in income_sales.items():
        if "unknown" in label.lower():
            unknown_income_mass += mass

    income_bins = build_bins_from_category_masses(income_sales)
    property_bins = build_bins_from_category_masses(property_sales)

    if not income_bins or not property_bins:
        raise ValueError("No usable modern income/property bins after parsing.")

    income_values, income_weights, known_income_mass, tail_values, top_bin_mass = _expand_income_bins_with_tail(
        income_bins,
        within_bin_points=within_bin_points,
        tail_spec=tail_spec,
        income_open_upper_k=income_open_upper_k,
    )
    price_values, price_weights, property_mass = _expand_property_bins(
        property_bins,
        open_upper=property_open_upper_k * 1_000.0,
        within_bin_points=within_bin_points,
    )

    total_income_mass = known_income_mass + unknown_income_mass
    unknown_share_total = (
        unknown_income_mass / total_income_mass if total_income_mass > 0.0 else 0.0
    )
    top_bin_share_known = top_bin_mass / known_income_mass if known_income_mass > 0.0 else 0.0

    diagnostics = {
        "source_year_psd": float(target_year_psd),
        "income_bins": float(len(income_bins)),
        "price_bins": float(len(property_bins)),
        "income_mass_known": known_income_mass,
        "income_mass_unknown": unknown_income_mass,
        "income_unknown_share_total": unknown_share_total,
        "unknown_income_share": unknown_share_total,
        "income_top_bin_mass": top_bin_mass,
        "income_top_bin_share_known": top_bin_share_known,
        "price_mass": property_mass,
        "loan_group_mass": float(sum(loan_sales.values())) if loan_sales else 0.0,
        "ltv_group_mass": float(sum(ltv_sales.values())) if ltv_sales else 0.0,
        "borrower_group_mass": float(sum(borrower_sales.values())) if borrower_sales else 0.0,
        "tail_alpha": tail_spec.pareto_alpha,
        "tail_x_min": tail_spec.pareto_x_min,
    }

    return _MarginalBundle(
        income_values=income_values,
        income_weights=income_weights,
        price_values=price_values,
        price_weights=price_weights,
        diagnostics=diagnostics,
        tail_income_values=tail_values,
    )


def _quantile_from_sorted(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    if q <= 0.0:
        return values[0]
    if q >= 1.0:
        return values[-1]
    idx = int(q * (len(values) - 1))
    return values[idx]


def _pareto_sensitivity_summary(marginal_cache: dict[float, _MarginalBundle]) -> dict[str, float]:
    if not marginal_cache:
        return {}

    alphas = sorted(marginal_cache.keys())
    q95_values: list[float] = []
    q99_values: list[float] = []
    for alpha in alphas:
        tail_values = sorted(marginal_cache[alpha].tail_income_values)
        if not tail_values:
            continue
        q95_values.append(_quantile_from_sorted(tail_values, 0.95))
        q99_values.append(_quantile_from_sorted(tail_values, 0.99))

    summary: dict[str, float] = {
        "pareto_alpha_min": min(alphas),
        "pareto_alpha_max": max(alphas),
    }
    if q95_values:
        summary["pareto_tail_q95_min"] = min(q95_values)
        summary["pareto_tail_q95_max"] = max(q95_values)
    if q99_values:
        summary["pareto_tail_q99_min"] = min(q99_values)
        summary["pareto_tail_q99_max"] = max(q99_values)
    if q95_values and min(q95_values) > 0.0:
        summary["pareto_tail_q95_spread_ratio"] = max(q95_values) / min(q95_values)
    if q99_values and min(q99_values) > 0.0:
        summary["pareto_tail_q99_spread_ratio"] = max(q99_values) / min(q99_values)
    return summary


def _parse_ppd_status(row: list[str]) -> str:
    if len(row) <= 14:
        return ""
    return row[14].strip().upper()


def _parse_ppd_year(row: list[str]) -> int | None:
    if len(row) <= 2:
        return None
    token = row[2].strip()
    if len(token) < 4 or not token[:4].isdigit():
        return None
    return int(token[:4])


def _update_accumulator(acc: _PpdAccumulator, log_price: float, max_samples_per_year: int) -> _PpdAccumulator:
    sample = list(acc.sample_log_prices)
    if len(sample) < max_samples_per_year:
        sample.append(log_price)
    return _PpdAccumulator(
        rows=acc.rows + 1,
        sum_log=acc.sum_log + log_price,
        sum_sq_log=acc.sum_sq_log + log_price * log_price,
        sample_log_prices=tuple(sample),
    )


def load_ppd_summary(
    *,
    ppd_paths: tuple[Path, ...],
    status_mode: str,
    max_samples_per_year: int = 10_000,
) -> PpdSummary:
    if status_mode not in (PPD_STATUS_A_ONLY, PPD_STATUS_ALL):
        raise ValueError(f"Unsupported status_mode: {status_mode}")

    rows_total = 0
    rows_used = 0
    by_year: dict[int, _PpdAccumulator] = {}

    for path in ppd_paths:
        if not path.exists():
            raise ValueError(f"Missing PPD CSV: {path}")

        with path.open("r", encoding="utf-8", newline="", errors="replace") as handle:
            reader = csv.reader(handle)
            for row in reader:
                rows_total += 1
                if len(row) <= 1:
                    continue

                year = _parse_ppd_year(row)
                if year is None:
                    continue

                try:
                    price = float(row[1].strip())
                except ValueError:
                    continue
                if price <= 0.0:
                    continue

                status = _parse_ppd_status(row)
                if status_mode == PPD_STATUS_A_ONLY and status != "A":
                    continue

                rows_used += 1
                log_price = math.log(price)
                previous = by_year.get(
                    year,
                    _PpdAccumulator(rows=0, sum_log=0.0, sum_sq_log=0.0, sample_log_prices=tuple()),
                )
                by_year[year] = _update_accumulator(previous, log_price, max_samples_per_year)

    if rows_used == 0:
        raise ValueError("No usable PPD rows after filtering.")

    year_moments: dict[int, PpdYearMoments] = {}
    for year, acc in by_year.items():
        if acc.rows <= 0:
            continue
        mean = acc.sum_log / acc.rows
        variance = max((acc.sum_sq_log / acc.rows) - (mean * mean), 0.0)
        year_moments[year] = PpdYearMoments(
            year=year,
            rows_used=acc.rows,
            mean_log_price=mean,
            variance_log_price=variance,
            std_log_price=math.sqrt(variance),
            sample_log_prices=acc.sample_log_prices,
        )

    if not year_moments:
        raise ValueError("No yearly PPD moments could be computed.")

    return PpdSummary(
        status_mode=status_mode,
        source_paths=tuple(str(path) for path in ppd_paths),
        rows_total=rows_total,
        rows_used=rows_used,
        year_moments=year_moments,
        loaded_years=tuple(sorted(year_moments)),
    )


def _find_band_index_for_value(value: float, bins: list[PsdBin]) -> int | None:
    for index, item in enumerate(bins):
        lower = -math.inf if item.lower is None else item.lower
        upper = math.inf if item.upper is None else item.upper
        if value >= lower and value <= upper:
            return index
    return None


def _property_bins_from_rows(rows: list[LongPsdRow], target_year_psd: int) -> list[PsdBin]:
    property_sales = aggregate_category_sales(rows, group=MODERN_2024_PROPERTY_GROUP, year=target_year_psd)
    if not property_sales:
        raise ValueError(f"Missing modern property group '{MODERN_2024_PROPERTY_GROUP}' for year {target_year_psd}.")
    property_bins = build_bins_from_category_masses(property_sales)
    if not property_bins:
        raise ValueError("No usable PSD property-value bins after parsing.")
    return property_bins


def load_raked_ppd_target(
    *,
    ppd_paths: tuple[Path, ...],
    status_mode: str,
    source_year: int,
    property_bins: list[PsdBin],
) -> RakedPpdTarget:
    if status_mode not in (PPD_STATUS_A_ONLY, PPD_STATUS_ALL):
        raise ValueError(f"Unsupported status_mode: {status_mode}")
    if not property_bins:
        raise ValueError("property_bins must be non-empty.")

    rows_total = 0
    rows_source_year = 0
    rows_valid_price = 0
    rows_unmatched = 0
    rows_by_band: list[list[float]] = [[] for _ in property_bins]

    for path in ppd_paths:
        if not path.exists():
            raise ValueError(f"Missing PPD CSV: {path}")

        with path.open("r", encoding="utf-8", newline="", errors="replace") as handle:
            reader = csv.reader(handle)
            for row in reader:
                rows_total += 1
                if len(row) <= 1:
                    continue
                year = _parse_ppd_year(row)
                if year != source_year:
                    continue
                rows_source_year += 1

                try:
                    price = float(row[1].strip())
                except ValueError:
                    continue
                if price <= 0.0:
                    continue

                status = _parse_ppd_status(row)
                if status_mode == PPD_STATUS_A_ONLY and status != "A":
                    continue

                rows_valid_price += 1
                band_index = _find_band_index_for_value(price, property_bins)
                if band_index is None:
                    rows_unmatched += 1
                    continue
                rows_by_band[band_index].append(math.log(price))

    log_prices: list[float] = []
    weights: list[float] = []
    rows_non_positive_weight = 0
    bands_with_rows = 0
    psd_total_mass = sum(max(item.mass, 0.0) for item in property_bins)
    if psd_total_mass <= 0.0:
        raise ValueError("PSD property-value bands require positive total mass.")

    for item, band_log_prices in zip(property_bins, rows_by_band):
        if not band_log_prices:
            continue
        if item.mass <= 0.0:
            rows_non_positive_weight += len(band_log_prices)
            continue
        bands_with_rows += 1
        weight_per_row = item.mass / len(band_log_prices)
        log_prices.extend(band_log_prices)
        weights.extend([weight_per_row] * len(band_log_prices))

    if not log_prices:
        raise ValueError("No usable raked PPD target rows after filtering and PSD-band matching.")

    weight_total = sum(weights)
    diagnostics = {
        "source_year_ppd": float(source_year),
        "ppd_rows_total": float(rows_total),
        "ppd_rows_source_year": float(rows_source_year),
        "ppd_rows_valid_price": float(rows_valid_price),
        "ppd_rows_used_raked": float(len(log_prices)),
        "ppd_rows_unmatched_to_psd_bands": float(rows_unmatched),
        "ppd_rows_non_positive_weight": float(rows_non_positive_weight),
        "ppd_raked_weight_total": weight_total,
        "ppd_raked_weight_total_normalized_check": 1.0,
        "ppd_property_band_count": float(len(property_bins)),
        "ppd_property_bands_with_rows": float(bands_with_rows),
        "ppd_2025_loaded": 1.0 if any("2025" in str(path) for path in ppd_paths) else 0.0,
    }
    normalized_weights = [weight / weight_total for weight in weights]
    return RakedPpdTarget(
        status_mode=status_mode,
        source_year=source_year,
        source_paths=tuple(str(path) for path in ppd_paths),
        rows_total=rows_total,
        rows_source_year=rows_source_year,
        rows_valid_price=rows_valid_price,
        rows_used=len(log_prices),
        rows_unmatched_to_psd_bands=rows_unmatched,
        rows_non_positive_weight=rows_non_positive_weight,
        property_band_count=len(property_bins),
        bands_with_ppd_rows=bands_with_rows,
        log_prices=log_prices,
        weights=normalized_weights,
        diagnostics=diagnostics,
    )


def _pooled_ppd_moments(summary: PpdSummary, years: tuple[int, ...]) -> tuple[float, float, int]:
    total_n = 0
    total_sum = 0.0
    total_sq = 0.0
    for year in years:
        if year not in summary.year_moments:
            raise ValueError(f"Missing PPD year {year} for status_mode={summary.status_mode}.")
        item = summary.year_moments[year]
        total_n += item.rows_used
        total_sum += item.mean_log_price * item.rows_used
        total_sq += (item.variance_log_price + item.mean_log_price**2) * item.rows_used

    if total_n <= 0:
        raise ValueError("No rows available for pooled PPD moments.")

    mean = total_sum / total_n
    variance = max((total_sq / total_n) - (mean * mean), 0.0)
    return mean, variance, total_n


def _solve_anchor_weighted_ols(
    x_values: list[float],
    y_values: list[float],
    *,
    x_anchor: float,
    y_anchor: float,
    anchor_weight: float,
) -> tuple[float, float]:
    if len(x_values) != len(y_values) or not x_values:
        raise ValueError("x_values and y_values must be non-empty and aligned.")
    if anchor_weight < 0.0:
        raise ValueError("anchor_weight must be non-negative.")

    xs = list(x_values)
    ys = list(y_values)
    ws = [1.0] * len(xs)

    if anchor_weight > 0.0:
        xs.append(x_anchor)
        ys.append(y_anchor)
        ws.append(anchor_weight)

    total_w = sum(ws)
    mean_x = sum(weight * x for x, weight in zip(xs, ws)) / total_w
    mean_y = sum(weight * y for y, weight in zip(ys, ws)) / total_w

    sxx = sum(weight * (x - mean_x) ** 2 for x, weight in zip(xs, ws))
    sxy = sum(weight * (x - mean_x) * (y - mean_y) for x, y, weight in zip(xs, ys, ws))
    if sxx <= 0.0:
        raise ValueError("Degenerate x-values; cannot estimate BUY_EXPONENT.")

    exponent = sxy / sxx
    intercept = mean_y - exponent * mean_x
    return intercept, exponent


def budget_median_multiple(*, buy_scale: float, buy_exponent: float, income: float) -> float:
    if income <= 0.0:
        raise ValueError("income must be positive.")
    median_budget = buy_scale * math.pow(income, buy_exponent)
    return median_budget / income


def budget_p95_multiple(*, buy_scale: float, buy_exponent: float, buy_sigma: float, income: float) -> float:
    if income <= 0.0:
        raise ValueError("income must be positive.")
    p95_budget = buy_scale * math.pow(income, buy_exponent) * math.exp(P95_Z * buy_sigma)
    return p95_budget / income


def evaluate_guardrails(
    *,
    buy_scale: float,
    buy_exponent: float,
    buy_mu: float,
    buy_sigma: float,
    hard_p95_cap: float,
    exponent_max: float,
    sigma_warning_low: float,
    sigma_warning_high: float,
    income_checkpoints: tuple[float, ...] = DEFAULT_INCOME_CHECKPOINTS,
    enforce_hard_gates: bool = True,
) -> GuardrailOutcome:
    hard_failures: list[str] = []
    warnings: list[str] = []

    median_multiples: dict[int, float] = {}
    p95_multiples: dict[int, float] = {}

    if abs(buy_mu) > 1e-12:
        hard_failures.append(f"BUY_MU must be 0 within tolerance 1e-12, got {buy_mu:.12g}.")
    if buy_scale <= 0.0:
        hard_failures.append(f"BUY_SCALE must be > 0, got {buy_scale:.12g}.")
    if buy_exponent <= 0.0:
        hard_failures.append(f"BUY_EXPONENT must be > 0, got {buy_exponent:.12g}.")
    if buy_exponent > exponent_max:
        hard_failures.append(
            f"BUY_EXPONENT must be <= {exponent_max:.6g}, got {buy_exponent:.6f}."
        )
    if buy_sigma < 0.1 or buy_sigma > 0.8:
        hard_failures.append(f"BUY_SIGMA must be in [0.1, 0.8], got {buy_sigma:.6f}.")

    previous_median_budget = -math.inf
    for income in income_checkpoints:
        median_budget = buy_scale * math.pow(income, buy_exponent)
        median_mult = median_budget / income
        p95_mult = budget_p95_multiple(
            buy_scale=buy_scale,
            buy_exponent=buy_exponent,
            buy_sigma=buy_sigma,
            income=income,
        )
        key = int(income)
        median_multiples[key] = median_mult
        p95_multiples[key] = p95_mult

        if not (median_mult > 1.0 and median_mult < 10.0):
            hard_failures.append(
                f"Median budget multiple must satisfy 1 < m < 10 at income={key}; got {median_mult:.6f}."
            )
        if p95_mult >= hard_p95_cap:
            hard_failures.append(
                f"P95 budget multiple must be < {hard_p95_cap:.0f} at income={key}; got {p95_mult:.6f}."
            )
        if median_budget <= previous_median_budget:
            hard_failures.append(
                f"Median budget must be strictly increasing; failed at income={key}."
            )
        previous_median_budget = median_budget

    if buy_sigma < sigma_warning_low or buy_sigma > sigma_warning_high:
        warnings.append(
            f"BUY_SIGMA={buy_sigma:.6f} outside warning band [{sigma_warning_low:.1f}, {sigma_warning_high:.1f}]."
        )

    passed = not hard_failures if enforce_hard_gates else True
    if not enforce_hard_gates and hard_failures:
        warnings.extend([f"(baseline relaxed) {item}" for item in hard_failures])
        hard_failures = []

    return GuardrailOutcome(
        passed=passed,
        hard_failures=tuple(hard_failures),
        warnings=tuple(warnings),
        median_budget_multiples=median_multiples,
        p95_budget_multiples=p95_multiples,
    )


def _model_log_price_moments(
    *,
    intercept: float,
    exponent: float,
    sigma: float,
    income_values: list[float],
    income_weights: list[float],
) -> tuple[float, float, float, float]:
    log_income = [math.log(max(value, 1e-12)) for value in income_values]
    mean_log_income = _weighted_mean(log_income, income_weights)
    var_log_income = _weighted_variance(log_income, income_weights, mean=mean_log_income)
    mean_log_price = intercept + exponent * mean_log_income
    var_log_price = max((exponent**2) * var_log_income + sigma**2, 0.0)
    return mean_log_price, var_log_price, mean_log_income, var_log_income


def _fit_error(model_value: float, target_value: float, floor: float) -> float:
    return abs(model_value - target_value) / max(abs(target_value), floor)


def _objective_from_components(
    *,
    weights: ObjectiveWeights,
    fit: float,
    anchor: float,
    p95: float,
    sigma: float,
    curve: float,
) -> ObjectiveComponents:
    total = (
        weights.w_fit * fit
        + weights.w_anchor * anchor
        + weights.w_p95 * p95
        + weights.w_sigma * sigma
        + weights.w_curve * curve
    )
    return ObjectiveComponents(
        objective_total=total,
        objective_fit=fit,
        objective_anchor=anchor,
        objective_p95=p95,
        objective_sigma=sigma,
        objective_median_curve=curve,
    )


def _penalty_sigma(*, sigma: float, low: float, high: float) -> float:
    if sigma < low:
        return (low - sigma) / max(low, 1e-9)
    if sigma > high:
        return (sigma - high) / max(high, 1e-9)
    return 0.0


def _penalty_p95(*, p95_map: dict[int, float], soft_cap: float) -> float:
    penalties = [max(0.0, value - soft_cap) / max(soft_cap, 1e-9) for value in p95_map.values()]
    return sum(penalties) / len(penalties) if penalties else 0.0


def _penalty_median_curve(*, med_map: dict[int, float], target_curve: dict[int, float]) -> float:
    penalties: list[float] = []
    for income_key, target in target_curve.items():
        observed = med_map.get(income_key)
        if observed is None:
            continue
        penalties.append(max(0.0, observed - target) / max(target, 1e-9))
    return sum(penalties) / len(penalties) if penalties else 0.0


def _huber(value: float, delta: float) -> float:
    magnitude = abs(value)
    if magnitude <= delta:
        return 0.5 * value * value
    return delta * (magnitude - 0.5 * delta)


def _weighted_median(values: list[float], weights: list[float]) -> float:
    return _weighted_quantile(values, weights, 0.5)


def _mixture_normal_cdf(
    *,
    y_value: float,
    log_scale: float,
    exponent: float,
    sigma: float,
    log_income_values: list[float],
    income_weights: list[float],
    normal: NormalDist,
) -> float:
    if sigma <= 0.0:
        raise ValueError("sigma must be positive.")
    total = 0.0
    for log_income, weight in zip(log_income_values, income_weights):
        center = log_scale + exponent * log_income
        total += weight * normal.cdf((y_value - center) / sigma)
    return total


def _mixture_normal_quantile(
    *,
    q: float,
    log_scale: float,
    exponent: float,
    sigma: float,
    log_income_values: list[float],
    income_weights: list[float],
    normal: NormalDist,
) -> float:
    if q <= 0.0 or q >= 1.0:
        raise ValueError("Mixture quantile q must be in (0,1).")
    centers = [log_scale + exponent * value for value in log_income_values]
    lower = min(centers) + sigma * normal.inv_cdf(max(q * 1.0e-4, 1.0e-8))
    upper = max(centers) + sigma * normal.inv_cdf(min(1.0 - (1.0 - q) * 1.0e-4, 1.0 - 1.0e-8))
    for _ in range(72):
        mid = (lower + upper) / 2.0
        cdf = _mixture_normal_cdf(
            y_value=mid,
            log_scale=log_scale,
            exponent=exponent,
            sigma=sigma,
            log_income_values=log_income_values,
            income_weights=income_weights,
            normal=normal,
        )
        if cdf < q:
            lower = mid
        else:
            upper = mid
    return (lower + upper) / 2.0


def _mixture_normal_quantiles(
    *,
    levels: tuple[float, ...],
    log_scale: float,
    exponent: float,
    sigma: float,
    log_income_values: list[float],
    income_weights: list[float],
    normal: NormalDist,
) -> tuple[float, ...]:
    return tuple(
        _mixture_normal_quantile(
            q=level,
            log_scale=log_scale,
            exponent=exponent,
            sigma=sigma,
            log_income_values=log_income_values,
            income_weights=income_weights,
            normal=normal,
        )
        for level in levels
    )


def _quantile_loss(
    *,
    target_log_quantiles: tuple[float, ...],
    model_log_quantiles: tuple[float, ...],
    quantile_weights: tuple[float, ...],
    huber_delta: float,
) -> float:
    total_weight = sum(quantile_weights)
    if total_weight <= 0.0:
        raise ValueError("quantile_weights require positive total weight.")
    total = 0.0
    for target, model, weight in zip(target_log_quantiles, model_log_quantiles, quantile_weights):
        total += weight * _huber(target - model, huber_delta)
    return total / total_weight


def _fit_2024_only_raked_quantiles(
    *,
    marginals: _MarginalBundle,
    raked_target: RakedPpdTarget,
    anchor: AnchorDiagnostics,
    exponent: float,
    spec: QuantileFitSpec,
    weights: ObjectiveWeights,
    income_checkpoints: tuple[float, ...],
) -> tuple[float, float, ObjectiveComponents, dict[str, float], tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    if exponent <= 0.0:
        raise ValueError("fixed exponent must be positive.")
    if spec.sigma_search_low <= 0.0 or spec.sigma_search_high < spec.sigma_search_low:
        raise ValueError("Invalid sigma search bounds.")

    normal = NormalDist()
    income_weight_total = sum(marginals.income_weights)
    if income_weight_total <= 0.0:
        raise ValueError("Income weights require positive total.")
    income_weights = [weight / income_weight_total for weight in marginals.income_weights]
    log_income_values = [math.log(max(value, 1.0e-12)) for value in marginals.income_values]

    levels = spec.quantile_levels
    target_log_quantiles = _weighted_quantiles(raked_target.log_prices, raked_target.weights, levels)
    quantile_weights = tuple(0.5 if level in (0.05, 0.95) else 1.0 for level in levels)

    sigma_values = [spec.sigma_search_low + idx * 0.01 for idx in range(int(round((spec.sigma_search_high - spec.sigma_search_low) / 0.01)) + 1)]
    best: tuple[float, float, ObjectiveComponents, tuple[float, ...], dict[str, float]] | None = None

    def evaluate_sigma(sigma: float) -> tuple[float, float, ObjectiveComponents, tuple[float, ...], dict[str, float]]:
        base_quantiles = _mixture_normal_quantiles(
            levels=levels,
            log_scale=0.0,
            exponent=exponent,
            sigma=sigma,
            log_income_values=log_income_values,
            income_weights=income_weights,
            normal=normal,
        )
        residual_shifts = [
            target - model
            for target, model in zip(target_log_quantiles, base_quantiles)
        ]
        log_scale = _weighted_median(residual_shifts, list(quantile_weights))
        model_quantiles = tuple(log_scale + value for value in base_quantiles)
        fit = _quantile_loss(
            target_log_quantiles=target_log_quantiles,
            model_log_quantiles=model_quantiles,
            quantile_weights=quantile_weights,
            huber_delta=spec.quantile_huber_delta,
        )

        buy_scale = math.exp(log_scale)
        guardrails = evaluate_guardrails(
            buy_scale=buy_scale,
            buy_exponent=exponent,
            buy_mu=0.0,
            buy_sigma=sigma,
            hard_p95_cap=spec.hard_p95_cap,
            exponent_max=spec.exponent_max,
            sigma_warning_low=spec.sigma_warning_low,
            sigma_warning_high=spec.sigma_warning_high,
            income_checkpoints=income_checkpoints,
            enforce_hard_gates=False,
        )
        model_median = _mixture_normal_quantile(
            q=0.5,
            log_scale=log_scale,
            exponent=exponent,
            sigma=sigma,
            log_income_values=log_income_values,
            income_weights=income_weights,
            normal=normal,
        )
        psd_property_median = math.log(_weighted_quantile(marginals.price_values, marginals.price_weights, 0.5))
        target_median = target_log_quantiles[levels.index(0.5)] if 0.5 in levels else _weighted_quantile(raked_target.log_prices, raked_target.weights, 0.5)
        anchor_values = [target_median, psd_property_median, math.log(anchor.implied_price)]
        anchor_penalty = sum(_huber(model_median - value, spec.quantile_huber_delta) for value in anchor_values) / len(anchor_values)
        penalty_p95 = _penalty_p95(p95_map=guardrails.p95_budget_multiples, soft_cap=spec.p95_soft_cap)
        penalty_sigma = _penalty_sigma(sigma=sigma, low=spec.sigma_warning_low, high=spec.sigma_warning_high)
        penalty_curve = _penalty_median_curve(
            med_map=guardrails.median_budget_multiples,
            target_curve=spec.resolved_median_target_curve(),
        )
        objective = _objective_from_components(
            weights=weights,
            fit=fit,
            anchor=anchor_penalty,
            p95=penalty_p95,
            sigma=penalty_sigma,
            curve=penalty_curve,
        )
        diagnostics = {
            "quantile_huber_delta": spec.quantile_huber_delta,
            "model_median_log_price": model_median,
            "target_raked_median_log_price": target_median,
            "psd_property_median_log_price": psd_property_median,
            "anchor_implied_log_price": math.log(anchor.implied_price),
            "raked_quantile_fit_loss": fit,
        }
        return objective.objective_total, log_scale, objective, model_quantiles, diagnostics

    for sigma in sigma_values:
        candidate = evaluate_sigma(sigma)
        if best is None or candidate[0] < best[0]:
            best = candidate

    if best is None:
        raise ValueError("No 2024-only sigma candidates were evaluated.")

    best_sigma = sigma_values[0]
    best_total = math.inf
    for sigma in sigma_values:
        candidate = evaluate_sigma(sigma)
        if candidate[0] < best_total:
            best_total = candidate[0]
            best_sigma = sigma

    refine_low = max(spec.sigma_search_low, best_sigma - 0.01)
    refine_high = min(spec.sigma_search_high, best_sigma + 0.01)
    refined_count = int(round((refine_high - refine_low) / 0.001)) + 1
    for idx in range(refined_count):
        sigma = refine_low + idx * 0.001
        candidate = evaluate_sigma(sigma)
        if candidate[0] < best[0]:
            best = candidate
            best_sigma = sigma

    _, log_scale, objective, model_log_quantiles, diagnostics = best
    buy_scale = math.exp(log_scale)
    residuals = tuple(target - model for target, model in zip(target_log_quantiles, model_log_quantiles))
    diagnostics["selected_sigma_grid_value"] = best_sigma
    diagnostics["selected_log_scale"] = log_scale
    return buy_scale, best_sigma, objective, diagnostics, target_log_quantiles, model_log_quantiles, residuals


def calibrate_buy_variant(
    *,
    marginals: _MarginalBundle,
    anchor: AnchorDiagnostics,
    ppd_summary: PpdSummary,
    fit_years: tuple[int, ...],
    status_mode: str,
    year_policy: str,
    guardrail_mode: str,
    spec: QuantileFitSpec,
    weights: ObjectiveWeights,
    tail_spec: TailSpec,
    income_checkpoints: tuple[float, ...] = DEFAULT_INCOME_CHECKPOINTS,
    enforce_hard_gates: bool = True,
    fit_degradation_vs_baseline: float | None = None,
    pareto_sensitivity_summary: dict[str, float] | None = None,
    raked_ppd_target: RakedPpdTarget | None = None,
) -> BuyBudgetVariantResult:
    if guardrail_mode not in GUARDRAIL_MODE_CHOICES:
        raise ValueError(f"Unsupported guardrail_mode: {guardrail_mode}")

    fit_mean_log_price, _fit_variance, fit_rows = _pooled_ppd_moments(ppd_summary, fit_years)

    income_values = marginals.income_values
    income_weights = marginals.income_weights
    price_values = marginals.price_values
    price_weights = marginals.price_weights

    income_quantiles = tuple(
        _weighted_quantile(income_values, income_weights, quantile)
        for quantile in spec.quantile_levels
    )
    price_quantiles = tuple(
        _weighted_quantile(price_values, price_weights, quantile)
        for quantile in spec.quantile_levels
    )

    log_income_values = [math.log(max(value, 1e-12)) for value in income_values]
    mean_log_income = _weighted_mean(log_income_values, income_weights)

    if year_policy == YEAR_POLICY_2024_ONLY:
        if raked_ppd_target is None:
            raise ValueError("2024_only BUY calibration requires a raked PPD target.")
        buy_exponent = 1.0 if spec.fixed_exponent is None else spec.fixed_exponent
        buy_scale, buy_sigma, objective, raked_diagnostics, target_log_quantiles, model_log_quantiles, residuals = _fit_2024_only_raked_quantiles(
            marginals=marginals,
            raked_target=raked_ppd_target,
            anchor=anchor,
            exponent=buy_exponent,
            spec=spec,
            weights=weights,
            income_checkpoints=income_checkpoints,
        )
        intercept = math.log(buy_scale)
        price_quantiles = tuple(math.exp(value) for value in target_log_quantiles)
        modeled_median_quantiles = tuple(math.exp(value) for value in model_log_quantiles)
        quantile_rmse_log = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    else:
        x_values = [math.log(max(value, 1e-12)) for value in income_quantiles]
        y_values = [math.log(max(value, 1e-12)) for value in price_quantiles]
        intercept, buy_exponent = _solve_anchor_weighted_ols(
            x_values,
            y_values,
            x_anchor=mean_log_income,
            y_anchor=fit_mean_log_price,
            anchor_weight=spec.ppd_mean_anchor_weight,
        )
        buy_scale = math.exp(intercept)
        residuals = tuple(y - (intercept + buy_exponent * x) for x, y in zip(x_values, y_values))
        buy_sigma = math.sqrt(sum(value * value for value in residuals) / len(residuals))
        median_curve_target = spec.resolved_median_target_curve()
        preliminary_guardrails = evaluate_guardrails(
            buy_scale=buy_scale,
            buy_exponent=buy_exponent,
            buy_mu=0.0,
            buy_sigma=buy_sigma,
            hard_p95_cap=spec.hard_p95_cap,
            exponent_max=spec.exponent_max,
            sigma_warning_low=spec.sigma_warning_low,
            sigma_warning_high=spec.sigma_warning_high,
            income_checkpoints=income_checkpoints,
            enforce_hard_gates=enforce_hard_gates,
        )
        median_income = _weighted_quantile(income_values, income_weights, 0.5)
        model_anchor_price = buy_scale * math.pow(max(median_income, 1e-12), buy_exponent)
        anchor_error = abs(model_anchor_price - anchor.implied_price) / max(anchor.implied_price, 1e-9)
        objective = _objective_from_components(
            weights=weights,
            fit=0.0,
            anchor=anchor_error,
            p95=_penalty_p95(p95_map=preliminary_guardrails.p95_budget_multiples, soft_cap=spec.p95_soft_cap),
            sigma=_penalty_sigma(sigma=buy_sigma, low=spec.sigma_warning_low, high=spec.sigma_warning_high),
            curve=_penalty_median_curve(
                med_map=preliminary_guardrails.median_budget_multiples,
                target_curve=median_curve_target,
            ),
        )
        modeled_median_quantiles = tuple(
            buy_scale * math.pow(max(income, 1e-12), buy_exponent)
            for income in income_quantiles
        )
        raked_diagnostics = {}
        quantile_rmse_log = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    buy_mu = 0.0

    model_mean_log_price, model_var_log_price, model_income_mean_log, model_income_var_log = _model_log_price_moments(
        intercept=intercept,
        exponent=buy_exponent,
        sigma=buy_sigma,
        income_values=income_values,
        income_weights=income_weights,
    )
    model_std_log_price = math.sqrt(model_var_log_price)

    yearly_fit_distance: dict[int, float] = {}
    yearly_fit_mean_error: dict[int, float] = {}
    yearly_fit_std_error: dict[int, float] = {}
    for year in (2024, 2025):
        year_item = ppd_summary.year_moments.get(year)
        if year_item is None:
            yearly_fit_distance[year] = math.inf
            yearly_fit_mean_error[year] = math.inf
            yearly_fit_std_error[year] = math.inf
            continue

        mean_error = _fit_error(model_mean_log_price, year_item.mean_log_price, floor=0.1)
        std_error = _fit_error(model_std_log_price, year_item.std_log_price, floor=0.05)
        yearly_fit_mean_error[year] = mean_error
        yearly_fit_std_error[year] = std_error
        yearly_fit_distance[year] = math.sqrt(mean_error**2 + std_error**2)

    worst_year_fit_distance = max(yearly_fit_distance[year] for year in fit_years)

    guardrails = evaluate_guardrails(
        buy_scale=buy_scale,
        buy_exponent=buy_exponent,
        buy_mu=buy_mu,
        buy_sigma=buy_sigma,
        hard_p95_cap=spec.hard_p95_cap,
        exponent_max=spec.exponent_max,
        sigma_warning_low=spec.sigma_warning_low,
        sigma_warning_high=spec.sigma_warning_high,
        income_checkpoints=income_checkpoints,
        enforce_hard_gates=enforce_hard_gates,
    )

    source_failures: list[str] = []
    if year_policy == YEAR_POLICY_2024_ONLY:
        if int(marginals.diagnostics.get("source_year_psd", -1)) != 2024:
            source_failures.append("source_year_psd must be 2024 for 2024_only BUY calibration.")
        if raked_ppd_target is None or raked_ppd_target.source_year != 2024:
            source_failures.append("source_year_ppd must be 2024 for 2024_only BUY calibration.")
        if 2025 in ppd_summary.loaded_years:
            source_failures.append("No PPD 2025 rows may be loaded for 2024_only BUY calibration.")
        if raked_ppd_target is not None and raked_ppd_target.diagnostics.get("ppd_2025_loaded", 0.0) > 0.0:
            source_failures.append("No PPD 2025 file may be loaded for 2024_only BUY calibration.")
        if fit_years != (2024,):
            source_failures.append("2024_only BUY calibration must fit exactly year 2024.")
    if source_failures:
        if enforce_hard_gates:
            guardrails = GuardrailOutcome(
                passed=False,
                hard_failures=guardrails.hard_failures + tuple(source_failures),
                warnings=guardrails.warnings,
                median_budget_multiples=guardrails.median_budget_multiples,
                p95_budget_multiples=guardrails.p95_budget_multiples,
            )
        else:
            guardrails = GuardrailOutcome(
                passed=guardrails.passed,
                hard_failures=guardrails.hard_failures,
                warnings=guardrails.warnings + tuple(f"(baseline relaxed) {item}" for item in source_failures),
                median_budget_multiples=guardrails.median_budget_multiples,
                p95_budget_multiples=guardrails.p95_budget_multiples,
            )

    median_income = _weighted_quantile(income_values, income_weights, 0.5)
    model_anchor_price = buy_scale * math.pow(max(median_income, 1e-12), buy_exponent)
    anchor_error = abs(model_anchor_price - anchor.implied_price) / max(anchor.implied_price, 1e-9)
    if year_policy != YEAR_POLICY_2024_ONLY:
        objective = _objective_from_components(
            weights=weights,
            fit=worst_year_fit_distance,
            anchor=anchor_error,
            p95=objective.objective_p95,
            sigma=objective.objective_sigma,
            curve=objective.objective_median_curve,
        )

    diagnostics = dict(marginals.diagnostics)
    diagnostics.update(raked_diagnostics)
    if raked_ppd_target is not None:
        diagnostics.update(raked_ppd_target.diagnostics)
    if pareto_sensitivity_summary:
        diagnostics.update(pareto_sensitivity_summary)
    diagnostics.update(
        {
            "fit_rows": float(fit_rows),
            "fit_mean_log_price": fit_mean_log_price,
            "intercept": intercept,
            "buy_mu_locked": 1.0,
            "fixed_exponent": buy_exponent if year_policy == YEAR_POLICY_2024_ONLY else float("nan"),
            "quantile_levels": tuple(spec.quantile_levels),
            "sigma_warning": 1.0
            if buy_sigma < spec.sigma_warning_low or buy_sigma > spec.sigma_warning_high
            else 0.0,
            "quantile_rmse_log": quantile_rmse_log,
            "model_mean_log_price": model_mean_log_price,
            "model_std_log_price": model_std_log_price,
            "model_income_mean_log": model_income_mean_log,
            "model_income_var_log": model_income_var_log,
            "anchor_median_loan": anchor.median_loan,
            "anchor_median_ltv_pct": anchor.median_ltv_pct,
            "anchor_implied_price": anchor.implied_price,
            "anchor_model_price": model_anchor_price,
            "anchor_price_error": anchor_error,
            "objective_total": objective.objective_total,
            "objective_fit": objective.objective_fit,
            "objective_anchor": objective.objective_anchor,
            "objective_p95": objective.objective_p95,
            "objective_sigma": objective.objective_sigma,
            "objective_median_curve": objective.objective_median_curve,
            "tail_alpha": tail_spec.pareto_alpha,
            "tail_count": float(len(marginals.tail_income_values)),
            "fit_degradation_vs_baseline": (
                fit_degradation_vs_baseline
                if fit_degradation_vs_baseline is not None
                else float("nan")
            ),
        }
    )

    model_income_series = _weighted_quantile_series(
        income_values,
        income_weights,
        spec.quantile_grid_size,
    )
    normal = NormalDist()
    model_log_price_series = tuple(
        intercept
        + buy_exponent * math.log(max(income, 1e-12))
        + buy_sigma * normal.inv_cdf((idx + 0.5) / spec.quantile_grid_size)
        for idx, income in enumerate(model_income_series)
        )

    if guardrail_mode == GUARDRAIL_MODE_FAIL and enforce_hard_gates and not guardrails.passed:
        diagnostics["guardrail_failed"] = 1.0
    else:
        diagnostics["guardrail_failed"] = 0.0

    return BuyBudgetVariantResult(
        status_mode=status_mode,
        year_policy=year_policy,
        buy_scale=buy_scale,
        buy_exponent=buy_exponent,
        buy_mu=buy_mu,
        buy_sigma=buy_sigma,
        selected_alpha=tail_spec.pareto_alpha,
        weight_profile_id=weights.profile_id,
        guardrail_mode=guardrail_mode,
        guardrails=guardrails,
        sigma_warning=(buy_sigma < spec.sigma_warning_low or buy_sigma > spec.sigma_warning_high),
        fit_years=fit_years,
        yearly_fit_distance=yearly_fit_distance,
        yearly_fit_mean_error=yearly_fit_mean_error,
        yearly_fit_std_error=yearly_fit_std_error,
        worst_year_fit_distance=worst_year_fit_distance,
        objective=objective,
        anchor=anchor,
        fit_degradation_vs_baseline=fit_degradation_vs_baseline,
        ppd_summary=ppd_summary,
        diagnostics=diagnostics,
        income_quantiles=income_quantiles,
        observed_price_quantiles=price_quantiles,
        modeled_median_quantiles=modeled_median_quantiles,
        model_log_price_series=model_log_price_series,
        tail_income_values=tuple(marginals.tail_income_values),
    )


def evaluate_variants(
    *,
    quarterly_csv: Path,
    target_year_psd: int,
    ppd_paths: tuple[Path, ...],
    status_mode: str,
    year_policy: str,
    guardrail_mode: str,
    spec: QuantileFitSpec,
    objective_weight_profiles: tuple[ObjectiveWeights, ...],
    tail_family: str,
    pareto_alpha_values: tuple[float, ...],
    income_open_upper_k: float,
    property_open_upper_k: float,
    income_checkpoints: tuple[float, ...] = DEFAULT_INCOME_CHECKPOINTS,
    workers: int = 1,
    progress_callback: Callable[[int, int, str], None] | None = None,
    enforce_hard_gates: bool = True,
) -> list[BuyBudgetVariantResult]:
    if workers <= 0:
        raise ValueError("workers must be positive.")
    if tail_family not in TAIL_FAMILY_CHOICES:
        raise ValueError(f"Unsupported tail family: {tail_family}")
    if not objective_weight_profiles:
        raise ValueError("objective_weight_profiles must be non-empty.")
    if not pareto_alpha_values:
        raise ValueError("pareto_alpha_values must be non-empty.")

    statuses = iter_status_modes(status_mode)
    policies = iter_year_policies(year_policy)

    rows = load_quarterly_psd_rows(quarterly_csv)
    anchor = _median_anchor_from_rows(rows, target_year_psd)
    property_bins = _property_bins_from_rows(rows, target_year_psd)

    summary_cache: dict[str, PpdSummary] = {
        status: load_ppd_summary(ppd_paths=ppd_paths, status_mode=status)
        for status in statuses
    }
    raked_target_cache: dict[str, RakedPpdTarget] = {}
    if YEAR_POLICY_2024_ONLY in policies:
        raked_target_cache = {
            status: load_raked_ppd_target(
                ppd_paths=ppd_paths,
                status_mode=status,
                source_year=2024,
                property_bins=property_bins,
            )
            for status in statuses
        }

    marginal_cache: dict[float, _MarginalBundle] = {}
    for alpha in pareto_alpha_values:
        tail = TailSpec(family=tail_family, pareto_alpha=float(alpha))
        marginal_cache[float(alpha)] = _modern_income_price_marginals(
            rows=rows,
            target_year_psd=target_year_psd,
            within_bin_points=spec.within_bin_points,
            income_open_upper_k=income_open_upper_k,
            property_open_upper_k=property_open_upper_k,
            tail_spec=tail,
        )
    pareto_sensitivity_summary = _pareto_sensitivity_summary(marginal_cache)

    tasks: list[tuple[str, str, float, ObjectiveWeights]] = []
    for status in statuses:
        for policy in policies:
            for alpha in pareto_alpha_values:
                for weights in objective_weight_profiles:
                    tasks.append((status, policy, float(alpha), weights))

    total = len(tasks)
    if total == 0:
        return []

    results: list[BuyBudgetVariantResult] = []

    def run_task(task: tuple[str, str, float, ObjectiveWeights]) -> BuyBudgetVariantResult:
        status, policy, alpha, weights = task
        tail = TailSpec(family=tail_family, pareto_alpha=alpha)
        return calibrate_buy_variant(
            marginals=marginal_cache[alpha],
            anchor=anchor,
            ppd_summary=summary_cache[status],
            fit_years=fit_years_from_policy(policy),
            status_mode=status,
            year_policy=policy,
            guardrail_mode=guardrail_mode,
            spec=spec,
            weights=weights,
            tail_spec=tail,
            income_checkpoints=income_checkpoints,
            enforce_hard_gates=enforce_hard_gates,
            fit_degradation_vs_baseline=None,
            pareto_sensitivity_summary=pareto_sensitivity_summary,
            raked_ppd_target=raked_target_cache.get(status),
        )

    if workers == 1 or total == 1:
        for processed, task in enumerate(tasks, start=1):
            item = run_task(task)
            results.append(item)
            if progress_callback is not None:
                progress_callback(processed, total, item.variant_id)
    else:
        max_workers = min(workers, total)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(run_task, task): task for task in tasks}
            processed = 0
            for future in as_completed(future_map):
                item = future.result()
                results.append(item)
                processed += 1
                if progress_callback is not None:
                    progress_callback(processed, total, item.variant_id)

    return rank_variants(results)


def evaluate_baseline_best_fit(
    *,
    quarterly_csv: Path,
    target_year_psd: int,
    ppd_paths: tuple[Path, ...],
    status_mode: str,
    year_policy: str,
    spec: QuantileFitSpec,
    tail_family: str,
    pareto_alpha_values: tuple[float, ...],
    income_open_upper_k: float,
    property_open_upper_k: float,
    income_checkpoints: tuple[float, ...] = DEFAULT_INCOME_CHECKPOINTS,
    workers: int = 1,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> list[BuyBudgetVariantResult]:
    relaxed_spec = QuantileFitSpec(
        within_bin_points=spec.within_bin_points,
        quantile_grid_size=spec.quantile_grid_size,
        quantile_levels=spec.quantile_levels,
        ppd_mean_anchor_weight=spec.ppd_mean_anchor_weight,
        hard_p95_cap=1e12,
        exponent_max=1e12,
        p95_soft_cap=1e12,
        sigma_warning_low=spec.sigma_warning_low,
        sigma_warning_high=spec.sigma_warning_high,
        median_target_curve={},
        fixed_exponent=spec.fixed_exponent,
        quantile_huber_delta=spec.quantile_huber_delta,
        sigma_search_low=spec.sigma_search_low,
        sigma_search_high=spec.sigma_search_high,
    )
    baseline_weights = (ObjectiveWeights(w_fit=1.0, w_anchor=0.0, w_p95=0.0, w_sigma=0.0, w_curve=0.0, profile_id="baseline"),)

    return evaluate_variants(
        quarterly_csv=quarterly_csv,
        target_year_psd=target_year_psd,
        ppd_paths=ppd_paths,
        status_mode=status_mode,
        year_policy=year_policy,
        guardrail_mode=GUARDRAIL_MODE_WARN,
        spec=relaxed_spec,
        objective_weight_profiles=baseline_weights,
        tail_family=tail_family,
        pareto_alpha_values=pareto_alpha_values,
        income_open_upper_k=income_open_upper_k,
        property_open_upper_k=property_open_upper_k,
        income_checkpoints=income_checkpoints,
        workers=workers,
        progress_callback=progress_callback,
        enforce_hard_gates=False,
    )


def rank_variants(results: list[BuyBudgetVariantResult]) -> list[BuyBudgetVariantResult]:
    status_rank = {PPD_STATUS_A_ONLY: 0, PPD_STATUS_ALL: 1}
    year_rank = {YEAR_POLICY_2024_ONLY: 0, YEAR_POLICY_POOLED_2024_2025: 1, YEAR_POLICY_2025_ONLY: 2}
    return sorted(
        results,
        key=lambda item: (
            0 if item.guardrails.passed else 1,
            item.objective.objective_total,
            item.worst_year_fit_distance,
            status_rank.get(item.status_mode, 9),
            year_rank.get(item.year_policy, 9),
            item.variant_id,
        ),
    )


def select_production_variant(results: list[BuyBudgetVariantResult]) -> ProductionSelection:
    eligible = [item for item in results if item.guardrails.passed]
    rejected = [item for item in results if not item.guardrails.passed]
    if not eligible:
        raise ValueError("No eligible variants passed hard guardrails.")

    ordered = rank_variants(eligible)
    return ProductionSelection(selected=ordered[0], eligible=ordered, rejected=rejected)


def apply_fit_degradation(
    *,
    results: list[BuyBudgetVariantResult],
    baseline_best_fit: float,
) -> list[BuyBudgetVariantResult]:
    updated: list[BuyBudgetVariantResult] = []
    for item in results:
        degradation = (
            (item.worst_year_fit_distance - baseline_best_fit) / baseline_best_fit
            if baseline_best_fit > 0.0
            else 0.0
        )
        diag = dict(item.diagnostics)
        diag["fit_degradation_vs_baseline"] = degradation
        updated.append(
            BuyBudgetVariantResult(
                status_mode=item.status_mode,
                year_policy=item.year_policy,
                buy_scale=item.buy_scale,
                buy_exponent=item.buy_exponent,
                buy_mu=item.buy_mu,
                buy_sigma=item.buy_sigma,
                selected_alpha=item.selected_alpha,
                weight_profile_id=item.weight_profile_id,
                guardrail_mode=item.guardrail_mode,
                guardrails=item.guardrails,
                sigma_warning=item.sigma_warning,
                fit_years=item.fit_years,
                yearly_fit_distance=item.yearly_fit_distance,
                yearly_fit_mean_error=item.yearly_fit_mean_error,
                yearly_fit_std_error=item.yearly_fit_std_error,
                worst_year_fit_distance=item.worst_year_fit_distance,
                objective=item.objective,
                anchor=item.anchor,
                fit_degradation_vs_baseline=degradation,
                ppd_summary=item.ppd_summary,
                diagnostics=diag,
                income_quantiles=item.income_quantiles,
                observed_price_quantiles=item.observed_price_quantiles,
                modeled_median_quantiles=item.modeled_median_quantiles,
                model_log_price_series=item.model_log_price_series,
                tail_income_values=item.tail_income_values,
            )
        )
    return updated


def reference_budget_rows(
    *,
    buy_scale: float,
    buy_exponent: float,
    buy_mu: float,
    buy_sigma: float,
    income_checkpoints: tuple[float, ...] = DEFAULT_INCOME_CHECKPOINTS,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for income in income_checkpoints:
        key = int(income)
        median_multiple = (
            buy_scale
            * math.pow(income, buy_exponent)
            * math.exp(buy_mu)
            / income
        )
        p95_multiple = (
            buy_scale
            * math.pow(income, buy_exponent)
            * math.exp(buy_mu + P95_Z * buy_sigma)
            / income
        )
        out[f"median_x_income_{key}"] = median_multiple
        out[f"p95_x_income_{key}"] = p95_multiple
    return out


def _histogram(values: tuple[float, ...], bins: int) -> tuple[list[float], list[float]]:
    if not values:
        raise ValueError("Cannot histogram empty values.")
    lower = min(values)
    upper = max(values)
    if upper <= lower:
        upper = lower + 1e-6
    width = (upper - lower) / bins
    counts = [0.0] * bins
    for value in values:
        idx = int((value - lower) / width)
        if idx >= bins:
            idx = bins - 1
        if idx < 0:
            idx = 0
        counts[idx] += 1.0
    density = [count / (len(values) * width) for count in counts]
    centers = [lower + (idx + 0.5) * width for idx in range(bins)]
    return centers, density


def write_overlay_plots(
    *,
    result: BuyBudgetVariantResult,
    output_dir: Path,
    year_for_distribution: int = 2025,
    plot_pareto_ccdf: bool = False,
) -> list[Path]:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("matplotlib is required for --plot-overlays") from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    quantile_path = output_dir / f"{result.variant_id.replace('|', '_')}_income_budget_overlay.png"
    plt.figure(figsize=(10, 6))
    plt.plot(result.income_quantiles, result.observed_price_quantiles, label="PSD implied price quantiles", linewidth=2)
    plt.plot(result.income_quantiles, result.modeled_median_quantiles, label="Model median budget quantiles", linewidth=2)
    plt.xlabel("Annual gross income (GBP)")
    plt.ylabel("Price / budget (GBP)")
    plt.title(f"Income to Price/Budget Overlay ({result.variant_id})")
    plt.legend()
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(quantile_path, dpi=140)
    plt.close()
    created.append(quantile_path)

    year_item = result.ppd_summary.year_moments.get(year_for_distribution)
    if year_item is not None and year_item.sample_log_prices:
        dist_path = output_dir / f"{result.variant_id.replace('|', '_')}_price_distribution_overlay.png"
        actual_centers, actual_density = _histogram(year_item.sample_log_prices, bins=50)
        model_centers, model_density = _histogram(result.model_log_price_series, bins=50)

        plt.figure(figsize=(10, 6))
        plt.plot(actual_centers, actual_density, label=f"PPD {year_for_distribution} log-price density", linewidth=2)
        plt.plot(model_centers, model_density, label="Model generated log-price density", linewidth=2)
        plt.xlabel("log(price)")
        plt.ylabel("Density")
        plt.title(f"Price Distribution Overlay ({result.variant_id})")
        plt.legend()
        plt.grid(alpha=0.25)
        plt.tight_layout()
        plt.savefig(dist_path, dpi=140)
        plt.close()
        created.append(dist_path)

    if plot_pareto_ccdf and result.tail_income_values:
        tail_sorted = sorted(result.tail_income_values)
        n = len(tail_sorted)
        x_min = max(min(tail_sorted), 1e-9)
        empirical_ccdf = [(n - idx) / n for idx in range(1, n + 1)]
        theoretical_ccdf = [math.pow(x_min / max(value, x_min), result.selected_alpha) for value in tail_sorted]

        ccdf_path = output_dir / f"{result.variant_id.replace('|', '_')}_pareto_ccdf_overlay.png"
        plt.figure(figsize=(10, 6))
        plt.plot(tail_sorted, empirical_ccdf, label="Synthetic tail empirical CCDF", linewidth=2)
        plt.plot(tail_sorted, theoretical_ccdf, label=f"Pareto(alpha={result.selected_alpha:g}) CCDF", linewidth=2)
        plt.xscale("log")
        plt.yscale("log")
        plt.xlabel("Income (GBP, tail)")
        plt.ylabel("CCDF")
        plt.title(f"Pareto Tail CCDF Overlay ({result.variant_id})")
        plt.legend()
        plt.grid(alpha=0.25)
        plt.tight_layout()
        plt.savefig(ccdf_path, dpi=140)
        plt.close()
        created.append(ccdf_path)

    return created


__all__ = [
    "AnchorDiagnostics",
    "BuyBudgetVariantResult",
    "DEFAULT_INCOME_CHECKPOINTS",
    "DEFAULT_MEDIAN_TARGET_CURVE",
    "DEFAULT_PARETO_ALPHA_GRID",
    "EXPONENT_MAX_DEFAULT",
    "GUARDRAIL_MODE_CHOICES",
    "GUARDRAIL_MODE_FAIL",
    "GUARDRAIL_MODE_WARN",
    "HARD_P95_MULTIPLE_CAP",
    "ObjectiveComponents",
    "ObjectiveWeights",
    "PPD_STATUS_A_ONLY",
    "PPD_STATUS_ALL",
    "PPD_STATUS_BOTH",
    "PPD_STATUS_CHOICES",
    "P95_SOFT_CAP_DEFAULT",
    "PpdSummary",
    "ProductionSelection",
    "QuantileFitSpec",
    "RakedPpdTarget",
    "SIGMA_WARNING_HIGH",
    "SIGMA_WARNING_LOW",
    "SoftTargetCurve",
    "TAIL_FAMILY_CHOICES",
    "TAIL_FAMILY_PARETO",
    "TailSpec",
    "YEAR_POLICY_2024_ONLY",
    "YEAR_POLICY_2025_ONLY",
    "YEAR_POLICY_BOTH",
    "YEAR_POLICY_CHOICES",
    "YEAR_POLICY_POOLED_2024_2025",
    "apply_fit_degradation",
    "build_objective_weight_profiles",
    "budget_median_multiple",
    "budget_p95_multiple",
    "evaluate_baseline_best_fit",
    "evaluate_guardrails",
    "evaluate_variants",
    "rank_variants",
    "reference_budget_rows",
    "select_production_variant",
    "write_overlay_plots",
]
