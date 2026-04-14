#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helpers for constructing PPD-derived national HPA signals.

@author: Max Stoddard
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

PPD_PRICE_INDEX = 1
PPD_DATE_INDEX = 2
PPD_CATEGORY_TYPE_INDEX = 14


@dataclass(frozen=True)
class PpdSaleRow:
    price: float
    transfer_year: int
    transfer_month: int
    category_type: str = "A"


@dataclass
class PpdLoadStats:
    total_rows: int = 0
    rows_missing_required_fields: int = 0
    rows_invalid_price: int = 0
    rows_non_positive_price: int = 0
    rows_invalid_transfer_date: int = 0
    rows_loaded: int = 0


@dataclass(frozen=True)
class HpaSignal:
    method_name: str
    anchor_year: int
    base_year: int
    value: float
    diagnostics: dict[str, object]


@dataclass(frozen=True)
class PpdSignalIndex:
    category_key: str
    annual_means: dict[int, float]
    monthly_means: dict[tuple[int, int], float]
    available_years: tuple[int, ...]
    rows_used: int


def _parse_transfer_year_month(raw_transfer_date: str) -> tuple[int, int] | None:
    value = raw_transfer_date.strip()
    if len(value) < 7:
        return None
    year_token = value[:4]
    month_token = value[5:7]
    if not year_token.isdigit() or not month_token.isdigit():
        return None
    year = int(year_token)
    month = int(month_token)
    if month < 1 or month > 12:
        return None
    return year, month


def load_ppd_rows(
    paths: Sequence[Path],
    *,
    delimiter: str = ",",
    price_index: int = PPD_PRICE_INDEX,
    transfer_date_index: int = PPD_DATE_INDEX,
    category_type_index: int = PPD_CATEGORY_TYPE_INDEX,
    category_types: set[str] | None = None,
) -> tuple[list[PpdSaleRow], PpdLoadStats]:
    normalized_category_types = (
        {str(category_type).strip() for category_type in category_types}
        if category_types is not None
        else None
    )
    max_required_index = max(
        price_index,
        transfer_date_index,
        category_type_index if normalized_category_types is not None else 0,
    )
    rows: list[PpdSaleRow] = []
    stats = PpdLoadStats()

    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            for row in reader:
                stats.total_rows += 1
                if len(row) <= max_required_index:
                    stats.rows_missing_required_fields += 1
                    continue
                price_raw = row[price_index].strip()
                if not price_raw:
                    stats.rows_invalid_price += 1
                    continue
                try:
                    price = float(price_raw)
                except ValueError:
                    stats.rows_invalid_price += 1
                    continue
                if price <= 0:
                    stats.rows_non_positive_price += 1
                    continue
                year_month = _parse_transfer_year_month(row[transfer_date_index])
                if year_month is None:
                    stats.rows_invalid_transfer_date += 1
                    continue
                if normalized_category_types is not None:
                    category_type = row[category_type_index].strip()
                    if category_type not in normalized_category_types:
                        continue
                rows.append(
                    PpdSaleRow(
                        price=price,
                        transfer_year=year_month[0],
                        transfer_month=year_month[1],
                        category_type=row[category_type_index].strip() if len(row) > category_type_index else "",
                    )
                )
                stats.rows_loaded += 1

    return rows, stats


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("Cannot compute mean of empty values.")
    return sum(values) / len(values)


def _annual_means(rows: Iterable[PpdSaleRow]) -> dict[int, float]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        grouped[row.transfer_year].append(row.price)
    return {year: _mean(prices) for year, prices in grouped.items()}


def _monthly_means(rows: Iterable[PpdSaleRow]) -> dict[tuple[int, int], float]:
    grouped: dict[tuple[int, int], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(row.transfer_year, row.transfer_month)].append(row.price)
    return {key: _mean(prices) for key, prices in grouped.items()}


def _annualised_growth(recent: float, base: float, year_gap: int) -> float:
    if base <= 0 or recent <= 0:
        raise ValueError("Signal inputs must be positive.")
    if year_gap <= 0:
        raise ValueError("Anchor year must be later than base year.")
    return (recent / base) ** (1.0 / year_gap) - 1.0


def resolve_base_year(
    available_years: Iterable[int],
    *,
    anchor_year: int,
    preferred_gap: int = 2,
) -> int:
    years = sorted(set(int(year) for year in available_years if int(year) < anchor_year))
    if not years:
        raise ValueError(f"No prior PPD year is available for anchor year {anchor_year}.")
    preferred_year = anchor_year - preferred_gap
    if preferred_year in years:
        return preferred_year
    return years[-1]


def build_ppd_signal_index(
    rows: Sequence[PpdSaleRow],
    *,
    category_key: str,
    category_types: set[str] | None = None,
) -> PpdSignalIndex:
    normalized_category_types = (
        {str(category_type).strip() for category_type in category_types}
        if category_types is not None
        else None
    )
    filtered_rows = [
        row
        for row in rows
        if normalized_category_types is None or row.category_type in normalized_category_types
    ]
    if not filtered_rows:
        raise ValueError(f"No PPD rows were available for category key {category_key}.")
    annual_means = _annual_means(filtered_rows)
    monthly_means = _monthly_means(filtered_rows)
    return PpdSignalIndex(
        category_key=category_key,
        annual_means=annual_means,
        monthly_means=monthly_means,
        available_years=tuple(sorted(annual_means)),
        rows_used=len(filtered_rows),
    )


