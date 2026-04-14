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


@dataclass(frozen=True)
class PpdSaleRow:
    price: float
    transfer_year: int
    transfer_month: int


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
) -> tuple[list[PpdSaleRow], PpdLoadStats]:
    max_required_index = max(price_index, transfer_date_index)
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
                rows.append(
                    PpdSaleRow(
                        price=price,
                        transfer_year=year_month[0],
                        transfer_month=year_month[1],
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


def build_hpa_signal(
    rows: Sequence[PpdSaleRow],
    *,
    anchor_year: int,
    base_year: int,
    method_name: str,
) -> HpaSignal:
    year_gap = anchor_year - base_year
    if year_gap <= 0:
        raise ValueError("anchor_year must be later than base_year.")

    if method_name == "annual_mean_annualised":
        annual_means = _annual_means(rows)
        if anchor_year not in annual_means or base_year not in annual_means:
            raise ValueError("Annual-mean signal requires both anchor and base years.")
        signal_value = _annualised_growth(annual_means[anchor_year], annual_means[base_year], year_gap)
        diagnostics = {
            "anchor_year": anchor_year,
            "base_year": base_year,
            "anchor_mean": annual_means[anchor_year],
            "base_mean": annual_means[base_year],
            "years_used": [base_year, anchor_year],
        }
    elif method_name == "annual_mean_cumulative":
        annual_means = _annual_means(rows)
        if anchor_year not in annual_means or base_year not in annual_means:
            raise ValueError("Annual-mean signal requires both anchor and base years.")
        signal_value = (annual_means[anchor_year] / annual_means[base_year]) - 1.0
        diagnostics = {
            "anchor_year": anchor_year,
            "base_year": base_year,
            "anchor_mean": annual_means[anchor_year],
            "base_mean": annual_means[base_year],
            "years_used": [base_year, anchor_year],
        }
    elif method_name == "java_like_annualised":
        monthly_means = _monthly_means(rows)
        recent_months = [10, 11, 12]
        missing_pairs = [
            (year, month)
            for year in (base_year, anchor_year)
            for month in recent_months
            if (year, month) not in monthly_means
        ]
        if missing_pairs:
            missing_text = ", ".join(f"{year}-{month:02d}" for year, month in missing_pairs)
            raise ValueError(f"java_like_annualised requires data for months: {missing_text}")
        recent = sum(monthly_means[(anchor_year, month)] for month in recent_months)
        base = sum(monthly_means[(base_year, month)] for month in recent_months)
        signal_value = _annualised_growth(recent, base, year_gap)
        diagnostics = {
            "anchor_year": anchor_year,
            "base_year": base_year,
            "recent_sum": recent,
            "base_sum": base,
            "months_used_recent": recent_months,
            "months_used_base": recent_months,
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


__all__ = [
    "HpaSignal",
    "PpdLoadStats",
    "PpdSaleRow",
    "build_hpa_signal",
    "load_ppd_rows",
    "resolve_base_year",
]
