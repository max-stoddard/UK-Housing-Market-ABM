#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rank retained public-proxy BANK_AGE_LIMIT candidates for the 2024 v4.9 recalibration.

Latest experiment findings (run on April 17, 2026):
  - Source bundle:
    - input-data-versions/calibration-evidence/bank-age-limit-v4.9/BankAgeLimitPublicSources.csv
  - Explicit origination caps: 70, 75, 75
  - Explicit repay-by caps: 80, 75, 75, 75, 80
  - Selected default:
    - conservative_mainstream_mode = 75
  - Rejected diagnostics:
    - hybrid_midpoint_round = 75
    - repay_cap_mean_round = 77
  - Interpretation:
    - Public 2024 evidence is sufficient to reject 65, but not to identify one
      direct market-wide maturity-age scalar, so the conservative mode of the
      explicit public thresholds is the least misleading proxy for the
      overloaded model parameter.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scripts.python.helpers.boe.bank_age_limit import (
    build_bank_age_limit_method_search_output,
    resolve_bank_age_limit_source_csv_path,
)
from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir


METHOD_SEARCH_FILE_NAME = "BankAgeLimitMethodSearch.csv"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rank retained public-proxy BANK_AGE_LIMIT calibration candidates.",
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
                "explicit_origination_caps",
                "explicit_repay_caps",
                "combined_explicit_thresholds",
                "origination_cap_mean",
                "repay_cap_mean",
                "hybrid_midpoint_raw",
                "target_year",
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
                    ",".join(str(value) for value in search_output.explicit_origination_caps),
                    ",".join(str(value) for value in search_output.explicit_repay_caps),
                    ",".join(str(value) for value in search_output.combined_explicit_thresholds),
                    search_output.origination_cap_mean,
                    search_output.repay_cap_mean,
                    search_output.hybrid_midpoint_raw,
                    search_output.target_year,
                ]
            )
    return output_path


def main() -> None:
    args = build_arg_parser().parse_args()
    try:
        source_csv = resolve_bank_age_limit_source_csv_path(args.source_csv)
        search_output = build_bank_age_limit_method_search_output(
            source_csv=source_csv,
            target_year=args.target_year,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))

    print("BANK_AGE_LIMIT public-proxy method search")
    print(f"Source CSV: {source_csv}")
    print(f"Target year: {search_output.target_year}")
    print(
        "Explicit origination caps: "
        + ", ".join(str(value) for value in search_output.explicit_origination_caps)
    )
    print(
        "Explicit non-BTL repay caps: "
        + ", ".join(str(value) for value in search_output.explicit_repay_caps)
    )
    print("")
    print("Candidate\tRaw\tRounded\tSelected")
    for candidate in search_output.candidates:
        status = "selected" if candidate.selected else "rejected"
        print(
            f"{candidate.candidate_id}\t"
            f"{format_float(candidate.raw_value)}\t"
            f"{candidate.value}\t"
            f"{status}"
        )

    if args.output_dir:
        output_dir = ensure_output_dir(args.output_dir)
        output_path = _write_csv(output_dir, search_output)
        print("")
        print(f"Wrote: {output_path}")


if __name__ == "__main__":
    main()