def build_hpa_signal_from_index(
    index: PpdSignalIndex,
    *,
    anchor_year: int,
    base_year: int,
    method_name: str,
) -> HpaSignal:
    year_gap = anchor_year - base_year
    if year_gap <= 0:
        raise ValueError("anchor_year must be later than base_year.")

    if method_name == "annual_mean_annualised":
        if anchor_year not in index.annual_means or base_year not in index.annual_means:
            raise ValueError("Annual-mean signal requires both anchor and base years.")
        signal_value = _annualised_growth(index.annual_means[anchor_year], index.annual_means[base_year], year_gap)
        diagnostics = {
            "anchor_year": anchor_year,
            "base_year": base_year,
            "anchor_mean": index.annual_means[anchor_year],
            "base_mean": index.annual_means[base_year],
            "years_used": [base_year, anchor_year],
            "category_key": index.category_key,
        }
    elif method_name == "annual_mean_cumulative":
        if anchor_year not in index.annual_means or base_year not in index.annual_means:
            raise ValueError("Annual-mean signal requires both anchor and base years.")
        signal_value = (index.annual_means[anchor_year] / index.annual_means[base_year]) - 1.0
        diagnostics = {
            "anchor_year": anchor_year,
            "base_year": base_year,
            "anchor_mean": index.annual_means[anchor_year],
            "base_mean": index.annual_means[base_year],
            "years_used": [base_year, anchor_year],
            "category_key": index.category_key,
        }
    elif method_name == "java_like_annualised":
        recent_months = [10, 11, 12]
        missing_pairs = [
            (year, month)
            for year in (base_year, anchor_year)
            for month in recent_months
            if (year, month) not in index.monthly_means
        ]
        if missing_pairs:
            missing_text = ", ".join(f"{year}-{month:02d}" for year, month in missing_pairs)
            raise ValueError(f"java_like_annualised requires data for months: {missing_text}")
        recent = sum(index.monthly_means[(anchor_year, month)] for month in recent_months)
        base = sum(index.monthly_means[(base_year, month)] for month in recent_months)
        signal_value = _annualised_growth(recent, base, year_gap)
        diagnostics = {
            "anchor_year": anchor_year,
            "base_year": base_year,
            "recent_sum": recent,
            "base_sum": base,
            "months_used_recent": recent_months,
            "months_used_base": recent_months,
            "category_key": index.category_key,
        }
    else:
        raise ValueError(f"Unsupported HPA signal method: {method_name}")

    return HpaSignal(
        method_name=method_name,
        anchor_year=anchor_year,
        base_year=base_year,
        value=signal_value,
        diagnostics=diagnostics,
    )


def build_hpa_signal(
    rows: Sequence[PpdSaleRow],
    *,
    anchor_year: int,
    base_year: int,
    method_name: str,
) -> HpaSignal:
    index = build_ppd_signal_index(rows, category_key="direct_rows")
    return build_hpa_signal_from_index(
        index,
        anchor_year=anchor_year,
        base_year=base_year,
        method_name=method_name,
    )


def build_signal_lookup_from_index(
    index: PpdSignalIndex,
    *,
    anchor_years: Sequence[int],
    method_names: Sequence[str],
    preferred_gap: int = 2,
) -> dict[str, dict[int, HpaSignal]]:
    signal_lookup: dict[str, dict[int, HpaSignal]] = {method_name: {} for method_name in method_names}
    for anchor_year in anchor_years:
        base_year = resolve_base_year(
            index.available_years,
            anchor_year=anchor_year,
            preferred_gap=preferred_gap,
        )
        for method_name in method_names:
            signal_lookup[method_name][int(anchor_year)] = build_hpa_signal_from_index(
                index,
                anchor_year=int(anchor_year),
                base_year=base_year,
                method_name=method_name,
            )
    return signal_lookup


def build_yearly_hpa_signals(
    rows: Sequence[PpdSaleRow],
    *,
    anchor_years: Sequence[int],
    method_name: str,
    preferred_gap: int = 2,
) -> dict[int, HpaSignal]:
    index = build_ppd_signal_index(rows, category_key="direct_rows")
    return build_signal_lookup_from_index(
        index,
        anchor_years=anchor_years,
        method_names=[method_name],
        preferred_gap=preferred_gap,
    )[method_name]


__all__ = [
    "HpaSignal",
    "PpdSignalIndex",
    "PpdLoadStats",
    "PpdSaleRow",
    "build_hpa_signal",
    "build_hpa_signal_from_index",
    "build_ppd_signal_index",
    "build_signal_lookup_from_index",
    "build_yearly_hpa_signals",
    "load_ppd_rows",
    "resolve_base_year",
]
