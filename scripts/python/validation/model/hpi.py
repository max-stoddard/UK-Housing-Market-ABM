"""Shared HPI parsing and metric helpers for 2024 validation.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Sequence

import numpy as np

HMLR_FULL_FILE_DATE_FORMAT = "%d/%m/%Y"
HMLR_REGION_NAME_UK = "United Kingdom"


def load_output_series(csv_path: Path, *, column_name: str) -> list[float]:
    """Load one semicolon-delimited series from Output-run1.csv."""

    if not csv_path.exists():
        raise RuntimeError(f"Missing required output series file: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";", skipinitialspace=True)
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing header row in output series file: {csv_path}")
        field_map = {field_name.strip(): field_name for field_name in reader.fieldnames if field_name is not None}
        source_field_name = field_map.get(column_name)
        if source_field_name is None:
            raise RuntimeError(f"Missing output column '{column_name}' in {csv_path}")

        values: list[float] = []
        for row in reader:
            raw_value = row.get(source_field_name)
            if raw_value is None:
                continue
            stripped = raw_value.strip()
            if not stripped:
                continue
            values.append(float(stripped))

    if not values:
        raise RuntimeError(f"No numeric values found for '{column_name}' in {csv_path}")
    return values


def load_hmlr_uk_full_file_series(
    csv_path: Path,
    *,
    field_name: str,
    start_year_month: tuple[int, int] | None = None,
    end_year_month: tuple[int, int] | None = None,
) -> list[float]:
    """Load one United Kingdom series from the archived HMLR full UK HPI CSV."""

    if not csv_path.exists():
        raise RuntimeError(f"Missing required HMLR source file: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise RuntimeError(f"Missing header row in HMLR source file: {csv_path}")
        field_map = {field_name_value.strip(): field_name_value for field_name_value in reader.fieldnames if field_name_value}
        region_field = field_map.get("RegionName")
        date_field = field_map.get("Date")
        value_field = field_map.get(field_name)
        if region_field is None or date_field is None or value_field is None:
            raise RuntimeError(f"Missing required HMLR columns in {csv_path}")

        rows: list[tuple[datetime, float]] = []
        for row in reader:
            if row[region_field].strip() != HMLR_REGION_NAME_UK:
                continue
            raw_value = row[value_field].strip()
            if not raw_value:
                continue
            date_value = datetime.strptime(row[date_field].strip(), HMLR_FULL_FILE_DATE_FORMAT)
            year_month = (date_value.year, date_value.month)
            if start_year_month is not None and year_month < start_year_month:
                continue
            if end_year_month is not None and year_month > end_year_month:
                continue
            rows.append((date_value, float(raw_value)))

    rows.sort(key=lambda item: item[0])
    if not rows:
        raise RuntimeError(f"No usable UK HPI rows found in {csv_path} for field {field_name}")
    return [value for _, value in rows]


def rebase_series_to_first_value(values: Sequence[float]) -> list[float]:
    """Rebase a strictly positive series so that the first value equals 1.0."""

    if not values:
        raise ValueError("Cannot rebase an empty series")
    first_value = float(values[0])
    if not math.isfinite(first_value) or abs(first_value) < 1e-12:
        raise RuntimeError("Cannot rebase a series with a zero or non-finite first value")
    return [float(value) / first_value for value in values]


def compute_population_mean(values: Sequence[float]) -> float:
    """Return the arithmetic mean of a non-empty series."""

    if not values:
        raise ValueError("Cannot compute a mean from an empty series")
    return float(statistics.fmean(values))


def compute_population_std(values: Sequence[float]) -> float:
    """Return the population standard deviation of a non-empty series."""

    if not values:
        raise ValueError("Cannot compute a standard deviation from an empty series")
    return float(statistics.pstdev(values))


def compute_rebased_mean(values: Sequence[float]) -> float:
    """Compute the mean after rebasing the series to its first value."""

    return compute_population_mean(rebase_series_to_first_value(values))


def compute_rebased_std(values: Sequence[float]) -> float:
    """Compute the population standard deviation after rebasing the series."""

    return compute_population_std(rebase_series_to_first_value(values))


def estimate_dominant_cycle_period_months(
    values: Sequence[float],
    *,
    moving_average_months: int = 12,
    min_period_months: float = 60.0,
    max_period_months: float = 240.0,
) -> float:
    """Estimate the dominant cycle period using the locked FFT method."""

    if moving_average_months <= 0:
        raise ValueError("moving_average_months must be positive")
    if min_period_months <= 0.0 or max_period_months <= 0.0 or min_period_months > max_period_months:
        raise ValueError("Invalid cycle-period search bounds")
    if len(values) < moving_average_months:
        raise RuntimeError("Series is too short for the configured moving-average window")

    series = np.asarray(values, dtype=float)
    kernel = np.ones(moving_average_months, dtype=float) / moving_average_months
    smoothed = np.convolve(series, kernel, mode="valid")
    if np.any(smoothed <= 0.0):
        raise RuntimeError("Cycle-period estimation requires strictly positive HPI values after smoothing")

    logged = np.log(smoothed)
    x_axis = np.arange(len(logged), dtype=float)
    slope, intercept = np.polyfit(x_axis, logged, 1)
    detrended = logged - (slope * x_axis + intercept)
    if np.allclose(detrended, 0.0):
        raise RuntimeError("Cannot estimate a cycle period from a flat HPI series")

    frequency = np.fft.rfftfreq(len(detrended), d=1.0)
    power = np.abs(np.fft.rfft(detrended)) ** 2
    periods = np.full_like(frequency, np.inf, dtype=float)
    positive_mask = frequency > 0.0
    periods[positive_mask] = 1.0 / frequency[positive_mask]
    search_mask = positive_mask & (periods >= min_period_months) & (periods <= max_period_months)
    if not np.any(search_mask):
        raise RuntimeError("No admissible cycle-period candidates were found in the requested search band")

    admissible_periods = periods[search_mask]
    admissible_power = power[search_mask]
    dominant_index = int(np.argmax(admissible_power))
    return float(admissible_periods[dominant_index])
