#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calibrate rental tenancy-length bounds from the EHS 2023-24 rented-sectors annex table.

Default extraction target:
  - table: AT2_10
  - population: private renters with assured shorthold tenancies resident less than 3 years
  - percentage rows: 6 months, 12 months, 18 months, other

The Java model currently represents tenancy length as a discrete uniform draw between
TENANCY_LENGTH_MIN and TENANCY_LENGTH_MAX. This helper therefore promotes the empirical
support bounds from the explicit month categories, while retaining the full source
distribution for audit.

@author: Max Stoddard
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from odf.opendocument import load as load_ods
from odf.table import Table, TableCell, TableRow
from odf.text import P

from scripts.python.helpers.common.paths import ensure_output_dir, repo_root


TENANCY_LENGTH_MIN_KEY = "TENANCY_LENGTH_MIN"
TENANCY_LENGTH_MAX_KEY = "TENANCY_LENGTH_MAX"
DEFAULT_TABLE_NAME = "AT2_10"
DEFAULT_TABLE_TITLE = (
    "Annex Table 2.10: Length of initial tenancy agreement, by tenancy type, "
    "two-years analysis, 2022-24"
)
DEFAULT_SOURCE_URL = (
    "https://assets.publishing.service.gov.uk/media/6874f2a3730a1bf28e2f9321/"
    "EHS_23-24_Rented_Sectors_Chapter_2_Annex_Tables.ods"
)
DEFAULT_SOURCE_PAGE_URL = (
    "https://www.gov.uk/government/statistics/"
    "english-housing-survey-2023-to-2024-rented-sectors"
)
DEFAULT_POPULATION = (
    "all private renters who have lived at the current address for less than 3 years; "
    "assured shorthold column"
)
DEFAULT_ODS_CANDIDATES = (
    Path(
        "input-data-versions/calibration-evidence/ehs-tenancy-length-v4.15/"
        "EHS_23-24_Rented_Sectors_Chapter_2_Annex_Tables.ods"
    ),
    Path("/tmp/EHS_23-24_Rented_Sectors_Chapter_2_Annex_Tables.ods"),
)
SOURCE_VALUES_FILE_NAME = "EhsTenancyLengthSourceValues.csv"
SUMMARY_FILE_NAME = "EhsTenancyLengthSummary.json"
EXPECTED_PERCENTAGES = {
    "6 months": 23.6,
    "12 months": 61.3,
    "18 months": 3.8,
    "other": 11.3,
}


@dataclass(frozen=True)
class TenancyLengthObservation:
    agreement_length: str
    assured_shorthold_households_thousands: float
    percentage: float
    rounded_percentage: int
    explicit_month_length: int | None
    selected_support_bound: bool


@dataclass(frozen=True)
class TenancyLengthCalibration:
    parameter_key_min: str
    parameter_key_max: str
    tenancy_length_min: int
    tenancy_length_max: int
    source_path: str
    source_url: str
    source_page_url: str
    source_sha256: str
    table_name: str
    table_title: str
    population: str
    observations: tuple[TenancyLengthObservation, ...]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract TENANCY_LENGTH_MIN/MAX from the EHS rented-sectors Annex Table 2.10 ODS."
    )
    parser.add_argument(
        "--ods-path",
        default=None,
        help="Optional explicit path to the EHS annex ODS. Defaults to the retained v4.15 evidence artifact.",
    )
    parser.add_argument(
        "--table",
        default=DEFAULT_TABLE_NAME,
        help=f"ODS table name to read (default: {DEFAULT_TABLE_NAME}).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"Optional output directory for {SOURCE_VALUES_FILE_NAME} and {SUMMARY_FILE_NAME}.",
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
        "Could not locate the default EHS tenancy-length ODS. Checked:\n"
        f"  - {checked_display}"
    )


def _normalize(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split()).strip().lower()


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


