#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a weighted FRS 2023-24 HRP age distribution for model calibration.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from scripts.python.helpers.common.paths import ensure_output_dir, repo_root
from scripts.python.helpers.was.csv_write import write_rows


DATA_AGE_DISTRIBUTION_KEY = "DATA_AGE_DISTRIBUTION"
DEFAULT_HOUSEHOLD_CSV = Path("private-datasets/frs/23-24/househol.csv")
HHAGEGRP_COLUMN = "hhagegrp"
HHAGEGR4_COLUMN = "hhageGR4"
WEIGHT_COLUMN = "gross4"
OUTPUT_FILE_NAME = "Age15-FRS-2023-24-Weighted.csv"
SOURCE_VALUES_FILE_NAME = "FrsAgeDistributionSourceValues.csv"
SUMMARY_FILE_NAME = "FrsAgeDistributionSummary.json"
MISSING_CODE_MIN = -9
MISSING_CODE_MAX = -1
INTEGRAL_TOLERANCE = 1.0e-9


@dataclass(frozen=True)
class AgeBand:
    code: int
    lower_edge: float
    upper_edge: float
    source_code: int | None = None
    source_share: float = 1.0

    @property
    def midpoint(self) -> float:
        return (self.lower_edge + self.upper_edge) / 2.0

    @property
    def width(self) -> float:
        return self.upper_edge - self.lower_edge


@dataclass(frozen=True)
class AgeDistributionRow:
    age_code: int
    source_age_column: str
    source_age_code: int
    source_share: float
    lower_edge: float
    upper_edge: float
    midpoint: float
    unweighted_count: int
    weight_sum: float
    mass: float
    density: float


FRS_HHAGEGRP_BANDS: tuple[AgeBand, ...] = (
    AgeBand(1, 16.0, 20.0),
    AgeBand(2, 20.0, 25.0),
    AgeBand(3, 25.0, 30.0),
    AgeBand(4, 30.0, 35.0),
    AgeBand(5, 35.0, 40.0),
    AgeBand(6, 40.0, 45.0),
    AgeBand(7, 45.0, 50.0),
    AgeBand(8, 50.0, 55.0),
    AgeBand(9, 55.0, 60.0),
    AgeBand(10, 60.0, 65.0),
    AgeBand(11, 65.0, 70.0),
    AgeBand(12, 70.0, 75.0),
    AgeBand(13, 75.0, 80.0),
    AgeBand(14, 80.0, 85.0),
    AgeBand(15, 85.0, 95.0),
)
FRS_HHAGEGRP_BAND_BY_CODE = {band.code: band for band in FRS_HHAGEGRP_BANDS}

FRS_HHAGEGR4_BANDS: tuple[AgeBand, ...] = (
    AgeBand(1, 16.0, 20.0, source_code=1),
    AgeBand(2, 20.0, 25.0, source_code=2),
    AgeBand(3, 25.0, 30.0, source_code=3),
    AgeBand(4, 30.0, 35.0, source_code=4),
    AgeBand(5, 35.0, 40.0, source_code=5),
    AgeBand(6, 40.0, 45.0, source_code=6),
    AgeBand(7, 45.0, 50.0, source_code=7),
    AgeBand(8, 50.0, 55.0, source_code=8),
    AgeBand(9, 55.0, 60.0, source_code=9),
    AgeBand(10, 60.0, 65.0, source_code=10),
    AgeBand(11, 65.0, 70.0, source_code=11),
    AgeBand(12, 70.0, 75.0, source_code=12),
    AgeBand(13, 75.0, 80.0, source_code=13, source_share=0.25),
    AgeBand(14, 80.0, 85.0, source_code=13, source_share=0.25),
    AgeBand(15, 85.0, 95.0, source_code=13, source_share=0.50),
)
FRS_HHAGEGR4_BAND_BY_CODE = {band.code: band for band in FRS_HHAGEGR4_BANDS}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate weighted FRS 2023-24 HRP age distribution."
    )
    parser.add_argument(
        "--household-csv",
        default=None,
        help="Optional FRS household CSV path. Defaults to private-datasets/frs/23-24/househol.csv.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional directory for Age15-FRS-2023-24-Weighted.csv. Defaults to tmp/frs/.",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help=(
            "Optional directory for aggregate source-value and summary evidence. "
            "Raw private FRS rows are not written."
        ),
    )
    return parser


def resolve_household_csv(path: str | Path | None, *, root: Path | None = None) -> Path:
    candidate = Path(path).expanduser() if path else DEFAULT_HOUSEHOLD_CSV
    base_root = root if root is not None else repo_root()
    resolved = candidate if candidate.is_absolute() else base_root / candidate
    if not resolved.exists():
        raise FileNotFoundError(f"Missing FRS household CSV: {resolved}")
    return resolved.resolve()


