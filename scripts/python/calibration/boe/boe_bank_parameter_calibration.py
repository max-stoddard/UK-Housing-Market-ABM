#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the locked BoE bank-parameter calibration and write the evidence bundle.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

from scripts.python.helpers.boe.bank_parameters import build_method_search_output
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir


ONS_FAMILIES_HOUSEHOLDS_2024_URL = (
    "https://www.ons.gov.uk/peoplepopulationandcommunity/birthsdeathsandmarriages/"
    "families/bulletins/familiesandhouseholds/2024"
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the locked BoE bank-parameter calibration and write evidence CSVs.",
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
        required=True,
        help="Output directory for evidence CSVs and machine-readable summary artifacts.",
    )
    return parser


def _write_monthly_series_csv(
    output_path: Path,
    observations,
    *,
    value_header: str,
) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["month_end", value_header])
        for item in observations:
            writer.writerow([item.observation_date.isoformat(), item.value])


def _write_delta_panel_csv(output_path: Path, rows) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "month_end",
                "spread_fraction",
                "credit_per_household",
                "delta_spread_fraction",
                "delta_credit_per_household",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["month_end"],
                    row["spread_fraction"],
                    row["credit_per_household"],
                    row["delta_spread_fraction"],
                    row["delta_credit_per_household"],
                ]
            )


def _write_ons_households_csv(output_path: Path, households: float, *, target_year: int) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "metric",
                "value",
                "units",
                "target_year",
                "source_url",
                "source_label",
            ]
        )
        writer.writerow(
            [
                "UK households denominator",
                int(households),
                "households",
                target_year,
                ONS_FAMILIES_HOUSEHOLDS_2024_URL,
                "ONS Families and households in the UK: 2024 bulletin",
            ]
        )


def _write_summary_csv(output_path: Path, search_output) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "parameter_key",
                "selected_value",
                "candidate_id",
                "window_label",
                "method_label",
                "rationale",
            ]
        )
        for candidate in search_output.candidates:
            if not candidate.selected:
                continue
            writer.writerow(
                [
                    candidate.parameter_key,
                    candidate.value,
                    candidate.candidate_id,
                    candidate.window_label,
                    candidate.method_label,
                    candidate.rationale,
                ]
            )
        writer.writerow([])
        writer.writerow(
            [
                "parameter_key",
                "rejected_value",
                "candidate_id",
                "window_label",
                "method_label",
                "rationale",
            ]
        )
        for candidate in search_output.candidates:
            if candidate.selected:
                continue
            writer.writerow(
                [
                    candidate.parameter_key,
                    candidate.value,
                    candidate.candidate_id,
                    candidate.window_label,
                    candidate.method_label,
                    candidate.rationale,
                ]
            )