def _cell_repeat_count(cell: TableCell) -> int:
    repeated = cell.getAttribute("numbercolumnsrepeated")
    if not repeated:
        return 1
    try:
        return max(1, int(repeated))
    except ValueError:
        return 1


def _ods_rows(table: Table) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.getElementsByType(TableRow):
        values: list[str] = []
        for cell in row.getElementsByType(TableCell):
            values.extend([_ods_cell_text(cell)] * _cell_repeat_count(cell))
        if any(value for value in values):
            rows.append(values)
    return rows


def read_table_rows(ods_path: Path, table_name: str) -> list[list[str]]:
    document = load_ods(str(ods_path))
    for table in document.spreadsheet.getElementsByType(Table):
        if table.getAttribute("name") == table_name:
            return _ods_rows(table)
    raise ValueError(f"Could not find table {table_name!r} in {ods_path}.")


def _find_section_start(rows: list[list[str]], marker: str) -> int:
    normalized_marker = _normalize(marker)
    for index, row in enumerate(rows):
        if any(_normalize(cell) == normalized_marker for cell in row if cell):
            return index
    raise ValueError(f"Could not find section marker {marker!r}.")


def _find_column_index(rows: list[list[str]], header_label: str) -> int:
    normalized_header = _normalize(header_label)
    for row in rows:
        for index, cell in enumerate(row):
            if _normalize(cell) == normalized_header:
                return index
    raise ValueError(f"Could not find column {header_label!r}.")


def _find_value_after_index(
    rows: list[list[str]],
    *,
    start_index: int,
    row_label: str,
    value_index: int,
) -> float:
    normalized_label = _normalize(row_label)
    for row in rows[start_index:]:
        if row and _normalize(row[0]) == "total":
            raise ValueError(f"Reached total row before finding {row_label!r}.")
        if any(_normalize(cell) == normalized_label for cell in row if cell):
            if value_index >= len(row):
                raise ValueError(f"Row {row_label!r} has no value at column {value_index}.")
            return _parse_float(row[value_index])
    raise ValueError(f"Could not find row label {row_label!r}.")


def extract_observations_from_rows(rows: list[list[str]]) -> tuple[TenancyLengthObservation, ...]:
    assured_shorthold_index = _find_column_index(rows, "assured shorthold")
    households_start = _find_section_start(rows, "thousands of households")
    percentages_start = _find_section_start(rows, "percentages")

    observations: list[TenancyLengthObservation] = []
    for label, expected_percentage in EXPECTED_PERCENTAGES.items():
        households = _find_value_after_index(
            rows,
            start_index=households_start,
            row_label=label,
            value_index=assured_shorthold_index,
        )
        percentage = _find_value_after_index(
            rows,
            start_index=percentages_start,
            row_label=label,
            value_index=assured_shorthold_index,
        )
        if abs(percentage - expected_percentage) > 0.05:
            raise ValueError(
                f"Unexpected percentage for {label!r}: {percentage}; "
                f"expected approximately {expected_percentage}."
            )
        explicit_month_length = int(label.split()[0]) if label.endswith("months") else None
        observations.append(
            TenancyLengthObservation(
                agreement_length=label,
                assured_shorthold_households_thousands=households,
                percentage=percentage,
                rounded_percentage=round(percentage),
                explicit_month_length=explicit_month_length,
                selected_support_bound=explicit_month_length in (6, 18),
            )
        )
    return tuple(observations)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_tenancy_length_calibration(
    ods_path: Path,
    *,
    table_name: str = DEFAULT_TABLE_NAME,
) -> TenancyLengthCalibration:
    rows = read_table_rows(ods_path, table_name)
    observations = extract_observations_from_rows(rows)
    month_lengths = sorted(
        observation.explicit_month_length
        for observation in observations
        if observation.explicit_month_length is not None
    )
    return TenancyLengthCalibration(
        parameter_key_min=TENANCY_LENGTH_MIN_KEY,
        parameter_key_max=TENANCY_LENGTH_MAX_KEY,
        tenancy_length_min=month_lengths[0],
        tenancy_length_max=month_lengths[-1],
        source_path=str(ods_path),
        source_url=DEFAULT_SOURCE_URL,
        source_page_url=DEFAULT_SOURCE_PAGE_URL,
        source_sha256=_sha256(ods_path),
        table_name=table_name,
        table_title=DEFAULT_TABLE_TITLE,
        population=DEFAULT_POPULATION,
        observations=observations,
    )


