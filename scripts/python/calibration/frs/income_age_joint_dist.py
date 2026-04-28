#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a weighted FRS 2023-24 household gross non-rent income-age joint distribution.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from scripts.python.calibration.frs.age_dist import (
    DEFAULT_HOUSEHOLD_CSV,
    FRS_HHAGEGR4_BANDS,
    HHAGEGR4_COLUMN,
    HHAGEGRP_COLUMN,
    MISSING_CODE_MAX,
    MISSING_CODE_MIN,
    WEIGHT_COLUMN,
    AgeBand,
    default_frs_output_dir,
    prepare_valid_age_rows,
    resolve_household_csv,
)
from scripts.python.helpers.common.paths import ensure_output_dir, repo_root
from scripts.python.helpers.was.income_processing import DEFAULT_INCOME_TRIM_PERCENTILE
from scripts.python.helpers.was.row_filters import filter_percentile_outliers
from scripts.python.helpers.was.csv_write import write_rows


DATA_INCOME_GIVEN_AGE_KEY = "DATA_INCOME_GIVEN_AGE"
DEFAULT_DICTIONARY_TXT = Path("private-datasets/frs/23-24/household_data_dictionary.txt")
INCOME_COLUMN = "hhinc"
SUBLET_COLUMN = "SUBLET"
RENTAL_INCOME_COLUMN = "SUBRENT"
DERIVED_RENTAL_INCOME_COLUMN = "rental_income_for_derivation"
GROSS_NON_RENT_INCOME_COLUMN = "gross_non_rent_income"
OUTPUT_FILE_NAME = "AgeGrossIncomeJointDist.csv"
SOURCE_VALUES_FILE_NAME = "FrsIncomeAgeJointDistSourceValues.csv"
SUMMARY_FILE_NAME = "FrsIncomeAgeJointDistSummary.json"
ANNUALISATION_FACTOR = 52.0
DEFAULT_INCOME_BIN_COUNT = 25
INCOME_TRIM_PERCENTILE = DEFAULT_INCOME_TRIM_PERCENTILE
PROBABILITY_TOLERANCE = 1.0e-9
ANNUAL_INCOME_COLUMN = "annual_income"
LOG_ANNUAL_INCOME_COLUMN = "log_annual_income"
EXPANDED_WEIGHT_COLUMN = "expanded_weight"
AGE_MIDPOINT_COLUMN = "age_midpoint"


@dataclass(frozen=True)
class DictionaryContract:
    variable: str
    label: str
    measurement_level: str


@dataclass(frozen=True)
class JointDistributionRow:
    age_lower_edge: float
    age_upper_edge: float
    log_income_lower_edge: float
    log_income_upper_edge: float
    probability: float


@dataclass(frozen=True)
class SourceAgeBandSummary:
    selected_age_column: str
    source_age_code: int
    source_share: float
    source_lower_edge: float
    source_upper_edge: float
    model_lower_edge: float
    model_upper_edge: float
    unweighted_count: int
    expanded_weight_sum: float


EXPECTED_DICTIONARY_CONTRACTS: tuple[DictionaryContract, ...] = (
    DictionaryContract(WEIGHT_COLUMN, "Grossing variable", "SCALE"),
    DictionaryContract(INCOME_COLUMN, "HH - Total Household income", "SCALE"),
    DictionaryContract(SUBLET_COLUMN, "Whether have formal sublet arrangement", "NOMINAL"),
    DictionaryContract(RENTAL_INCOME_COLUMN, "Amount of rent from subletting", "SCALE"),
    DictionaryContract(HHAGEGRP_COLUMN, "Age of HRP (Pub)", "NOMINAL"),
    DictionaryContract(HHAGEGR4_COLUMN, "Age of HRP - 5 Year Age Bands - Anon", "NOMINAL"),
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate weighted FRS 2023-24 gross non-rent household income by HRP age distribution."
    )
    parser.add_argument(
        "--household-csv",
        default=None,
        help="Optional FRS household CSV path. Defaults to private-datasets/frs/23-24/househol.csv.",
    )
    parser.add_argument(
        "--dictionary-txt",
        default=None,
        help=(
            "Optional FRS household data dictionary path. Defaults to "
            "private-datasets/frs/23-24/household_data_dictionary.txt."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional directory for AgeGrossIncomeJointDist.csv. Defaults to tmp/frs/.",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help=(
            "Optional directory for aggregate source-value and summary evidence. "
            "Raw private FRS rows are not written."
        ),
    )
    return parser


