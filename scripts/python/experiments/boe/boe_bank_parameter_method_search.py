#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rank BoE bank-parameter calibration candidates against the agreed 2024 defaults.

Latest experiment findings (run on April 15, 2026):
  - Inputs:
    - Bank Rate history: private-datasets/boe/BoE - Bank Rate history and data.csv
    - Mortgage spread workbook: private-datasets/boe/housing-tools.xlsx
    - VTUZ gross-lending CSV: official BoE database export through 2024-12
    - ONS households denominator: 28,600,000
  - Selected defaults:
    - CENTRAL_BANK_INITIAL_BASE_RATE = 0.051083333333333335
    - BANK_INITIAL_RATE = 0.05649531436698348
    - BANK_INITIAL_CREDIT_SUPPLY = 704.9388111888112
    - BANK_D_INTEREST_D_DEMAND = 5.471987263431394e-07
  - Rejected diagnostic:
    - BANK_D_INTEREST_D_DEMAND 2024-only fit = -5.91912917550825e-06
  - Interpretation:
    - The static initial parameters are stable under the agreed 2024 full-year proxy,
      while the demand-response coefficient is only defensible on the longer pre-2025
      overlap because the 2024-only delta fit is negative.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scripts.python.helpers.boe.bank_parameters import build_method_search_output
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank BoE bank-parameter calibration candidates and write diagnostics.",
    )
    parser.add_argument(
        "--bank-rate-csv",
        required=True,
        help="Path to the BoE Bank Rate history CSV.",
    )
    parser.add_argument(
        "--housing-tools-xlsx",
        required=True,
        help="Path to the BoE housing-tools workbook.",
    )
    parser.add_argument(
        "--vtuz-csv",
        required=True,
        help="Path to the BoE VTUZ gross-lending CSV export.",
    )
    parser.add_argument(
        "--ons-households",
        required=True,
        type=float,
        help="ONS household denominator used to convert credit supply to pounds per household.",
    )
    parser.add_argument(
        "--target-year",
        type=int,
        default=2024,
        help="Static-parameter target year (default: 2024).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory for method-search CSV export.",
    )
    return parser


def _write_csv(output_dir: Path, search_output) -> Path:
    output_path = output_dir / "BoeBankParameterMethodSearch.csv"
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "parameter_key",
                "candidate_id",
                "rank",
                "selected",
                "value",
                "window_label",
                "method_label",
                "rationale",
            ]
        )
        for candidate in search_output.candidates:
            writer.writerow(
                [
                    candidate.parameter_key,
                    candidate.candidate_id,
                    candidate.rank,
                    str(candidate.selected).lower(),
                    candidate.value,
                    candidate.window_label,
                    candidate.method_label,
                    candidate.rationale,
                ]
            )
    return output_path


def main() -> None:
    args = build_arg_parser().parse_args()
    search_output = build_method_search_output(
        bank_rate_csv=Path(args.bank_rate_csv),
        housing_tools_xlsx=Path(args.housing_tools_xlsx),
        vtuz_csv=Path(args.vtuz_csv),
        ons_households=args.ons_households,
        target_year=args.target_year,
    )

    print("BoE bank-parameter method search")
    print(f"Target year: {args.target_year}")
    print(f"ONS households: {int(args.ons_households):,}")
    print("")
    for parameter_key in (
        "CENTRAL_BANK_INITIAL_BASE_RATE",
        "BANK_INITIAL_RATE",
        "BANK_D_INTEREST_D_DEMAND",
        "BANK_INITIAL_CREDIT_SUPPLY",
    ):
        print(parameter_key)
        for candidate in search_output.candidates:
            if candidate.parameter_key != parameter_key:
                continue
            status = "selected" if candidate.selected else "rejected"
            print(
                "  "
                f"[{status}] rank={candidate.rank} value={format_float(candidate.value)} "
                f"window={candidate.window_label} method={candidate.method_label}"
            )
        print("")

    if args.output_dir:
        output_dir = ensure_output_dir(args.output_dir)
        output_path = _write_csv(output_dir, search_output)
        print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