def default_frs_output_dir() -> Path:
    return repo_root() / "tmp" / "frs"


def load_frs_age_weight_data(household_csv: Path) -> pd.DataFrame:
    return pd.read_csv(
        household_csv,
        usecols=[HHAGEGRP_COLUMN, HHAGEGR4_COLUMN, WEIGHT_COLUMN],
    )


def _valid_age_mask(prepared: pd.DataFrame, age_column: str, valid_age_codes: set[int]) -> pd.Series:
    missing_code_mask = (
        prepared[age_column].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
        | prepared[WEIGHT_COLUMN].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
    )
    return (
        prepared[age_column].isin(valid_age_codes)
        & prepared[WEIGHT_COLUMN].notna()
        & (prepared[WEIGHT_COLUMN] > 0.0)
        & ~missing_code_mask
    )


def prepare_valid_age_rows(
    raw_data: pd.DataFrame,
) -> tuple[pd.DataFrame, tuple[AgeBand, ...], str, dict[str, int | str]]:
    missing_columns = [
        column
        for column in (HHAGEGRP_COLUMN, WEIGHT_COLUMN)
        if column not in raw_data.columns
    ]
    if missing_columns:
        raise ValueError(f"FRS household data missing required columns: {missing_columns}")

    prepared = raw_data.copy()
    raw_age_values = sorted(str(value) for value in prepared[HHAGEGRP_COLUMN].dropna().unique())
    prepared[HHAGEGRP_COLUMN] = pd.to_numeric(prepared[HHAGEGRP_COLUMN], errors="coerce")
    if HHAGEGR4_COLUMN in prepared.columns:
        prepared[HHAGEGR4_COLUMN] = pd.to_numeric(prepared[HHAGEGR4_COLUMN], errors="coerce")
    prepared[WEIGHT_COLUMN] = pd.to_numeric(prepared[WEIGHT_COLUMN], errors="coerce")

    valid_hhagegrp_mask = _valid_age_mask(
        prepared,
        HHAGEGRP_COLUMN,
        set(FRS_HHAGEGRP_BAND_BY_CODE),
    )
    age_column = HHAGEGRP_COLUMN
    band_scheme = FRS_HHAGEGRP_BANDS
    valid_mask = valid_hhagegrp_mask
    fallback_reason = ""
    if not valid_mask.any() and HHAGEGR4_COLUMN in prepared.columns:
        valid_hhagegr4_mask = _valid_age_mask(
            prepared,
            HHAGEGR4_COLUMN,
            set(range(1, 14)),
        )
        if valid_hhagegr4_mask.any():
            age_column = HHAGEGR4_COLUMN
            band_scheme = FRS_HHAGEGR4_BANDS
            valid_mask = valid_hhagegr4_mask
            fallback_reason = (
                "hhagegrp is anonymized/unusable in househol.csv; using populated "
                "hhageGR4 and splitting its 75+ tail uniformly across 75-80, 80-85, and 85-95."
            )
    valid = prepared.loc[valid_mask].copy()
    valid[age_column] = valid[age_column].astype(int)

    missing_code_mask = (
        prepared[age_column].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
        | prepared[WEIGHT_COLUMN].between(MISSING_CODE_MIN, MISSING_CODE_MAX)
    )
    valid_age_codes = set(
        FRS_HHAGEGRP_BAND_BY_CODE if age_column == HHAGEGRP_COLUMN else range(1, 14)
    )
    diagnostics = {
        "rawRows": int(len(prepared)),
        "validRows": int(len(valid)),
        "droppedRows": int(len(prepared) - len(valid)),
        "missingCodeRows": int(missing_code_mask.sum()),
        "invalidAgeRows": int((~prepared[age_column].isin(valid_age_codes)).sum()),
        "nonPositiveOrMissingWeightRows": int(
            (prepared[WEIGHT_COLUMN].isna() | (prepared[WEIGHT_COLUMN] <= 0.0)).sum()
        ),
        "ageColumn": age_column,
        "fallbackReason": fallback_reason,
    }
    if valid.empty:
        raise ValueError(
            "No valid FRS age rows after filtering. "
            f"Observed {HHAGEGRP_COLUMN} values before numeric parsing: {raw_age_values}. "
            "The requested 15-bin calibration requires a populated hhagegrp column."
        )
    return valid, band_scheme, age_column, diagnostics


