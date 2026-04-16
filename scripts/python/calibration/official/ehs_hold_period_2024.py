#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibrate HOLD_PERIOD from the EHS 2023-24 housing-history annex table.

Default extraction target:
  - table: AT3_6
  - row: all owner occupiers
  - year: 2023-24

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from odf.opendocument import load as load_ods
from odf.table import Table, TableCell, TableRow
from odf.text import P

from scripts.python.helpers.common.cli import format_float
from scripts.python.helpers.common.paths import ensure_output_dir, repo_root


HOLD_PERIOD_KEY = "HOLD_PERIOD"
DEFAULT_TABLE_NAME = "AT3_6"
DEFAULT_ROW_LABEL = "all owner occupiers"
DEFAULT_YEAR = "2023-24"
DEFAULT_ODS_CANDIDATES = (
    Path(
        "private-datasets/ehs/"
        "2023-24_EHS_Headline_Report_Chapter_3_Housing_History_and_future_housing_Annex_Tables.ods"
    ),
    Path(
        "private-datasets/ehs/EHS-2023-24/mrdoc/excel/"
        "9442_2023-24_ehs_headline_report_on_demographics_and_household_resilience_"
        "chapter_3_housing_history_and_future_housing_annex_tables.ods"
    ),
)
SOURCE_VALUES_FILE_NAME = "ehs_hold_period_source_values.csv"
SUMMARY_FILE_NAME = "ehs_hold_period_summary.json"


