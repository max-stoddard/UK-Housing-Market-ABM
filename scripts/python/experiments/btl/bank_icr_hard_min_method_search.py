#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rank retained public-proxy BANK_ICR_HARD_MIN candidates for the 2024 v4.10 recalibration.

Latest experiment findings (run on April 17, 2026):
  - Source bundle:
    - input-data-versions/calibration-evidence/bank-icr-hard-min-v4.10/BankIcrHardMinPublicSources.csv
  - Decision thresholds:
    - 1.25, 1.25, 1.30, 1.30, 1.40, 1.40, 1.45, 1.45
  - Context-only observed UK Finance ICRs:
    - 1.91, 1.96, 1.95, 2.01
  - Selected default:
    - literal_standard_floor_125 = 1.25
  - Rejected diagnostics:
    - stress_mapped_floor = 1.22
    - cross_segment_mean = 1.35
  - Interpretation:
    - Public 2024 evidence is sufficient to replace the unresolved legacy 1.2
      note with a defensible lender-side proxy, but not to identify a market-
      weighted threshold.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scripts.python.helpers.btl.bank_icr_hard_min import (
    build_bank_icr_hard_min_method_search_output,
    resolve_bank_icr_hard_min_config_path,
    resolve_bank_icr_hard_min_source_csv_path,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir


METHOD_SEARCH_FILE_NAME = "BankIcrHardMinMethodSearch.csv"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank retained public-proxy BANK_ICR_HARD_MIN calibration candidates.",
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
        "--output-dir",
        default=None,
        help="Optional output directory for method-search CSV export.",
    )
    return parser


def _write_csv(output_dir: Path, search_output) -> Path:
    output_path = output_dir / METHOD_SEARCH_FILE_NAME
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "parameter_key",
                "candidate_id",
                "rank",
                "selected",
                "raw_value",
                "rounded_value",
                "method_label",
                "rationale",
                "target_year",
                "bank_initial_rate",
                "representative_stress_rate_fraction",
                "decision_icr_fractions",
                "context_icr_fractions",
                "excluded_document_labels",
            ]
        )
        for candidate in search_output.candidates:
            writer.writerow(
                [
                    candidate.parameter_key,
                    candidate.candidate_id,
                    candidate.rank,
                    str(candidate.selected).lower(),
                    candidate.raw_value,
                    candidate.value,
                    candidate.method_label,
                    candidate.rationale,
                    search_output.target_year,
                    search_output.bank_initial_rate,
                    search_output.representative_stress_rate_fraction,
                    ",".join(
                        format_float(value, decimals=4)
                        for value in search_output.decision_icr_fractions
                    ),
                    ",".join(
                        format_float(value, decimals=4)
                        for value in search_output.context_icr_fractions
                    ),
                    ",".join(row.document_label for row in search_output.excluded_rows),
                ]
            )
    return output_path


def main() -> None:
    args = build_arg_parser().parse_args()
    try:
        source_csv = resolve_bank_icr_hard_min_source_csv_path(args.source_csv)
        config_path = resolve_bank_icr_hard_min_config_path(args.config_path)
        search_output = build_bank_icr_hard_min_method_search_output(
            source_csv=source_csv,
            config_path=config_path,
            target_year=args.target_year,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))

    print("BANK_ICR_HARD_MIN public-proxy method search")
    print(f"Source CSV: {source_csv}")
    print(f"Config path: {config_path}")
    print(f"Target year: {search_output.target_year}")
    print(f"BANK_INITIAL_RATE diagnostic: {format_float(search_output.bank_initial_rate)}")
    print(
        "Decision ICR thresholds: "
        + ", ".join(format_float(value, decimals=2) for value in search_output.decision_icr_fractions)
    )
    print(
        "Context-only UK Finance ICRs: "
        + ", ".join(format_float(value, decimals=2) for value in search_output.context_icr_fractions)
    )
    print("")
    print("Candidate\tRaw\tRounded\tSelected")
    for candidate in search_output.candidates:
        status = "selected" if candidate.selected else "rejected"
        print(
            f"{candidate.candidate_id}\t"
            f"{format_float(candidate.raw_value)}\t"
            f"{format_float(candidate.value)}\t"
            f"{status}"
        )

    if args.output_dir:
        output_dir = ensure_output_dir(args.output_dir)
        output_path = _write_csv(output_dir, search_output)
        print("")
        print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()

