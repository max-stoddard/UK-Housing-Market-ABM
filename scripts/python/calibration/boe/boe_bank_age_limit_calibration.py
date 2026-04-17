#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run the retained public-proxy BANK_AGE_LIMIT calibration for v4.9.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

from scripts.python.helpers.boe.bank_age_limit import (
    BANK_AGE_LIMIT_KEY,
    DEFAULT_METHOD,
    METHOD_CHOICES,
    build_bank_age_limit_method_search_output,
    resolve_bank_age_limit_source_csv_path,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir, repo_root


SOURCE_VALUES_FILE_NAME = "BankAgeLimitCalibrationSourceValues.csv"
SUMMARY_FILE_NAME = "BankAgeLimitCalibrationSummary.json"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the retained public-proxy BANK_AGE_LIMIT calibration.",
    )
    parser.add_argument(
        "--source-csv",
        default=None,
        help=(
            "Optional explicit retained public-source CSV. Defaults to the tracked "
            "bank-age-limit-v4.9 evidence bundle."
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
        "parameterKey": BANK_AGE_LIMIT_KEY,
        "selectedConfigValues": {
            BANK_AGE_LIMIT_KEY: candidate.value,
        },
        "targetYear": search_output.target_year,
        "sourcePath": search_output.source_path,
        "method": {
            "candidateId": candidate.candidate_id,
            "methodLabel": candidate.method_label,
            "rawValue": candidate.raw_value,
            "roundedValue": candidate.value,
            "selectedByDefault": candidate.selected,
            "rationale": candidate.rationale,
        },
        "diagnostics": {
            "explicitOriginationCaps": list(search_output.explicit_origination_caps),
            "explicitRepayCaps": list(search_output.explicit_repay_caps),
            "combinedExplicitThresholds": list(search_output.combined_explicit_thresholds),
            "originationCapMean": search_output.origination_cap_mean,
            "repayCapMean": search_output.repay_cap_mean,
            "hybridMidpointRaw": search_output.hybrid_midpoint_raw,
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
                "provider",
                "application_age_cap",
                "repay_by_cap",
                "source_url",
                "source_as_of",
                "notes",
                "used_in_origination_vector",
                "used_in_repay_vector",
            ],
        )
        writer.writeheader()
        for source in search_output.sources:
            writer.writerow(
                {
                    **asdict(source),
                    "used_in_origination_vector": str(source.application_age_cap is not None).lower(),
                    "used_in_repay_vector": "true",
                }
            )


def run_calibration(
    *,
    source_csv: Path,
    target_year: int,
    method: str = DEFAULT_METHOD,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    search_output = build_bank_age_limit_method_search_output(
        source_csv=source_csv,
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
        source_csv = resolve_bank_age_limit_source_csv_path(args.source_csv)
        summary = run_calibration(
            source_csv=source_csv,
            target_year=args.target_year,
            method=args.method,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError, StopIteration) as exc:
        raise SystemExit(str(exc))

    diagnostics = summary["diagnostics"]
    selected = summary["method"]

    print("Calibrated BANK_AGE_LIMIT from retained public-source proxy evidence")
    print(f"Source CSV: {_display_path(Path(summary['sourcePath']))}")
    print(f"Target year: {summary['targetYear']}")
    print(f"Method: {selected['candidateId']}")
    print(
        "Explicit origination caps: "
        + ", ".join(str(value) for value in diagnostics["explicitOriginationCaps"])
    )
    print(
        "Explicit non-BTL repay caps: "
        + ", ".join(str(value) for value in diagnostics["explicitRepayCaps"])
    )
    print("Rejected alternatives:")
    for candidate in diagnostics["rejectedCandidates"]:
        print(f"  - {candidate['candidateId']} = {candidate['roundedValue']}")
    print("")
    print(f"{BANK_AGE_LIMIT_KEY} = {summary['selectedConfigValues'][BANK_AGE_LIMIT_KEY]}")
    print(f"Selected raw value: {format_float(float(selected['rawValue']))}")

    if args.output_dir:
        output_root = ensure_output_dir(args.output_dir)
        print("")
        print(f"Wrote: {_display_path(output_root / SOURCE_VALUES_FILE_NAME)}")
        print(f"Wrote: {_display_path(output_root / SUMMARY_FILE_NAME)}")


if __name__ == "__main__":
    main()