@dataclass(frozen=True)
class HoldPeriodObservation:
    parameter_key: str
    config_value: float
    extracted_value: float
    source_path: str
    table_name: str
    row_label: str
    year: str


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract HOLD_PERIOD from the EHS headline-report housing-history "
            "annex ODS table."
        )
    )
    parser.add_argument(
        "--ods-path",
        default=None,
        help="Optional explicit path to the EHS annex ODS. Defaults to the repo-local 2023-24 artifact.",
    )
    parser.add_argument(
        "--table",
        default=DEFAULT_TABLE_NAME,
        help=f"ODS table name to read (default: {DEFAULT_TABLE_NAME}).",
    )
    parser.add_argument(
        "--row-label",
        default=DEFAULT_ROW_LABEL,
        help=f"Row label to read (default: {DEFAULT_ROW_LABEL!r}).",
    )
    parser.add_argument(
        "--year",
        default=DEFAULT_YEAR,
        help=f"Year column to read (default: {DEFAULT_YEAR}).",
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


def resolve_ods_path(
    ods_path: str | None,
    *,
    candidate_paths: Sequence[Path] | None = None,
    root: Path | None = None,
) -> Path:
    if ods_path:
        resolved = Path(ods_path).expanduser()
        if not resolved.exists():
            raise FileNotFoundError(f"Missing EHS ODS: {resolved}")
        return resolved.resolve()

    base_root = root if root is not None else repo_root()
    candidates = candidate_paths if candidate_paths is not None else DEFAULT_ODS_CANDIDATES
    checked: list[str] = []
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else base_root / candidate
        checked.append(str(resolved))
        if resolved.exists():
            return resolved.resolve()
    checked_display = "\n  - ".join(checked)
    raise FileNotFoundError(
        "Could not locate the default EHS hold-period ODS. Checked:\n"
        f"  - {checked_display}"
    )


def _normalize(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip().lower()


def _clean_string(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").split())


def _parse_float(value: str) -> float:
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        raise ValueError("Expected a numeric value, found blank text.")
    return float(cleaned)


def _ods_cell_text(cell: TableCell) -> str:
    parts: list[str] = []
    for paragraph in cell.getElementsByType(P):
        for child in paragraph.childNodes:
            data = getattr(child, "data", None)
            if data:
                parts.append(data)
    return " ".join(" ".join(parts).split())


def _ods_rows(table: Table) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.getElementsByType(TableRow):
        values = [_ods_cell_text(cell) for cell in row.getElementsByType(TableCell)]
        if any(value for value in values):
            rows.append(values)
    return rows


def read_table_rows(ods_path: Path, table_name: str) -> list[list[str]]:
    document = load_ods(str(ods_path))
    for table in document.spreadsheet.getElementsByType(Table):
        if table.getAttribute("name") == table_name:
            return _ods_rows(table)
    raise ValueError(f"Could not find table {table_name!r} in {ods_path}.")


def extract_value_from_rows(
    rows: list[list[str]],
    *,
    row_label: str,
    year: str,
) -> float:
    normalized_year = _normalize(year)
    header_row = next(
        (
            row
            for row in rows
            if any(_normalize(cell) == normalized_year for cell in row if cell)
        ),
        None,
    )
    if header_row is None:
        raise ValueError(f"Could not find column {year!r}.")

    year_index = next(
        (
            index
            for index, cell in enumerate(header_row)
            if _normalize(cell) == normalized_year
        ),
        None,
    )
    if year_index is None:
        raise ValueError(f"Could not find column {year!r}.")

    normalized_row_label = _normalize(row_label)
    value_row = next(
        (
            row
            for row in rows
            if any(_normalize(cell) == normalized_row_label for cell in row if cell)
        ),
        None,
    )
    if value_row is None:
        raise ValueError(f"Could not find row label {row_label!r}.")

    if year_index >= len(value_row):
        raise ValueError(f"Row {row_label!r} has no value for {year!r}.")
    raw_value = _clean_string(value_row[year_index])
    if not raw_value:
        raise ValueError(f"Row {row_label!r} has no value for {year!r}.")
    return _parse_float(raw_value)


def extract_hold_period(
    ods_path: Path,
    *,
    table_name: str = DEFAULT_TABLE_NAME,
    row_label: str = DEFAULT_ROW_LABEL,
    year: str = DEFAULT_YEAR,
) -> HoldPeriodObservation:
    rows = read_table_rows(ods_path, table_name)
    extracted_value = extract_value_from_rows(rows, row_label=row_label, year=year)
    return HoldPeriodObservation(
        parameter_key=HOLD_PERIOD_KEY,
        config_value=extracted_value,
        extracted_value=extracted_value,
        source_path=str(ods_path),
        table_name=table_name,
        row_label=row_label,
        year=year,
    )


def build_calibration_summary(observation: HoldPeriodObservation) -> dict[str, object]:
    return {
        "parameterKey": observation.parameter_key,
        "selectedConfigValues": {
            observation.parameter_key: observation.config_value,
        },
        "source": asdict(observation),
        "method": "published_ehs_annex_table_extraction",
    }


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(repo_root()))
    except ValueError:
        return str(path)


def run_calibration(
    *,
    ods_path: Path,
    table_name: str = DEFAULT_TABLE_NAME,
    row_label: str = DEFAULT_ROW_LABEL,
    year: str = DEFAULT_YEAR,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    observation = extract_hold_period(
        ods_path,
        table_name=table_name,
        row_label=row_label,
        year=year,
    )
    summary = build_calibration_summary(observation)
    if output_dir is not None:
        output_root = ensure_output_dir(output_dir)
        source_values_path = output_root / SOURCE_VALUES_FILE_NAME
        with source_values_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "parameter_key",
                    "config_value",
                    "extracted_value",
                    "source_path",
                    "table_name",
                    "row_label",
                    "year",
                ],
            )
            writer.writeheader()
            writer.writerow(asdict(observation))
        summary_path = output_root / SUMMARY_FILE_NAME
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _format_config_value(value: float) -> str:
    return f"{value:.1f}"


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        ods_path = resolve_ods_path(args.ods_path)
        summary = run_calibration(
            ods_path=ods_path,
            table_name=args.table,
            row_label=args.row_label,
            year=args.year,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))

    observation = summary["source"]
    config_value = float(summary["selectedConfigValues"][HOLD_PERIOD_KEY])
    print("Extracted HOLD_PERIOD from EHS annex table")
    print(f"Source path: {_display_path(Path(observation['source_path']))}")
    print(f"Table: {observation['table_name']}")
    print(f"Row label: {observation['row_label']}")
    print(f"Year: {observation['year']}")
    print(f"Extracted value: {format_float(float(observation['extracted_value']), decimals=1)}")
    print("")
    print(f"{HOLD_PERIOD_KEY} = {_format_config_value(config_value)}")

    if args.output_dir:
        output_root = ensure_output_dir(args.output_dir)
        print("")
        print(f"Wrote: {_display_path(output_root / SOURCE_VALUES_FILE_NAME)}")
        print(f"Wrote: {_display_path(output_root / SUMMARY_FILE_NAME)}")


if __name__ == "__main__":
    main()
