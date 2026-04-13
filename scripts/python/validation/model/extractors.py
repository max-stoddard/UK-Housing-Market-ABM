"""Metric extractors for the 2024 validation framework.

@author: Max Stoddard
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from scripts.python.helpers.common.abm_policy_sweep import load_core_indicator_values, select_post_burn_in_window
from scripts.python.helpers.was.constants import (
    WAS_BTL_HOUSES_TOTAL_VALUE,
    WAS_CASH_ISA_VALUE,
    WAS_CHILD_OTHER_SAVINGS_VALUE,
    WAS_CHILD_TRUST_FUND_VALUE,
    WAS_CURRENT_ACCOUNT_CREDIT_VALUE,
    WAS_FORMAL_FINANCIAL_ASSETS,
    WAS_GROSS_ANNUAL_INCOME,
    WAS_GROSS_ANNUAL_RENTAL_INCOME,
    WAS_MAIN_RESIDENCE_VALUE,
    WAS_NATIONAL_SAVINGS_VALUE,
    WAS_NET_ANNUAL_INCOME,
    WAS_NET_ANNUAL_RENTAL_INCOME,
    WAS_OTHER_HOUSES_TOTAL_VALUE,
    WAS_PROPERTY_VALUE_SUM,
    WAS_SAVINGS_ACCOUNTS_VALUE,
    WAS_TOTAL_PROPERTY_WEALTH,
    WAS_WEIGHT,
)
from scripts.python.helpers.was.derived_columns import (
    GROSS_NON_RENT_INCOME,
    LIQ_FINANCIAL_WEALTH,
    derive_gross_housing_wealth_column,
    derive_liquid_financial_wealth_column,
    derive_non_rent_income_columns,
)
from scripts.python.helpers.was.io import read_results, read_was_data
from scripts.python.helpers.was.row_filters import filter_percentile_outliers, filter_positive_values
from scripts.python.validation.model.schema import VALIDATION_WINDOW_END, VALIDATION_WINDOW_START


@dataclass(frozen=True)
class HouseholdDistributionSpec:
    """Locked extraction settings for one household realism metric."""

    results_file_name: str
    use_columns: tuple[str, ...]
    variable_name: str
    bin_edges: tuple[float, ...]
    requires_income_floor: bool = False
    income_floor: float = 1_000.0


HOUSEHOLD_DISTRIBUTION_SPECS: dict[str, HouseholdDistributionSpec] = {
    "income_distribution_jsd": HouseholdDistributionSpec(
        results_file_name="MonthlyGrossEmploymentIncome-run1.csv",
        use_columns=(
            WAS_WEIGHT,
            WAS_GROSS_ANNUAL_INCOME,
            WAS_NET_ANNUAL_INCOME,
            WAS_GROSS_ANNUAL_RENTAL_INCOME,
            WAS_NET_ANNUAL_RENTAL_INCOME,
        ),
        variable_name=GROSS_NON_RENT_INCOME,
        bin_edges=tuple(np.logspace(math.log(1_000.0), 12.25, int(12.25 - math.log(1_000.0)) * 4 + 2, base=math.e)),
        requires_income_floor=True,
        income_floor=1_000.0,
    ),
    "housing_wealth_distribution_jsd": HouseholdDistributionSpec(
        results_file_name="HousingWealth-run1.csv",
        use_columns=(
            WAS_WEIGHT,
            WAS_TOTAL_PROPERTY_WEALTH,
            WAS_PROPERTY_VALUE_SUM,
            WAS_MAIN_RESIDENCE_VALUE,
            WAS_OTHER_HOUSES_TOTAL_VALUE,
            WAS_BTL_HOUSES_TOTAL_VALUE,
        ),
        variable_name=WAS_TOTAL_PROPERTY_WEALTH,
        bin_edges=tuple(np.logspace(6.0, 16.0, int(16.0 - 6.0) * 4 + 1, base=math.e)),
    ),
    "financial_wealth_distribution_jsd": HouseholdDistributionSpec(
        results_file_name="BankBalance-run1.csv",
        use_columns=(
            WAS_WEIGHT,
            WAS_NATIONAL_SAVINGS_VALUE,
            WAS_CHILD_TRUST_FUND_VALUE,
            WAS_CHILD_OTHER_SAVINGS_VALUE,
            WAS_SAVINGS_ACCOUNTS_VALUE,
            WAS_CASH_ISA_VALUE,
            WAS_CURRENT_ACCOUNT_CREDIT_VALUE,
            WAS_FORMAL_FINANCIAL_ASSETS,
        ),
        variable_name=LIQ_FINANCIAL_WEALTH,
        bin_edges=tuple(np.logspace(0.0, 20.0, int(20.0 - 0.0) * 4 + 1, base=math.e)),
    ),
}


def extract_core_indicator_mean(csv_path: Path, *, scale: float = 1.0) -> float:
    """Read a core-indicator series and return its fixed validation-window mean."""

    values = load_core_indicator_values(csv_path)
    window = select_post_burn_in_window(
        values,
        start_index=VALIDATION_WINDOW_START,
        end_index=VALIDATION_WINDOW_END,
    )
    expected_count = VALIDATION_WINDOW_END - VALIDATION_WINDOW_START
    if len(window) != expected_count:
        raise RuntimeError(f"Incomplete validation window in {csv_path}")
    return statistics.fmean(window) * scale


def extract_household_jsd(
    *,
    model_values: Sequence[float],
    target_values: Sequence[float],
    target_weights: Sequence[float],
    bin_edges: Sequence[float],
) -> float:
    """Compute Jensen-Shannon distance between normalized model and target histograms."""

    if len(bin_edges) < 2:
        raise ValueError("Household JSD requires at least two bin edges")
    if len(target_values) != len(target_weights):
        raise ValueError("Target values and weights must have the same length")
    model_hist = build_normalized_histogram(values=model_values, bin_edges=bin_edges)
    target_hist = build_normalized_histogram(values=target_values, bin_edges=bin_edges, weights=target_weights)
    midpoint = 0.5 * (model_hist + target_hist)
    return math.sqrt(0.5 * (_kl_divergence(model_hist, midpoint) + _kl_divergence(target_hist, midpoint)))


def build_normalized_histogram(
    *,
    values: Sequence[float],
    bin_edges: Sequence[float],
    weights: Sequence[float] | None = None,
) -> np.ndarray:
    """Build a histogram normalized to unit mass."""

    histogram = np.histogram(values, bins=bin_edges, density=False, weights=weights)[0].astype(float)
    total_mass = float(histogram.sum())
    if total_mass <= 0.0:
        raise RuntimeError("Cannot normalize an empty histogram")
    return histogram / total_mass


def extract_household_metric_from_results(*, metric_id: str, results_dir: Path, was_data_root: str | Path) -> float:
    """Extract a household JSD metric from one run output directory."""

    spec = HOUSEHOLD_DISTRIBUTION_SPECS[metric_id]
    model_values = _load_model_distribution_values(results_dir / spec.results_file_name, spec)
    target_values, target_weights = _load_target_distribution_values(spec=spec, was_data_root=Path(was_data_root))
    return extract_household_jsd(
        model_values=model_values,
        target_values=target_values,
        target_weights=target_weights,
        bin_edges=spec.bin_edges,
    )


def _load_model_distribution_values(results_path: Path, spec: HouseholdDistributionSpec) -> list[float]:
    if not results_path.exists():
        raise RuntimeError(f"Missing required validation results file: {results_path}")
    raw_values = read_results(str(results_path), VALIDATION_WINDOW_START, VALIDATION_WINDOW_END)
    if spec.results_file_name == "MonthlyGrossEmploymentIncome-run1.csv":
        scaled_values = [12.0 * value for value in raw_values if value > 0.0]
        return [value for value in scaled_values if value >= spec.income_floor]
    return [value for value in raw_values if value > 0.0]


def _load_target_distribution_values(
    *,
    spec: HouseholdDistributionSpec,
    was_data_root: Path,
) -> tuple[list[float], list[float]]:
    chunk = read_was_data(str(was_data_root), list(spec.use_columns))

    if spec.variable_name == GROSS_NON_RENT_INCOME:
        derive_non_rent_income_columns(chunk)
        chunk = filter_percentile_outliers(
            chunk,
            lower_bound_column=WAS_NET_ANNUAL_INCOME,
            upper_bound_column=WAS_GROSS_ANNUAL_INCOME,
        )
    elif spec.variable_name == LIQ_FINANCIAL_WEALTH:
        derive_liquid_financial_wealth_column(chunk)
    elif spec.variable_name == WAS_TOTAL_PROPERTY_WEALTH:
        derive_gross_housing_wealth_column(chunk)

    filtered = filter_positive_values(chunk, [spec.variable_name])
    if spec.requires_income_floor:
        filtered = filtered[filtered[spec.variable_name] >= spec.income_floor]
    if filtered.empty:
        raise RuntimeError(f"No WAS observations remain after filtering for {spec.variable_name}")

    return (
        filtered[spec.variable_name].astype(float).tolist(),
        filtered[WAS_WEIGHT].astype(float).tolist(),
    )


def _kl_divergence(left: np.ndarray, right: np.ndarray) -> float:
    total = 0.0
    for left_value, right_value in zip(left, right, strict=True):
        if left_value <= 0.0:
            continue
        if right_value <= 0.0:
            raise RuntimeError("JSD midpoint contains zero mass where input histogram is positive")
        total += left_value * math.log(left_value / right_value)
    return total