def resolve_dictionary_txt(path: str | Path | None, *, root: Path | None = None) -> Path:
    candidate = Path(path).expanduser() if path else DEFAULT_DICTIONARY_TXT
    base_root = root if root is not None else repo_root()
    resolved = candidate if candidate.is_absolute() else base_root / candidate
    if not resolved.exists():
        raise FileNotFoundError(f"Missing FRS household data dictionary: {resolved}")
    return resolved.resolve()


def load_frs_income_age_data(household_csv: Path) -> pd.DataFrame:
    return pd.read_csv(
        household_csv,
        usecols=[
            HHAGEGRP_COLUMN,
            HHAGEGR4_COLUMN,
            INCOME_COLUMN,
            SUBLET_COLUMN,
            RENTAL_INCOME_COLUMN,
            WEIGHT_COLUMN,
        ],
    )


def validate_dictionary_contracts(dictionary_txt: Path) -> list[dict[str, str | bool]]:
    text = dictionary_txt.read_text(encoding="utf-8", errors="replace")
    validated: list[dict[str, str | bool]] = []
    for contract in EXPECTED_DICTIONARY_CONTRACTS:
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


def prepare_valid_income_age_rows(
    raw_data: pd.DataFrame,
    *,
    trim_percentile: float = INCOME_TRIM_PERCENTILE,
) -> tuple[pd.DataFrame, tuple[AgeBand, ...], str, dict[str, object]]:
    missing_columns = [
        column
        for column in (
            HHAGEGRP_COLUMN,
            HHAGEGR4_COLUMN,
            INCOME_COLUMN,
            SUBLET_COLUMN,
            RENTAL_INCOME_COLUMN,
            WEIGHT_COLUMN,
        )
        if column not in raw_data.columns
    ]
    if missing_columns:
        raise ValueError(f"FRS household data missing required columns: {missing_columns}")

    age_valid_data, band_scheme, age_column, age_diagnostics = prepare_valid_age_rows(raw_data)
    prepared = age_valid_data.copy()
    prepared[INCOME_COLUMN] = pd.to_numeric(prepared[INCOME_COLUMN], errors="coerce")
    prepared[SUBLET_COLUMN] = pd.to_numeric(prepared[SUBLET_COLUMN], errors="coerce")
    prepared[RENTAL_INCOME_COLUMN] = pd.to_numeric(prepared[RENTAL_INCOME_COLUMN], errors="coerce")
    prepared[WEIGHT_COLUMN] = pd.to_numeric(prepared[WEIGHT_COLUMN], errors="coerce")

    income_numeric_mask = prepared[INCOME_COLUMN].notna()
    income_finite_mask = _finite_mask(prepared[INCOME_COLUMN])
    income_missing_code_mask = prepared[INCOME_COLUMN].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
    sublet_numeric_mask = prepared[SUBLET_COLUMN].notna()
    sublet_finite_mask = _finite_mask(prepared[SUBLET_COLUMN])
    sublet_missing_code_mask = prepared[SUBLET_COLUMN].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
    subletter_mask = (
        sublet_numeric_mask
        & sublet_finite_mask
        & ~sublet_missing_code_mask
        & (prepared[SUBLET_COLUMN] == 1.0)
    )
    non_subletter_mask = (
        sublet_numeric_mask
        & sublet_finite_mask
        & ~sublet_missing_code_mask
        & (prepared[SUBLET_COLUMN] == 2.0)
    )
    rental_income_numeric_mask = prepared[RENTAL_INCOME_COLUMN].notna()
    rental_income_finite_mask = _finite_mask(prepared[RENTAL_INCOME_COLUMN])
    rental_income_missing_code_mask = prepared[RENTAL_INCOME_COLUMN].between(
        MISSING_CODE_MIN,
        MISSING_CODE_MAX,
    )
    rental_income_non_negative_mask = prepared[RENTAL_INCOME_COLUMN] >= 0.0
    weight_finite_mask = _finite_mask(prepared[WEIGHT_COLUMN])

    valid_subletter_rental_income_mask = (
        subletter_mask
        & rental_income_numeric_mask
        & rental_income_finite_mask
        & ~rental_income_missing_code_mask
        & rental_income_non_negative_mask
    )
    prepared[DERIVED_RENTAL_INCOME_COLUMN] = np.nan
    prepared.loc[non_subletter_mask, DERIVED_RENTAL_INCOME_COLUMN] = 0.0
    prepared.loc[valid_subletter_rental_income_mask, DERIVED_RENTAL_INCOME_COLUMN] = prepared.loc[
        valid_subletter_rental_income_mask,
        RENTAL_INCOME_COLUMN,
    ].astype(float)
    rental_income_for_derivation_finite_mask = _finite_mask(prepared[DERIVED_RENTAL_INCOME_COLUMN])

    source_income_mask = (
        income_numeric_mask
        & income_finite_mask
        & ~income_missing_code_mask
        & rental_income_for_derivation_finite_mask
    )
    prepared[GROSS_NON_RENT_INCOME_COLUMN] = (
        prepared[INCOME_COLUMN].astype(float) - prepared[DERIVED_RENTAL_INCOME_COLUMN].astype(float)
    )
    derived_income_finite_mask = _finite_mask(prepared[GROSS_NON_RENT_INCOME_COLUMN])
    derived_income_positive_mask = prepared[GROSS_NON_RENT_INCOME_COLUMN] > 0.0

    valid_income_mask = (
        source_income_mask
        & derived_income_finite_mask
        & derived_income_positive_mask
        & weight_finite_mask
    )
    positive_valid = prepared.loc[valid_income_mask].copy()
    positive_valid[ANNUAL_INCOME_COLUMN] = (
        positive_valid[GROSS_NON_RENT_INCOME_COLUMN].astype(float) * ANNUALISATION_FACTOR
    )
    trimmed = filter_percentile_outliers(
        positive_valid,
        lower_bound_column=ANNUAL_INCOME_COLUMN,
        upper_bound_column=ANNUAL_INCOME_COLUMN,
        percentile=trim_percentile,
    ).copy()
    trimmed[LOG_ANNUAL_INCOME_COLUMN] = np.log(trimmed[ANNUAL_INCOME_COLUMN])

    trim_lower_bound = float(trimmed[ANNUAL_INCOME_COLUMN].min()) if not trimmed.empty else None
    trim_upper_bound = float(trimmed[ANNUAL_INCOME_COLUMN].max()) if not trimmed.empty else None

    diagnostics = {
        "rawRows": int(len(raw_data)),
        "ageValidRows": int(len(age_valid_data)),
        "positiveIncomeRows": int(len(positive_valid)),
        "validRows": int(len(trimmed)),
        "droppedRows": int(len(raw_data) - len(trimmed)),
        "droppedRowsAfterAgeFilter": int(len(age_valid_data) - len(trimmed)),
        "ageFilter": age_diagnostics,
        "incomeFilter": {
            "totalIncomeNonNumericRows": int((~income_numeric_mask).sum()),
            "totalIncomeNonFiniteRows": int((income_numeric_mask & ~income_finite_mask).sum()),
            "totalIncomeMissingCodeRows": int((income_numeric_mask & income_missing_code_mask).sum()),
            "subletNonNumericRows": int((~sublet_numeric_mask).sum()),
            "subletNonFiniteRows": int((sublet_numeric_mask & ~sublet_finite_mask).sum()),
            "subletMissingCodeRows": int((sublet_numeric_mask & sublet_missing_code_mask).sum()),
            "subletInvalidCodeRows": int(
                (
                    sublet_numeric_mask
                    & sublet_finite_mask
                    & ~sublet_missing_code_mask
                    & ~prepared[SUBLET_COLUMN].isin([1.0, 2.0])
                ).sum()
            ),
            "subletterRows": int(subletter_mask.sum()),
            "nonSubletterRows": int(non_subletter_mask.sum()),
            "nonSubletterRentalIncomeCoercedRows": int(non_subletter_mask.sum()),
            "rentalIncomeNonNumericRows": int((subletter_mask & ~rental_income_numeric_mask).sum()),
            "rentalIncomeNonFiniteRows": int(
                (subletter_mask & rental_income_numeric_mask & ~rental_income_finite_mask).sum()
            ),
            "rentalIncomeMissingCodeRows": int(
                (subletter_mask & rental_income_numeric_mask & rental_income_missing_code_mask).sum()
            ),
            "rentalIncomeNegativeRows": int(
                (
                    subletter_mask
                    & rental_income_numeric_mask
                    & rental_income_finite_mask
                    & ~rental_income_missing_code_mask
                    & ~rental_income_non_negative_mask
                ).sum()
            ),
            "subletterInvalidRentalIncomeRows": int(
                (
                    subletter_mask
                    & (
                        ~rental_income_numeric_mask
                        | ~rental_income_finite_mask
                        | rental_income_missing_code_mask
                        | ~rental_income_non_negative_mask
                    )
                ).sum()
            ),
            "nonSubletterUnexpectedNumericRentalIncomeRows": int(
                (
                    non_subletter_mask
                    & rental_income_numeric_mask
                    & rental_income_finite_mask
                    & ~rental_income_missing_code_mask
                    & rental_income_non_negative_mask
                ).sum()
            ),
            "derivedIncomeNonFiniteRows": int((source_income_mask & ~derived_income_finite_mask).sum()),
            "nonPositiveRows": int(
                (
                    source_income_mask
                    & derived_income_finite_mask
                    & ~derived_income_positive_mask
                ).sum()
            ),
        },
        "incomeTrim": {
            "percentile": trim_percentile,
            "droppedRows": int(len(positive_valid) - len(trimmed)),
            "lowerAnnualIncomeBound": trim_lower_bound,
            "upperAnnualIncomeBound": trim_upper_bound,
        },
        "weightFilter": {
            "nonFiniteRowsAfterAgeFilter": int((~weight_finite_mask).sum()),
        },
        "ageColumn": age_column,
        "fallbackReason": age_diagnostics.get("fallbackReason", ""),
    }
    if trimmed.empty:
        raise ValueError("No valid FRS income-age rows after filtering.")
    return trimmed, band_scheme, age_column, diagnostics