def _write_summary_json(output_path: Path, search_output) -> None:
    selected = {
        candidate.parameter_key: {
            "value": candidate.value,
            "candidateId": candidate.candidate_id,
            "windowLabel": candidate.window_label,
            "methodLabel": candidate.method_label,
            "rationale": candidate.rationale,
        }
        for candidate in search_output.candidates
        if candidate.selected
    }
    rejected = [
        {
            "parameterKey": candidate.parameter_key,
            "value": candidate.value,
            "candidateId": candidate.candidate_id,
            "windowLabel": candidate.window_label,
            "methodLabel": candidate.method_label,
            "rationale": candidate.rationale,
        }
        for candidate in search_output.candidates
        if not candidate.selected
    ]
    payload = {
        "targetYear": search_output.target_year,
        "onsHouseholds": int(search_output.ons_households),
        "selectedParameters": selected,
        "rejectedDiagnostics": rejected,
        "evidenceFiles": {
            "bankRateHistoryInputCsv": "BoEBankRateHistoryInput.csv",
            "bankRateMonthlyCsv": "BoEBankRate2024Monthly.csv",
            "housingToolsSpreadMonthlyCsv": "BoEHousingToolsSpreadMonthly.csv",
            "housingToolsSpread2024Csv": "BoEHousingToolsSpread2024Monthly.csv",
            "mortgageRateProxyCsv": "BoEMortgageRateProxy2024Monthly.csv",
            "vtuzInputCsv": "BoEVTUZGrossLendingInput.csv",
            "creditSupplyPerHouseholdCsv": "BoEVTUZCreditSupplyPerHousehold2024Monthly.csv",
            "deltaPanelFullCsv": "BoEVTUZSpreadAlignedDeltas1995To2024.csv",
            "deltaPanelTargetYearCsv": "BoEVTUZSpreadAlignedDeltas2024.csv",
            "onsHouseholdsCsv": "OnsHouseholds2024.csv",
            "summaryCsv": "BoeBankParameterCalibrationSummary.csv",
        },
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _copy_if_needed(source_path: Path, destination_path: Path) -> None:
    if source_path.resolve() == destination_path.resolve():
        return
    shutil.copyfile(source_path, destination_path)


def run_calibration(
    *,
    bank_rate_csv: Path,
    housing_tools_xlsx: Path,
    vtuz_csv: Path,
    ons_households: float,
    target_year: int,
    output_dir: Path,
) -> dict[str, str]:
    output_dir = ensure_output_dir(output_dir)
    search_output = build_method_search_output(
        bank_rate_csv=bank_rate_csv,
        housing_tools_xlsx=housing_tools_xlsx,
        vtuz_csv=vtuz_csv,
        ons_households=ons_households,
        target_year=target_year,
    )

    _copy_if_needed(bank_rate_csv, output_dir / "BoEBankRateHistoryInput.csv")
    _copy_if_needed(vtuz_csv, output_dir / "BoEVTUZGrossLendingInput.csv")
    _write_monthly_series_csv(
        output_dir / "BoEBankRate2024Monthly.csv",
        search_output.bank_rate_monthly,
        value_header="bank_rate_fraction",
    )
    _write_monthly_series_csv(
        output_dir / "BoEHousingToolsSpreadMonthly.csv",
        search_output.housing_tools_spread_monthly,
        value_header="spread_percentage_points",
    )
    _write_monthly_series_csv(
        output_dir / "BoEHousingToolsSpread2024Monthly.csv",
        search_output.housing_tools_spread_target_year,
        value_header="spread_percentage_points",
    )
    _write_monthly_series_csv(
        output_dir / "BoEMortgageRateProxy2024Monthly.csv",
        search_output.mortgage_rate_proxy_target_year,
        value_header="mortgage_rate_fraction",
    )
    _write_monthly_series_csv(
        output_dir / "BoEVTUZCreditSupplyPerHousehold2024Monthly.csv",
        search_output.credit_supply_target_year,
        value_header="credit_supply_pounds_per_household",
    )
    _write_delta_panel_csv(
        output_dir / "BoEVTUZSpreadAlignedDeltas1995To2024.csv",
        search_output.delta_panel_full,
    )
    _write_delta_panel_csv(
        output_dir / "BoEVTUZSpreadAlignedDeltas2024.csv",
        search_output.delta_panel_target_year,
    )
    _write_ons_households_csv(
        output_dir / "OnsHouseholds2024.csv",
        ons_households,
        target_year=target_year,
    )
    _write_summary_csv(output_dir / "BoeBankParameterCalibrationSummary.csv", search_output)
    _write_summary_json(output_dir / "BoeBankParameterCalibrationSummary.json", search_output)

    return {
        "CENTRAL_BANK_INITIAL_BASE_RATE": format_float(
            search_output.selected_value("CENTRAL_BANK_INITIAL_BASE_RATE")
        ),
        "BANK_INITIAL_RATE": format_float(
            search_output.selected_value("BANK_INITIAL_RATE")
        ),
        "BANK_D_INTEREST_D_DEMAND": format_float(
            search_output.selected_value("BANK_D_INTEREST_D_DEMAND")
        ),
        "BANK_INITIAL_CREDIT_SUPPLY": format_float(
            search_output.selected_value("BANK_INITIAL_CREDIT_SUPPLY")
        ),
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    selected_values = run_calibration(
        bank_rate_csv=Path(args.bank_rate_csv),
        housing_tools_xlsx=Path(args.housing_tools_xlsx),
        vtuz_csv=Path(args.vtuz_csv),
        ons_households=args.ons_households,
        target_year=args.target_year,
        output_dir=Path(args.output_dir),
    )
    for key in (
        "CENTRAL_BANK_INITIAL_BASE_RATE",
        "BANK_INITIAL_RATE",
        "BANK_D_INTEREST_D_DEMAND",
        "BANK_INITIAL_CREDIT_SUPPLY",
    ):
        print(f"{key} = {selected_values[key]}")


if __name__ == "__main__":
    main()
