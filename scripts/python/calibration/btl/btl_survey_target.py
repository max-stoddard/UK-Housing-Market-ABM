#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute survey-side BTL/rental-income prevalence targets.

By default this script uses ``--weight-mode weighted``. To reproduce the legacy
WAS Wave 3 target in old config comments, run with ``--weight-mode unweighted``;
that path should reproduce ``0.0752617`` after rounding. The value ``1.76`` is a
model-side multiplier, not a survey share, so the script reports
``multiplier * table_mean`` separately from the survey target.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from scripts.python.calibration.frs.age_dist import (
    DEFAULT_HOUSEHOLD_CSV as DEFAULT_FRS_HOUSEHOLD_CSV,
    MISSING_CODE_MAX,
    MISSING_CODE_MIN,
    WEIGHT_COLUMN as FRS_WEIGHT_COLUMN,
)
from scripts.python.calibration.frs.income_age_joint_dist import (
    ANNUAL_INCOME_COLUMN,
    ANNUALISATION_FACTOR,
    DEFAULT_DICTIONARY_TXT as DEFAULT_FRS_DICTIONARY_TXT,
    DERIVED_RENTAL_INCOME_COLUMN,
    GROSS_NON_RENT_INCOME_COLUMN,
    INCOME_COLUMN as FRS_INCOME_COLUMN,
    RENTAL_INCOME_COLUMN as FRS_RENTAL_INCOME_COLUMN,
    SUBLET_COLUMN as FRS_SUBLET_COLUMN,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import repo_root
from scripts.python.helpers.was import config as was_config
from scripts.python.helpers.was import derived_columns as was_derived
from scripts.python.helpers.was.dataset import reload_was_modules
from scripts.python.helpers.was.row_filters import filter_percentile_outliers


DATASET_W3 = was_config.WAVE_3_DATA
DATASET_R8 = was_config.ROUND_8_DATA
DATASET_FRS_2023_24 = "FRS_2023_24"
DATASET_CHOICES = (DATASET_W3, DATASET_R8, DATASET_FRS_2023_24)
DEFAULT_DATASETS = ",".join(DATASET_CHOICES)

WEIGHT_MODE_WEIGHTED = "weighted"
WEIGHT_MODE_UNWEIGHTED = "unweighted"
WEIGHT_MODE_CHOICES = (WEIGHT_MODE_WEIGHTED, WEIGHT_MODE_UNWEIGHTED)

DEFAULT_MULTIPLIER = 1.76
DEFAULT_EQUIVALENCE_TOLERANCE = 1.0e-9
DEFAULT_PERCENTILE_BIN_COUNT = 100
INCOME_TRIM_PERCENTILE = 0.01

SURVEY_INCOME_COLUMN = "survey_income"
SURVEY_WEIGHT_COLUMN = "survey_weight"
SURVEY_INDICATOR_COLUMN = "survey_btl_proxy"


@dataclass(frozen=True)
class FrsDictionaryContract:
    variable: str
    label: str
    measurement_level: str


@dataclass(frozen=True)
class PreparedSurveyData:
    dataset: str
    source_path: str
    proxy_label: str
    proxy_note: str
    frame: pd.DataFrame
    diagnostics: dict[str, object]
    columns: dict[str, str]
    notes: list[str]


FRS_DICTIONARY_CONTRACTS: tuple[FrsDictionaryContract, ...] = (
    FrsDictionaryContract(FRS_WEIGHT_COLUMN, "Grossing variable", "SCALE"),
    FrsDictionaryContract(FRS_INCOME_COLUMN, "HH - Total Household income", "SCALE"),
    FrsDictionaryContract(FRS_SUBLET_COLUMN, "Whether have formal sublet arrangement", "NOMINAL"),
    FrsDictionaryContract(FRS_RENTAL_INCOME_COLUMN, "Amount of rent from subletting", "SCALE"),
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute BTL/rental-income survey targets for WAS and FRS.",
    )
    parser.add_argument(
        "--datasets",
        default=DEFAULT_DATASETS,
        help=f"Comma-separated datasets to compute (default: {DEFAULT_DATASETS}).",
    )
    parser.add_argument(
        "--weight-mode",
        default=WEIGHT_MODE_WEIGHTED,
        choices=WEIGHT_MODE_CHOICES,
        help="Primary target weighting mode (default: weighted).",
    )
    parser.add_argument(
        "--multiplier",
        type=float,
        default=DEFAULT_MULTIPLIER,
        help=f"BTL_PROBABILITY_MULTIPLIER value to report against table means (default: {DEFAULT_MULTIPLIER}).",
    )
    parser.add_argument(
        "--frs-household-csv",
        default=None,
        help="Optional FRS household CSV. Defaults to private-datasets/frs/23-24/househol.csv.",
    )
    parser.add_argument(
        "--frs-dictionary-txt",
        default=None,
        help="Optional FRS household dictionary. Defaults to private-datasets/frs/23-24/household_data_dictionary.txt.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional JSON output path for the full summary.",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        help="Optional CSV output path for one-row-per-dataset summary values.",
    )
    parser.add_argument(
        "--equivalence-tolerance",
        type=float,
        default=DEFAULT_EQUIVALENCE_TOLERANCE,
        help=f"Tolerance for direct-share/table-mean equivalence checks (default: {DEFAULT_EQUIVALENCE_TOLERANCE}).",
    )
    return parser


def parse_datasets(value: str) -> list[str]:
    datasets = [item.strip() for item in value.split(",") if item.strip()]
    if not datasets:
        raise ValueError("At least one dataset must be requested.")
    invalid = [item for item in datasets if item not in DATASET_CHOICES]
    if invalid:
        raise ValueError(
            f"Unsupported dataset(s): {', '.join(invalid)}. "
            f"Valid choices: {', '.join(DATASET_CHOICES)}"
        )
    return datasets


def _resolve_repo_path(path: str | Path | None, default_path: str | Path) -> Path:
    candidate = Path(path).expanduser() if path is not None else Path(default_path)
    resolved = candidate if candidate.is_absolute() else repo_root() / candidate
    if not resolved.exists():
        raise FileNotFoundError(f"Missing required path: {resolved}")
    return resolved.resolve()


def _finite_mask(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return pd.Series(np.isfinite(values.to_numpy(dtype=float)), index=series.index)


def weighted_share(indicators: pd.Series | np.ndarray, weights: pd.Series | np.ndarray) -> float:
    indicator_values = np.asarray(indicators, dtype=float)
    weight_values = np.asarray(weights, dtype=float)
    valid = np.isfinite(indicator_values) & np.isfinite(weight_values) & (weight_values > 0.0)
    if not np.any(valid):
        raise ValueError("No positive-weight observations for weighted share.")
    total_weight = float(weight_values[valid].sum())
    return float((indicator_values[valid] * weight_values[valid]).sum() / total_weight)


def compute_equal_mass_percentile_table(
    income_values: pd.Series | np.ndarray,
    indicators: pd.Series | np.ndarray,
    weights: pd.Series | np.ndarray,
    *,
    n_bins: int = DEFAULT_PERCENTILE_BIN_COUNT,
) -> dict[str, object]:
    if n_bins <= 0:
        raise ValueError("n_bins must be positive.")

    frame = pd.DataFrame(
        {
            "income": pd.to_numeric(pd.Series(income_values), errors="coerce"),
            "indicator": pd.to_numeric(pd.Series(indicators), errors="coerce"),
            "weight": pd.to_numeric(pd.Series(weights), errors="coerce"),
        }
    )
    valid = (
        _finite_mask(frame["income"])
        & _finite_mask(frame["indicator"])
        & _finite_mask(frame["weight"])
        & (frame["weight"] > 0.0)
    )
    frame = frame.loc[valid].sort_values("income", kind="mergesort")
    if frame.empty:
        raise ValueError("No valid observations for percentile table.")

    total_weight = float(frame["weight"].sum())
    if total_weight <= 0.0:
        raise ValueError("Total table weight must be positive.")

    target_bin_weight = total_weight / n_bins
    bin_weights = np.zeros(n_bins, dtype=float)
    bin_indicator_weights = np.zeros(n_bins, dtype=float)
    current_bin = 0
    remaining_capacity = target_bin_weight
    tolerance = max(total_weight, 1.0) * 1.0e-12

    for row in frame.itertuples(index=False):
        remaining_row_weight = float(row.weight)
        indicator = float(row.indicator)
        while remaining_row_weight > tolerance and current_bin < n_bins:
            take = min(remaining_row_weight, remaining_capacity)
            bin_weights[current_bin] += take
            bin_indicator_weights[current_bin] += take * indicator
            remaining_row_weight -= take
            remaining_capacity -= take
            if remaining_capacity <= tolerance:
                current_bin += 1
                remaining_capacity = target_bin_weight

    probabilities = np.divide(
        bin_indicator_weights,
        bin_weights,
        out=np.full(n_bins, np.nan, dtype=float),
        where=bin_weights > 0.0,
    )
    if np.isnan(probabilities).any():
        raise ValueError("Equal-mass table produced empty bins.")

    table_mean = float(probabilities.mean())
    direct_share = weighted_share(frame["indicator"], frame["weight"])
    return {
        "mean": table_mean,
        "directShare": direct_share,
        "equivalenceGap": float(abs(table_mean - direct_share)),
        "min": float(probabilities.min()),
        "max": float(probabilities.max()),
        "binCount": n_bins,
    }


def compute_legacy_weak_percentile_table(
    income_values: pd.Series | np.ndarray,
    indicators: pd.Series | np.ndarray,
    *,
    n_bins: int = DEFAULT_PERCENTILE_BIN_COUNT,
) -> dict[str, object]:
    if n_bins <= 0:
        raise ValueError("n_bins must be positive.")
    frame = pd.DataFrame(
        {
            "income": pd.to_numeric(pd.Series(income_values), errors="coerce"),
            "indicator": pd.to_numeric(pd.Series(indicators), errors="coerce"),
        }
    )
    valid = _finite_mask(frame["income"]) & _finite_mask(frame["indicator"])
    frame = frame.loc[valid]
    if frame.empty:
        raise ValueError("No valid observations for legacy weak-percentile table.")

    weak_percentiles = frame["income"].rank(method="max", pct=True) * 100.0
    bin_width = 100.0 / n_bins
    probabilities: list[float] = []
    empty_bins = 0
    for bin_index in range(n_bins):
        lower = bin_index * bin_width
        upper = (bin_index + 1) * bin_width
        mask = (lower < weak_percentiles) & (weak_percentiles <= upper)
        if not mask.any():
            probabilities.append(float("nan"))
            empty_bins += 1
        else:
            probabilities.append(float(frame.loc[mask, "indicator"].mean()))

    non_empty = [value for value in probabilities if math.isfinite(value)]
    if not non_empty:
        raise ValueError("Legacy weak-percentile table has no populated bins.")
    return {
        "mean": float(sum(non_empty) / len(non_empty)),
        "min": float(min(non_empty)),
        "max": float(max(non_empty)),
        "binCount": n_bins,
        "emptyBinCount": empty_bins,
    }


def read_btl_probability_table_mean(path: str | Path) -> float:
    values: list[float] = []
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, skipinitialspace=True)
        for row in reader:
            if not row or row[0].startswith("#"):
                continue
            if len(row) < 3:
                raise ValueError(f"Malformed BTL probability row in {path}: {row}")
            values.append(float(row[2]))
    if not values:
        raise ValueError(f"No BTL probability rows found in {path}")
    return float(sum(values) / len(values))


def _checked_in_table_path(dataset: str) -> Path | None:
    if dataset == DATASET_W3:
        return repo_root() / "input-data-versions" / "v0" / "BTLProbabilityPerIncomePercentileBin.csv"
    if dataset == DATASET_R8:
        return repo_root() / "src" / "main" / "resources" / "BTLProbabilityPerIncomePercentileBin-R8.csv"
    return None


def prepare_was_survey_data(dataset: str) -> PreparedSurveyData:
    config, constants, io_module, derived = reload_was_modules(
        dataset,
        extra_modules=(was_derived,),
    )
    use_columns = [
        constants.WAS_WEIGHT,
        constants.WAS_GROSS_ANNUAL_INCOME,
        constants.WAS_NET_ANNUAL_INCOME,
        constants.WAS_GROSS_ANNUAL_RENTAL_INCOME,
        constants.WAS_NET_ANNUAL_RENTAL_INCOME,
    ]
    raw = io_module.read_was_data(config.WAS_DATA_ROOT, use_columns)
    before_rows = int(len(raw))
    derived.derive_non_rent_income_columns(raw)
    trimmed = filter_percentile_outliers(
        raw,
        lower_bound_column=derived.GROSS_NON_RENT_INCOME,
        upper_bound_column=derived.GROSS_NON_RENT_INCOME,
        percentile=INCOME_TRIM_PERCENTILE,
    ).copy()
    trimmed[SURVEY_INCOME_COLUMN] = pd.to_numeric(
        trimmed[derived.GROSS_NON_RENT_INCOME],
        errors="coerce",
    )
    trimmed[SURVEY_WEIGHT_COLUMN] = pd.to_numeric(
        trimmed[constants.WAS_WEIGHT],
        errors="coerce",
    )
    trimmed[SURVEY_INDICATOR_COLUMN] = (
        pd.to_numeric(
            trimmed[constants.WAS_GROSS_ANNUAL_RENTAL_INCOME],
            errors="coerce",
        )
        > 0.0
    ).astype(float)
    valid = (
        _finite_mask(trimmed[SURVEY_INCOME_COLUMN])
        & _finite_mask(trimmed[SURVEY_WEIGHT_COLUMN])
        & (trimmed[SURVEY_WEIGHT_COLUMN] > 0.0)
    )
    prepared = trimmed.loc[
        valid,
        [SURVEY_INCOME_COLUMN, SURVEY_WEIGHT_COLUMN, SURVEY_INDICATOR_COLUMN],
    ].copy()
    source_path = _resolve_repo_path(None, Path(config.WAS_DATA_ROOT) / config.WAS_DATA_FILENAME)
    return PreparedSurveyData(
        dataset=dataset,
        source_path=str(source_path),
        proxy_label="positive_gross_rental_income",
        proxy_note="Household has positive WAS gross annual rental income.",
        frame=prepared,
        diagnostics={
            "rawRows": before_rows,
            "trimmedRows": int(len(trimmed)),
            "validRows": int(len(prepared)),
            "droppedRowsAfterTrimForInvalidWeightOrIncome": int(len(trimmed) - len(prepared)),
            "trimPercentile": INCOME_TRIM_PERCENTILE,
        },
        columns={
            "weight": constants.WAS_WEIGHT,
            "grossTotalIncome": constants.WAS_GROSS_ANNUAL_INCOME,
            "grossRentalIncome": constants.WAS_GROSS_ANNUAL_RENTAL_INCOME,
            "grossNonRentIncome": derived.GROSS_NON_RENT_INCOME,
        },
        notes=[],
    )


def validate_frs_dictionary_contracts(dictionary_txt: str | Path) -> list[dict[str, object]]:
    text = Path(dictionary_txt).read_text(encoding="utf-8", errors="replace")
    validated: list[dict[str, object]] = []
    for contract in FRS_DICTIONARY_CONTRACTS:
        entry = _extract_dictionary_entry(text, contract.variable)
        label = _extract_entry_label(entry)
        measurement_level = _extract_measurement_level(entry)
        is_numeric = "This variable is  numeric" in entry or "This variable is numeric" in entry
        missing_values = "SPSS user missing values = -9.0 thru -1.0" in entry
        if label != contract.label:
            raise ValueError(
                f"Dictionary label mismatch for {contract.variable}: "
                f"expected {contract.label!r}, got {label!r}"
            )
        if measurement_level != contract.measurement_level:
            raise ValueError(
                f"Dictionary measurement mismatch for {contract.variable}: "
                f"expected {contract.measurement_level!r}, got {measurement_level!r}"
            )
        if not is_numeric:
            raise ValueError(f"Dictionary variable {contract.variable} is not marked numeric.")
        if not missing_values:
            raise ValueError(
                f"Dictionary variable {contract.variable} does not declare -9.0 thru -1.0 missing values."
            )
        validated.append(
            {
                "variable": contract.variable,
                "label": label,
                "measurementLevel": measurement_level,
                "numeric": is_numeric,
                "missingValuesMinus9ToMinus1": missing_values,
            }
        )
    return validated


def _extract_dictionary_entry(text: str, variable: str) -> str:
    pattern = re.compile(
        rf"Pos\. = \d+\s+Variable = {re.escape(variable)}\s+Variable label = .+?"
        rf"(?=\nPos\. = \d+\s+Variable = |\Z)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise ValueError(f"Dictionary variable {variable!r} not found.")
    return match.group(0)


def _extract_entry_label(entry: str) -> str:
    match = re.search(r"Variable label = (?P<label>.+)", entry)
    if not match:
        raise ValueError("Dictionary entry missing variable label.")
    return match.group("label").strip()


def _extract_measurement_level(entry: str) -> str:
    match = re.search(r"SPSS measurement level is (?P<level>[A-Z]+)", entry)
    if not match:
        raise ValueError("Dictionary entry missing SPSS measurement level.")
    return match.group("level").strip()


def load_frs_btl_data(household_csv: str | Path) -> pd.DataFrame:
    return pd.read_csv(
        household_csv,
        usecols=[
            FRS_WEIGHT_COLUMN,
            FRS_INCOME_COLUMN,
            FRS_SUBLET_COLUMN,
            FRS_RENTAL_INCOME_COLUMN,
        ],
    )


def prepare_frs_btl_target_rows(
    raw_data: pd.DataFrame,
    *,
    trim_percentile: float = INCOME_TRIM_PERCENTILE,
) -> tuple[pd.DataFrame, dict[str, object]]:
    required_columns = [
        FRS_WEIGHT_COLUMN,
        FRS_INCOME_COLUMN,
        FRS_SUBLET_COLUMN,
        FRS_RENTAL_INCOME_COLUMN,
    ]
    missing_columns = [column for column in required_columns if column not in raw_data.columns]
    if missing_columns:
        raise ValueError(f"FRS household data missing required columns: {missing_columns}")

    prepared = raw_data.copy()
    for column in required_columns:
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce")

    weight_valid = _finite_mask(prepared[FRS_WEIGHT_COLUMN]) & (prepared[FRS_WEIGHT_COLUMN] > 0.0)
    income_valid = (
        _finite_mask(prepared[FRS_INCOME_COLUMN])
        & ~prepared[FRS_INCOME_COLUMN].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
    )
    sublet_valid = (
        _finite_mask(prepared[FRS_SUBLET_COLUMN])
        & ~prepared[FRS_SUBLET_COLUMN].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
        & prepared[FRS_SUBLET_COLUMN].isin([1.0, 2.0])
    )
    rental_valid_for_subletters = (
        _finite_mask(prepared[FRS_RENTAL_INCOME_COLUMN])
        & ~prepared[FRS_RENTAL_INCOME_COLUMN].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
        & (prepared[FRS_RENTAL_INCOME_COLUMN] >= 0.0)
    )
    subletter = prepared[FRS_SUBLET_COLUMN] == 1.0
    non_subletter = prepared[FRS_SUBLET_COLUMN] == 2.0

    prepared[DERIVED_RENTAL_INCOME_COLUMN] = np.nan
    prepared.loc[non_subletter & sublet_valid, DERIVED_RENTAL_INCOME_COLUMN] = 0.0
    prepared.loc[
        subletter & sublet_valid & rental_valid_for_subletters,
        DERIVED_RENTAL_INCOME_COLUMN,
    ] = prepared.loc[
        subletter & sublet_valid & rental_valid_for_subletters,
        FRS_RENTAL_INCOME_COLUMN,
    ]

    rental_for_derivation_valid = _finite_mask(prepared[DERIVED_RENTAL_INCOME_COLUMN])
    prepared[GROSS_NON_RENT_INCOME_COLUMN] = (
        prepared[FRS_INCOME_COLUMN] - prepared[DERIVED_RENTAL_INCOME_COLUMN]
    )
    derived_income_valid = (
        _finite_mask(prepared[GROSS_NON_RENT_INCOME_COLUMN])
        & (prepared[GROSS_NON_RENT_INCOME_COLUMN] > 0.0)
    )
    valid = (
        weight_valid
        & income_valid
        & sublet_valid
        & rental_for_derivation_valid
        & derived_income_valid
    )
    positive_valid = prepared.loc[valid].copy()
    positive_valid[ANNUAL_INCOME_COLUMN] = (
        positive_valid[GROSS_NON_RENT_INCOME_COLUMN] * ANNUALISATION_FACTOR
    )
    trimmed = filter_percentile_outliers(
        positive_valid,
        lower_bound_column=ANNUAL_INCOME_COLUMN,
        upper_bound_column=ANNUAL_INCOME_COLUMN,
        percentile=trim_percentile,
    ).copy()
    trimmed[SURVEY_INCOME_COLUMN] = trimmed[ANNUAL_INCOME_COLUMN]
    trimmed[SURVEY_WEIGHT_COLUMN] = trimmed[FRS_WEIGHT_COLUMN]
    trimmed[SURVEY_INDICATOR_COLUMN] = (
        (trimmed[FRS_SUBLET_COLUMN] == 1.0)
        & (trimmed[DERIVED_RENTAL_INCOME_COLUMN] > 0.0)
    ).astype(float)

    diagnostics = {
        "rawRows": int(len(raw_data)),
        "positiveIncomeRows": int(len(positive_valid)),
        "trimmedRows": int(len(trimmed)),
        "droppedRows": int(len(raw_data) - len(trimmed)),
        "trimPercentile": trim_percentile,
        "subletterRowsBeforeTrim": int((subletter & sublet_valid & rental_valid_for_subletters).sum()),
        "nonSubletterRowsBeforeTrim": int((non_subletter & sublet_valid).sum()),
        "subletterPositiveRentRowsAfterTrim": int((trimmed[SURVEY_INDICATOR_COLUMN] > 0.0).sum()),
        "invalidSubletRows": int((~sublet_valid).sum()),
        "invalidSubletterRentalIncomeRows": int((subletter & sublet_valid & ~rental_valid_for_subletters).sum()),
        "nonPositiveDerivedIncomeRows": int(
            (
                weight_valid
                & income_valid
                & sublet_valid
                & rental_for_derivation_valid
                & ~derived_income_valid
            ).sum()
        ),
        "nonPositiveOrInvalidWeightRows": int((~weight_valid).sum()),
    }
    if trimmed.empty:
        raise ValueError("No valid FRS BTL target rows after filtering.")
    return trimmed[
        [SURVEY_INCOME_COLUMN, SURVEY_WEIGHT_COLUMN, SURVEY_INDICATOR_COLUMN]
    ].copy(), diagnostics


def prepare_frs_survey_data(
    *,
    household_csv: str | Path | None = None,
    dictionary_txt: str | Path | None = None,
) -> PreparedSurveyData:
    resolved_household_csv = _resolve_repo_path(household_csv, DEFAULT_FRS_HOUSEHOLD_CSV)
    resolved_dictionary_txt = _resolve_repo_path(dictionary_txt, DEFAULT_FRS_DICTIONARY_TXT)
    dictionary_contracts = validate_frs_dictionary_contracts(resolved_dictionary_txt)
    raw = load_frs_btl_data(resolved_household_csv)
    prepared, diagnostics = prepare_frs_btl_target_rows(raw)
    diagnostics["dictionaryContracts"] = dictionary_contracts
    return PreparedSurveyData(
        dataset=DATASET_FRS_2023_24,
        source_path=str(resolved_household_csv),
        proxy_label="positive_formal_sublet_rent",
        proxy_note=(
            "Closest FRS household-file proxy: SUBLET == 1 and SUBRENT > 0. "
            "This is narrower than the WAS positive gross rental income proxy."
        ),
        frame=prepared,
        diagnostics=diagnostics,
        columns={
            "weight": FRS_WEIGHT_COLUMN,
            "totalIncome": FRS_INCOME_COLUMN,
            "subletIndicator": FRS_SUBLET_COLUMN,
            "rentalIncome": FRS_RENTAL_INCOME_COLUMN,
            "grossNonRentIncomeAnnual": ANNUAL_INCOME_COLUMN,
        },
        notes=[
            "FRS household file has a formal-subletting rent proxy, not the same gross rental income field used in WAS.",
            "hhrent is gross rent paid by the household and is intentionally not used as landlord rental income.",
        ],
    )


def build_survey_result(
    prepared: PreparedSurveyData,
    *,
    weight_mode: str,
    multiplier: float,
    equivalence_tolerance: float,
) -> dict[str, object]:
    frame = prepared.frame
    selected_weights = (
        frame[SURVEY_WEIGHT_COLUMN]
        if weight_mode == WEIGHT_MODE_WEIGHTED
        else pd.Series(np.ones(len(frame)), index=frame.index)
    )
    selected_direct = weighted_share(frame[SURVEY_INDICATOR_COLUMN], selected_weights)
    selected_table = compute_equal_mass_percentile_table(
        frame[SURVEY_INCOME_COLUMN],
        frame[SURVEY_INDICATOR_COLUMN],
        selected_weights,
    )
    weighted_direct = weighted_share(frame[SURVEY_INDICATOR_COLUMN], frame[SURVEY_WEIGHT_COLUMN])
    unweighted_direct = weighted_share(
        frame[SURVEY_INDICATOR_COLUMN],
        pd.Series(np.ones(len(frame)), index=frame.index),
    )
    weighted_table = compute_equal_mass_percentile_table(
        frame[SURVEY_INCOME_COLUMN],
        frame[SURVEY_INDICATOR_COLUMN],
        frame[SURVEY_WEIGHT_COLUMN],
    )
    unweighted_table = compute_equal_mass_percentile_table(
        frame[SURVEY_INCOME_COLUMN],
        frame[SURVEY_INDICATOR_COLUMN],
        pd.Series(np.ones(len(frame)), index=frame.index),
    )

    result: dict[str, object] = {
        "dataset": prepared.dataset,
        "sourcePath": prepared.source_path,
        "proxy": {
            "label": prepared.proxy_label,
            "note": prepared.proxy_note,
        },
        "columns": prepared.columns,
        "diagnostics": prepared.diagnostics,
        "weightMode": weight_mode,
        "multiplier": multiplier,
        "selected": {
            "directShare": selected_direct,
            "equalMassTableMean": selected_table["mean"],
            "tableEquivalenceGap": selected_table["equivalenceGap"],
            "equivalentWithinTolerance": selected_table["equivalenceGap"] <= equivalence_tolerance,
            "multiplierTimesEqualMassTableMean": multiplier * float(selected_table["mean"]),
        },
        "sensitivity": {
            "weightedDirectShare": weighted_direct,
            "unweightedDirectShare": unweighted_direct,
            "weightedEqualMassTableMean": weighted_table["mean"],
            "unweightedEqualMassTableMean": unweighted_table["mean"],
        },
        "equalMassTableStats": {
            "selected": selected_table,
            "weighted": weighted_table,
            "unweighted": unweighted_table,
        },
        "notes": prepared.notes,
    }

    if prepared.dataset in (DATASET_W3, DATASET_R8):
        legacy_weak = compute_legacy_weak_percentile_table(
            frame[SURVEY_INCOME_COLUMN],
            frame[SURVEY_INDICATOR_COLUMN],
        )
        result["legacyWeakPercentileTable"] = legacy_weak
        checked_in_path = _checked_in_table_path(prepared.dataset)
        if checked_in_path is not None and checked_in_path.exists():
            checked_in_mean = read_btl_probability_table_mean(checked_in_path)
            result["checkedInTable"] = {
                "path": str(checked_in_path),
                "mean": checked_in_mean,
                "gapVsLegacyWeakMean": abs(checked_in_mean - float(legacy_weak["mean"])),
                "multiplierTimesMean": multiplier * checked_in_mean,
            }
    return result


def run_btl_survey_targets(
    *,
    datasets: Iterable[str] = DATASET_CHOICES,
    weight_mode: str = WEIGHT_MODE_WEIGHTED,
    multiplier: float = DEFAULT_MULTIPLIER,
    frs_household_csv: str | Path | None = None,
    frs_dictionary_txt: str | Path | None = None,
    equivalence_tolerance: float = DEFAULT_EQUIVALENCE_TOLERANCE,
) -> dict[str, object]:
    if weight_mode not in WEIGHT_MODE_CHOICES:
        raise ValueError(f"Unsupported weight mode: {weight_mode}")
    prepared_items: list[PreparedSurveyData] = []
    for dataset in datasets:
        if dataset in (DATASET_W3, DATASET_R8):
            prepared_items.append(prepare_was_survey_data(dataset))
        elif dataset == DATASET_FRS_2023_24:
            prepared_items.append(
                prepare_frs_survey_data(
                    household_csv=frs_household_csv,
                    dictionary_txt=frs_dictionary_txt,
                )
            )
        else:
            raise ValueError(f"Unsupported dataset: {dataset}")

    results = [
        build_survey_result(
            prepared,
            weight_mode=weight_mode,
            multiplier=multiplier,
            equivalence_tolerance=equivalence_tolerance,
        )
        for prepared in prepared_items
    ]
    return {
        "weightMode": weight_mode,
        "multiplier": multiplier,
        "equivalenceTolerance": equivalence_tolerance,
        "datasets": [result["dataset"] for result in results],
        "results": results,
    }


def _write_json(path: str | Path, summary: dict[str, object]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def _write_csv(path: str | Path, summary: dict[str, object]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "dataset",
        "proxy_label",
        "weight_mode",
        "direct_share",
        "equal_mass_table_mean",
        "table_equivalence_gap",
        "multiplier",
        "multiplier_times_equal_mass_table_mean",
        "weighted_direct_share",
        "unweighted_direct_share",
        "legacy_weak_percentile_table_mean",
        "checked_in_table_mean",
        "valid_rows",
        "source_path",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in summary["results"]:
            selected = result["selected"]
            sensitivity = result["sensitivity"]
            diagnostics = result["diagnostics"]
            writer.writerow(
                {
                    "dataset": result["dataset"],
                    "proxy_label": result["proxy"]["label"],
                    "weight_mode": result["weightMode"],
                    "direct_share": selected["directShare"],
                    "equal_mass_table_mean": selected["equalMassTableMean"],
                    "table_equivalence_gap": selected["tableEquivalenceGap"],
                    "multiplier": result["multiplier"],
                    "multiplier_times_equal_mass_table_mean": selected[
                        "multiplierTimesEqualMassTableMean"
                    ],
                    "weighted_direct_share": sensitivity["weightedDirectShare"],
                    "unweighted_direct_share": sensitivity["unweightedDirectShare"],
                    "legacy_weak_percentile_table_mean": result.get(
                        "legacyWeakPercentileTable",
                        {},
                    ).get("mean", ""),
                    "checked_in_table_mean": result.get("checkedInTable", {}).get("mean", ""),
                    "valid_rows": diagnostics.get("validRows", diagnostics.get("trimmedRows", "")),
                    "source_path": result["sourcePath"],
                }
            )


def _print_summary(summary: dict[str, object]) -> None:
    print("BTL survey target reproduction")
    print(f"Weight mode: {summary['weightMode']}")
    print(f"Multiplier: {format_float(float(summary['multiplier']))}")
    for result in summary["results"]:
        selected = result["selected"]
        sensitivity = result["sensitivity"]
        print("")
        print(f"{result['dataset']} ({result['proxy']['label']})")
        print(f"  Direct share: {format_float(float(selected['directShare']), decimals=16)}")
        print(
            "  Equal-mass table mean: "
            f"{format_float(float(selected['equalMassTableMean']), decimals=16)}"
        )
        print(
            "  Table/direct gap: "
            f"{format_float(float(selected['tableEquivalenceGap']), decimals=16)}"
        )
        print(
            "  Multiplier * equal-mass table mean: "
            f"{format_float(float(selected['multiplierTimesEqualMassTableMean']), decimals=16)}"
        )
        print(
            "  Sensitivity shares: "
            f"weighted={format_float(float(sensitivity['weightedDirectShare']), decimals=16)}, "
            f"unweighted={format_float(float(sensitivity['unweightedDirectShare']), decimals=16)}"
        )
        if "legacyWeakPercentileTable" in result:
            legacy = result["legacyWeakPercentileTable"]
            print(
                "  Legacy weak-percentile table mean: "
                f"{format_float(float(legacy['mean']), decimals=16)}"
            )
        if "checkedInTable" in result:
            checked = result["checkedInTable"]
            print(
                "  Checked-in table mean: "
                f"{format_float(float(checked['mean']), decimals=16)}"
            )
        for note in result["notes"]:
            print(f"  Note: {note}")


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        datasets = parse_datasets(args.datasets)
        summary = run_btl_survey_targets(
            datasets=datasets,
            weight_mode=args.weight_mode,
            multiplier=args.multiplier,
            frs_household_csv=args.frs_household_csv,
            frs_dictionary_txt=args.frs_dictionary_txt,
            equivalence_tolerance=args.equivalence_tolerance,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))

    if args.output_json:
        _write_json(args.output_json, summary)
    if args.output_csv:
        _write_csv(args.output_csv, summary)
    _print_summary(summary)


if __name__ == "__main__":
    main()