def _finite_mask(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return pd.Series(np.isfinite(values.to_numpy(dtype=float)), index=series.index)


def compute_income_age_joint_distribution(
    valid_data: pd.DataFrame,
    band_scheme: tuple[AgeBand, ...],
    age_column: str,
    income_bin_edges: np.ndarray | None = None,
) -> tuple[list[JointDistributionRow], list[SourceAgeBandSummary], np.ndarray, dict[str, object]]:
    expanded, source_summaries = _expand_source_age_bands(valid_data, band_scheme, age_column)
    if expanded.empty:
        raise ValueError("No rows available for FRS income-age histogram.")

    if income_bin_edges is None:
        log_income_min = float(valid_data[LOG_ANNUAL_INCOME_COLUMN].min())
        log_income_max = float(valid_data[LOG_ANNUAL_INCOME_COLUMN].max())
        if not math.isfinite(log_income_min) or not math.isfinite(log_income_max):
            raise ValueError("Log annual income bounds must be finite.")
        if log_income_min >= log_income_max:
            raise ValueError(
                f"Log annual income bounds must be increasing, got {log_income_min} >= {log_income_max}."
            )
        income_bin_edges = np.linspace(log_income_min, log_income_max, DEFAULT_INCOME_BIN_COUNT + 1)
    else:
        income_bin_edges = np.asarray(income_bin_edges, dtype=float)
        if np.any(np.diff(income_bin_edges) <= 0):
            raise ValueError("Income bin edges must be strictly increasing.")

    age_bin_edges = np.asarray(_age_bin_edges_from_scheme(band_scheme), dtype=float)
    if np.any(np.diff(age_bin_edges) <= 0):
        raise ValueError("Age bin edges must be strictly increasing.")

    histogram = np.histogram2d(
        expanded[AGE_MIDPOINT_COLUMN].to_numpy(dtype=float),
        expanded[LOG_ANNUAL_INCOME_COLUMN].to_numpy(dtype=float),
        bins=[age_bin_edges, income_bin_edges],
        weights=expanded[EXPANDED_WEIGHT_COLUMN].to_numpy(dtype=float),
    )[0]

    rows: list[JointDistributionRow] = []
    age_bin_probability_sums: dict[str, float] = {}
    age_bin_weight_sums: dict[str, float] = {}
    empty_age_bin_probability_sources: dict[str, str] = {}
    zero_bin_counts: dict[str, int] = {}
    row_weight_sums = histogram.sum(axis=1)
    populated_age_bin_indexes = np.flatnonzero(row_weight_sums > 0.0)
    if populated_age_bin_indexes.size == 0:
        raise ValueError("No populated FRS age bins available for income-age histogram.")
    for age_index, (line, age_lower, age_upper) in enumerate(
        zip(histogram, age_bin_edges[:-1], age_bin_edges[1:])
    ):
        age_lower = float(age_lower)
        age_upper = float(age_upper)
        age_bin_key = f"{age_lower:g}-{age_upper:g}"
        weight_sum = float(row_weight_sums[age_index])
        age_bin_weight_sums[age_bin_key] = weight_sum
        if weight_sum > 0.0:
            probabilities = line / weight_sum
        else:
            nearest_populated_index = min(
                populated_age_bin_indexes,
                key=lambda populated_index: abs(int(populated_index) - age_index),
            )
            nearest_line = histogram[nearest_populated_index]
            nearest_weight_sum = row_weight_sums[nearest_populated_index]
            probabilities = nearest_line / nearest_weight_sum
            source_lower = float(age_bin_edges[nearest_populated_index])
            source_upper = float(age_bin_edges[nearest_populated_index + 1])
            empty_age_bin_probability_sources[age_bin_key] = f"{source_lower:g}-{source_upper:g}"

        probability_sum = float(probabilities.sum())
        age_bin_probability_sums[age_bin_key] = probability_sum
        zero_bin_counts[age_bin_key] = int((probabilities == 0.0).sum())
        if abs(probability_sum - 1.0) > PROBABILITY_TOLERANCE:
            raise ValueError(
                f"Probability sum for age bin {age_lower:g}-{age_upper:g} must be 1.0, got {probability_sum}."
            )
        for probability, income_lower, income_upper in zip(
            probabilities,
            income_bin_edges[:-1],
            income_bin_edges[1:],
        ):
            rows.append(
                JointDistributionRow(
                    age_lower_edge=age_lower,
                    age_upper_edge=age_upper,
                    log_income_lower_edge=float(income_lower),
                    log_income_upper_edge=float(income_upper),
                    probability=float(probability),
                )
            )

    diagnostics = {
        "ageBinProbabilitySums": age_bin_probability_sums,
        "ageBinWeightSums": age_bin_weight_sums,
        "emptyAgeBinProbabilitySources": empty_age_bin_probability_sources,
        "zeroBinCounts": zero_bin_counts,
        "ageBinEdges": [float(edge) for edge in age_bin_edges],
        "incomeBinEdges": [float(edge) for edge in income_bin_edges],
        "expandedRows": int(len(expanded)),
        "expandedWeightSum": float(expanded[EXPANDED_WEIGHT_COLUMN].sum()),
        "logAnnualIncomeMin": float(income_bin_edges[0]),
        "logAnnualIncomeMax": float(income_bin_edges[-1]),
    }
    return rows, source_summaries, income_bin_edges, diagnostics


def _expand_source_age_bands(
    valid_data: pd.DataFrame,
    band_scheme: tuple[AgeBand, ...],
    age_column: str,
) -> tuple[pd.DataFrame, list[SourceAgeBandSummary]]:
    expanded_parts: list[pd.DataFrame] = []
    source_summaries: list[SourceAgeBandSummary] = []
    for band in band_scheme:
        source_code = band.source_code if band.source_code is not None else band.code
        mask = valid_data[age_column] == source_code
        source_rows = valid_data.loc[mask].copy()
        expanded_weight_sum = float(source_rows[WEIGHT_COLUMN].sum()) * band.source_share
        source_summaries.append(
            SourceAgeBandSummary(
                selected_age_column=age_column,
                source_age_code=source_code,
                source_share=band.source_share,
                source_lower_edge=band.lower_edge,
                source_upper_edge=band.upper_edge,
                model_lower_edge=band.lower_edge,
                model_upper_edge=band.upper_edge,
                unweighted_count=int(mask.sum()),
                expanded_weight_sum=expanded_weight_sum,
            )
        )
        if source_rows.empty:
            continue
        source_rows[EXPANDED_WEIGHT_COLUMN] = source_rows[WEIGHT_COLUMN].astype(float) * band.source_share
        source_rows[AGE_MIDPOINT_COLUMN] = band.midpoint
        expanded_parts.append(
            source_rows[
                [
                    AGE_MIDPOINT_COLUMN,
                    LOG_ANNUAL_INCOME_COLUMN,
                    EXPANDED_WEIGHT_COLUMN,
                ]
            ]
        )
    if not expanded_parts:
        return pd.DataFrame(), source_summaries
    return pd.concat(expanded_parts, ignore_index=True), source_summaries


def _age_bin_edges_from_scheme(band_scheme: tuple[AgeBand, ...]) -> list[float]:
    edges = [float(band_scheme[0].lower_edge)]
    for band in band_scheme:
        if abs(edges[-1] - band.lower_edge) > PROBABILITY_TOLERANCE:
            raise ValueError(
                f"Age bands must be contiguous, got previous edge {edges[-1]} and next lower {band.lower_edge}."
            )
        edges.append(float(band.upper_edge))
    return edges


def _distribution_csv_rows(rows: Iterable[JointDistributionRow]) -> list[tuple[float, float, float, float, float]]:
    return [
        (
            row.age_lower_edge,
            row.age_upper_edge,
            row.log_income_lower_edge,
            row.log_income_upper_edge,
            row.probability,
        )
        for row in rows
    ]


def _write_source_values_csv(path: Path, rows: Iterable[JointDistributionRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "age_lower_edge",
                "age_upper_edge",
                "log_income_lower_edge",
                "log_income_upper_edge",
                "probability",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def run_income_age_joint_distribution(
    *,
    household_csv: str | Path | None = None,
    dictionary_txt: str | Path | None = None,
    output_dir: str | Path | None = None,
    evidence_dir: str | Path | None = None,
) -> dict[str, object]:
    resolved_csv = resolve_household_csv(household_csv)
    resolved_dictionary = resolve_dictionary_txt(dictionary_txt)
    dictionary_contracts = validate_dictionary_contracts(resolved_dictionary)
    raw_data = load_frs_income_age_data(resolved_csv)
    valid_data, band_scheme, age_column, filter_diagnostics = prepare_valid_income_age_rows(raw_data)
    rows, source_summaries, income_bin_edges, histogram_diagnostics = compute_income_age_joint_distribution(
        valid_data,
        band_scheme,
        age_column,
    )

    output_root = ensure_output_dir(output_dir, default_dir=default_frs_output_dir())
    output_path = output_root / OUTPUT_FILE_NAME
    write_rows(
        str(output_path),
        (
            "# Age (lower edge), Age (upper edge), Log Gross Income (lower edge), "
            "Log Gross Income (upper edge), Probability\n"
        ),
        _distribution_csv_rows(rows),
    )

    summary = {
        "parameterKey": DATA_INCOME_GIVEN_AGE_KEY,
        "selectedConfigValues": {
            DATA_INCOME_GIVEN_AGE_KEY: f"src/main/resources/{OUTPUT_FILE_NAME}",
        },
        "sourcePath": str(resolved_csv),
        "dictionaryPath": str(resolved_dictionary),
        "outputPath": str(output_path),
        "method": (
            "weighted FRS 2023-24 household gross non-rent income conditional on HRP age; "
            "age selection reuses scripts.python.calibration.frs.age_dist, weekly "
            "rental income is set to 0.0 for SUBLET == 2 and read from non-negative "
            "numeric SUBRENT for SUBLET == 1, gross_non_rent_income is derived as "
            "hhinc - rental_income_for_derivation, annualised with *52, positive "
            "derived values are retained before WAS-style percentile tail trimming, and "
            "log annual income is histogrammed into row-normalised FRS age-bin probabilities"
        ),
        "columns": {
            "requestedAge": HHAGEGRP_COLUMN,
            "fallbackAge": HHAGEGR4_COLUMN,
            "selectedAge": age_column,
            "totalIncome": INCOME_COLUMN,
            "subletIndicator": SUBLET_COLUMN,
            "rentalIncome": RENTAL_INCOME_COLUMN,
            "derivedRentalIncome": DERIVED_RENTAL_INCOME_COLUMN,
            "income": GROSS_NON_RENT_INCOME_COLUMN,
            "weight": WEIGHT_COLUMN,
        },
        "dictionaryContracts": dictionary_contracts,
        "diagnostics": {
            **filter_diagnostics,
            **histogram_diagnostics,
            "sourceAgeBands": [asdict(summary_row) for summary_row in source_summaries],
            "incomeBinCount": int(len(income_bin_edges) - 1),
            "annualisationFactor": ANNUALISATION_FACTOR,
            "incomeTrimPercentile": INCOME_TRIM_PERCENTILE,
            "ageBandScheme": "hhageGR4" if band_scheme == FRS_HHAGEGR4_BANDS else "hhagegrp",
        },
    }

    if evidence_dir is not None:
        evidence_root = ensure_output_dir(evidence_dir)
        _write_source_values_csv(evidence_root / SOURCE_VALUES_FILE_NAME, rows)
        (evidence_root / SUMMARY_FILE_NAME).write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "output_file": str(output_path),
        "summary": summary,
        "rows": rows,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    result = run_income_age_joint_distribution(
        household_csv=args.household_csv,
        dictionary_txt=args.dictionary_txt,
        output_dir=args.output_dir,
        evidence_dir=args.evidence_dir,
    )
    summary = result["summary"]
    diagnostics = summary["diagnostics"]
    print(f"{DATA_INCOME_GIVEN_AGE_KEY} = {summary['selectedConfigValues'][DATA_INCOME_GIVEN_AGE_KEY]}")
    print(f"Output: {summary['outputPath']}")
    print(f"Selected age column: {summary['columns']['selectedAge']}")
    print(f"Valid rows: {diagnostics['validRows']}")
    print(f"Log annual income range: {diagnostics['logAnnualIncomeMin']:.12f} to {diagnostics['logAnnualIncomeMax']:.12f}")


if __name__ == "__main__":
    main()
