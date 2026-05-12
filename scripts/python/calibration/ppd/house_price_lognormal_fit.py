#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compute log-normal house price parameters from one or more UK PPD CSV files.

PPD CSV format (headerless):
transaction_unique_identifier,price,date_of_transfer,postcode,property_type,
old_new,duration,paon,saon,street,locality,town_city,district,county,
ppd_category_type,record_status

Outputs:
  HOUSE_PRICES_SCALE (mu)  = mean of log(price)
  HOUSE_PRICES_SHAPE (sigma) = std dev of log(price)

Methods:
  - focused_repro_default (default):
      category=all, status=a_only, year=all_rows, std=population, trim=0
  - legacy_sample_all:
      include all valid prices, std=sample

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


METHOD_FOCUSED_REPRO_DEFAULT = "focused_repro_default"
METHOD_LEGACY_SAMPLE_ALL = "legacy_sample_all"
METHOD_CHOICES = (METHOD_FOCUSED_REPRO_DEFAULT, METHOD_LEGACY_SAMPLE_ALL)
PPD_DATE_OF_TRANSFER_INDEX = 2
PPD_RECORD_STATUS_INDEX = 15


@dataclass
class RunningStats:
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    min_value: float = math.inf
    max_value: float = -math.inf

    def update(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        delta2 = value - self.mean
        self.m2 += delta * delta2
        if value < self.min_value:
            self.min_value = value
        if value > self.max_value:
            self.max_value = value

    def variance(self, *, std_mode: str) -> float:
        if std_mode == "population":
            if self.count == 0:
                return 0.0
            return self.m2 / self.count
        if std_mode == "sample":
            if self.count < 2:
                return 0.0
            return self.m2 / (self.count - 1)
        raise ValueError(f"Unsupported std_mode: {std_mode}")

    def std(self, *, std_mode: str) -> float:
        return math.sqrt(self.variance(std_mode=std_mode))


@dataclass
class ParseStats:
    total_rows: int = 0
    rows_missing_required_fields: int = 0
    skipped_rows: int = 0
    invalid_price_rows: int = 0
    valid_price_rows: int = 0
    invalid_transfer_year_rows: int = 0
    filtered_non_a_status_rows: int = 0
    used_rows: int = 0


def _std_mode_for_method(method: str) -> str:
    if method == METHOD_FOCUSED_REPRO_DEFAULT:
        return "population"
    if method == METHOD_LEGACY_SAMPLE_ALL:
        return "sample"
    raise ValueError(f"Unsupported method: {method}")


def _method_details(method: str) -> str:
    if method == METHOD_FOCUSED_REPRO_DEFAULT:
        return "category=all|status=a_only|year=all_rows|std=population|trim=0"
    if method == METHOD_LEGACY_SAMPLE_ALL:
        return "category=all|status=all|year=all_rows|std=sample|trim=0"
    raise ValueError(f"Unsupported method: {method}")


def _parse_transfer_year(raw_date: str) -> int | None:
    value = raw_date.strip()
    if len(value) < 4:
        return None
    year_token = value[:4]
    if not year_token.isdigit():
        return None
    return int(year_token)


def update_stats_from_file(
    stats: RunningStats,
    parse_stats: ParseStats,
    path: Path,
    price_index: int,
    delimiter: str,
    skip_rows: int,
    method: str,
    target_year: int,
) -> None:
    required_max_index = max(price_index, PPD_DATE_OF_TRANSFER_INDEX, PPD_RECORD_STATUS_INDEX)
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row_index, row in enumerate(reader):
            parse_stats.total_rows += 1
            if row_index < skip_rows:
                parse_stats.skipped_rows += 1
                continue
            if len(row) <= required_max_index:
                parse_stats.rows_missing_required_fields += 1
                continue

            raw_price = row[price_index].strip()
            if not raw_price:
                parse_stats.invalid_price_rows += 1
                continue
            try:
                price = float(raw_price)
            except ValueError:
                parse_stats.invalid_price_rows += 1
                continue
            if price <= 0:
                parse_stats.invalid_price_rows += 1
                continue
            parse_stats.valid_price_rows += 1

            transfer_year = _parse_transfer_year(row[PPD_DATE_OF_TRANSFER_INDEX])
            if transfer_year is None:
                parse_stats.invalid_transfer_year_rows += 1
            # Target-year is currently carried for forward-compatible method expansion.
            _ = target_year

            record_status = row[PPD_RECORD_STATUS_INDEX].strip()
            if method == METHOD_FOCUSED_REPRO_DEFAULT and record_status != "A":
                parse_stats.filtered_non_a_status_rows += 1
                continue

            stats.update(math.log(price))
            parse_stats.used_rows += 1


def compute_parameters(
    paths: Iterable[Path],
    price_index: int,
    delimiter: str,
    skip_rows: int,
    method: str,
    target_year: int,
) -> tuple[RunningStats, ParseStats]:
    stats = RunningStats()
    parse_stats = ParseStats()
    for path in paths:
        update_stats_from_file(
            stats,
            parse_stats,
            path,
            price_index,
            delimiter,
            skip_rows,
            method,
            target_year,
        )
    return stats, parse_stats


def format_float(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute log-normal house price parameters from PPD CSV files.",
    )
    parser.add_argument(
        "files",
        nargs="+",
        help="One or more PPD CSV files (headerless).",
    )
    parser.add_argument(
        "--price-index",
        type=int,
        default=1,
        help="Zero-based index of the price column (default: 1).",
    )
    parser.add_argument(
        "--delimiter",
        default=",",
        help="CSV delimiter (default: ',').",
    )
    parser.add_argument(
        "--skip-rows",
        type=int,
        default=0,
        help="Number of initial rows to skip in each file (default: 0).",
    )
    parser.add_argument(
        "--method",
        default=METHOD_FOCUSED_REPRO_DEFAULT,
        choices=list(METHOD_CHOICES),
        help=(
            "Estimation method (default: focused_repro_default). "
            "Use legacy_sample_all for historical script behavior."
        ),
    )
    parser.add_argument(
        "--target-year",
        type=int,
        default=2024,
        help=(
            "Target year placeholder for future year-conditional methods "
            "(default: 2024)."
        ),
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    paths = [Path(p) for p in args.files]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        parser.error(f"Missing files: {', '.join(missing)}")

    stats, parse_stats = compute_parameters(
        paths,
        price_index=args.price_index,
        delimiter=args.delimiter,
        skip_rows=args.skip_rows,
        method=args.method,
        target_year=args.target_year,
    )

    if stats.count == 0:
        raise SystemExit("No valid prices found; cannot compute parameters.")

    mu = stats.mean
    std_mode = _std_mode_for_method(args.method)
    sigma = stats.std(std_mode=std_mode)

    print("Computed log-normal parameters from PPD data")
    print(f"Files: {len(paths)}")
    print(f"Total rows read: {parse_stats.total_rows}")
    if args.skip_rows:
        print(f"Rows skipped per file: {args.skip_rows}")
    print(f"Rows missing required fields: {parse_stats.rows_missing_required_fields}")
    print(f"Valid prices: {parse_stats.valid_price_rows}")
    print(f"Invalid/empty price rows: {parse_stats.invalid_price_rows}")
    print(f"Invalid transfer-year rows: {parse_stats.invalid_transfer_year_rows}")
    print(f"Rows filtered by non-A status: {parse_stats.filtered_non_a_status_rows}")
    print(f"Rows used for estimation: {parse_stats.used_rows}")
    print(f"Method: {args.method}")
    print(f"Method details: {_method_details(args.method)}")
    print(f"Std mode: {std_mode}")
    print(f"Target year parameter: {args.target_year}")
    print()
    print(f"HOUSE_PRICES_SCALE = {format_float(mu)}")
    print(f"HOUSE_PRICES_SHAPE = {format_float(sigma)}")


if __name__ == "__main__":
    main()