def compute_weighted_age_distribution(
    valid_data: pd.DataFrame,
    band_scheme: tuple[AgeBand, ...] = FRS_HHAGEGRP_BANDS,
    age_column: str = HHAGEGRP_COLUMN,
) -> tuple[list[AgeDistributionRow], float]:
    total_weight = float(valid_data[WEIGHT_COLUMN].sum())
    if total_weight <= 0.0:
        raise ValueError("Total FRS weight must be positive.")

    rows: list[AgeDistributionRow] = []
    for band in band_scheme:
        source_code = band.source_code if band.source_code is not None else band.code
        mask = valid_data[age_column] == source_code
        weight_sum = float(valid_data.loc[mask, WEIGHT_COLUMN].sum()) * band.source_share
        mass = weight_sum / total_weight
        rows.append(
            AgeDistributionRow(
                age_code=band.code,
                source_age_column=age_column,
                source_age_code=source_code,
                source_share=band.source_share,
                lower_edge=band.lower_edge,
                upper_edge=band.upper_edge,
                midpoint=band.midpoint,
                unweighted_count=int(mask.sum()),
                weight_sum=weight_sum,
                mass=mass,
                density=mass / band.width,
            )
        )

    integral = sum(row.density * (row.upper_edge - row.lower_edge) for row in rows)
    if abs(integral - 1.0) > INTEGRAL_TOLERANCE:
        raise ValueError(f"FRS age-density integral must be 1.0, got {integral}")
    return rows, total_weight


def _distribution_csv_rows(rows: Iterable[AgeDistributionRow]) -> list[tuple[float, float, float]]:
    return [(row.lower_edge, row.upper_edge, row.density) for row in rows]


def _write_source_values_csv(path: Path, rows: Iterable[AgeDistributionRow]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "age_code",
                "source_age_column",
                "source_age_code",
                "source_share",
                "lower_edge",
                "upper_edge",
                "midpoint",
                "unweighted_count",
                "weight_sum",
                "mass",
                "density",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def run_age_distribution(
    *,
    household_csv: str | Path | None = None,
    output_dir: str | Path | None = None,
    evidence_dir: str | Path | None = None,
) -> dict[str, object]:
    resolved_csv = resolve_household_csv(household_csv)
    raw_data = load_frs_age_weight_data(resolved_csv)
    valid_data, band_scheme, age_column, diagnostics = prepare_valid_age_rows(raw_data)
    rows, total_weight = compute_weighted_age_distribution(valid_data, band_scheme, age_column)

    output_root = ensure_output_dir(output_dir, default_dir=default_frs_output_dir())
    output_path = output_root / OUTPUT_FILE_NAME
    write_rows(
        str(output_path),
        "# Age (lower edge), Age (upper edge), Probability\n",
        _distribution_csv_rows(rows),
    )

    integral = sum(row.density * (row.upper_edge - row.lower_edge) for row in rows)
    summary = {
        "parameterKey": DATA_AGE_DISTRIBUTION_KEY,
        "selectedConfigValues": {
            DATA_AGE_DISTRIBUTION_KEY: f"src/main/resources/{OUTPUT_FILE_NAME}",
        },
        "sourcePath": str(resolved_csv),
        "outputPath": str(output_path),
        "method": (
            "weighted FRS HRP age density using gross4 household grossing weights; "
            "hhagegrp is preferred when populated, otherwise hhageGR4 is used with "
            "the 75+ tail split uniformly into the requested 15-bin output"
        ),
        "columns": {
            "requestedAge": HHAGEGRP_COLUMN,
            "selectedAge": age_column,
            "weight": WEIGHT_COLUMN,
        },
        "diagnostics": {
            **diagnostics,
            "totalValidWeight": total_weight,
            "densityIntegral": integral,
            "ageBands": [asdict(row) for row in rows],
        },
    }

    if evidence_dir is not None:
        evidence_root = ensure_output_dir(evidence_dir)
        _write_source_values_csv(evidence_root / SOURCE_VALUES_FILE_NAME, rows)
        (evidence_root / SUMMARY_FILE_NAME).write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )

    return {
        "output_file": str(output_path),
        "summary": summary,
        "rows": rows,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    result = run_age_distribution(
        household_csv=args.household_csv,
        output_dir=args.output_dir,
        evidence_dir=args.evidence_dir,
    )
    summary = result["summary"]
    print(f"{DATA_AGE_DISTRIBUTION_KEY} = {summary['selectedConfigValues'][DATA_AGE_DISTRIBUTION_KEY]}")
    print(f"Output: {summary['outputPath']}")
    print(f"Valid rows: {summary['diagnostics']['validRows']}")
    print(f"Density integral: {summary['diagnostics']['densityIntegral']:.12f}")


if __name__ == "__main__":
    main()