def build_calibration_summary(calibration: TenancyLengthCalibration) -> dict[str, object]:
    return {
        "parameterKeys": [
            calibration.parameter_key_min,
            calibration.parameter_key_max,
        ],
        "selectedConfigValues": {
            calibration.parameter_key_min: calibration.tenancy_length_min,
            calibration.parameter_key_max: calibration.tenancy_length_max,
        },
        "source": {
            "source_path": calibration.source_path,
            "source_url": calibration.source_url,
            "source_page_url": calibration.source_page_url,
            "source_sha256": calibration.source_sha256,
            "table_name": calibration.table_name,
            "table_title": calibration.table_title,
            "population": calibration.population,
            "observations": [asdict(observation) for observation in calibration.observations],
        },
        "method": "published_ehs_annex_table_support_bounds",
        "modelingCaveat": (
            "The model draws tenancy length uniformly between TENANCY_LENGTH_MIN and "
            "TENANCY_LENGTH_MAX, so the empirical EHS distribution is retained for audit "
            "while only the explicit month-category support bounds are promoted."
        ),
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
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    calibration = extract_tenancy_length_calibration(ods_path, table_name=table_name)
    summary = build_calibration_summary(calibration)
    if output_dir is not None:
        output_root = ensure_output_dir(output_dir)
        source_values_path = output_root / SOURCE_VALUES_FILE_NAME
        with source_values_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "agreement_length",
                    "assured_shorthold_households_thousands",
                    "percentage",
                    "rounded_percentage",
                    "explicit_month_length",
                    "selected_support_bound",
                    "source_path",
                    "source_url",
                    "source_page_url",
                    "source_sha256",
                    "table_name",
                    "population",
                ],
            )
            writer.writeheader()
            for observation in calibration.observations:
                row = asdict(observation)
                row.update(
                    {
                        "source_path": calibration.source_path,
                        "source_url": calibration.source_url,
                        "source_page_url": calibration.source_page_url,
                        "source_sha256": calibration.source_sha256,
                        "table_name": calibration.table_name,
                        "population": calibration.population,
                    }
                )
                writer.writerow(row)
        summary_path = output_root / SUMMARY_FILE_NAME
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        ods_path = resolve_ods_path(args.ods_path)
        summary = run_calibration(
            ods_path=ods_path,
            table_name=args.table,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc))

    source = summary["source"]
    selected = summary["selectedConfigValues"]
    print("Extracted TENANCY_LENGTH_MIN/MAX from EHS annex table")
    print(f"Source path: {_display_path(Path(source['source_path']))}")
    print(f"Source URL: {source['source_url']}")
    print(f"Source SHA256: {source['source_sha256']}")
    print(f"Table: {source['table_name']}")
    print(f"Population: {source['population']}")
    print("")
    for observation in source["observations"]:
        print(
            f"{observation['agreement_length']}: {observation['percentage']:.1f}% "
            f"(rounded {observation['rounded_percentage']}%)"
        )
    print("")
    print(f"{TENANCY_LENGTH_MIN_KEY} = {selected[TENANCY_LENGTH_MIN_KEY]}")
    print(f"{TENANCY_LENGTH_MAX_KEY} = {selected[TENANCY_LENGTH_MAX_KEY]}")

    if args.output_dir:
        output_root = ensure_output_dir(args.output_dir)
        print("")
        print(f"Wrote: {_display_path(output_root / SOURCE_VALUES_FILE_NAME)}")
        print(f"Wrote: {_display_path(output_root / SUMMARY_FILE_NAME)}")


if __name__ == "__main__":
    main()
