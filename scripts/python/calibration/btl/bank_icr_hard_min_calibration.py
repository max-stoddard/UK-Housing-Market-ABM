#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the retained public-proxy BANK_ICR_HARD_MIN calibration for v4.10.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from scripts.python.helpers.btl.bank_icr_hard_min import (
    BANK_ICR_HARD_MIN_KEY,
    DEFAULT_METHOD,
    METHOD_CHOICES,
    build_bank_icr_hard_min_method_search_output,
    resolve_bank_icr_hard_min_config_path,
    resolve_bank_icr_hard_min_source_csv_path,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir, repo_root


SOURCE_VALUES_FILE_NAME = "BankIcrHardMinCalibrationSourceValues.csv"
SUMMARY_FILE_NAME = "BankIcrHardMinCalibrationSummary.json"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the retained public-proxy BANK_ICR_HARD_MIN calibration.",
    )
    parser.add_argument(
        "--source-csv",
        default=None,
        help=(
            "Optional explicit retained public-source CSV. Defaults to the tracked "
            "bank-icr-hard-min-v4.10 evidence bundle."
        ),
    )
    parser.add_argument(
        "--config-path",
        default=None,
        help=(
            "Optional config.properties path used to read BANK_INITIAL_RATE for the "
            "rejected stress-mapped diagnostic."
        ),
    )
    parser.add_argument(
        "--target-year",
        type=int,
        default=2024,
        help="Target calendar year represented by the public-source proxy (default: 2024).",
    )
    parser.add_argument(
        "--method",
        default=DEFAULT_METHOD,
        choices=METHOD_CHOICES,
        help=f"Calibration method to promote (default: {DEFAULT_METHOD}).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Optional output directory for "
            f"{SOURCE_VALUES_FILE_NAME} and {SUMMARY_FILE_NAME}."
        ),
    )
    return parser


def build_calibration_summary(search_output, *, method: str) -> dict[str, object]:
    candidate = next(
        item for item in search_output.candidates if item.candidate_id == method
    )
    return {
        "parameterKey": BANK_ICR_HARD_MIN_KEY,
        "selectedConfigValues": {
            BANK_ICR_HARD_MIN_KEY: candidate.value,
        },
        "targetYear": search_output.target_year,
        "sourcePath": search_output.source_path,
        "configPath": search_output.config_path,
        "method": {
            "candidateId": candidate.candidate_id,
            "methodLabel": candidate.method_label,
            "rawValue": candidate.raw_value,
            "roundedValue": candidate.value,
            "selectedByDefault": candidate.selected,
            "rationale": candidate.rationale,
        },
        "diagnostics": {
            "bankInitialRate": search_output.bank_initial_rate,
            "representativeStressRateFraction": search_output.representative_stress_rate_fraction,
            "decisionIcrFractions": list(search_output.decision_icr_fractions),
            "contextIcrFractions": list(search_output.context_icr_fractions),
            "excludedRows": [asdict(item) for item in search_output.excluded_rows],
            "rejectedCandidates": [
                {
                    "candidateId": item.candidate_id,
                    "rawValue": item.raw_value,
                    "roundedValue": item.value,
                    "methodLabel": item.method_label,
                    "rationale": item.rationale,
                }
                for item in search_output.candidates
                if item.candidate_id != method
            ],
        },
        "sourceRows": [asdict(item) for item in search_output.sources],
    }


def _write_source_values_csv(output_path: Path, search_output) -> None:
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "role",
                "document_path",
                "document_label",
                "source_as_of",
                "publisher",
                "segment",
                "icr_fraction",
                "stress_rate_fraction",
                "notes",
                "included_in_decision_pool",
            ],
        )
        writer.writeheader()
        for source in search_output.sources:
            writer.writerow(
                {
                    **asdict(source),
                    "included_in_decision_pool": str(source.role == "decision").lower(),
                }
            )


def run_calibration(
    *,
    source_csv: Path,
    config_path: Path,
    target_year: int,
    method: str = DEFAULT_METHOD,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    search_output = build_bank_icr_hard_min_method_search_output(
        source_csv=source_csv,
        config_path=config_path,
        target_year=target_year,
    )
    if method not in METHOD_CHOICES:
        raise ValueError(f"Unsupported method: {method}")
    summary = build_calibration_summary(search_output, method=method)
    if output_dir is not None:
        output_root = ensure_output_dir(output_dir)
        _write_source_values_csv(output_root / SOURCE_VALUES_FILE_NAME, search_output)
        (output_root / SUMMARY_FILE_NAME).write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )
    return summary


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(repo_root()))
    except ValueError:
        return str(path)


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        source_csv = resolve_bank_icr_hard_min_source_csv_path(args.source_csv)
        config_path = resolve_bank_icr_hard_min_config_path(args.config_path)
        summary = run_calibration(
            source_csv=source_csv,
            config_path=config_path,
            target_year=args.target_year,
            method=args.method,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError, StopIteration) as exc:
        raise SystemExit(str(exc))

    diagnostics = summary["diagnostics"]
    selected = summary["method"]

    print("Calibrated BANK_ICR_HARD_MIN from retained public-proxy evidence")
    print(f"Source CSV: {_display_path(Path(summary['sourcePath']))}")
    print(f"Config path: {_display_path(Path(summary['configPath']))}")
    print(f"Target year: {summary['targetYear']}")
    print(f"Method: {selected['candidateId']}")
    print(
        "Decision ICR thresholds: "
        + ", ".join(
            format_float(float(value), decimals=2)
            for value in diagnostics["decisionIcrFractions"]
        )
    )
    print(
        "Context-only UK Finance ICRs: "
        + ", ".join(
            format_float(float(value), decimals=2)
            for value in diagnostics["contextIcrFractions"]
        )
    )
    print(f"BANK_INITIAL_RATE diagnostic: {format_float(float(diagnostics['bankInitialRate']))}")
    print("Rejected alternatives:")
    for candidate in diagnostics["rejectedCandidates"]:
        print(
            f"  - {candidate['candidateId']} = "
            f"{format_float(float(candidate['roundedValue']), decimals=2)}"
        )
    print("")
    print(
        f"{BANK_ICR_HARD_MIN_KEY} = "
        f"{format_float(float(summary['selectedConfigValues'][BANK_ICR_HARD_MIN_KEY]), decimals=2)}"
    )
    print(f"Selected raw value: {format_float(float(selected['rawValue']))}")

    if args.output_dir:
        output_root = ensure_output_dir(args.output_dir)
        print("")
        print(f"Wrote: {_display_path(output_root / SOURCE_VALUES_FILE_NAME)}")
        print(f"Wrote: {_display_path(output_root / SUMMARY_FILE_NAME)}")


if __name__ == "__main__":
    main()

